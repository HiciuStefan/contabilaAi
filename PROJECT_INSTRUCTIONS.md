# ContabilaAi Project Instructions

## Project Identity

**Project name:** `ContabilaAi`

**Short definition:**
ContabilaAi is a local financial copilot that ingests the company's financial documents, interprets them economically, and answers user questions as accurately as the available evidence allows.

**Core principle:**
The system must answer from data, not improvise. When a result is exact, say it is exact. When it is estimated, say it is estimated. When the available documents are not enough, say clearly why the answer cannot be exact.

## What The Project Is

ContabilaAi is:
- a local-first financial understanding system
- a document ingestion and interpretation engine
- a queryable financial memory for the business
- a reviewable and trainable system that improves from user corrections
- a practical copilot over real financial evidence

The core supported data sources are:
- bank statements
- issued invoices
- received invoices

The system should unify those sources into a shared financial model and let the user ask natural-language questions over that model.

## What The Project Is Not

ContabilaAi is not:
- only a chatbot over bank transactions
- only an import tool
- only a dashboard
- a fake accounting expert that pretends certainty without evidence
- a full ERP or full general-ledger accounting suite

It must not:
- invent certainty where the documents do not support it
- claim exact accounting profit from bank statements alone
- answer canned templates without grounding in the actual data
- hardcode user-specific categories in source code

## Product Goal

The goal is to help the user put all relevant financial documents into one local system so that the system can:
- understand the documents as well as possible
- correlate them where possible
- answer financial, accounting-adjacent, and operational questions
- explain the limits of the answer when the data is incomplete
- learn from user corrections and reuse them later

## Main User Workflow

1. The user imports one or more document sources:
- bank statements
- issued invoices
- received invoices

2. The system parses and stores the data in a normalized model.

3. The system interprets transactions and entities economically:
- client
- supplier
- collaborator
- partner
- creditare
- recuperare creditare
- tax payments
- bank fees
- transfers
- other business-relevant meanings

4. The user asks questions in natural language.

5. The system builds a structured query plan from the question.

6. The system answers based on the available evidence:
- exact when possible
- estimated when only an approximation is possible
- unsupported when the required data is missing

7. The user reviews uncertain or incorrectly interpreted rows.

8. The system stores the correction and applies it to future reasoning and similar transactions.

## Data Sources

### 1. Bank Statements

Used for:
- cash inflows
- cash outflows
- cashflow net
- transfers
- fees
- taxes
- financing movements
- repayment movements
- relationship to real transaction dates and cash movement

Bank statements alone are not enough for full accounting truth.

### 2. Issued Invoices

Used for:
- invoiced revenue
- turnover / cifra de afaceri
- client billing history
- comparison between invoiced and collected amounts
- identifying expected receivables

### 3. Received Invoices

Used for:
- documented expenses
- supplier obligations
- comparison between invoiced expenses and paid expenses
- improving expense and profitability understanding

## Output Philosophy

Every answer should implicitly or explicitly fall into one of these categories:

### Exact

Use when the available documents support a direct answer.

Examples:
- total bank inflows in 2025
- total payments to supplier X
- number of creditare transactions in 2025
- amount invoiced to client Y when issued invoices exist

### Estimated

Use when the system can derive a meaningful approximation but not accounting certainty.

Examples:
- profit-like answers from bank cashflow only
- operational income estimates from available evidence
- approximations where some but not all documents exist

### Unsupported

Use when the data required for correctness is missing.

Examples:
- exact VAT liability without full invoice and fiscal context
- exact accounting profit without enough cost and accounting evidence
- official financial statements from incomplete document sets

## Example Question Handling

### Questions that should be answerable exactly when data exists

- `cat am incasat in 2025`
- `cat am platit catre furnizori in 2024`
- `cate recuperari creditare au fost in 2025`
- `cat am facturat catre clientul X`
- `ce tranzactii am cu Dedeman`
- `cat am avut cheltuieli cu casa`

### Questions that may be estimated depending on available data

- `cat profit am pe 2024`
- `care e cifra de afaceri daca nu am toate facturile importate`
- `cat m-a costat operational firma in 2025`

### Questions that should be marked unsupported when evidence is insufficient

