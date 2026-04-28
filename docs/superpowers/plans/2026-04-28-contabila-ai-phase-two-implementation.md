# ContabilaAi Phase Two Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Finish phase 2 by making business memory substantially more expressive, extending invoice matching beyond the current short-window heuristics, and upgrading the planner to answer relationship-style questions safely and usefully.

**Architecture:** Keep the product deterministic at execution time, but expand the interpretation layer. Business memory will move to a staged extraction pipeline that accepts freer natural language, validates it into structured facts, and then projects those facts into deterministic rules and workspace-scoped filters. Matching will gain stronger bundle and timeline heuristics while preserving explicit proposals. Planner improvements will use those structured facts to provide relationship summaries and better clarification behavior.

**Tech Stack:** Python 3, SQLite, local HTTP server in `src/contabila_ai/server/http.py`, browser UI in `web/`, pytest for verification, GitHub remote on `origin`.

---

## File Structure

### Existing files to extend

- `C:\Users\stefan\Documents\Codex\2026-04-22-aici-avem-codex-superpowers-active\ContabilaAi\src\contabila_ai\memory\models.py`
  - fact dataclasses and structured fact payloads
- `C:\Users\stefan\Documents\Codex\2026-04-22-aici-avem-codex-superpowers-active\ContabilaAi\src\contabila_ai\memory\service.py`
  - instruction parsing, validation, and deterministic projection into store rules
- `C:\Users\stefan\Documents\Codex\2026-04-22-aici-avem-codex-superpowers-active\ContabilaAi\src\contabila_ai\matching\service.py`
  - invoice-payment proposal generation
- `C:\Users\stefan\Documents\Codex\2026-04-22-aici-avem-codex-superpowers-active\ContabilaAi\src\contabila_ai\planning\models.py`
  - planner model for new relationship summary responses
- `C:\Users\stefan\Documents\Codex\2026-04-22-aici-avem-codex-superpowers-active\ContabilaAi\src\contabila_ai\planning\planner.py`
  - natural-language intent extraction and clarification rules
- `C:\Users\stefan\Documents\Codex\2026-04-22-aici-avem-codex-superpowers-active\ContabilaAi\src\contabila_ai\storage\store.py`
  - persistence, query execution, rule storage, and planner SQL
- `C:\Users\stefan\Documents\Codex\2026-04-22-aici-avem-codex-superpowers-active\ContabilaAi\src\contabila_ai\server\http.py`
  - answer rendering and API surface
- `C:\Users\stefan\Documents\Codex\2026-04-22-aici-avem-codex-superpowers-active\ContabilaAi\src\contabila_ai\change_review\service.py`
  - surfacing proposed interpretation changes when new memory or invoice evidence changes meaning
- `C:\Users\stefan\Documents\Codex\2026-04-22-aici-avem-codex-superpowers-active\ContabilaAi\web\app.js`
  - business memory and question UX integration
- `C:\Users\stefan\Documents\Codex\2026-04-22-aici-avem-codex-superpowers-active\ContabilaAi\docs\PRODUCT_DOCUMENTATION.md`
  - product-level phase status and capability notes

### Existing tests to extend

- `C:\Users\stefan\Documents\Codex\2026-04-22-aici-avem-codex-superpowers-active\ContabilaAi\tests\test_memory.py`
- `C:\Users\stefan\Documents\Codex\2026-04-22-aici-avem-codex-superpowers-active\ContabilaAi\tests\test_matching.py`
- `C:\Users\stefan\Documents\Codex\2026-04-22-aici-avem-codex-superpowers-active\ContabilaAi\tests\test_planner.py`
- `C:\Users\stefan\Documents\Codex\2026-04-22-aici-avem-codex-superpowers-active\ContabilaAi\tests\test_http_smoke.py`

---

### Task 1: Expand Business Memory Into a Staged Semantic Parser

**Files:**
- Modify: `C:\Users\stefan\Documents\Codex\2026-04-22-aici-avem-codex-superpowers-active\ContabilaAi\src\contabila_ai\memory\models.py`
- Modify: `C:\Users\stefan\Documents\Codex\2026-04-22-aici-avem-codex-superpowers-active\ContabilaAi\src\contabila_ai\memory\service.py`
- Modify: `C:\Users\stefan\Documents\Codex\2026-04-22-aici-avem-codex-superpowers-active\ContabilaAi\tests\test_memory.py`

