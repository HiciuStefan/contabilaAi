# ContabilaAi Product Documentation

## 1. Product Overview

### 1.1 What ContabilaAi Is

ContabilaAi is a local finance copilot for small service businesses, especially IT firms. It is built to ingest bank statements and invoices, organize them inside a company workspace, learn business-specific context from the user, and answer natural-language questions only after the data is sufficiently reviewed.

The product is intentionally local-first:

- documents are imported from local files
- data is stored locally
- the application runs on a local server
- the user remains in control of classification, memory, and matching decisions

### 1.2 What Problem It Solves

The product solves a recurring finance workflow problem:

- businesses have bank statements, issued invoices, and received invoices
- raw accounting signals are spread across documents
- many transactions require company-specific interpretation
- users want trustworthy answers, not generic AI-sounding guesses

ContabilaAi turns this into a guided workflow:

1. import documents
2. add business context
3. review uncertain items
4. query the cleaned workspace

### 1.3 What It Is Not

ContabilaAi is not:

- a replacement for full accounting software
- a legal or fiscal reporting engine
- a generic chatbot over arbitrary documents
- an email client or email integration platform

It is a controlled interpretation layer over bank and invoice data, optimized for business reasoning and traceable answers.

## 2. Product Goals

### 2.1 Primary Goals

- support repeated imports over time for the same company
- preserve business memory per company
- classify and match transactions with strong auditability
- prioritize review effort instead of forcing perfect cleanup everywhere
- answer natural-language finance questions only when confidence is justified

### 2.2 Secondary Goals

- reduce repetitive manual categorization
- help the user isolate special expense buckets such as `casa`
- support projects as first-class business concepts
- maintain enough structure that future automation remains safe

## 3. Core Product Concepts

### 3.1 Workspace

A workspace represents one company.

The user may have multiple companies. Each company has its own:

- bank statements
- invoices
- business memory
- projects
- categories
- review state
- query readiness

This is the main persistence boundary.

### 3.2 Session

In practical UI language, a session is the current company workspace being opened and worked on.

The user may:

- create a new company workspace
- reopen an existing company workspace
- keep adding documents to the same workspace over time

### 3.3 Documents

Documents are imported into a workspace and stay attached to it over time.

Document types:

- bank statements
- issued invoices
- received invoices

### 3.4 Accounts

Accounts are first-class internal records inside a workspace. They help distinguish:

- `RON`
- `EUR`
- `USD`
- `credit`

Accounts are useful for continuity, matching, deduplication, and future reporting. They should exist strongly in the model but lightly in the UI.

### 3.5 Entities

Entities are business actors such as:

- partner
- collaborator
- associate
- general vendor
- bank
- state

For this product, a few business meanings are especially important:

- `partner` means someone who pays the company, usually based on issued invoices
- `collaborator` means someone who delivers services to the company
- `associate` is used for owner-level flows such as `creditare` and `recuperare_creditare`

### 3.6 Projects

Projects are first-class entities, not just tags.

They may be linked to:

- collaborators
- transactions
- invoices
- business-memory rules
- categories when useful

### 3.7 Analysis Categories

Analysis categories are user-facing business buckets such as:

- `casa`
- `software`
- `motorina`
- `marketing`
- `echipamente`

Each category has:

- name
- description
- operational scope

Operational scope values:

- `operational`
- `non_operational`
- `personal`
- `unassigned`

### 3.8 Business Memory

Business memory is workspace-scoped knowledge derived from natural-language instructions.

Examples:

- `Ai Excellence e partener`
- `X si Y lucreaza pe proiectul Z`
- `am facut o casa intre 2020-2024, si am facturi pentru asta`

The user writes naturally. The system stores structured meaning internally.

Business memory may override heuristic interpretation, but never rewrites raw source data.

## 4. User Experience Model

### 4.1 Product States

The product has three major user states:

1. `Workspace Home`
2. `Onboarding Wizard`
3. `Firm Workspace`

### 4.2 Workspace Home

The home screen lists company workspaces.

Each workspace shows a simple readiness status:

- `needs import`
- `needs review`
- `ready`

Possible actions:

- create company workspace
- open company workspace

### 4.3 Onboarding Wizard

The onboarding wizard is the setup flow for a workspace.

It exists because trustworthy answers require prepared data.

Wizard steps:

1. import documents
2. add business instructions
3. review prioritized items
4. review proposed changes after reprocessing
5. reach ready state

### 4.4 Firm Workspace

Once the workspace is ready, the user works in a normal multi-tab workspace.

Recommended areas:

- Questions
- Transactions
- Categories
- Invoices
- Business Memory
- Review

