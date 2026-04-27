# ContabilaAi

ContabilaAi is a local-first finance copilot for importing bank statements and invoices, storing full transaction data per company workspace, answering natural-language questions, and learning from user corrections.

## Current status

This repository already ships the current workspace architecture:
- named company workspaces
- review severity and query gate
- business memory instructions
- workspace invoice hub
- phase 1 invoice matching
- change review workflow
- onboarding shell for `home -> onboarding -> ready`

## Run locally

Use the bundled launcher:

```cmd
run-contabila.cmd
```

The app now starts from a company workspace. Import files from the UI so each upload is attached to the selected firm and can later influence review, matching, and business memory.

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
3. Create or open a firm workspace
4. Import a bank statement into that firm
5. Add invoices and business instructions when you have them
6. Close `critical` and `high` review items
7. Ask questions such as `cat am avut creditare pe 2024`
8. Use `Reseteaza tot` when you want a completely clean start

## Import behavior

- each uploaded file creates its own saved import batch
- each import batch belongs to a selected company workspace
- later invoice imports can trigger matching and change review
- review and questions are scoped by workspace and selected import
- `Reseteaza tot` clears local saved imports, invoice hub data, matches, change review items, and review data from the local SQLite database

## What should work now

- create and reopen named firms
- import validated bank statements into the selected firm
- reject statement imports when declared totals and parsed totals do not match
- store business memory facts per firm
- import workspace-scoped invoices
- propose phase 1 matches between invoices and payments
- create change review items for proposed category changes
- block serious questions while `critical` or `high` review items remain
- route the UI between workspace home, onboarding, and ready workspace shells

## Bootstrap validation snapshot

Validated against the current Garanti PDF fixture:

- parsed transactions: `623`
- first transaction date: `2024-09-13`
- last transaction date: `2026-04-22`
- total income: `2225700.95`
- total expenses: `2161702.5`
- net cashflow: `63998.45`