- [ ] **Step 1: Write failing parser tests for freer natural language**

```python
def test_business_memory_parses_house_category_hint_with_period() -> None:
    facts = parse_instruction_to_facts(
        "am facut o casa intre 2020-2024, pune cheltuielile astea la categoria casa"
    )

    assert [fact.fact_type for fact in facts] == ["category_rule"]
    assert facts[0].fact_value == "casa"
    assert facts[0].extra["date_start"] == "2020-01-01"
    assert facts[0].extra["date_end"] == "2024-12-31"


def test_business_memory_parses_project_assignment_from_natural_sentence() -> None:
    facts = parse_instruction_to_facts(
        "Sergiu Munteanu si Casa Decor SRL lucreaza pentru proiectul Atlas"
    )

    assert len(facts) == 2
    assert {fact.fact_type for fact in facts} == {"project_assignment"}
    assert {fact.fact_value for fact in facts} == {"Atlas"}
```

- [ ] **Step 2: Run the focused tests to verify RED**

Run: `pytest tests/test_memory.py -k "house_category_hint or natural_sentence" -v`

Expected: FAIL because `category_rule` and freer project parsing are not yet implemented.

- [ ] **Step 3: Extend fact modeling for validated semantic extras**

```python
@dataclass(frozen=True, slots=True)
class BusinessFact:
    fact_type: str
    subject_name: str
    fact_value: str
    confidence: float = 1.0
    status: str = "accepted"
    extra: dict[str, object] = field(default_factory=dict)
```

- [ ] **Step 4: Implement staged extraction and validation**

```python
def parse_instruction_to_facts(raw_text: str) -> list[BusinessFact]:
    text = " ".join(raw_text.split()).strip()
    for extractor in (
        _extract_entity_correction,
        _extract_entity_assertion,
        _extract_project_assignments,
        _extract_category_rules,
    ):
        facts = extractor(text)
        if facts:
            return _validate_business_facts(facts)
    return [BusinessFact(fact_type="note", subject_name="workspace", fact_value=text)]
```

- [ ] **Step 5: Re-run focused memory tests**

Run: `pytest tests/test_memory.py -k "house_category_hint or natural_sentence" -v`

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/contabila_ai/memory/models.py src/contabila_ai/memory/service.py tests/test_memory.py
git commit -m "feat: expand semantic business memory parsing"
```

---

### Task 2: Project Business Memory Into Deterministic Category Rules

**Files:**
- Modify: `C:\Users\stefan\Documents\Codex\2026-04-22-aici-avem-codex-superpowers-active\ContabilaAi\src\contabila_ai\memory\service.py`
- Modify: `C:\Users\stefan\Documents\Codex\2026-04-22-aici-avem-codex-superpowers-active\ContabilaAi\src\contabila_ai\storage\store.py`
- Modify: `C:\Users\stefan\Documents\Codex\2026-04-22-aici-avem-codex-superpowers-active\ContabilaAi\src\contabila_ai\change_review\service.py`
- Modify: `C:\Users\stefan\Documents\Codex\2026-04-22-aici-avem-codex-superpowers-active\ContabilaAi\tests\test_memory.py`

- [ ] **Step 1: Write failing integration test for category rule projection**

```python
def test_business_memory_category_rule_creates_change_review_for_matching_transactions() -> None:
    store = SQLiteTransactionStore(db_path)
    workspace_id = store.create_workspace("MobExc")
    _seed_house_transactions(store, workspace_id)
    service = BusinessMemoryService(store)

    result = service.add_instruction(
        workspace_id,
        "am facut o casa intre 2020-2024, pune cheltuielile astea la categoria casa",
    )

    items = store.list_change_review_items(workspace_id)
    assert result["fact_count"] == 1
    assert any(item["field_name"] == "analysis_category" and item["new_value"] == "casa" for item in items)
