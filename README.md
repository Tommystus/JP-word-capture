# Japanese words capture
Capture Japanese words, translate each and save to a table.
Try it [here](https://tommystus.github.io/jp-word-capture/)

## How it works

- **Speech** — the browser's `SpeechRecognition` API with `lang = ja-JP`. Chrome
  streams audio to Google; Edge uses Azure Speech, so Edge is more reliable if
  Google is blocked on your network.
- **Translation** — the English definition column comes from MyMemory
  (free, CORS-open). It is the only column that needs the network.
- **Kana and romaji** — computed locally from the dictionaries in `kana.js`. No
  API call, instant, works offline. This is deliberate: the free Japanese
  dictionary APIs (Jisho, Jotoba) send no `Access-Control-Allow-Origin` header,
  so a browser cannot call them.
- **AI fallback** — when `kana.js` cannot fully read a phrase, the row is marked
  with `✦`. Clicking it asks Puter AI for a better reading. The ✦ flag is the
  signal that a word is missing from `kana.js`.

## Adding words from a CSV

`add_words.py` merges readings from a CSV into `kana.js`. Edit the CSV, re-run,
reload the page.

```bash
python add_words.py words.csv          # preview only — writes nothing
python add_words.py words.csv --apply  # updates kana.js, keeping kana.js.bak
```

CSV format — two columns, header optional:

```csv
word,reading
鮭,さけ
眼鏡,めがね
行く,いく
```

**It picks the table for you.** Entries of 1 character go in `SINGLE`,
entries of 2 or more go in `WORDS`. You do not need to decide.

| Table | Holds | Why |
|---|---|---|
| `SINGLE` | a single kanji | default reading, used for compounds |
| `WORDS` | a multi-kanji word | matched longest-first, beats per-kanji |

`WORDS` is what makes irregulars come out right — 今日 → きょう rather than
こんにち read one character at a time. A one-character entry in `WORDS` would be
silently ignored by the matcher, so the script routes those to `SINGLE` instead.

**The script is deliberately cautious.** Preview is the default; `--apply` writes
a backup first; re-running is idempotent. It will refuse rather than guess:

- a **conflicting** reading is left alone and reported, never silently overwritten
- a reading containing kanji, katakana, or Latin is rejected with the reason
- a kana-only word is reported as needing no entry

### Editing kana.js by hand

If you add a key that already exists, **the later one silently wins** — nothing
warns you. Search the file first, and prefer adding to `WORDS` over redefining a
`SINGLE` reading, since that keeps the default reading intact for other words.
For a kanji with several readings, put the common one in `SINGLE` and the
exceptions in `WORDS` (行 is こう by default, but 行く is いく).

### Checking your work

No browser needed — replace `眼鏡` with the words you just added:

```bash
node -e "global.window={}; require('./kana.js'); const K=global.window.Kana;
['眼鏡'].forEach(t=>{var h=K.toHiragana(t); console.log(t,'->',h,'|',K.toRomaji(h));});"
```

Expected: `眼鏡 -> めがね | megane`. If a word still shows kanji in the output,
it isn't in the dictionaries yet — which is exactly when the ✦ flag appears.

