# ContabilaAi Workspace, Business Memory, Planner, and Matching Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Convert the current single-workspace MVP into a named company workspace product with onboarding, review severity, business memory, invoice reprocessing, and a safer planner.

**Architecture:** Extend the current deterministic Python + SQLite backend with explicit workspace-scoped domain records, then layer onboarding state, business memory, invoice matching, change review, and planner gating on top. Keep raw documents immutable, make interpretation auditable, and only let natural-language logic propose or structure facts while deterministic code stores, filters, matches, and calculates.

**Tech Stack:** Python 3, SQLite, local HTTP server in `src/contabila_ai/server/http.py`, browser UI in `web/`, pytest for test coverage.

---

## File Structure

### Existing files to extend

- `C:\Users\stefan\Documents\Codex\2026-04-22-aici-avem-codex-superpowers-active\ContabilaAi\src\contabila_ai\storage\schema.py`
  - owns SQLite schema creation and lightweight migrations
- `C:\Users\stefan\Documents\Codex\2026-04-22-aici-avem-codex-superpowers-active\ContabilaAi\src\contabila_ai\storage\store.py`
  - owns persistence, queries, and execution helpers
- `C:\Users\stefan\Documents\Codex\2026-04-22-aici-avem-codex-superpowers-active\ContabilaAi\src\contabila_ai\importing\importers.py`
  - owns document import logic
- `C:\Users\stefan\Documents\Codex\2026-04-22-aici-avem-codex-superpowers-active\ContabilaAi\src\contabila_ai\planning\models.py`
  - planner dataclasses and support flags
- `C:\Users\stefan\Documents\Codex\2026-04-22-aici-avem-codex-superpowers-active\ContabilaAi\src\contabila_ai\planning\planner.py`
  - natural-language intent extraction
- `C:\Users\stefan\Documents\Codex\2026-04-22-aici-avem-codex-superpowers-active\ContabilaAi\src\contabila_ai\review\service.py`
  - review queue logic and category application
- `C:\Users\stefan\Documents\Codex\2026-04-22-aici-avem-codex-superpowers-active\ContabilaAi\src\contabila_ai\server\http.py`
  - HTTP routes and answer rendering
- `C:\Users\stefan\Documents\Codex\2026-04-22-aici-avem-codex-superpowers-active\ContabilaAi\web\index.html`
  - main shell and sections
- `C:\Users\stefan\Documents\Codex\2026-04-22-aici-avem-codex-superpowers-active\ContabilaAi\web\app.js`
  - client-side state, fetches, DOM rendering
- `C:\Users\stefan\Documents\Codex\2026-04-22-aici-avem-codex-superpowers-active\ContabilaAi\web\styles.css`
  - layout and view states

### New backend files to create

- `C:\Users\stefan\Documents\Codex\2026-04-22-aici-avem-codex-superpowers-active\ContabilaAi\src\contabila_ai\workspaces\models.py`
  - small dataclasses for workspace, account, readiness, and view models
- `C:\Users\stefan\Documents\Codex\2026-04-22-aici-avem-codex-superpowers-active\ContabilaAi\src\contabila_ai\workspaces\service.py`
  - workspace lifecycle and readiness orchestration
- `C:\Users\stefan\Documents\Codex\2026-04-22-aici-avem-codex-superpowers-active\ContabilaAi\src\contabila_ai\memory\models.py`
  - business memory fact types and statuses
- `C:\Users\stefan\Documents\Codex\2026-04-22-aici-avem-codex-superpowers-active\ContabilaAi\src\contabila_ai\memory\service.py`
  - business instruction ingestion and fact retrieval
- `C:\Users\stefan\Documents\Codex\2026-04-22-aici-avem-codex-superpowers-active\ContabilaAi\src\contabila_ai\matching\models.py`
  - invoice match result, change proposal, residuals
- `C:\Users\stefan\Documents\Codex\2026-04-22-aici-avem-codex-superpowers-active\ContabilaAi\src\contabila_ai\matching\service.py`
  - phase 1 matching logic and reprocessing entry point
- `C:\Users\stefan\Documents\Codex\2026-04-22-aici-avem-codex-superpowers-active\ContabilaAi\src\contabila_ai\change_review\service.py`
  - proposed interpretation changes and accept/reject flows

### Existing tests to extend

- `C:\Users\stefan\Documents\Codex\2026-04-22-aici-avem-codex-superpowers-active\ContabilaAi\tests\test_storage.py`
- `C:\Users\stefan\Documents\Codex\2026-04-22-aici-avem-codex-superpowers-active\ContabilaAi\tests\test_importers.py`
- `C:\Users\stefan\Documents\Codex\2026-04-22-aici-avem-codex-superpowers-active\ContabilaAi\tests\test_planner.py`
- `C:\Users\stefan\Documents\Codex\2026-04-22-aici-avem-codex-superpowers-active\ContabilaAi\tests\test_review.py`
- `C:\Users\stefan\Documents\Codex\2026-04-22-aici-avem-codex-superpowers-active\ContabilaAi\tests\test_http_smoke.py`

### New tests to create

- `C:\Users\stefan\Documents\Codex\2026-04-22-aici-avem-codex-superpowers-active\ContabilaAi\tests\test_workspaces.py`
- `C:\Users\stefan\Documents\Codex\2026-04-22-aici-avem-codex-superpowers-active\ContabilaAi\tests\test_memory.py`
- `C:\Users\stefan\Documents\Codex\2026-04-22-aici-avem-codex-superpowers-active\ContabilaAi\tests\test_matching.py`
- `C:\Users\stefan\Documents\Codex\2026-04-22-aici-avem-codex-superpowers-active\ContabilaAi\tests\test_change_review.py`

---

