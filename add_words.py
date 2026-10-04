#!/usr/bin/env python3
"""Add Japanese word readings from a CSV into kana.js.

The file has two dictionaries, and the script routes entries automatically:

  SINGLE : a single kanji          (1 character)
  WORDS  : a multi-kanji word      (2+ characters)

WORDS entries are matched longest-first and always beat per-kanji readings, so
irregular compounds (今日 -> きょう) belong there. A 1-character entry in WORDS
would be silently ignored by the matcher, so the script refuses to write one.

CSV format — two columns, header optional:

    word,reading
    鮭,さけ
    眼鏡,めがね
    行く,いく

Usage:
    python add_words.py words.csv           # preview only (safe default)
    python add_words.py words.csv --apply   # write a backup + update kana.js
"""

import argparse
import csv
import re
import shutil
import sys
from pathlib import Path

# The Windows console defaults to cp1252 and cannot print Japanese.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

KANA_FILE = Path(__file__).with_name("kana.js")

# Explicit code points throughout — ranges written with literal glyphs are easy
# to get wrong. ぀ is U+3040, so a naive "katakana" range of ぀-ヿ would also
# swallow the whole hiragana block (U+3041-U+3096).
#   hiragana  U+3041-U+3096   katakana  U+30A1-U+30FF
# U+30FC (ー, chōonpu) is excluded from the katakana class on purpose: it is a
# length mark valid inside hiragana readings, e.g. コーヒー -> こーひー.
def _rng(a, b):
    """Build a regex range from code points, so nothing here can be mistyped."""
    return chr(a) + "-" + chr(b)


_KANJI_CHARS = _rng(0x4E00, 0x9FFF) + chr(0x3005) + chr(0x3006)   # 一-鿿 々 〆
# U+30FC (ー) is excluded: it is a length mark, valid inside hiragana readings
_KATAKANA_CHARS = _rng(0x30A1, 0x30FB) + _rng(0x30FD, 0x30FF)

KANJI_RE = re.compile("[" + _KANJI_CHARS + "]")
KATAKANA_RE = re.compile("[" + _KATAKANA_CHARS + "]")
NOT_KANA_RE = re.compile("[" + _KANJI_CHARS + _KATAKANA_CHARS + "A-Za-z]")


def find_block(lines, name):
    """Return (opening_index, closing_index) for `var NAME = {` ... `};`."""
    opener = re.compile(r"^\s*var\s+%s\s*=\s*\{\s*$" % name)
    for i, line in enumerate(lines):
        if opener.match(line):
            for j in range(i + 1, len(lines)):
                if lines[j].rstrip() == "  };":
                    return i, j
            raise SystemExit("could not find the end of the %s block" % name)
    raise SystemExit("could not find 'var %s = {' in %s" % (name, KANA_FILE))


def existing_keys(lines, start, end):
    """Keys already defined inside a block."""
    entry = re.compile(r"""^\s*(['"])(.+?)\1\s*:""")
    keys = {}
    for line in lines[start:end]:
        m = entry.match(line)
        if m:
            keys[m.group(2)] = line.strip()
    return keys


def read_rows(path):
    """Yield (word, reading, row_number), skipping blanks."""
    with open(path, newline="", encoding="utf-8-sig") as fh:
        reader = csv.reader(fh)
        for n, row in enumerate(reader, start=1):
            if not row or not any(c.strip() for c in row):
                continue
            if len(row) < 2:
                print("  line %d: skipped, needs 2 columns (found %d)" % (n, len(row)))
                continue
            word = row[0].strip()
            reading = row[1].strip()
            # tolerate a header row named word/reading/kanji/hiragana
            if n == 1 and word.lower() in ("word", "kanji", "japanese", "text"):
                continue
            yield word, reading, n


def main():
    ap = argparse.ArgumentParser(description="Add readings from a CSV into kana.js")
    ap.add_argument("csv", type=Path, help="CSV file with word,reading columns")
    ap.add_argument("--apply", action="store_true",
                    help="actually write the changes (default is preview only)")
    args = ap.parse_args()

    if not args.csv.exists():
        sys.exit("no such CSV file: %s" % args.csv)

    lines = KANA_FILE.read_text(encoding="utf-8").splitlines(keepends=True)

    s_open, s_close = find_block(lines, "SINGLE")
    w_open, w_close = find_block(lines, "WORDS")
    have_single = existing_keys(lines, s_open, s_close)
    have_words = existing_keys(lines, w_open, w_close)

    add_single, add_words = {}, {}
    skipped, conflicts, bad = [], [], []

    for word, reading, line_no in read_rows(args.csv):
        if not word or not reading:
            bad.append((word or "(blank)", "empty word or reading"))
            continue
        if "'" in word or "\\" in word:
            bad.append((word, "contains a quote or backslash"))
            continue
        if NOT_KANA_RE.search(reading):
            bad.append((word, "reading %r is not hiragana" % reading))
            continue

        target = add_single if len(word) == 1 else add_words
        existing = have_single if len(word) == 1 else have_words

        if word in target:
            if target[word] == reading:
                skipped.append(word)
            else:
                conflicts.append((word, target[word], reading))
            continue
        if word in existing:
            # already defined — same reading is a no-op, different is a conflict
            found = re.search(r":\s*'([^']*)'", existing[word])
            found_reading = found.group(1) if found else "?"
            if found_reading == reading:
                skipped.append(word)
            else:
                conflicts.append((word, found_reading, reading))
            continue

        # Checked last, so a kana word already in the file counts as correct.
        if not KANJI_RE.search(word):
            bad.append((word, "kana only — nothing to add"))
            continue
        target[word] = reading

    print("kanji.js: %s" % KANA_FILE)
    print("  SINGLE (single kanji) : %d new" % len(add_single))
    print("  WORDS  (multi-kanji)  : %d new" % len(add_words))
    print("  already correct       : %d" % len(skipped))
    print("  conflicts             : %d" % len(conflicts))
    print("  rejected              : %d" % len(bad))

    for word, was, now in conflicts:
        print("  ! conflict %s: file has %s, CSV says %s (left alone)" % (word, was, now))
    for word, why in bad:
        print("  ! rejected %s: %s" % (word, why))

    if not add_single and not add_words:
        print("\nNothing to add.")
        return

    for table, entries in (("SINGLE", add_single), ("WORDS", add_words)):
        if not entries:
            continue
        print("\n  -> %s" % table)
        for w, r in sorted(entries.items()):
            print("     '%s': '%s'," % (w, r))

    if not args.apply:
        print("\nPreview only. Re-run with --apply to write these changes.")
        return

    # insert just before each block's closing brace
    for name, additions in (("SINGLE", add_single), ("WORDS", add_words)):
        if not additions:
            continue
        _, close = find_block(lines, name)
        # make sure the previous entry ends with a comma
        prev = close - 1
        while prev >= 0 and not lines[prev].strip():
            prev -= 1
        if lines[prev].rstrip().endswith(","):
            pass
        else:
            lines[prev] = lines[prev].rstrip("\n") + ",\n"

        block = "".join("    '%s': '%s',\n" % (w, r) for w, r in sorted(additions.items()))
        lines.insert(close, block)

    backup = KANA_FILE.with_suffix(".js.bak")
    shutil.copy2(KANA_FILE, backup)
    KANA_FILE.write_text("".join(lines), encoding="utf-8")

    total = len(add_single) + len(add_words)
    print("\nAdded %d entries to kana.js. Backup: %s" % (total, backup.name))


if __name__ == "__main__":
    main()