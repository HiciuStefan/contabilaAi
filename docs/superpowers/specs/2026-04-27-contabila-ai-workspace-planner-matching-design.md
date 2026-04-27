# ContabilaAi Workspace, Planner, Matching, and Business Memory Design

## Goal

Transform ContabilaAi from a single-import MVP into a persistent local finance copilot organized around named company workspaces. Each workspace should support repeated document imports over time, structured business memory derived from natural-language instructions, guided onboarding with review severity, invoice-to-transaction matching, and trustworthy natural-language queries once critical onboarding work is complete.

## Product Shape

The application should treat one company as one persistent workspace. A workspace contains:

- bank statements imported over time
- issued invoices
- received invoices
- business memory scoped to the current company
- projects as first-class entities
- review state and change-review decisions
- transaction classifications and category assignments

The user can start with a historical import, then keep adding new monthly statements and invoices. The system should preserve continuity rather than treating each import as a separate isolated session.

## Core Principles

1. Raw documents remain immutable. Interpretation changes, not source data.
2. Natural-language business instructions are allowed, but they must be converted into structured, editable business memory.
3. Business memory may override heuristic interpretation, but every override must remain audit-friendly.
4. Serious queries should only unlock once `critical` and `high` review items are resolved.
5. Factures added later may trigger reprocessing, but proposed changes should never silently rewrite accepted meaning.

## Domain Model

### Workspace

A workspace represents one company. It has:

- explicit display name
- created timestamp
- current readiness state
- one or more document imports over time
- one or more internal accounts

### Account

Accounts exist as internal first-class records even if they stay light in the UI. They help separate:

- `RON`
- `EUR`
- `USD`
- `credit`

The UI should not force the user to think deeply about accounts during the happy path, but the model should preserve them for matching, continuity, and future reporting.

### Entity

Entities include:

- partner
- collaborator
- associate
- general vendor
- bank
- state

Entity type is workspace-scoped and may be inferred from documents, rules, or business memory.

### Project

Projects are first-class entities, not just categories. They can be linked to:

- collaborators
- transactions
- invoices
- business-memory rules
- categories when relevant

### Analysis Category

Categories remain user-facing analytical buckets. Each category has:

- name
- description
- operational scope
  - `operational`
  - `non_operational`
  - `personal`
  - `unassigned`

Examples include `casa`, `software`, `motorina`, `marketing`, `echipamente`.

### Business Memory

Business memory is scoped to one workspace and comes from natural-language instructions such as:

- `Ai Excellence e partener`
- `X si Y lucreaza pe proiectul Z`
- `am facut o casa intre 2020-2024, si am facturi pentru asta`

The system stores:

- raw instruction text
- parsed structured facts
- confidence
- whether the fact is proposed, accepted, or rejected
- downstream effects on transactions, categories, projects, or matching

Business memory may act as a stronger source of interpretation than heuristics, but not as a rewrite of raw data.

## Workflow

### 1. Workspace Home

The home screen should list company workspaces with a lightweight status:

- `needs import`
- `needs review`
- `ready`

The user can:

- create a new company workspace
- reopen an existing one

### 2. Onboarding Wizard

Each workspace has a guided onboarding flow.

#### Step 1: Import Documents

The user can:

- add bank statement
- import issued invoices
- import received invoices

This step should support historical bootstrapping and future periodic imports.

#### Step 2: Business Instructions

The user gets a large natural-language input box where they can describe extra knowledge. The system parses it into structured workspace memory and shows the interpreted result in an editable memory view later.

#### Step 3: Prioritized Review

Transactions and proposed interpretations are prioritized by severity:

- `critical`
- `high`
- `medium`
- `low`

Only `critical` and `high` block serious query usage.

#### Step 4: Change Review

If later invoice imports or new business memory reinterpret accepted data, the system creates explicit proposed changes and asks the user to accept or reject them.

#### Step 5: Ready

When no `critical` or `high` items remain, the workspace becomes query-ready.

### 3. Firm Workspace

After onboarding, the user works in a normal workspace with dedicated areas:

- Questions
- Transactions
- Categories
- Invoices
- Business Memory
- Review

The Questions area stays intentionally minimal. Cleanup, audit, and corrections belong in their own tabs.

## Review Severity

Severity should be derived from business impact and uncertainty.

### Critical

- large uncategorized transactions
- ambiguous invoice matching with material amounts
- missing entity interpretation for major counterparties
- changes likely to alter business conclusions significantly

### High

- substantial transactions with uncertain category or project
- repeated similar transactions lacking confirmation
- newly propagated business-memory effects not yet validated