### Task 1: Introduce Named Company Workspaces

**Files:**
- Create: `C:\Users\stefan\Documents\Codex\2026-04-22-aici-avem-codex-superpowers-active\ContabilaAi\src\contabila_ai\workspaces\models.py`
- Create: `C:\Users\stefan\Documents\Codex\2026-04-22-aici-avem-codex-superpowers-active\ContabilaAi\src\contabila_ai\workspaces\service.py`
- Modify: `C:\Users\stefan\Documents\Codex\2026-04-22-aici-avem-codex-superpowers-active\ContabilaAi\src\contabila_ai\storage\schema.py`
- Modify: `C:\Users\stefan\Documents\Codex\2026-04-22-aici-avem-codex-superpowers-active\ContabilaAi\src\contabila_ai\storage\store.py`
- Test: `C:\Users\stefan\Documents\Codex\2026-04-22-aici-avem-codex-superpowers-active\ContabilaAi\tests\test_workspaces.py`
- Test: `C:\Users\stefan\Documents\Codex\2026-04-22-aici-avem-codex-superpowers-active\ContabilaAi\tests\test_storage.py`

- [ ] **Step 1: Write the failing workspace storage tests**

```python
from contabila_ai.storage.store import LedgerStore


def test_store_creates_and_lists_named_workspaces(tmp_path):
    store = LedgerStore(tmp_path / "ledger.db")
    workspace_id = store.create_workspace("MobExc")

    workspaces = store.list_workspaces()

    assert len(workspaces) == 1
    assert workspaces[0]["id"] == workspace_id
    assert workspaces[0]["name"] == "MobExc"
    assert workspaces[0]["status"] == "needs_import"


def test_store_assigns_imports_to_workspace(tmp_path, sample_transactions):
    store = LedgerStore(tmp_path / "ledger.db")
    workspace_id = store.create_workspace("MobExc")

    import_id = store.create_import_batch(
        source_name="statement.pdf",
        workspace_id=workspace_id,
        source_type="bank_statement",
    )
    store.insert_transactions(import_id, sample_transactions)

    workspaces = store.list_workspaces()

    assert workspaces[0]["import_count"] == 1
    assert workspaces[0]["transaction_count"] == len(sample_transactions)
```

- [ ] **Step 2: Run the new tests to verify they fail**

Run: `pytest tests/test_workspaces.py -v`

Expected: FAIL with `AttributeError` or missing table/column errors for `create_workspace`, `list_workspaces`, or `workspace_id`.

- [ ] **Step 3: Add the workspace schema**

```python
CREATE TABLE IF NOT EXISTS workspaces (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    status TEXT NOT NULL DEFAULT 'needs_import',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS accounts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    workspace_id INTEGER NOT NULL,
    name TEXT NOT NULL,
    currency TEXT,
    account_kind TEXT NOT NULL DEFAULT 'bank',
    external_ref TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(workspace_id, name),
    FOREIGN KEY(workspace_id) REFERENCES workspaces(id)
);
```

- [ ] **Step 4: Add minimal store methods**

```python
def create_workspace(self, name: str) -> int:
    with self._connect() as connection:
        cursor = connection.execute(
            "INSERT INTO workspaces (name, status) VALUES (?, 'needs_import')",
            (name.strip(),),
        )
        return int(cursor.lastrowid)


def list_workspaces(self) -> list[dict[str, object]]:
    query = """
        SELECT
            w.id,
            w.name,
            w.status,
            COUNT(DISTINCT ib.id) AS import_count,
            COUNT(t.id) AS transaction_count
        FROM workspaces w
        LEFT JOIN import_batches ib ON ib.workspace_id = w.id
        LEFT JOIN transactions t ON t.import_batch_id = ib.id
        GROUP BY w.id, w.name, w.status
        ORDER BY w.created_at DESC, w.id DESC
    """
    with self._connect() as connection:
        rows = connection.execute(query).fetchall()
    return [dict(row) for row in rows]
```

- [ ] **Step 5: Extend import batch ownership**

```python
def create_import_batch(
    self,
    source_name: str,
    workspace_id: int,
    source_type: str = "bank_statement",
) -> int:
    with self._connect() as connection:
        cursor = connection.execute(
            """
            INSERT INTO import_batches (source_name, source_type, workspace_id)
            VALUES (?, ?, ?)
            """,
            (source_name, source_type, workspace_id),
        )
        return int(cursor.lastrowid)
```

- [ ] **Step 6: Run focused tests**

Run: `pytest tests/test_workspaces.py tests/test_storage.py -v`

Expected: PASS for the new workspace tests.

- [ ] **Step 7: Commit**

```bash
git add src/contabila_ai/workspaces/models.py src/contabila_ai/workspaces/service.py src/contabila_ai/storage/schema.py src/contabila_ai/storage/store.py tests/test_workspaces.py tests/test_storage.py
git commit -m "feat: add named company workspaces"
```

---

### Task 2: Add Workspace Home and Current Workspace Selection

**Files:**
- Modify: `C:\Users\stefan\Documents\Codex\2026-04-22-aici-avem-codex-superpowers-active\ContabilaAi\src\contabila_ai\server\http.py`
- Modify: `C:\Users\stefan\Documents\Codex\2026-04-22-aici-avem-codex-superpowers-active\ContabilaAi\web\index.html`
- Modify: `C:\Users\stefan\Documents\Codex\2026-04-22-aici-avem-codex-superpowers-active\ContabilaAi\web\app.js`
- Modify: `C:\Users\stefan\Documents\Codex\2026-04-22-aici-avem-codex-superpowers-active\ContabilaAi\web\styles.css`
- Test: `C:\Users\stefan\Documents\Codex\2026-04-22-aici-avem-codex-superpowers-active\ContabilaAi\tests\test_http_smoke.py`

