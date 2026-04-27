# ContabilaAi

ContabilaAi is a local-first finance copilot for importing bank statements, storing full transaction data, answering natural-language questions, and learning from user corrections.

## Current status

This repository is in active bootstrap. The long-term goal is to support:
- PDF, CSV, and JSON imports
- SQLite-backed transaction storage
- economic classification
- natural-language planning over real data
- compact review and correction workflows

## Run locally

Use the bundled launcher:

```cmd
run-contabila.cmd
```

The app now starts with no active import selected. Import files from the UI so each upload becomes a saved discussion session (import batch).

The current canonical PDF fixture used during bootstrap validation is:

```text
C:\Users\stefan\Downloads\Date\ExtrasDeCont.pdf
```

The local app runs at:

```text
http://127.0.0.1:8010
```

## Recommended startup flow

1. Run `run-contabila.cmd`
2. Open `http://127.0.0.1:8010`
3. Paste a PDF, CSV, or JSON path into the import field
4. Import the file and let the app save it as a separate import batch
5. The imported file becomes the active session automatically
6. Ask questions such as `cat am avut creditare pe 2024`
7. Use `Adauga categoria` or `Marcheaza corect` in review when needed
8. Use `Reseteaza tot` when you want a completely clean start

## Import behavior

- each uploaded file creates its own saved import batch
- the app starts with no active import selected
- uploading a second file does not overwrite the first one
- review and questions work on the active selected import
- `Reseteaza tot` clears all saved imports and review data from the local SQLite database

## Bootstrap validation snapshot

Validated against the current Garanti PDF fixture:

- parsed transactions: `623`
- first transaction date: `2024-09-13`
- last transaction date: `2026-04-22`
- total income: `2225700.95`
- total expenses: `2161702.5`
- net cashflow: `63998.45`
