# ContabilaAi Architecture Blueprint

## Product Direction

ContabilaAi should be a local financial copilot built around a simple principle:

**The bank statement is the primary record of cash reality. Invoices and other documents enrich, explain, and validate that cash reality.**

The project should not be shaped as a chatbot over bank rows. It should be shaped as a financial understanding system with a natural language interface.

## Core Product Model

The product has three conceptual layers:

1. `Cash reality`

Bank statements show what actually moved in and out of the business bank account.

This layer is the strongest source for:
- cash inflows
- cash outflows
- net cashflow
- bank fees
- tax payments
- owner financing movements
- financing recovery movements
- actual payment dates

2. `Document enrichment`

Issued and received invoices explain what some cash movements represent.

This layer helps with:
- invoiced revenue
- documented supplier expenses
- unpaid or partially paid invoices
- client and supplier relationships
- matching invoice references to bank transactions
- separating operational business activity from financing or personal analysis categories

The user may only have part of the invoice set. The system must be useful even when invoices are incomplete.

3. `Answer confidence`

Every answer must be internally classified as:
- `exact`
- `estimated`
- `unsupported`

This is not just UI wording. It is part of the query engine contract.

## What Exact Means

An answer is `exact` when the available documents support a direct calculation.

Examples:
- total bank inflows for a period
- total bank outflows for a period
- cashflow net for a period
- total creditare in bank transactions
- total recuperare creditare in bank transactions
- total invoiced revenue when the relevant issued invoices are present
- payments to a known supplier from bank transactions

## What Estimated Means

An answer is `estimated` when the system can provide a useful approximation, but the dataset is incomplete or the concept is not fully represented by the available documents.

Examples:
- profit-like answers when only bank statements exist
- operational income inferred from bank inflows after excluding creditare/internal transfers
- operational expenses inferred from bank outflows after excluding recuperare creditare/internal transfers
- profit-style views when only part of received invoices exists

Estimated answers must say what source was used and what may be missing.

## What Unsupported Means

An answer is `unsupported` when the available documents cannot support a responsible answer.

Examples:
- exact VAT position without complete invoice and fiscal context
- official balance sheet
- official profit and loss statement from incomplete records
- exact accounting profit without enough received invoices, unpaid obligations, adjustments, depreciation, and tax context

Unsupported answers should explain what data would be needed.

## Source Priority

The source priority is not the same for every question.

For cash questions:
- prefer bank statements

For invoiced revenue:
- prefer issued invoices

For documented supplier expenses:
- prefer received invoices

For payment status:
- combine invoices and bank transactions

For profit-like questions:
- combine all available sources
- downgrade confidence when source coverage is incomplete

## Target Architecture

### `importing`

Responsible for turning raw files into normalized imported objects.

Subdomains:
- bank statement importers
- issued invoice importers
- received invoice importers

This layer should not decide final financial meaning beyond extracting source fields.

### `documents`

Responsible for normalized document models.

Core objects:
- `BankTransaction`
- `IssuedInvoice`
- `ReceivedInvoice`
- `ImportedDocument`
- `DocumentLine` where useful

This layer should preserve raw payloads and source metadata.

### `storage`

Responsible for SQLite schema, migrations, repositories, and data retrieval.

It should persist:
- bank transactions
- issued invoices
- received invoices
- import batches
- entities
- classifications
- analysis categories
- matching links
- user corrections

### `classification`

Responsible for economic interpretation of rows.

Examples:
- `creditare`
- `recuperare_creditare`
- `supplier_payment`
- `client_receipt`
- `tax_payment`
- `bank_fee`
- `internal_transfer`
- `other_inflow`
- `other_outflow`

This layer should remain deterministic and explainable where possible.

### `matching`

Responsible for linking documents to cash movements.

Examples:
- issued invoice matched to incoming bank transfer
- received invoice matched to outgoing supplier payment
- partial payment
- multiple payments for one invoice
- one payment covering multiple invoices

Matching should produce confidence and explanation, not silent certainty.

### `knowledge`

Responsible for user-taught memory.

Examples:
- entity type corrections
- supplier/client/partner/collaborator identity
- user-defined categories such as `casa` or `motorina`
- rules for similar transactions
- review decisions

This layer is where the system learns progressively.

### `planning`

Responsible for turning natural language into a structured financial question.

A plan should include:
- metric
- period
- grouping
- source preference
- entity filter
- entity type filter
- economic kind
- analysis category
- confidence requirement
- expected answer type: exact, estimated, unsupported

The planner should not directly generate prose answers.

### `answering`

Responsible for executing financial plans and producing answer objects.

An answer object should include:
- answer text
- confidence level
- source basis
- rows used
- documents used
- assumptions
- missing data notes

This should become separate from HTTP/server code.

### `review`

Responsible for surfacing uncertain or high-impact items.

Review candidates include:
- low confidence classifications
- unmatched invoices
- unmatched large bank transactions
- category suggestions
- ambiguous entity identity
- profit-impacting uncategorized rows

### `server`

Responsible only for local HTTP API transport.

It should not contain financial reasoning or answer logic.

### `web`

Responsible for the local UI.

The UI should remain practical:
- import documents
- select active data scope
- ask questions
- view evidence
- review and correct interpretations

## What To Keep From The Current Implementation

Keep:
- current clean repository structure
- bank statement parser
- CSV and JSON import foundations
- SQLite store as a starting point
- economic classification rules around creditare and recuperare creditare
- analysis categories
- review workflow foundation
- natural language planner tests and examples
- local HTTP server
- minimal UI direction
- test suite

## What Needs To Change

### 1. Introduce document-first models