- [ ] **Step 1: Write the failing HTTP smoke tests for workspace home**

```python
def test_workspaces_endpoint_creates_and_lists_workspace(client):
    create_response = client.post("/api/workspaces", json={"name": "MobExc"})
    assert create_response.status_code == 200

    list_response = client.get("/api/workspaces")
    payload = list_response.get_json()

    assert payload["items"][0]["name"] == "MobExc"
    assert payload["items"][0]["status"] == "needs_import"
```

- [ ] **Step 2: Run the smoke test to verify it fails**

Run: `pytest tests/test_http_smoke.py::test_workspaces_endpoint_creates_and_lists_workspace -v`

Expected: FAIL with `404 NOT FOUND`.

- [ ] **Step 3: Add workspace endpoints**

```python
@app.get("/api/workspaces")
def list_workspaces_route():
    return jsonify({"items": store.list_workspaces()})


@app.post("/api/workspaces")
def create_workspace_route():
    payload = request.get_json(force=True) or {}
    name = str(payload.get("name") or "").strip()
    if not name:
        return jsonify({"error": "Workspace name is required."}), 400
    workspace_id = store.create_workspace(name)
    return jsonify({"workspace_id": workspace_id})
```

- [ ] **Step 4: Add the minimal home screen shell**

```html
<section id="workspace-home" class="workspace-home">
  <div class="card">
    <h1>Firme</h1>
    <form id="workspace-create-form">
      <input id="workspace-name" placeholder="ex: MobExc" />
      <button type="submit">Firma noua</button>
    </form>
    <div id="workspace-list"></div>
  </div>
</section>
```

- [ ] **Step 5: Add client-side workspace loading**

```javascript
async function loadWorkspaces() {
  const response = await fetch("/api/workspaces");
  const payload = await response.json();
  renderWorkspaceList(payload.items || []);
}

async function createWorkspace(name) {
  await fetch("/api/workspaces", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name }),
  });
  await loadWorkspaces();
}
```

- [ ] **Step 6: Run the focused smoke test**

Run: `pytest tests/test_http_smoke.py::test_workspaces_endpoint_creates_and_lists_workspace -v`

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add src/contabila_ai/server/http.py web/index.html web/app.js web/styles.css tests/test_http_smoke.py
git commit -m "feat: add workspace home flow"
```

---

### Task 3: Add Review Severity and Workspace Readiness Gate

**Files:**
- Modify: `C:\Users\stefan\Documents\Codex\2026-04-22-aici-avem-codex-superpowers-active\ContabilaAi\src\contabila_ai\storage\schema.py`
- Modify: `C:\Users\stefan\Documents\Codex\2026-04-22-aici-avem-codex-superpowers-active\ContabilaAi\src\contabila_ai\storage\store.py`
- Modify: `C:\Users\stefan\Documents\Codex\2026-04-22-aici-avem-codex-superpowers-active\ContabilaAi\src\contabila_ai\review\service.py`
- Modify: `C:\Users\stefan\Documents\Codex\2026-04-22-aici-avem-codex-superpowers-active\ContabilaAi\src\contabila_ai\server\http.py`
- Modify: `C:\Users\stefan\Documents\Codex\2026-04-22-aici-avem-codex-superpowers-active\ContabilaAi\tests\test_review.py`
- Modify: `C:\Users\stefan\Documents\Codex\2026-04-22-aici-avem-codex-superpowers-active\ContabilaAi\tests\test_http_smoke.py`

- [ ] **Step 1: Write failing severity and query-gate tests**

```python
def test_review_queue_groups_items_by_severity(tmp_path, seeded_store):
    queue = build_review_service(seeded_store).list_review_groups(workspace_id=1)
    severities = {group["severity"] for group in queue}
    assert "critical" in severities
    assert "high" in severities


def test_questions_block_when_workspace_has_critical_items(client, seeded_workspace):
    response = client.post("/api/ask", json={"workspace_id": seeded_workspace, "question": "cat am cheltuit"})
    payload = response.get_json()
    assert payload["support_level"] == "blocked"
```

- [ ] **Step 2: Run the targeted tests**

Run: `pytest tests/test_review.py tests/test_http_smoke.py -k "severity or critical_items" -v`

Expected: FAIL because severity fields and blocked support are missing.

- [ ] **Step 3: Add severity fields to review outputs**

```python
def _derive_review_severity(amount_abs: float, category_name: str | None, confidence: float) -> str:
    if amount_abs >= 10000 and not category_name:
        return "critical"
    if amount_abs >= 2500 or confidence < 0.4:
        return "high"
    if amount_abs >= 500:
        return "medium"
    return "low"
```

- [ ] **Step 4: Add workspace readiness computation**

```python
def compute_workspace_status(self, workspace_id: int) -> str:
    counts = self.get_review_severity_counts(workspace_id)
    if counts["critical"] or counts["high"]:
        return "needs_review"
    if self.workspace_has_imports(workspace_id):
        return "ready"
    return "needs_import"
```

- [ ] **Step 5: Block question execution when required**

```python
if store.workspace_has_blocking_review_items(workspace_id):
    return jsonify(
        {
            "answer": "Mai ai tranzactii critical sau high de revizuit inainte de intrebari serioase.",
            "support_level": "blocked",
            "transactions": [],
        }
    )
```

- [ ] **Step 6: Run focused tests**

Run: `pytest tests/test_review.py tests/test_http_smoke.py -k "severity or critical_items" -v`

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add src/contabila_ai/storage/schema.py src/contabila_ai/storage/store.py src/contabila_ai/review/service.py src/contabila_ai/server/http.py tests/test_review.py tests/test_http_smoke.py
git commit -m "feat: add review severity and query gate"
```