```

- [ ] **Step 2: Run focused test to verify RED**

Run: `pytest tests/test_memory.py::BusinessMemoryTest::test_business_memory_category_rule_creates_change_review_for_matching_transactions -v`

Expected: FAIL because category-rule facts are not projected into deterministic changes.

- [ ] **Step 3: Add store helper that finds transactions matching a category rule**

```python
def list_transactions_for_business_rule(self, *, workspace_id: int, date_start: str | None, date_end: str | None) -> list[dict[str, Any]]:
    ...
```

- [ ] **Step 4: Apply category rules as proposed changes, not silent rewrites**

```python
if fact.fact_type == "category_rule":
    self._project_category_rule(workspace_id=workspace_id, fact=fact)
```

- [ ] **Step 5: Re-run focused memory test**

Run: `pytest tests/test_memory.py::BusinessMemoryTest::test_business_memory_category_rule_creates_change_review_for_matching_transactions -v`

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/contabila_ai/memory/service.py src/contabila_ai/storage/store.py src/contabila_ai/change_review/service.py tests/test_memory.py
git commit -m "feat: project memory rules into category review"
```

---

### Task 3: Deepen Matching Heuristics Across Longer Timelines

**Files:**
- Modify: `C:\Users\stefan\Documents\Codex\2026-04-22-aici-avem-codex-superpowers-active\ContabilaAi\src\contabila_ai\matching\service.py`
- Modify: `C:\Users\stefan\Documents\Codex\2026-04-22-aici-avem-codex-superpowers-active\ContabilaAi\tests\test_matching.py`

- [ ] **Step 1: Write failing matching test for long-window bundle settlement**

```python
def test_matching_service_can_match_bundle_settlement_beyond_short_window() -> None:
    store = _seed_delayed_bundle_settlement_store(db_path)
    service = MatchingService(store)

    proposals = service.match_workspace(workspace_id=1)

    assert len(proposals) == 2
    assert {proposal["match_kind"] for proposal in proposals} == {"bulk_settlement"}
```

- [ ] **Step 2: Run focused matching test to verify RED**

Run: `pytest tests/test_matching.py -k delayed_bundle_settlement -v`

Expected: FAIL because the current 45-day window rejects the valid bundle.

- [ ] **Step 3: Add progressive windowing and stronger candidate ranking**

```python
WINDOW_DAYS = (45, 120, 365)
...
for window_days in WINDOW_DAYS:
    eligible = self._eligible_invoices_for_transaction(transaction, invoices, max_window_days=window_days)
    ...
```

- [ ] **Step 4: Re-run focused matching test**

Run: `pytest tests/test_matching.py -k delayed_bundle_settlement -v`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/contabila_ai/matching/service.py tests/test_matching.py
git commit -m "feat: improve long-window bundle matching"
```

---

### Task 4: Add Relationship Summary Planning

**Files:**
- Modify: `C:\Users\stefan\Documents\Codex\2026-04-22-aici-avem-codex-superpowers-active\ContabilaAi\src\contabila_ai\planning\models.py`
- Modify: `C:\Users\stefan\Documents\Codex\2026-04-22-aici-avem-codex-superpowers-active\ContabilaAi\src\contabila_ai\planning\planner.py`
- Modify: `C:\Users\stefan\Documents\Codex\2026-04-22-aici-avem-codex-superpowers-active\ContabilaAi\tests\test_planner.py`

- [ ] **Step 1: Write failing planner tests for relationship summary**

```python
def test_build_query_plan_detects_entity_relationship_summary() -> None:
    plan = build_query_plan("care e situatia lui ai excellence")

    assert plan.metric == "entity_relationship_summary"
    assert plan.entity_name == "ai excellence"
    assert plan.support_level == "exact"
```

- [ ] **Step 2: Run planner test to verify RED**

Run: `pytest tests/test_planner.py -k relationship_summary -v`

Expected: FAIL because ambiguous relationship questions still clarify instead of producing a scoped summary metric.

- [ ] **Step 3: Extend the planner model and intent rules**

```python
PLANNER_METRICS = (..., "entity_relationship_summary")
```

- [ ] **Step 4: Re-run focused planner tests**

Run: `pytest tests/test_planner.py -k relationship_summary -v`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/contabila_ai/planning/models.py src/contabila_ai/planning/planner.py tests/test_planner.py
git commit -m "feat: add relationship summary planning"
```