### Medium

- moderate impact items still worth review

### Low

- low-impact noise such as small fees or residual unclear rows with little effect on analysis

## Query Gate

The query system should not return falsely confident answers when the workspace is not ready.

- If `critical` or `high` items remain, serious questions should be blocked or rerouted to review.
- Lower-severity items may remain, but the system should know they still affect confidence.
- Ambiguous natural-language questions should request clarification instead of falling back to global totals.

## Planner Design

The planner should evolve from token-based fallback behavior into a structured intent layer.

### Planner responsibilities

- detect metric
- detect period
- detect direction
- detect entity
- detect category
- detect project
- detect relationship intent
- decide whether the question is exact, estimated, blocked, or needs clarification

### Query families to support

- payments to entity
- receipts from entity
- relationship summary with entity
- category totals
- project totals
- crediting and recovery
- net cashflow
- invoice-backed revenue questions

### Planner rules

- never answer with a global fallback if the intent is unclear
- request clarification when the metric or relationship is ambiguous
- prefer deterministic execution once intent is known
- use business memory and matching results as structured filters

## Invoice and Matching Design

### Invoice roles

- issued invoices support partner-side revenue understanding
- received invoices support category, collaborator, project, and operational interpretation

### Reprocessing

Adding invoices later is not passive. It triggers targeted reprocessing of affected transactions.

If reprocessing changes:

- category
- entity type
- project
- invoice match
- review severity

the system must open a change-review queue instead of silently overwriting accepted meaning.

### Matching phases

#### Phase 1

- one invoice to one payment
- one payment to one invoice
- clear partial payment support when confidence is high

#### Phase 2

Mandatory future improvement:

- one invoice paid in multiple installments
- many-to-many allocation where needed

### Matching outputs

Each match should store:

- matched document IDs
- confidence
- reasoning
- matched amount
- residual unmatched amount if partial
- whether the match is proposed or accepted

## Business Memory UX

The user writes natural text, but the application should expose the resulting structured facts in an editable view.

The memory area should show:

- instructions history
- parsed entities
- parsed projects
- parsed rules
- parsed relationships
- status of each fact

This lets the user both talk naturally and inspect what the system thinks it learned.

## Category Suggestion UX

When a category is created or reinforced, the system should propose similar transactions using:

- normalized merchant
- similar description
- related invoice evidence
- project relations
- known business-memory facts

The user should be able to:

- accept
- reject
- skip
- apply to all similar

## Change Review UX

When reprocessing creates conflicts with current interpretation, the UI should show:

- before value
- proposed value
- reason for change
- confidence
- scope of propagation

Actions:

- accept
- reject
- skip for now
- accept all similar

## Implementation Shape

Implementation should be split into checkpoint-sized slices.

### Checkpoint 1: Workspace Model

- named company workspaces
- document imports attached to workspace
- internal account records
- workspace readiness state

### Checkpoint 2: Query Gate and Review Severity

- review severity model
- onboarding readiness rules
- query blocking for unresolved `critical` and `high`

### Checkpoint 3: Business Memory

- natural-language instruction input
- parsed structured memory
- editable memory view
- rule application into classification

### Checkpoint 4: Invoice Hub

- stronger issued/received invoice handling
- attachment to workspace and account context

### Checkpoint 5: Matching Engine Phase 1

- one-to-one matching
- clear partial payment support
- audit trail

### Checkpoint 6: Change Review

- detect interpretation changes after reprocessing
- approval or rejection flow

### Checkpoint 7: Planner Upgrade

- entity, project, and relationship aware query planning
- better clarification behavior

### Checkpoint 8: Post-Onboarding Workspace

- stable tabs for questions, transactions, categories, invoices, memory, review

### Checkpoint 9: Matching Phase 2

- installment and many-to-many matching

## Risks

- allowing memory overrides without clear audit may destroy trust
- allowing questions before review is clean may produce answers that feel precise but are wrong
- collapsing projects into categories would limit future reporting and business reasoning
- building matching too ambitiously in phase 1 would slow delivery and increase false positives

## Non-Goals for Phase 1

- direct email integration
- full accounting statements beyond what source documents support
- fully automatic many-to-many reconciliation
- making internal accounts a heavy user-facing concept

## Recommended Implementation Strategy

Build this as an incremental deterministic system with LLM assistance only where it improves understanding:

- LLM for natural-language instructions and fuzzy interpretation proposals
- deterministic engine for storage, matching, execution, review state, and query calculation

That keeps the product auditable, stable, and suitable for real finance workflows.