---

### Task 4: Add Business Memory Instruction Storage and Parsed Facts

**Files:**
- Create: `C:\Users\stefan\Documents\Codex\2026-04-22-aici-avem-codex-superpowers-active\ContabilaAi\src\contabila_ai\memory\models.py`
- Create: `C:\Users\stefan\Documents\Codex\2026-04-22-aici-avem-codex-superpowers-active\ContabilaAi\src\contabila_ai\memory\service.py`
- Modify: `C:\Users\stefan\Documents\Codex\2026-04-22-aici-avem-codex-superpowers-active\ContabilaAi\src\contabila_ai\storage\schema.py`
- Modify: `C:\Users\stefan\Documents\Codex\2026-04-22-aici-avem-codex-superpowers-active\ContabilaAi\src\contabila_ai\storage\store.py`
- Modify: `C:\Users\stefan\Documents\Codex\2026-04-22-aici-avem-codex-superpowers-active\ContabilaAi\src\contabila_ai\server\http.py`
- Create: `C:\Users\stefan\Documents\Codex\2026-04-22-aici-avem-codex-superpowers-active\ContabilaAi\tests\test_memory.py`

- [ ] **Step 1: Write failing tests for business instructions**

```python
def test_add_business_instruction_creates_structured_fact(tmp_path):
    store = LedgerStore(tmp_path / "ledger.db")
    workspace_id = store.create_workspace("MobExc")

    instruction_id = store.add_business_instruction(
        workspace_id=workspace_id,
        raw_text="Ai Excellence e partener",
    )

    facts = store.list_business_facts(workspace_id)
    assert instruction_id > 0
    assert facts[0]["subject_name"] == "Ai Excellence"
    assert facts[0]["fact_type"] == "entity_type"
    assert facts[0]["fact_value"] == "partner"
```

- [ ] **Step 2: Run the new tests**

Run: `pytest tests/test_memory.py -v`

Expected: FAIL because memory tables and methods do not exist.

- [ ] **Step 3: Add memory tables**

```python
CREATE TABLE IF NOT EXISTS business_instructions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    workspace_id INTEGER NOT NULL,
    raw_text TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(workspace_id) REFERENCES workspaces(id)
);

CREATE TABLE IF NOT EXISTS business_facts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    workspace_id INTEGER NOT NULL,
    instruction_id INTEGER,
    fact_type TEXT NOT NULL,
    subject_name TEXT NOT NULL,
    fact_value TEXT NOT NULL,
    extra_json TEXT,
    confidence REAL NOT NULL DEFAULT 1.0,
    status TEXT NOT NULL DEFAULT 'accepted',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(workspace_id) REFERENCES workspaces(id),
    FOREIGN KEY(instruction_id) REFERENCES business_instructions(id)
);
```

- [ ] **Step 4: Implement a deterministic first parser**

```python
def parse_instruction_to_facts(raw_text: str) -> list[dict[str, object]]:
    lowered = raw_text.lower().strip()
    if lowered.endswith(" e partener"):
        subject = raw_text[: raw_text.lower().rfind(" e partener")].strip()
        return [{"fact_type": "entity_type", "subject_name": subject, "fact_value": "partner"}]
    if " lucreaza pe proiectul " in lowered:
        left, right = raw_text.split("lucreaza pe proiectul", 1)
        project_name = right.strip()
        return [{"fact_type": "project_assignment", "subject_name": name.strip(), "fact_value": project_name} for name in left.split("si")]
    return [{"fact_type": "note", "subject_name": "workspace", "fact_value": raw_text}]
```

- [ ] **Step 5: Add HTTP routes and list view payloads**

```python
@app.post("/api/business-memory")
def add_business_memory_route():
    payload = request.get_json(force=True) or {}
    workspace_id = int(payload["workspace_id"])
    raw_text = str(payload.get("text") or "").strip()
    return jsonify(memory_service.add_instruction(workspace_id, raw_text))


@app.get("/api/business-memory")
def list_business_memory_route():
    workspace_id = int(request.args["workspace_id"])
    return jsonify({"facts": store.list_business_facts(workspace_id)})
```

- [ ] **Step 6: Run focused tests**

Run: `pytest tests/test_memory.py tests/test_http_smoke.py -k "business_memory" -v`

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add src/contabila_ai/memory/models.py src/contabila_ai/memory/service.py src/contabila_ai/storage/schema.py src/contabila_ai/storage/store.py src/contabila_ai/server/http.py tests/test_memory.py tests/test_http_smoke.py
git commit -m "feat: add business memory foundation"
```

---

### Task 5: Apply Business Memory to Classification and Entity Normalization

**Files:**
- Modify: `C:\Users\stefan\Documents\Codex\2026-04-22-aici-avem-codex-superpowers-active\ContabilaAi\src\contabila_ai\classification\engine.py`
- Modify: `C:\Users\stefan\Documents\Codex\2026-04-22-aici-avem-codex-superpowers-active\ContabilaAi\src\contabila_ai\review\service.py`
- Modify: `C:\Users\stefan\Documents\Codex\2026-04-22-aici-avem-codex-superpowers-active\ContabilaAi\src\contabila_ai\storage\store.py`
- Modify: `C:\Users\stefan\Documents\Codex\2026-04-22-aici-avem-codex-superpowers-active\ContabilaAi\tests\test_classification.py`
- Modify: `C:\Users\stefan\Documents\Codex\2026-04-22-aici-avem-codex-superpowers-active\ContabilaAi\tests\test_review.py`

- [ ] **Step 1: Write failing tests for memory-driven overrides**

```python
def test_business_memory_marks_entity_as_partner(tmp_path):
    store = LedgerStore(tmp_path / "ledger.db")
    workspace_id = store.create_workspace("MobExc")
    store.add_business_instruction(workspace_id, "Ai Excellence e partener")

    tx = {
        "description": "Transfer catre AI EXCELLENCE SRL",
        "merchant": "AI EXCELLENCE SRL",
        "amount": -1200.0,
        "posted_at": "2026-01-10",
    }
    classified = classify_transaction(tx, business_facts=store.list_business_facts(workspace_id))

    assert classified["entity_type"] == "partner"