---

### Task 5: Execute Relationship Summary and Improve Answers

**Files:**
- Modify: `C:\Users\stefan\Documents\Codex\2026-04-22-aici-avem-codex-superpowers-active\ContabilaAi\src\contabila_ai\storage\store.py`
- Modify: `C:\Users\stefan\Documents\Codex\2026-04-22-aici-avem-codex-superpowers-active\ContabilaAi\src\contabila_ai\server\http.py`
- Modify: `C:\Users\stefan\Documents\Codex\2026-04-22-aici-avem-codex-superpowers-active\ContabilaAi\tests\test_http_smoke.py`

- [ ] **Step 1: Write failing HTTP smoke test for entity relationship summary**

```python
def test_chat_returns_entity_relationship_summary(client, seeded_workspace_with_ai_excellence_flows):
    response = client.post(
        "/api/chat",
        json={"workspace_id": seeded_workspace_with_ai_excellence_flows, "question": "care e situatia lui ai excellence"},
    )
    payload = response.get_json()

    assert payload["plan"]["metric"] == "entity_relationship_summary"
    assert "incasari" in payload["answer"].lower()
    assert "plati" in payload["answer"].lower()
    assert "net" in payload["answer"].lower()
```

- [ ] **Step 2: Run focused HTTP smoke test to verify RED**

Run: `pytest tests/test_http_smoke.py -k entity_relationship_summary -v`

Expected: FAIL because store execution and answer rendering do not support the new metric.

- [ ] **Step 3: Add deterministic relationship-summary execution**

```python
if plan.metric == "entity_relationship_summary":
    sql, params = self._build_entity_relationship_summary_query(plan)
```

- [ ] **Step 4: Render a business-meaningful answer**

```python
return (
    f"Relatia cu {entity_name}: incasari {income_total}, plati {expense_total}, net {net_total}. "
    f"Tip entitate observat: {entity_type_label}."
)
```

- [ ] **Step 5: Re-run focused smoke test**

Run: `pytest tests/test_http_smoke.py -k entity_relationship_summary -v`

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/contabila_ai/storage/store.py src/contabila_ai/server/http.py tests/test_http_smoke.py
git commit -m "feat: answer relationship summary queries"
```

---

### Task 6: Refresh Docs and Run Full Regression

**Files:**
- Modify: `C:\Users\stefan\Documents\Codex\2026-04-22-aici-avem-codex-superpowers-active\ContabilaAi\docs\PRODUCT_DOCUMENTATION.md`
- Modify: `C:\Users\stefan\Documents\Codex\2026-04-22-aici-avem-codex-superpowers-active\ContabilaAi\README.md`

- [ ] **Step 1: Update docs to reflect shipped phase-2 behavior**

```markdown
- semantic business memory now supports freer natural-language parsing with validated structured facts
- matching can resolve delayed bundle settlements across longer invoice timelines
- relationship summary questions return receipts, payments, net, and observed entity role
```

- [ ] **Step 2: Run full regression**

Run: `pytest -v`

Expected: PASS.

- [ ] **Step 3: Commit**

```bash
git add docs/PRODUCT_DOCUMENTATION.md README.md
git commit -m "checkpoint: complete phase two core workflow"
```

---

## Checkpoint Map

- **Checkpoint F:** Tasks 1-2
  - business memory can parse freer instructions and project category-rule proposals into review
- **Checkpoint G:** Task 3
  - matching supports delayed bundle settlements with deterministic ranking
- **Checkpoint H:** Tasks 4-5
  - planner and answers support relationship summaries instead of useless global totals
- **Checkpoint I:** Task 6
  - docs refreshed and full regression green

## Self-Review

- Spec coverage: phase-2 roadmap items now map to semantic business memory, deeper matching heuristics, and relationship-aware planner execution.
- Placeholder scan: no `TODO`, `TBD`, or vague “implement later” wording remains.
- Type consistency: `category_rule`, `project_assignment`, `entity_relationship_summary`, `matched_amount`, `residual_amount`, and `workspace_id` naming is consistent across tasks.