The Questions area should remain simple. Heavy cleanup and inspection should happen elsewhere.

## 5. Onboarding Wizard Design

### 5.1 Step 1: Import Documents

The user can:

- add bank statement
- import issued invoices
- import received invoices

This step supports:

- first-time historical bootstrap
- monthly or periodic updates later

### 5.2 Step 2: Business Instructions

The user gets a large text box where they can write natural business context.

The system should:

- parse the instruction
- propose structured facts
- save them into workspace-scoped business memory

### 5.3 Step 3: Prioritized Review

Review is not flat. It is sorted by severity:

- `critical`
- `high`
- `medium`
- `low`

The product focuses first on what changes business conclusions most.

### 5.4 Step 4: Change Review

When new invoices or business memory change existing interpretation, the system must show a comparison instead of silently overwriting prior accepted meaning.

User actions:

- accept
- reject
- skip
- accept all similar

### 5.5 Step 5: Ready

The workspace becomes query-ready once:

- no `critical` review items remain
- no `high` review items remain

Medium and low items may remain, but they should not block general usage.

## 6. Review and Severity Model

### 6.1 Why Severity Exists

The user does not benefit from reviewing everything with equal urgency.

Severity allows the application to:

- gate serious queries
- focus the user on impactful decisions
- allow lower-priority cleanup later

### 6.2 Critical

Examples:

- large uncategorized transactions
- major ambiguous invoice matches
- unknown entity identity for important counterparties
- changes that would materially alter relationship, category, or cashflow conclusions

### 6.3 High

Examples:

- substantial transactions with uncertain category
- repeated patterns that likely need one decision propagated
- newly applied business-memory rules not yet validated

### 6.4 Medium

Examples:

- meaningful but not urgent interpretation uncertainty
- project mapping not yet closed

### 6.5 Low

Examples:

- small fees
- low-impact noise
- residual ambiguous rows with little analytical significance

## 7. Query Readiness and Query Gate

### 7.1 Why Query Gate Exists

The product should not answer with false confidence when key data is still unresolved.

### 7.2 Gate Rule

Serious natural-language queries are unlocked only when:

- no `critical` items remain
- no `high` items remain

### 7.3 Ambiguous Questions

If the planner does not understand a query clearly, it should:

- ask for clarification
- never fall back to a global total

This avoids plausible-but-wrong answers.

## 8. Planner Design

### 8.1 Planner Role

The planner converts natural-language questions into structured intent.

It should determine:

- metric
- period
- direction
- entity
- category
- project
- relationship intent
- support level

### 8.2 Query Families

Expected query families include:

- payments to an entity
- receipts from an entity
- relationship summary with an entity
- category totals
- project totals
- crediting and recovery
- cashflow net
- invoice-backed revenue

### 8.3 Planner Rules

- do not use silent global fallback when the question is unclear
- request clarification for ambiguous relationship questions
- prefer deterministic execution once the question is understood
- use business memory, categories, projects, and matching outputs as structured filters

### 8.4 Planner + Review Interaction

Planner execution should be aware of workspace readiness. It should know when:

- a question can be answered
- a question should be blocked by unresolved high-severity review
- a question should be clarified

## 9. Invoice Model and Matching

### 9.1 Issued Invoices

Issued invoices support:

- revenue interpretation
- partner understanding
- invoice-backed turnover views

### 9.2 Received Invoices

Received invoices support:

- category understanding
- collaborator and vendor understanding
- project allocation
- operational versus non-operational interpretation

### 9.3 Reprocessing

If invoices are added later, the system must reprocess affected records.

This is required because new invoice evidence may change:

- category
- entity type
- project
- invoice link
- review priority

### 9.4 Matching Phase 1

Phase 1 supports:

- one invoice to one payment
- one payment to one invoice
- clear partial payment support when confidence is high

### 9.5 Matching Phase 2

Mandatory future improvement:

- one invoice paid in multiple installments
- many-to-many allocation when needed

### 9.6 Matching Output

Each match should store:

- matched document IDs
- confidence
- reasoning
- matched amount
- residual unmatched amount
- proposed vs accepted state

## 10. Business Memory Design

### 10.1 Input Model

The user writes natural text. The product does not force structured form input as the primary path.

### 10.2 Internal Structured Memory

Natural instructions should be converted into structured facts such as:

- entity type assertions
- project membership
- category hints
- project-to-entity links
- override rules

### 10.3 Editability

The user should also be able to inspect and edit the structured result.

The Business Memory area should expose:

- instructions history
- parsed entities
- parsed projects
- parsed relationships
- parsed rules
- status for each item

### 10.4 Authority Model

Business memory is allowed to override heuristics.

However:

- raw document data remains unchanged
- overrides must be auditable
- changes triggered by memory should be reviewable if they alter accepted interpretation

## 11. Category Workflow

### 11.1 Category Creation

When a category is created or strengthened, the product should search for similar candidate transactions.

Signals may include:

- normalized merchant
- similar descriptions
- invoice evidence
- related project
- previously accepted business-memory facts

### 11.2 Suggestion Review

The user should be able to:

- accept
- reject
- skip
- apply to all similar

### 11.3 Category Metadata

Each category should carry enough meaning to be useful later:

- name
- description
- operational scope

## 12. Change Review

### 12.1 Why It Exists

Later imports should not invisibly rewrite previously accepted meaning.

### 12.2 What Triggers It

Change review should appear when reprocessing proposes changes to:

- category
- entity type
- project
- invoice match
- review severity

### 12.3 UX Expectations

The UI should show:

- previous state
- proposed state
- reason
- confidence
- propagation scope

User actions:

- accept
- reject
- skip for now
- accept all similar

## 13. Current Implemented Capabilities

At the current stage of the repository, the product already implements the main workspace architecture:

- named company workspaces with readiness states
- local import for bank statements from PDF, CSV, and JSON
- strict statement validation for supported PDF parsers so declared totals and parsed totals must match
- SQLite storage
- custom parsing for real files used by the project
- local web UI
- automatic basic transaction classification
- category metadata and category transaction browsing
- review queue with `critical`, `high`, `medium`, and `low`
- query gate that blocks serious questions while `critical` or `high` items remain
- business memory instructions stored per workspace
- workspace-scoped invoice hub
- phase 1 invoice matching
- change review workflow for category proposals
- natural-language planner for a subset of supported finance questions, now scoped to workspace and project filters
- onboarding workflow with checklist, guided tabs, business memory input, invoice hub, and change review visibility
- tests covering storage, import, planner, matching, change review, review, workspaces, and HTTP smoke flows

This is still not the final target product, but it is now well beyond a generic MVP bootstrap.

## 14. Current Gaps Relative to Target Product

The major gaps between the current implementation and the intended full product are:

- project support exists in planner and business facts, but not yet as a full first-class editing UI
- business memory parsing is still deterministic and intentionally narrow
- invoice matching now supports one-to-one, installments, and one-payment-to-multiple-invoices,
  but still needs deeper many-to-many balancing heuristics across longer payment timelines
- change review is implemented for category proposals, but not yet for the full field matrix
- invoice hub and matching are now visible in the workspace UI, but still need deeper analytics and operator tooling

## 15. Architecture Direction

The recommended architecture is layered:

1. document layer
2. business memory layer
3. matching and interpretation layer
4. planner and answer layer

This keeps responsibilities separated:

- raw document ingestion stays deterministic
- business knowledge remains explicit
- matching remains auditable
- planner remains explainable

## 16. Use of Models

The recommended product design uses a model, but only where it helps.

### 16.1 Use Model For

- understanding natural-language business instructions
- interpreting fuzzy questions
- proposing ambiguous matches
- generating natural explanations

### 16.2 Do Not Use Model For

- raw arithmetic
- totals
- deterministic filtering
- persistence logic
- exact matching when strict keys exist

### 16.3 Guiding Principle

Use LLMs for understanding and proposal generation.

Use deterministic code for:

- calculation
- storage
- execution
- review state
- final answer auditability

## 17. Risks

- memory overrides without audit may reduce trust
- answering too early may give precise-looking but wrong outputs
- mixing project with category would limit future reasoning
- over-ambitious first-pass matching would increase false positives

## 18. Non-Goals for Phase 1

- direct email integration
- full accounting statement generation
- fully automatic many-to-many reconciliation
- heavy account-centric UI

## 19. Recommended Roadmap

### Phase 1

- workspace model
- onboarding shell
- severity-based review gate
- business memory foundation
- invoice hub
- matching engine phase 1
- change review foundation
- planner upgrade

### Phase 2

- installment and many-to-many matching
- stronger project-aware analytics
- deeper memory editing and rule management
- full onboarding wizard experience

## 20. Operational Notes

### 20.1 Local Runtime

The application is expected to run locally on:

- local Python runtime
- local SQLite database
- local static UI served by the local HTTP service

### 20.2 Data Ownership

The data belongs to the local workspace. The product should preserve user control and make resets, reimports, and reprocessing explicit.

## 21. Documentation Usage

This document is the full product-level reference. It should be used as the source of truth for:

- future implementation planning
- onboarding new agents or tools
- validating roadmap choices
- checking whether new features fit the intended product

More specific design docs may sit underneath it, but they should not contradict it.