```

- [ ] **Step 2: Run the failing classification tests**

Run: `pytest tests/test_classification.py -k business_memory -v`

Expected: FAIL because classifier ignores business facts.

- [ ] **Step 3: Thread business facts into classification**

```python
def classify_transaction(transaction: dict[str, object], business_facts: list[dict[str, object]] | None = None) -> dict[str, object]:
    result = _classify_from_description(transaction)
    memory_override = _lookup_entity_override(transaction, business_facts or [])
    if memory_override:
        result["entity_type"] = memory_override
    return result
```

- [ ] **Step 4: Add normalized entity lookup**

```python
def _lookup_entity_override(transaction: dict[str, object], business_facts: list[dict[str, object]]) -> str | None:
    merchant = _normalize_entity_name(str(transaction.get("merchant") or ""))
    for fact in business_facts:
        if fact["fact_type"] != "entity_type":
            continue
        if _normalize_entity_name(str(fact["subject_name"])) == merchant:
            return str(fact["fact_value"])
    return None
```

- [ ] **Step 5: Recompute review candidates using business memory**

```python
def build_review_groups(self, workspace_id: int) -> list[dict[str, object]]:
    facts = self._store.list_business_facts(workspace_id)
    transactions = self._store.list_workspace_transactions(workspace_id)
    return _group_transactions_for_review(transactions, business_facts=facts)
```

- [ ] **Step 6: Run focused tests**

Run: `pytest tests/test_classification.py tests/test_review.py -k business_memory -v`

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add src/contabila_ai/classification/engine.py src/contabila_ai/review/service.py src/contabila_ai/storage/store.py tests/test_classification.py tests/test_review.py
git commit -m "feat: apply business memory to classification"
```

---

### Task 6: Build the Invoice Hub for Issued and Received Documents

**Files:**
- Modify: `C:\Users\stefan\Documents\Codex\2026-04-22-aici-avem-codex-superpowers-active\ContabilaAi\src\contabila_ai\storage\schema.py`
- Modify: `C:\Users\stefan\Documents\Codex\2026-04-22-aici-avem-codex-superpowers-active\ContabilaAi\src\contabila_ai\storage\store.py`
- Modify: `C:\Users\stefan\Documents\Codex\2026-04-22-aici-avem-codex-superpowers-active\ContabilaAi\src\contabila_ai\importing\importers.py`
- Modify: `C:\Users\stefan\Documents\Codex\2026-04-22-aici-avem-codex-superpowers-active\ContabilaAi\src\contabila_ai\server\http.py`
- Modify: `C:\Users\stefan\Documents\Codex\2026-04-22-aici-avem-codex-superpowers-active\ContabilaAi\tests\test_importers.py`
- Modify: `C:\Users\stefan\Documents\Codex\2026-04-22-aici-avem-codex-superpowers-active\ContabilaAi\tests\test_http_smoke.py`

- [ ] **Step 1: Write failing invoice hub tests**

```python
def test_import_issued_invoice_records_workspace_and_role(tmp_path, invoice_fixture_path):
    store = LedgerStore(tmp_path / "ledger.db")
    workspace_id = store.create_workspace("MobExc")

    result = import_invoice_documents(
        store=store,
        workspace_id=workspace_id,
        role="issued",
        source_path=invoice_fixture_path,
    )

    invoices = store.list_workspace_invoices(workspace_id)
    assert result["invoice_count"] == 1
    assert invoices[0]["role"] == "issued"
```

- [ ] **Step 2: Run the focused importer tests**

Run: `pytest tests/test_importers.py -k workspace_and_role -v`

Expected: FAIL because invoices are not yet workspace-scoped in a unified hub.

- [ ] **Step 3: Add a unified invoices table**

```python
CREATE TABLE IF NOT EXISTS invoices (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    workspace_id INTEGER NOT NULL,
    import_batch_id INTEGER,
    role TEXT NOT NULL,
    issuer_name TEXT,
    counterparty_name TEXT,
    invoice_number TEXT,
    issued_at TEXT,
    due_at TEXT,
    currency TEXT,
    total_amount REAL,
    raw_payload_json TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(workspace_id) REFERENCES workspaces(id),
    FOREIGN KEY(import_batch_id) REFERENCES import_batches(id)
);
```

- [ ] **Step 4: Normalize invoice import entry points**

```python
def import_invoice_documents(store, workspace_id: int, role: str, source_path: str) -> dict[str, object]:
    invoices = parse_invoice_source(source_path)
    import_batch_id = store.create_import_batch(
        source_name=Path(source_path).name,
        workspace_id=workspace_id,
        source_type=f"{role}_invoice",
    )
    store.insert_invoices(workspace_id, import_batch_id, role, invoices)
    return {"invoice_count": len(invoices), "import_batch_id": import_batch_id}
```

- [ ] **Step 5: Add invoice listing endpoints**

```python
@app.get("/api/invoices")
def list_invoices_route():
    workspace_id = int(request.args["workspace_id"])
    return jsonify({"items": store.list_workspace_invoices(workspace_id)})
```

- [ ] **Step 6: Run tests**