- `cat TVA am de plata exact`
- `fa-mi bilantul`
- `fa-mi contul oficial de profit si pierdere` when required documents are missing

## Financial Interpretation Rules

The system must distinguish between:
- cash movement
- invoiced revenue/expense
- financing movements
- repayments
- internal transfers
- operational transactions
- user-defined analysis categories

Important:
- `creditare` and `recuperare creditare` are not normal operating revenue
- they must not be mixed into turnover or ordinary business income
- negative recovery wording must not be misread as positive crediting
- generic bank wording containing `credit` must not automatically mean economic `creditare`

## Entity Model

The system should support entity types such as:
- `partner`
- `supplier`
- `client`
- `collaborator`

The user must be able to correct entity identity and entity type.

The system must remember such corrections and reuse them.

## Categories And Labels

The system should support two layers:

### Fixed economic meaning

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

### User-defined analysis categories

Examples:
- `casa`
- `motorina`
- `personal`
- `investitie`

Rules for user-defined categories:
- do not precreate them without user request
- create them only when the user explicitly asks
- allow them to be applied to current and similar transactions
- allow them to be queried later in natural language
- treat them as analysis overlays, not silent replacements of base economic meaning

## Review And Learning

The system must support review of uncertain transactions.

Review should focus on:
- amount
- date
- direction
- economic interpretation
- entity classification
- category assignment

The system should help the user:
- confirm an interpretation
- correct an interpretation
- assign a category
- apply corrections to similar transactions

Corrections should improve later results.

## Natural Language Query Requirements

The system should not rely on a few canned questions.

It should parse questions into structured intent such as:
- metric
- period
- grouping
- entity filter
- entity type filter
- economic kind
- analysis category
- direction
- exact vs estimated vs unsupported semantics

Examples of supported structure:
- `cat am avut creditare pe 2023/2024/2025`
- `pe jumatate de an, cat am avut cheltuielile cu casa`
- `da-mi toate incasarile de la Palade Elena Cristina`
- `cat am platit catre colaboratori in 2024`

The planner must support entity filters in aggregate questions, not just search questions.

## UI Principles

The UI should remain simple and practical.

Required UI qualities:
- minimal
- clear
- low clutter
- local
- fast to use

Main UI surfaces:
- import documents
- select active import/session
- ask a question
- read the answer
- inspect matching rows
- review uncertain transactions

Avoid:
- dashboard overload
- noisy charts by default
- too many screens

## Technical Direction

Preferred architecture:
- modular Python application
- local SQLite storage
- clear module boundaries
- testable domain logic
- minimal web frontend

Suggested module boundaries:
- `importing`
- `storage`
- `classification`
- `planning`
- `review`
- `server`
- `web`

## Coding Principles

The code should:
- stay modular
- separate parsing, storage, classification, planning, review, and transport concerns
- avoid accidental coupling
- prefer explicit structured models over ad-hoc dictionaries where practical
- be test-driven for behavior changes and bug fixes
- preserve explainability in financial reasoning

Do not:
- bury financial meaning inside UI code
- hardcode user business categories in source
- tie business logic to a single wording pattern when a structured plan is possible
- return financial certainty unsupported by data

## Required Behavior For Answers

Answers should be:
- concise
- grounded in the data
- transparent about limitations
- phrased naturally

When useful, answers should be accompanied by:
- matching transactions
- matching invoices
- grouped results
- explanation of what source was used

## Current Product Standard

When asked something like:
- `cat profit am pe 2024`

the system should not blindly answer with a fake accounting number.

Instead it should:
1. detect that `profit` is requested
2. inspect what sources are present
3. decide whether the answer is exact, estimated, or unsupported
4. answer accordingly

Example behaviors:
- with only bank statements: answer as cashflow net estimate, clearly labeled
- with bank statements + issued invoices + received invoices: provide a stronger estimate or partial profit-style view, still transparent if not fully accounting-complete
- with insufficient documents: explain why exact profit is not available

## High-Level Success Criteria

The project is successful when:
- the user can import all relevant financial documents
- the system stores and interprets them coherently
- the user can ask natural-language financial questions
- the answers are grounded, useful, and transparent
- the system learns from user corrections
- the UI remains simple
- the project behaves like a financial copilot, not a fragile bank-text chatbot