The app needs explicit models for:
- bank transactions
- issued invoices
- received invoices

Currently the bank transaction model is the center. That remains important, but it should become one document type in a broader financial model.

### 2. Separate answering from server code

`render_answer` and plan execution should move out of HTTP code.

Target:
- `planning` builds plans
- `answering` executes plans and formats answer objects
- `server` serializes responses

### 3. Add source-aware answer confidence

The current planner already has some `support_level` behavior. This should become a first-class concept.

Target answer levels:
- `exact`
- `estimated`
- `unsupported`

### 4. Add received invoice import

Issued invoices already have early support. Received invoices should be added as a distinct source.

### 5. Add matching layer

Matching should link:
- issued invoices to incoming payments
- received invoices to outgoing payments

It should support unmatched and partially matched states.

### 6. Improve entity-aware questions

Natural language questions must support entity filters in both search and aggregate questions.

Examples:
- `da-mi toate incasarile de la Palade Elena Cristina`
- `cat am incasat de la clientul X`
- `cat am platit catre furnizorul Y`
- `profit pe 2024 pentru clientul X`

### 7. Reduce HTTP file size

HTTP code should be split into smaller handlers or service functions after answer logic is extracted.

## Proposed Migration Sequence

### Phase 1: Stabilize Current MVP

Goal:
Make current behavior reliable enough to continue building on it.

Tasks:
- fix entity filters in aggregate questions
- remove dead/legacy answer code
- ensure app starts cleanly through `python app.py`
- verify import and chat flow in browser

### Phase 2: Extract Answer Engine

Goal:
Move financial answer logic out of HTTP.

Create:
- `answering/models.py`
- `answering/engine.py`
- `answering/rendering.py`

The server should call the answer engine and return serialized answer objects.

### Phase 3: Formalize Source Confidence

Goal:
Make exact/estimated/unsupported a consistent contract.

Add:
- `AnswerConfidence`
- `SourceBasis`
- `MissingDataNote`
- tests for profit, cashflow, turnover, VAT, and entity filters

### Phase 4: Received Invoices

Goal:
Support imported supplier invoices as a first-class source.

Add:
- received invoice model
- CSV importer
- PDF importer if practical
- storage table
- summary queries

### Phase 5: Matching

Goal:
Link invoices and bank transactions.

Start simple:
- exact amount + entity + near date
- invoice number/reference text
- manual link override
- partial match support later

### Phase 6: Better Review

Goal:
Review the highest value uncertainty first.

Add review groups for:
- large unmatched bank payments
- invoices with no matching payment
- bank inflows with no matching invoice
- categories affecting profit/cashflow answers

### Phase 7: UI Refinement

Goal:
Keep the UI simple but more operational.

Suggested views:
- import
- ask
- evidence
- review
- data sources

Avoid turning it into a dashboard-heavy accounting product.

## Handling Profit Questions

`cat profit am pe 2024` should be handled as a financial intent, not as a hardcoded question.

The system should:
1. identify metric: profit-like result
2. inspect available sources
3. determine answer confidence
4. calculate the best supported answer
5. explain what is included and missing

Possible outcomes:

### Only bank statements available

Answer:
- estimated cashflow net
- not exact accounting profit

### Bank statements + issued invoices available

Answer:
- cashflow net
- invoiced revenue if relevant
- still incomplete for profit if received invoices are missing

### Bank statements + issued invoices + received invoices available

Answer:
- stronger profit-style estimate
- still not official accounting profit unless all needed adjustments exist

### Missing core documents

Answer:
- unsupported or limited estimate
- explain required missing data

## Handling Turnover / Cifra De Afaceri

Preferred source:
- issued invoices

If issued invoices are complete for the period:
- answer can be exact from invoices

If only bank statements are present:
- answer should be estimated operational inflow
- exclude creditare and internal transfers
- label clearly as estimate

## Handling VAT

VAT should generally be unsupported unless invoice data and tax rules are sufficient.

The system can eventually estimate VAT from invoices, but should not present it as official without correct fiscal treatment.

## Handling Cashflow

Cashflow is the strongest bank-led metric.

It can be exact from bank statements:
- inflows
- outflows
- net cashflow
- grouped by month/year/semester
- filtered by entity/category/economic kind

## Handling Entity Questions

Entity questions should work across:
- bank transactions
- issued invoices
- received invoices
- matched records

Examples:
- `cat am incasat de la Palade Elena Cristina`
- `ce facturi am emis catre clientul X`
- `cat am platit catre furnizorul Y`
- `ce sold am de incasat de la clientul X`

The planner must capture entity filters even for aggregate questions.

## Implementation Rules For Future Tools

Any parallel tool or agent should follow these rules:

- Do not treat the project as a generic chatbot.
- Keep the bank statement as primary cash reality.
- Treat invoices as enrichment and validation.
- Keep exact/estimated/unsupported explicit.
- Do not hardcode user-specific categories.
- Do not claim exact accounting profit from incomplete evidence.
- Prefer small modules with tests.
- Keep financial reasoning outside HTTP handlers.
- Preserve raw document data and source metadata.
- Make corrections reusable and explainable.

## Immediate Next Step

The next engineering step should be:

**Extract a dedicated answer engine and fix entity-aware aggregate questions.**

Why:
- it aligns current code with the target architecture
- it fixes the observed UI problem
- it starts moving reasoning out of the HTTP layer
- it creates the right place for exact/estimated/unsupported answer contracts

Suggested first slice:
- create `src/contabila_ai/answering/`
- move `render_answer` there
- add answer model with confidence/source basis
- update server to call answer engine
- add tests for `incasari de la Palade Elena Cristina`
- add tests for `profit pe 2024` with only bank data