Run: `pytest tests/test_importers.py tests/test_http_smoke.py -k invoices -v`

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add src/contabila_ai/storage/schema.py src/contabila_ai/storage/store.py src/contabila_ai/importing/importers.py src/contabila_ai/server/http.py tests/test_importers.py tests/test_http_smoke.py
git commit -m "feat: add workspace invoice hub"
```

---

### Task 7: Add Matching Engine Phase 1 and Reprocessing Hooks

**Files:**
- Create: `C:\Users\stefan\Documents\Codex\2026-04-22-aici-avem-codex-superpowers-active\ContabilaAi\src\contabila_ai\matching\models.py`
- Create: `C:\Users\stefan\Documents\Codex\2026-04-22-aici-avem-codex-superpowers-active\ContabilaAi\src\contabila_ai\matching\service.py`
- Modify: `C:\Users\stefan\Documents\Codex\2026-04-22-aici-avem-codex-superpowers-active\ContabilaAi\src\contabila_ai\storage\schema.py`
- Modify: `C:\Users\stefan\Documents\Codex\2026-04-22-aici-avem-codex-superpowers-active\ContabilaAi\src\contabila_ai\storage\store.py`
- Create: `C:\Users\stefan\Documents\Codex\2026-04-22-aici-avem-codex-superpowers-active\ContabilaAi\tests\test_matching.py`

- [ ] **Step 1: Write failing matching tests**

```python
def test_matching_service_matches_invoice_to_single_payment(tmp_path):
    store = seeded_store_with_invoice_and_payment(tmp_path)
    service = MatchingService(store)

    matches = service.match_workspace(workspace_id=1)

    assert len(matches) == 1
    assert matches[0]["match_kind"] == "one_to_one"
    assert matches[0]["status"] == "proposed"


def test_matching_service_marks_clear_partial_payment(tmp_path):
    store = seeded_store_with_partial_payment(tmp_path)
    service = MatchingService(store)

    matches = service.match_workspace(workspace_id=1)

    assert matches[0]["matched_amount"] == 500.0
    assert matches[0]["residual_amount"] == 250.0
```

- [ ] **Step 2: Run the matching tests**

Run: `pytest tests/test_matching.py -v`

Expected: FAIL because the matching service does not exist.

- [ ] **Step 3: Add the match storage table**

```python
CREATE TABLE IF NOT EXISTS invoice_matches (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    workspace_id INTEGER NOT NULL,
    transaction_id INTEGER NOT NULL,
    invoice_id INTEGER NOT NULL,
    match_kind TEXT NOT NULL,
    matched_amount REAL NOT NULL,
    residual_amount REAL NOT NULL DEFAULT 0,
    confidence REAL NOT NULL,
    reasoning TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'proposed',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(workspace_id) REFERENCES workspaces(id)
);
```

- [ ] **Step 4: Implement the minimal phase 1 matcher**

```python
def match_workspace(self, workspace_id: int) -> list[dict[str, object]]:
    transactions = self._store.list_unmatched_workspace_transactions(workspace_id)
    invoices = self._store.list_workspace_invoices(workspace_id)
    proposals = []
    for transaction in transactions:
        candidate = self._pick_best_invoice_candidate(transaction, invoices)
        if candidate is None:
            continue
        proposals.append(
            self._store.create_invoice_match(
                workspace_id=workspace_id,
                transaction_id=transaction["id"],
                invoice_id=candidate["invoice_id"],
                match_kind=candidate["match_kind"],
                matched_amount=candidate["matched_amount"],
                residual_amount=candidate["residual_amount"],
                confidence=candidate["confidence"],
                reasoning=candidate["reasoning"],
            )
        )
    return proposals
```

- [ ] **Step 5: Trigger reprocessing after invoice imports**

```python
matching_service.match_workspace(workspace_id)
change_review_service.refresh_for_workspace(workspace_id)
```

- [ ] **Step 6: Run focused tests**

Run: `pytest tests/test_matching.py tests/test_importers.py -k "match or partial" -v`

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add src/contabila_ai/matching/models.py src/contabila_ai/matching/service.py src/contabila_ai/storage/schema.py src/contabila_ai/storage/store.py tests/test_matching.py tests/test_importers.py
git commit -m "feat: add phase 1 invoice matching"
```

---

### Task 8: Add Change Review for Reprocessing Side Effects

**Files:**
- Create: `C:\Users\stefan\Documents\Codex\2026-04-22-aici-avem-codex-superpowers-active\ContabilaAi\src\contabila_ai\change_review\service.py`
- Modify: `C:\Users\stefan\Documents\Codex\2026-04-22-aici-avem-codex-superpowers-active\ContabilaAi\src\contabila_ai\storage\schema.py`
- Modify: `C:\Users\stefan\Documents\Codex\2026-04-22-aici-avem-codex-superpowers-active\ContabilaAi\src\contabila_ai\storage\store.py`
- Modify: `C:\Users\stefan\Documents\Codex\2026-04-22-aici-avem-codex-superpowers-active\ContabilaAi\src\contabila_ai\server\http.py`
- Create: `C:\Users\stefan\Documents\Codex\2026-04-22-aici-avem-codex-superpowers-active\ContabilaAi\tests\test_change_review.py`

- [ ] **Step 1: Write failing change-review tests**

```python
def test_change_review_records_category_change_proposal(tmp_path):
    store = seeded_store_with_existing_category_and_new_invoice(tmp_path)
    service = ChangeReviewService(store)

    proposals = service.refresh_for_workspace(workspace_id=1)

    assert proposals[0]["field_name"] == "analysis_category"
    assert proposals[0]["old_value"] == "fara categorie"
    assert proposals[0]["new_value"] == "casa"
    assert proposals[0]["status"] == "pending"
```

- [ ] **Step 2: Run the new tests**

Run: `pytest tests/test_change_review.py -v`

Expected: FAIL because change review does not exist.

- [ ] **Step 3: Add change proposal storage**

```python
CREATE TABLE IF NOT EXISTS change_review_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    workspace_id INTEGER NOT NULL,
    transaction_id INTEGER,
    field_name TEXT NOT NULL,
    old_value TEXT,
    new_value TEXT,
    reason TEXT NOT NULL,
    confidence REAL NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(workspace_id) REFERENCES workspaces(id)
);
```

- [ ] **Step 4: Implement proposal refresh and decision routes**

```python
@app.get("/api/change-review")
def list_change_review_route():
    workspace_id = int(request.args["workspace_id"])
    return jsonify({"items": store.list_change_review_items(workspace_id)})


@app.post("/api/change-review/decision")
def change_review_decision_route():
    payload = request.get_json(force=True) or {}
    return jsonify(change_review_service.apply_decision(
        item_id=int(payload["item_id"]),
        decision=str(payload["decision"]),
    ))
```

- [ ] **Step 5: Apply accepted changes deterministically**

```python
def apply_decision(self, item_id: int, decision: str) -> dict[str, object]:
    item = self._store.get_change_review_item(item_id)
    if decision == "accept" and item["field_name"] == "analysis_category":
        self._store.set_transaction_category(item["transaction_id"], item["new_value"])
    self._store.set_change_review_status(item_id, decision)
    return {"ok": True, "decision": decision}
```

- [ ] **Step 6: Run focused tests**

Run: `pytest tests/test_change_review.py tests/test_http_smoke.py -k change_review -v`

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add src/contabila_ai/change_review/service.py src/contabila_ai/storage/schema.py src/contabila_ai/storage/store.py src/contabila_ai/server/http.py tests/test_change_review.py tests/test_http_smoke.py
git commit -m "feat: add change review workflow"
```

---

### Task 9: Upgrade the Planner with Workspace Context, Projects, and Blocking

**Files:**
- Modify: `C:\Users\stefan\Documents\Codex\2026-04-22-aici-avem-codex-superpowers-active\ContabilaAi\src\contabila_ai\planning\models.py`
- Modify: `C:\Users\stefan\Documents\Codex\2026-04-22-aici-avem-codex-superpowers-active\ContabilaAi\src\contabila_ai\planning\planner.py`
- Modify: `C:\Users\stefan\Documents\Codex\2026-04-22-aici-avem-codex-superpowers-active\ContabilaAi\src\contabila_ai\storage\store.py`
- Modify: `C:\Users\stefan\Documents\Codex\2026-04-22-aici-avem-codex-superpowers-active\ContabilaAi\tests\test_planner.py`
- Modify: `C:\Users\stefan\Documents\Codex\2026-04-22-aici-avem-codex-superpowers-active\ContabilaAi\tests\test_http_smoke.py`

- [ ] **Step 1: Write failing planner tests for project and relationship filters**

```python
def test_build_query_plan_extracts_project_name():
    plan = build_query_plan("cat am platit pe proiectul Casa Noua")
    assert plan.project_name == "Casa Noua"


def test_build_query_plan_clarifies_ambiguous_entity_status():
    plan = build_query_plan("care e relatia cu Ai Excellence")
    assert plan.support_level == "clarify"


def test_ask_route_blocks_when_workspace_not_ready(client, seeded_workspace):
    response = client.post("/api/ask", json={"workspace_id": seeded_workspace, "question": "cat am platit catre ai excellence"})
    assert response.get_json()["support_level"] == "blocked"
```

- [ ] **Step 2: Run the planner tests**

Run: `pytest tests/test_planner.py tests/test_http_smoke.py -k "project_name or blocked_when_workspace_not_ready" -v`

Expected: FAIL because project extraction and readiness-aware execution do not exist.

- [ ] **Step 3: Extend the plan model**

```python
@dataclass(slots=True)
class QueryPlan:
    question: str
    metric: str
    direction: str | None = None
    entity_name: str | None = None
    project_name: str | None = None
    category_name: str | None = None
    workspace_id: int | None = None
    support_level: str = "exact"
```

- [ ] **Step 4: Add project and category detection**

```python
project_match = re.search(r"proiectul\s+(.+)$", question, re.IGNORECASE)
if project_match:
    project_name = project_match.group(1).strip(" ?.")
```

- [ ] **Step 5: Thread workspace-aware filters through execution**

```python
if plan.project_name:
    where_clauses.append("COALESCE(t.project_name, '') = ?")
    params.append(plan.project_name)
if plan.workspace_id:
    where_clauses.append("ib.workspace_id = ?")
    params.append(plan.workspace_id)
```

- [ ] **Step 6: Run focused tests**

Run: `pytest tests/test_planner.py tests/test_http_smoke.py -k "project_name or relationship or blocked" -v`

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add src/contabila_ai/planning/models.py src/contabila_ai/planning/planner.py src/contabila_ai/storage/store.py tests/test_planner.py tests/test_http_smoke.py
git commit -m "feat: upgrade planner for workspace-aware queries"
```

---

### Task 10: Build the Onboarding Wizard and Workspace Tabs

**Files:**
- Modify: `C:\Users\stefan\Documents\Codex\2026-04-22-aici-avem-codex-superpowers-active\ContabilaAi\web\index.html`
- Modify: `C:\Users\stefan\Documents\Codex\2026-04-22-aici-avem-codex-superpowers-active\ContabilaAi\web\app.js`
- Modify: `C:\Users\stefan\Documents\Codex\2026-04-22-aici-avem-codex-superpowers-active\ContabilaAi\web\styles.css`
- Modify: `C:\Users\stefan\Documents\Codex\2026-04-22-aici-avem-codex-superpowers-active\ContabilaAi\tests\test_http_smoke.py`

- [ ] **Step 1: Write a smoke test that confirms the new shell renders**

```python
def test_index_contains_workspace_and_onboarding_sections(client):
    response = client.get("/")
    body = response.data.decode("utf-8")
    assert "workspace-home" in body
    assert "onboarding-wizard" in body
    assert "business-memory-panel" in body
```

- [ ] **Step 2: Run the smoke test**

Run: `pytest tests/test_http_smoke.py::test_index_contains_workspace_and_onboarding_sections -v`

Expected: FAIL because the new sections do not exist yet.

- [ ] **Step 3: Add the shell sections**

```html
<main>
  <section id="workspace-home"></section>
  <section id="onboarding-wizard" hidden></section>
  <section id="workspace-app" hidden>
    <nav class="workspace-tabs">
      <button data-tab="questions">Intrebari</button>
      <button data-tab="transactions">Tranzactii</button>
      <button data-tab="categories">Categorii</button>
      <button data-tab="invoices">Facturi</button>
      <button data-tab="memory">Business Memory</button>
      <button data-tab="review">Review</button>
    </nav>
  </section>
</main>
```

- [ ] **Step 4: Add client-side view-state management**

```javascript
function setWorkspaceView(mode) {
  document.getElementById("workspace-home").hidden = mode !== "home";
  document.getElementById("onboarding-wizard").hidden = mode !== "onboarding";
  document.getElementById("workspace-app").hidden = mode !== "app";
}
```

- [ ] **Step 5: Route ready vs needs-review workspaces**

```javascript
function openWorkspace(workspace) {
  currentWorkspaceId = workspace.id;
  if (workspace.status === "ready") {
    setWorkspaceView("app");
    loadWorkspaceApp();
    return;
  }
  setWorkspaceView("onboarding");
  loadOnboardingWorkspace();
}
```

- [ ] **Step 6: Run the smoke test**

Run: `pytest tests/test_http_smoke.py::test_index_contains_workspace_and_onboarding_sections -v`

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add web/index.html web/app.js web/styles.css tests/test_http_smoke.py
git commit -m "feat: add onboarding wizard shell"
```

---

### Task 11: Integrate End-to-End Workspace Flow and Run Full Regression

**Files:**
- Modify: `C:\Users\stefan\Documents\Codex\2026-04-22-aici-avem-codex-superpowers-active\ContabilaAi\tests\test_http_smoke.py`
- Modify: `C:\Users\stefan\Documents\Codex\2026-04-22-aici-avem-codex-superpowers-active\ContabilaAi\README.md`
- Modify: `C:\Users\stefan\Documents\Codex\2026-04-22-aici-avem-codex-superpowers-active\ContabilaAi\docs\PRODUCT_DOCUMENTATION.md`

- [ ] **Step 1: Write a full happy-path smoke test**

```python
def test_workspace_can_progress_from_import_to_ready(client, sample_statement_path):
    create_payload = client.post("/api/workspaces", json={"name": "MobExc"}).get_json()
    workspace_id = create_payload["workspace_id"]

    client.post("/api/import", json={"workspace_id": workspace_id, "file_path": sample_statement_path})
    client.post("/api/business-memory", json={"workspace_id": workspace_id, "text": "Ai Excellence e partener"})
    readiness = client.get(f"/api/workspaces").get_json()["items"][0]["status"]

    assert readiness in {"needs_review", "ready"}
```

- [ ] **Step 2: Run the smoke test to confirm any integration gaps**

Run: `pytest tests/test_http_smoke.py::test_workspace_can_progress_from_import_to_ready -v`

Expected: Initially FAIL if any route still assumes global singleton state.

- [ ] **Step 3: Remove remaining global-state assumptions**

```python
workspace_id = int(payload["workspace_id"])
summary = store.workspace_summary(workspace_id)
review_groups = review_service.list_review_groups(workspace_id=workspace_id)
```

- [ ] **Step 4: Update the product docs to reflect shipped checkpoint behavior**

```markdown
## Current Workspace Architecture

- company-scoped workspaces are now implemented
- onboarding and review gate are active
- invoice matching phase 1 is available
```

- [ ] **Step 5: Run the full suite**

Run: `pytest -v`

Expected: PASS for all tests.

- [ ] **Step 6: Commit**

```bash
git add tests/test_http_smoke.py README.md docs/PRODUCT_DOCUMENTATION.md
git commit -m "docs: align product docs with workspace architecture"
```

---

## Checkpoint Map

- **Checkpoint A:** Tasks 1-2
  - named workspaces exist and can be created/opened
- **Checkpoint B:** Tasks 3-5
  - review severity, readiness gate, and business memory influence interpretation
- **Checkpoint C:** Tasks 6-8
  - invoice hub, phase 1 matching, and change review work end-to-end
- **Checkpoint D:** Tasks 9-10
  - planner and UI onboarding flow are aligned with workspace readiness
- **Checkpoint E:** Task 11
  - integrated regression pass and docs refresh

## Phase 2 Must-Do After This Plan

- add installment matching where one invoice is paid in multiple tranches
- add many-to-many invoice-payment allocation only after phase 1 is stable
- strengthen project-aware category and planner analytics
- improve business memory parsing beyond the deterministic starter parser

## Self-Review

- Spec coverage check: workspace model, onboarding, severity gate, business memory, invoice hub, reprocessing, change review, planner upgrade, and post-onboarding tabs are all mapped to concrete tasks above.
- Placeholder scan: no `TODO`, `TBD`, or “similar to task N” shortcuts remain in the plan.
- Type consistency check: `workspace_id`, `project_name`, `fact_type`, `fact_value`, `support_level`, `status`, and `residual_amount` naming is consistent across storage, planner, matching, and tests.
