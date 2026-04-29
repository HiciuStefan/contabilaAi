const workspaceCreateForm = document.getElementById("workspace-create-form");
const workspaceNameInput = document.getElementById("workspace-name");
const workspaceList = document.getElementById("workspace-list");
const workspaceCurrent = document.getElementById("workspace-current");
const workspaceHome = document.getElementById("workspace-home");
const onboardingWizard = document.getElementById("onboarding-wizard");
const onboardingStatus = document.getElementById("onboarding-status");
const workspaceApp = document.getElementById("workspace-app");
const onboardingChecklist = document.getElementById("onboarding-checklist");
const uploadPathInput = document.getElementById("upload-path");
const uploadFileInput = document.getElementById("upload-file");
const uploadButton = document.getElementById("upload-button");
const uploadConfirmButton = document.getElementById("upload-confirm-button");
const uploadCancelButton = document.getElementById("upload-cancel-button");
const importDialog = document.getElementById("import-dialog");
const resetButton = document.getElementById("reset-button");
const uploadResult = document.getElementById("upload-result");
const invoiceRoleSelect = document.getElementById("invoice-role");
const invoicePathInput = document.getElementById("invoice-path");
const invoiceUploadButton = document.getElementById("invoice-upload-button");
const invoiceUploadResult = document.getElementById("invoice-upload-result");
const importSelect = document.getElementById("import-select");
const importMeta = document.getElementById("import-meta");
const questionInput = document.getElementById("question-input");
const questionButton = document.getElementById("question-button");
const answerBox = document.getElementById("answer");
const chatRows = document.getElementById("chat-rows");
const summaryBox = document.getElementById("summary");
const reviewList = document.getElementById("review-list");
const refreshReviewButton = document.getElementById("refresh-review");
const categoriesRefreshButton = document.getElementById("categories-refresh");
const categoriesList = document.getElementById("categories-list");
const transactionsRefreshButton = document.getElementById("transactions-refresh");
const transactionsList = document.getElementById("transactions-list");
const txMinAmountInput = document.getElementById("tx-min-amount");
const txDirectionSelect = document.getElementById("tx-direction");
const txSearchInput = document.getElementById("tx-search");
const invoicesRefreshButton = document.getElementById("invoices-refresh");
const invoicesSummary = document.getElementById("invoices-summary");
const invoicesList = document.getElementById("invoices-list");
const matchesList = document.getElementById("matches-list");
const businessMemoryForm = document.getElementById("business-memory-form");
const businessMemoryInput = document.getElementById("business-memory-input");
const businessMemorySubmit = document.getElementById("business-memory-submit");
const businessMemoryResult = document.getElementById("business-memory-result");
const businessMemoryRefreshButton = document.getElementById("business-memory-refresh");
const businessMemoryFacts = document.getElementById("business-memory-facts");
const changeReviewRefreshButton = document.getElementById("change-review-refresh");
const changeReviewList = document.getElementById("change-review-list");
const workspaceTabs = Array.from(document.querySelectorAll(".workspace-tab"));
const tabPanels = Array.from(document.querySelectorAll("[data-tab-panel]"));

let activeImportId = null;
let currentWorkspaceId = null;
let currentWorkspace = null;
let currentWorkspaceName = null;
let currentTab = "questions";
let knownCategories = [];
let knownImports = [];

function importHasTransactions(item) {
  return Number(item?.transaction_count || 0) > 0;
}

function preferredTransactionImportId(imports, selectedImportId = activeImportId) {
  if (!imports.length) {
    return null;
  }
  const selected = imports.find((item) => Number(item.id) === Number(selectedImportId));
  if (selected && importHasTransactions(selected)) {
    return Number(selected.id);
  }
  const latestWithTransactions = imports.find((item) => importHasTransactions(item));
  return latestWithTransactions ? Number(latestWithTransactions.id) : null;
}

function currentTransactionImportId() {
  return preferredTransactionImportId(knownImports, activeImportId);
}

function importLabel(item) {
  const parts = [
    item.source_file || `Import #${item.id}`,
    `${Number(item.transaction_count || 0)} tranzactii`,
  ];
  if (!importHasTransactions(item)) {
    parts.push("facturi/matching");
  }
  return parts.join(" | ");
}

function setWorkspaceView(mode) {
  workspaceHome.hidden = mode !== "home";
  onboardingWizard.hidden = mode !== "guided";
  workspaceApp.hidden = mode === "home";
}

function setActiveTab(tabName) {
  currentTab = tabName;
  workspaceTabs.forEach((button) => {
    button.classList.toggle("is-active", button.dataset.tab === tabName);
  });
  tabPanels.forEach((panel) => {
    panel.hidden = panel.dataset.tabPanel !== tabName;
  });
}

function syncWorkspaceView(workspace) {
  if (!workspace) {
    setWorkspaceView("home");
    return;
  }
  if (workspace.status === "ready") {
    onboardingStatus.textContent = `Firma ${workspace.name} este pregatita. Poti lucra direct in workspace si poti pune intrebari.`;
    setWorkspaceView("app");
    return;
  }
  onboardingStatus.textContent = `Firma ${workspace.name} este in starea ${workspace.status}. Continua cu importul, instructiunile de business si review-ul important inainte de intrebari serioase.`;
  setWorkspaceView("guided");
}

async function requestJson(url, options = {}) {
  const response = await fetch(url, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  const payload = await response.json();
  if (!response.ok) {
    throw new Error(payload.error || "Cererea a esuat.");
  }
  return payload;
}

async function requestFileUpload(file, workspaceId = currentWorkspaceId) {
  const formData = new FormData();
  formData.append("file", file);
  const query = workspaceId === null || workspaceId === undefined
    ? ""
    : `?workspace_id=${encodeURIComponent(workspaceId)}`;
  const response = await fetch(`/api/upload-file${query}`, {
    method: "POST",
    body: formData,
  });
  const payload = await response.json();
  if (!response.ok) {
    throw new Error(payload.error || "Upload-ul a esuat.");
  }
  return payload;
}

function setEmptySessionState(message) {
  importMeta.textContent = message;
  summaryBox.textContent = "Niciun import activ.";
  reviewList.innerHTML = `<p class="muted">${escapeHtml(message)}</p>`;
  categoriesList.innerHTML = `<p class="muted">${escapeHtml(message)}</p>`;
  transactionsList.innerHTML = `<p class="muted">${escapeHtml(message)}</p>`;
  invoicesList.innerHTML = `<p class="muted">${escapeHtml(message)}</p>`;
  matchesList.innerHTML = `<p class="muted">${escapeHtml(message)}</p>`;
  changeReviewList.innerHTML = `<p class="muted">${escapeHtml(message)}</p>`;
  answerBox.textContent = "Raspunsul apare aici.";
  chatRows.innerHTML = '<p class="muted">Selecteaza sau importa un extras pentru a porni sesiunea.</p>';
}

function currentReviewCounts() {
  return currentWorkspace && currentWorkspace.review_counts
    ? currentWorkspace.review_counts
    : { critical: 0, high: 0, medium: 0, low: 0 };
}

function updateOnboardingChecklist(extra = {}) {
  if (!currentWorkspace) {
    return;
  }
  const importCount = Number(currentWorkspace.import_count || 0);
  const factCount = Number(extra.factCount || 0);
  const changeCount = Number(extra.changeReviewCount || 0);
  const invoiceCount = Number(extra.invoiceCount || 0);
  const reviewCounts = currentReviewCounts();

  document.querySelector('[data-step-status="imports"]').textContent = importCount
    ? `${importCount} importuri active. ${invoiceCount} facturi inregistrate.`
    : "Fara importuri inca.";
  document.querySelector('[data-step-status="memory"]').textContent = factCount
    ? `${factCount} fapte de business salvate.`
    : "Nicio instructiune salvata inca.";
  document.querySelector('[data-step-status="review"]').textContent = `Critical ${reviewCounts.critical || 0}, high ${reviewCounts.high || 0}, medium ${reviewCounts.medium || 0}, low ${reviewCounts.low || 0}.`;
  document.querySelector('[data-step-status="change-review"]').textContent = changeCount
    ? `${changeCount} schimbari propuse asteapta o decizie.`
    : "Nicio schimbare propusa.";

  onboardingChecklist.classList.toggle(
    "is-ready",
    currentWorkspace.status === "ready" || ((reviewCounts.critical || 0) === 0 && (reviewCounts.high || 0) === 0 && importCount > 0)
  );
}

function renderWorkspaceList(items) {
  if (!items.length) {
    workspaceList.innerHTML = '<p class="muted">Nu exista inca firme salvate. Creeaza prima firma mai sus.</p>';
    workspaceCurrent.textContent = "Nicio firma selectata inca.";
    currentWorkspace = null;
    currentWorkspaceName = null;
    syncWorkspaceView(null);
    return;
  }

  workspaceList.innerHTML = items.map((item) => `
    <button
      type="button"
      class="workspace-chip${Number(item.id) === currentWorkspaceId ? " is-active" : ""}"
      data-workspace-id="${item.id}"
      data-workspace-name="${escapeHtml(item.name)}"
    >
      <strong>${escapeHtml(item.name)}</strong>
      <span>${escapeHtml(item.status)}</span>
      <span>${escapeHtml(String(item.import_count || 0))} importuri</span>
    </button>
  `).join("");

  const active = items.find((item) => Number(item.id) === currentWorkspaceId) || items[0];
  currentWorkspaceId = Number(active.id);
  currentWorkspaceName = active.name;
  currentWorkspace = active;
  workspaceCurrent.textContent = `Firma activa: ${active.name} (${active.status})`;
  syncWorkspaceView(active);
}

async function loadWorkspaces(preferredWorkspaceId = currentWorkspaceId) {
  const payload = await requestJson("/api/workspaces");
  const items = payload.items || [];
  if (preferredWorkspaceId !== null && preferredWorkspaceId !== undefined) {
    currentWorkspaceId = Number(preferredWorkspaceId);
  } else if (items.length) {
    currentWorkspaceId = Number(items[0].id);
  } else {
    currentWorkspaceId = null;
  }
  renderWorkspaceList(items);
  return items;
}

async function loadImports(selectedImportId = activeImportId) {
  if (currentWorkspaceId === null) {
    knownImports = [];
    importSelect.innerHTML = '<option value="">Niciun import selectat</option>';
    setEmptySessionState("Creeaza sau alege mai intai o firma.");
    return [];
  }
  const payload = await requestJson(`/api/imports?workspace_id=${encodeURIComponent(currentWorkspaceId)}`);
  const imports = payload.imports || [];
  knownImports = imports;

  importSelect.innerHTML = [
    '<option value="">Niciun import selectat</option>',
    ...imports.map((item) => `<option value="${item.id}">${escapeHtml(importLabel(item))} (#${item.id})</option>`),
  ].join("");

  if (selectedImportId === null || selectedImportId === undefined || selectedImportId === "") {
    activeImportId = preferredTransactionImportId(imports) ?? (imports.length ? Number(imports[0].id) : null);
  } else {
    activeImportId = Number(selectedImportId);
  }

  if (activeImportId === null && imports.length) {
    activeImportId = Number(imports[0].id);
  }

  importSelect.value = activeImportId === null ? "" : String(activeImportId);

  if (activeImportId === null) {
    importMeta.textContent = imports.length
      ? "Exista importuri salvate, dar niciunul nu este activ. Selecteaza unul sau importa un extras nou."
      : "Nu exista inca importuri salvate. Importa un extras nou pentru a crea o sesiune.";
    return imports;
  }

  const activeImport = imports.find((item) => Number(item.id) === activeImportId);
  const transactionImportId = currentTransactionImportId();
  const transactionImport = imports.find((item) => Number(item.id) === Number(transactionImportId));
  if (!activeImport) {
    activeImportId = null;
    importSelect.value = "";
    importMeta.textContent = "Importul selectat nu mai exista. Alege altul sau importa din nou.";
    return imports;
  }

  if (transactionImport && Number(transactionImport.id) !== Number(activeImport.id)) {
    importMeta.textContent = `${activeImport.source_file} este selectat pentru facturi/matching. Intrebarile si tranzactiile folosesc ${transactionImport.source_file}.`;
  } else {
    importMeta.textContent = `${activeImport.source_file} | ${activeImport.transaction_count} tranzactii | ${activeImport.created_at}`;
  }
  return imports;
}

async function loadCategories() {
  const payload = await requestJson("/api/categories");
  knownCategories = payload.categories || [];
  return knownCategories;
}

async function loadSummary() {
  if (currentWorkspaceId === null) {
    summaryBox.textContent = "Nicio firma activa.";
    return;
  }
  const transactionImportId = currentTransactionImportId();
  const params = new URLSearchParams();
  params.set("workspace_id", String(currentWorkspaceId));
  if (transactionImportId !== null) {
    params.set("import_id", String(transactionImportId));
  }
  const payload = await requestJson(`/api/summary?${params.toString()}`);
  summaryBox.textContent = JSON.stringify(payload, null, 2);
}

async function loadReview() {
  if (currentWorkspaceId === null) {
    reviewList.innerHTML = '<p class="muted">Selecteaza o firma pentru review.</p>';
    return;
  }
  const transactionImportId = currentTransactionImportId();
  const params = new URLSearchParams();
  params.set("workspace_id", String(currentWorkspaceId));
  if (transactionImportId !== null) {
    params.set("import_id", String(transactionImportId));
  }
  const payload = await requestJson(`/api/review?${params.toString()}`);
  await loadCategories();
  renderReviewGroups(payload.groups || []);
}

async function loadCategoryCatalog() {
  const categories = await loadCategories();
  if (!categories.length) {
    categoriesList.innerHTML = '<p class="muted">Nu exista inca nicio categorie salvata.</p>';
    return;
  }
  const transactionImportId = currentTransactionImportId();
  const categoryRows = await Promise.all(
    categories.map(async (category) => {
      const params = new URLSearchParams();
      params.set("category_name", category.name);
      params.set("limit", "25");
      if (currentWorkspaceId !== null) {
        params.set("workspace_id", String(currentWorkspaceId));
      }
      if (transactionImportId !== null) {
        params.set("import_id", String(transactionImportId));
      }
      const payload = await requestJson(`/api/category-transactions?${params.toString()}`);
      return {
        ...category,
        rows: payload.rows || [],
      };
    }),
  );
  renderCategoryCatalog(categoryRows);
}

async function loadTransactions() {
  if (currentWorkspaceId === null) {
    transactionsList.innerHTML = '<p class="muted">Selecteaza o firma pentru registrul de tranzactii.</p>';
    return;
  }
  const transactionImportId = currentTransactionImportId();
  const params = new URLSearchParams();
  params.set("workspace_id", String(currentWorkspaceId));
  if (transactionImportId !== null) {
    params.set("import_id", String(transactionImportId));
  }
  params.set("limit", "100");
  if (txMinAmountInput.value.trim()) {
    params.set("min_abs_amount", txMinAmountInput.value.trim());
  }
  if (txDirectionSelect.value) {
    params.set("direction", txDirectionSelect.value);
  }
  if (txSearchInput.value.trim()) {
    params.set("search", txSearchInput.value.trim());
  }
  const payload = await requestJson(`/api/transactions?${params.toString()}`);
  renderTransactions(payload.rows || []);
}

async function loadBusinessMemory() {
  if (currentWorkspaceId === null) {
    businessMemoryFacts.innerHTML = '<p class="muted">Selecteaza o firma pentru business memory.</p>';
    return 0;
  }
  const payload = await requestJson(`/api/business-memory?workspace_id=${encodeURIComponent(currentWorkspaceId)}`);
  renderBusinessMemoryFacts(payload.facts || []);
  return (payload.facts || []).length;
}

async function loadInvoices() {
  if (currentWorkspaceId === null) {
    invoicesSummary.textContent = "Selecteaza o firma pentru facturi.";
    invoicesList.innerHTML = '<p class="muted">Selecteaza o firma pentru facturi.</p>';
    return 0;
  }
  const [issued, received] = await Promise.all([
    requestJson(`/api/invoices?workspace_id=${encodeURIComponent(currentWorkspaceId)}&role=issued`),
    requestJson(`/api/invoices?workspace_id=${encodeURIComponent(currentWorkspaceId)}&role=received`),
  ]);
  const items = [
    ...(issued.items || []).map((item) => ({ ...item, role_label: "emise" })),
    ...(received.items || []).map((item) => ({ ...item, role_label: "primite" })),
  ];
  renderInvoices(items);
  invoicesSummary.textContent = items.length
    ? `${issued.items.length} facturi emise, ${received.items.length} facturi primite in firma curenta.`
    : "Nu exista inca facturi in firma curenta.";
  return items.length;
}

async function loadInvoiceMatches() {
  if (currentWorkspaceId === null) {
    matchesList.innerHTML = '<p class="muted">Selecteaza o firma pentru matching.</p>';
    return;
  }
  try {
    const payload = await requestJson(`/api/invoice-matches?workspace_id=${encodeURIComponent(currentWorkspaceId)}`);
    renderInvoiceMatches(payload.items || []);
  } catch (error) {
    matchesList.innerHTML = `<p class="muted">${escapeHtml(error.message)}</p>`;
  }
}

async function loadChangeReview() {
  if (currentWorkspaceId === null) {
    changeReviewList.innerHTML = '<p class="muted">Selecteaza o firma pentru change review.</p>';
    return 0;
  }
  const payload = await requestJson(`/api/change-review?workspace_id=${encodeURIComponent(currentWorkspaceId)}`);
  renderChangeReviewItems(payload.items || []);
  return (payload.items || []).length;
}

async function refreshWorkspaceData() {
  await loadWorkspaces(currentWorkspaceId);
  await loadImports(activeImportId);
  if (currentWorkspaceId === null) {
    setEmptySessionState("Creeaza sau alege mai intai o firma.");
    return;
  }
  await loadSummary();
  await loadReview();
  await loadCategoryCatalog();
  await loadTransactions();
  const [factCount, invoiceCount, changeReviewCount] = await Promise.all([
    loadBusinessMemory(),
    loadInvoices(),
    loadChangeReview(),
  ]);
  await loadInvoiceMatches();
  updateOnboardingChecklist({ factCount, invoiceCount, changeReviewCount });
}

function renderChatRows(rows) {
  if (!rows || !rows.length) {
    chatRows.innerHTML = '<p class="muted">Nu exista tranzactii de afisat pentru intrebarea curenta.</p>';
    return;
  }

  const items = rows.map((row) => {
    const amount = row.metric_value !== undefined ? row.metric_value : row.amount;
    const currency = row.currency || "RON";
    const title = row.description || row.group_key || "Rezultat";
    const details = [
      row.transaction_date,
      row.merchant,
      row.economic_kind,
      row.direction,
      row.transaction_count !== undefined ? `${row.transaction_count} tranzactii` : null,
    ].filter(Boolean);

    return `
      <article class="chat-result-item">
        <div class="chat-result-topline">
          <strong>${escapeHtml(String(title))}</strong>
          <span>${escapeHtml(String(amount))}${row.amount !== undefined ? ` ${escapeHtml(currency)}` : ""}</span>
        </div>
        <div class="chat-result-meta">${details.map((item) => `<span>${escapeHtml(String(item))}</span>`).join("")}</div>
      </article>
    `;
  }).join("");

  chatRows.innerHTML = `
    <details class="chat-results-panel">
      <summary>Vezi tranzactiile (${rows.length})</summary>
      <div class="chat-result-list">${items}</div>
    </details>
  `;
}

function renderReviewGroups(groups) {
  if (!groups.length) {
    reviewList.innerHTML = '<p class="muted">Nu exista candidati de review pentru importul activ.</p>';
    return;
  }

  const bulkOptions = [
    '<option value="">Alege categoria pentru selectate</option>',
    ...knownCategories.map((category) => `<option value="${escapeHtml(category.name)}">${escapeHtml(category.name)}</option>`),
    '<option value="__new__">Creeaza categorie noua...</option>',
  ].join("");

  const groupHtml = groups.map((group) => {
    const categories = group.analysis_categories && group.analysis_categories.length
      ? `<p class="muted">Categorii: ${escapeHtml(group.analysis_categories.join(", "))}</p>`
      : '<p class="muted">Categorii: niciuna</p>';
    const samples = (group.samples || []).map((sample) => `
      <li>
        <strong>${escapeHtml(String(sample.amount))} ${escapeHtml(sample.currency || "RON")}</strong>
        <span>${escapeHtml(sample.transaction_date)} | ${escapeHtml(sample.description)}</span>
      </li>
    `).join("");

    return `
      <article class="review-item review-group">
        <div class="review-main">
          <div class="review-topline">
            <label class="review-select-label">
              <input type="checkbox" class="review-group-checkbox" data-ids="${escapeHtml((group.transaction_ids || []).join(","))}">
              <strong>${escapeHtml(group.group_label || "Tranzactii similare")}</strong>
            </label>
            <span>${escapeHtml(String(group.transaction_count))} tranzactii</span>
          </div>
          <div class="review-meta">
            <span>confidence minim ${escapeHtml(String(group.min_confidence))}</span>
            <span>total ${escapeHtml(String(group.total_amount))} RON</span>
          </div>
          ${categories}
          <ul class="review-samples">${samples}</ul>
        </div>
        <div class="review-actions">
          ${categoryControlHtml("category-group", group)}
          <button type="button" data-action="category-group" data-group-key="${escapeHtml(group.group_key)}" data-ids="${escapeHtml((group.transaction_ids || []).join(","))}">Aplica categoria</button>
        </div>
      </article>
    `;
  }).join("");

  reviewList.innerHTML = `
    <div class="bulk-review-actions">
      <div>
        <strong>Actiune pe selectie</strong>
        <p class="muted">Bifeaza mai multe grupuri si aplica aceeasi categorie o singura data.</p>
      </div>
      <div class="bulk-review-controls">
        <select id="bulk-category-select" class="category-select">${bulkOptions}</select>
        <input id="bulk-category-new" class="category-new-input" type="text" placeholder="Nume categorie noua" hidden>
        <button type="button" data-action="category-bulk">Aplica pe selectate</button>
      </div>
    </div>
    ${groupHtml}
  `;
}

function categoryControlHtml(prefix, group) {
  const suggested = group.suggested_category || "";
  const options = [
    '<option value="">Alege categoria</option>',
    ...knownCategories.map((category) => {
      const selected = category.name === suggested ? " selected" : "";
      return `<option value="${escapeHtml(category.name)}"${selected}>${escapeHtml(category.name)}</option>`;
    }),
    '<option value="__new__">Creeaza categorie noua...</option>',
  ].join("");
  const hint = suggested ? `<p class="muted">Sugestie: ${escapeHtml(suggested)}</p>` : "";
  return `
    <select id="${prefix}-select-${escapeHtml(group.group_key)}" class="category-select">${options}</select>
    <input id="${prefix}-new-${escapeHtml(group.group_key)}" class="category-new-input" type="text" placeholder="Nume categorie noua" hidden>
    ${hint}
  `;
}

function renderCategoryCatalog(categories) {
  const visibleCategories = categories.filter((category) => (category.rows || []).length > 0);
  if (!visibleCategories.length) {
    categoriesList.innerHTML = '<p class="muted">Nu exista categorii cu tranzactii in extrasul bancar activ. Selecteaza un extras sau reclasifica din review.</p>';
    return;
  }

  categoriesList.innerHTML = visibleCategories.map((category) => {
    const rows = category.rows || [];
    const rowHtml = rows.map((row) => {
      const selectId = `category-move-${row.id}`;
      const options = [
        '<option value="">Muta in...</option>',
        ...knownCategories
          .filter((item) => item.name !== category.name)
          .map((item) => `<option value="${escapeHtml(item.name)}">${escapeHtml(item.name)}</option>`),
        '<option value="__new__">Categorie noua...</option>',
      ].join("");
      return `
        <tr>
          <td>${escapeHtml(row.transaction_date || "-")}</td>
          <td>${escapeHtml(row.merchant || "Fara partener")}</td>
          <td title="${escapeHtml(row.description || "")}">${escapeHtml(transactionDetails(row.description || "").short)}</td>
          <td class="amount-cell">${escapeHtml(formatAmount(row.amount, row.currency || "RON"))}</td>
          <td>
            <select id="${selectId}" class="category-select category-inline-select">${options}</select>
            <input id="${selectId}-new" class="category-new-input" type="text" placeholder="Nume categorie" hidden>
            <button type="button" data-action="move-category-transaction" data-id="${row.id}" data-current-category="${escapeHtml(category.name)}">Muta</button>
          </td>
        </tr>
      `;
    }).join("");

    return `
      <details class="review-item category-card">
        <summary class="category-summary">
          <strong>${escapeHtml(category.name)}</strong>
          <span>${escapeHtml(prettyOperationalScope(category.operational_scope))}</span>
          <span>${escapeHtml(String(rows.length))} tranzactii in extrasul activ</span>
        </summary>
        <div class="category-editor">
          <label class="field">
            <span>Explicatie categorie</span>
            <input id="category-description-${escapeHtml(category.id)}" type="text" value="${escapeHtml(category.description || "")}" placeholder="Ex: cheltuieli legate de casa, non-operationale">
          </label>
          <label class="field">
            <span>Tip categorie</span>
            <select id="category-scope-${escapeHtml(category.id)}">${renderOperationalScopeOptions(category.operational_scope)}</select>
          </label>
          <button type="button" data-action="save-category-meta" data-category-name="${escapeHtml(category.name)}" data-category-id="${escapeHtml(category.id)}">Salveaza categoria</button>
        </div>
        <p class="muted">Total iesiri: ${escapeHtml(String(category.total_expenses || 0))} RON | Total intrari: ${escapeHtml(String(category.total_income || 0))} RON</p>
        <div class="transactions-table-wrap">
          <table class="transactions-table">
            <thead>
              <tr>
                <th>Data</th>
                <th>Partener</th>
                <th>Detalii</th>
                <th>Suma</th>
                <th>Mutare</th>
              </tr>
            </thead>
            <tbody>${rowHtml}</tbody>
          </table>
        </div>
      </details>
    `;
  }).join("");
}

function renderTransactions(rows) {
  if (!rows.length) {
    transactionsList.innerHTML = '<p class="muted">Nu exista tranzactii pentru filtrele curente.</p>';
    return;
  }
  const bodyRows = rows.map((row) => {
    const kind = row.economic_kind || "neclasificat";
    const entityType = prettyEntityType(row.entity_type);
    const details = transactionDetails(row.description || "");
    const invoiceNumber = extractInvoiceNumber(row.description || "") || "-";
    const category = row.category_names || "fara categorie";
    return `
      <tr>
        <td>${escapeHtml(row.transaction_date || "-")}</td>
        <td>${escapeHtml(row.merchant || "Fara partener")}</td>
        <td>${escapeHtml(entityType)}</td>
        <td>${escapeHtml(kind)}</td>
        <td title="${escapeHtml(details.full)}">${escapeHtml(details.short)}</td>
        <td>${escapeHtml(invoiceNumber)}</td>
        <td>${escapeHtml(category)}</td>
        <td>${escapeHtml(row.review_status || "needs_review")}</td>
        <td class="amount-cell">${escapeHtml(formatAmount(row.amount, row.currency || "RON"))}</td>
      </tr>
    `;
  }).join("");

  transactionsList.innerHTML = `
    <div class="transactions-table-wrap">
      <table class="transactions-table">
        <thead>
          <tr>
            <th>Data</th>
            <th>Partener / colaborator</th>
            <th>Tip entitate</th>
            <th>Tip tranzactie</th>
            <th>Detalii</th>
            <th>Nr factura</th>
            <th>Categorie</th>
            <th>Status</th>
            <th>Suma</th>
          </tr>
        </thead>
        <tbody>${bodyRows}</tbody>
      </table>
    </div>
  `;
}

function renderInvoices(items) {
  if (!items.length) {
    invoicesList.innerHTML = '<p class="muted">Nu exista inca facturi in workspace-ul curent.</p>';
    return;
  }
  invoicesList.innerHTML = items.map((item) => `
    <article class="review-item">
      <div class="review-main">
        <div class="review-topline">
          <strong>${escapeHtml(item.invoice_number || "Factura fara numar")}</strong>
          <span>${escapeHtml(formatAmount(item.total_amount || 0, item.currency || "RON"))}</span>
        </div>
        <div class="review-meta">
          <span>${escapeHtml(item.role_label)}</span>
          <span>${escapeHtml(item.issue_date || "-")}</span>
          <span>${escapeHtml(item.counterparty_name || "Fara contraparte")}</span>
        </div>
        <p class="muted">Status factura: ${escapeHtml(item.status || "necunoscut")}</p>
      </div>
    </article>
  `).join("");
}

function renderInvoiceMatches(items) {
  if (!items.length) {
    matchesList.innerHTML = '<p class="muted">Nu exista inca matching-uri salvate pentru firma curenta.</p>';
    return;
  }
  matchesList.innerHTML = items.map((item) => `
    <article class="review-item">
      <div class="review-main">
        <div class="review-topline">
          <strong>${escapeHtml(item.invoice_number || "Factura")}</strong>
          <span>${escapeHtml(String(item.match_kind || "match"))}</span>
        </div>
        <div class="review-meta">
          <span>${escapeHtml(item.counterparty_name || item.merchant || "Fara contraparte")}</span>
          <span>${escapeHtml(String(item.status || "proposed"))}</span>
          <span>confidence ${escapeHtml(String(item.confidence || 0))}</span>
        </div>
        <p class="muted">Potrivire: ${escapeHtml(formatAmount(item.matched_amount || 0, item.currency || "RON"))}. Rest: ${escapeHtml(formatAmount(item.residual_amount || 0, item.currency || "RON"))}.</p>
      </div>
    </article>
  `).join("");
}

function renderBusinessMemoryFacts(facts) {
  if (!facts.length) {
    businessMemoryFacts.innerHTML = '<p class="muted">Nu exista inca fapte salvate.</p>';
    return;
  }
  businessMemoryFacts.innerHTML = facts.map((fact) => `
    <article class="review-item">
      <div class="review-main">
        <div class="review-topline">
          <strong>${escapeHtml(fact.subject_name || "workspace")}</strong>
          <span>${escapeHtml(fact.fact_type || "fact")}</span>
        </div>
        <div class="review-meta">
          <span>${escapeHtml(fact.fact_value || "-")}</span>
          <span>${escapeHtml(fact.status || "accepted")}</span>
          <span>confidence ${escapeHtml(String(fact.confidence || 1))}</span>
        </div>
      </div>
    </article>
  `).join("");
}

function renderChangeReviewItems(items) {
  if (!items.length) {
    changeReviewList.innerHTML = '<p class="muted">Nu exista schimbari propuse in acest moment.</p>';
    return;
  }
  const fieldLabels = {
    analysis_category: "categorie propusa",
    entity_type: "tip entitate propus",
  };
  changeReviewList.innerHTML = items.map((item) => `
    <article class="review-item">
      <div class="review-main">
        <div class="review-topline">
          <strong>${escapeHtml(fieldLabels[item.field_name] || item.field_name || "schimbare")}</strong>
          <span>${escapeHtml(item.status || "pending")}</span>
        </div>
        <div class="review-meta">
          <span>vechi: ${escapeHtml(item.old_value || "-")}</span>
          <span>nou: ${escapeHtml(item.new_value || "-")}</span>
          <span>confidence ${escapeHtml(String(item.confidence || 0))}</span>
        </div>
        <p class="muted">${escapeHtml(item.reason || "Fara motiv explicit")}</p>
        ${item.transaction_id ? `
          <div class="review-meta">
            <span>${escapeHtml(item.transaction_date || "-")}</span>
            <span>${escapeHtml(item.merchant || "Fara partener")}</span>
            <span>${escapeHtml(formatAmount(item.amount || 0, item.currency || "RON"))}</span>
          </div>
          <p class="muted">${escapeHtml(item.description || "-")}</p>
          <p class="muted">Acum: tip ${escapeHtml(prettyEntityType(item.entity_type))}, categorii ${escapeHtml(item.category_names || "-")}.</p>
        ` : ""}
      </div>
      <div class="review-actions">
        <button type="button" data-action="change-review-decision" data-decision="accept" data-id="${item.id}">Accepta</button>
        <button type="button" class="button-secondary" data-action="change-review-decision" data-decision="reject" data-id="${item.id}">Respinge</button>
      </div>
    </article>
  `).join("");
}

function prettyEntityType(value) {
  if (!value) {
    return "neclasificat";
  }
  const labels = {
    supplier: "furnizor",
    client: "client",
    partner: "partener",
    collaborator: "colaborator",
    owner: "asociat",
    employee: "angajat",
    bank: "banca",
    unknown: "neclasificat",
  };
  return labels[value] || value;
}

function prettyOperationalScope(value) {
  const labels = {
    operational: "operational",
    non_operational: "non-operational",
    personal: "personal / owner-related",
    unassigned: "neprecizat",
  };
  return labels[value] || value || "neprecizat";
}

function renderOperationalScopeOptions(selectedValue) {
  const options = [
    ["unassigned", "Neprecizat"],
    ["operational", "Operational"],
    ["non_operational", "Non-operational"],
    ["personal", "Personal / owner-related"],
  ];
  return options.map(([value, label]) => {
    const selected = value === selectedValue ? " selected" : "";
    return `<option value="${value}"${selected}>${label}</option>`;
  }).join("");
}

function transactionDetails(description) {
  const normalized = description.replaceAll(/\s+/g, " ").trim();
  const chunks = normalized.split("|").map((item) => item.trim()).filter(Boolean);
  const full = chunks.length ? chunks.join(" | ") : normalized;
  const short = full.length > 95 ? `${full.slice(0, 95)}...` : full;
  return { short: short || "-", full: full || "-" };
}

function extractInvoiceNumber(description) {
  const patterns = [
    /\bfact(?:ura)?\s*(?:nr\.?|numarul)?\s*([A-Za-z0-9\-\/]+)/i,
    /\binv(?:oice)?\s*(?:nr\.?|no\.?)?\s*([A-Za-z0-9\-\/]+)/i,
    /\bcv\s*fc\s*nr\s*([A-Za-z0-9\-\/]+)/i,
  ];
  for (const pattern of patterns) {
    const match = description.match(pattern);
    if (match && match[1]) {
      return match[1];
    }
  }
  return null;
}

function formatAmount(amount, currency) {
  const numeric = Number(amount);
  if (!Number.isFinite(numeric)) {
    return `${amount} ${currency}`;
  }
  return `${numeric.toFixed(2)} ${currency}`;
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

workspaceTabs.forEach((button) => {
  button.addEventListener("click", () => {
    setActiveTab(button.dataset.tab);
  });
});

onboardingWizard.addEventListener("click", (event) => {
  const button = event.target.closest("[data-open-tab]");
  if (!button) {
    return;
  }
  setActiveTab(button.dataset.openTab);
});

uploadButton.addEventListener("click", () => {
  importDialog.showModal();
});

uploadCancelButton.addEventListener("click", () => {
  importDialog.close();
});

uploadConfirmButton.addEventListener("click", async () => {
  if (currentWorkspaceId === null) {
    uploadResult.textContent = "Creeaza sau alege mai intai firma in care vrei sa incarci extrasul.";
    return;
  }
  const file = uploadFileInput.files && uploadFileInput.files.length ? uploadFileInput.files[0] : null;
  const path = uploadPathInput.value.trim();
  if (!file && !path) {
    uploadResult.textContent = "Alege un fisier PDF, CSV sau JSON sau lipeste calea completa.";
    return;
  }

  try {
    uploadConfirmButton.disabled = true;
    uploadResult.textContent = file ? `Import ${file.name} in curs...` : "Import din calea introdusa in curs...";
    const payload = file
      ? await requestFileUpload(file, currentWorkspaceId)
      : await requestJson("/api/upload", {
          method: "POST",
          body: JSON.stringify({ path, workspace_id: currentWorkspaceId }),
        });
    if (payload.document_type === "issued_invoices") {
      uploadResult.textContent = `Facturi importate: ${payload.result.inserted}. Sarite: ${payload.result.skipped}.`;
    } else {
      activeImportId = payload.active_import_id || null;
      uploadResult.textContent = `Import reusit. Batch activ: ${activeImportId}. ${payload.imported_count} tranzactii citite.`;
    }
    uploadFileInput.value = "";
    uploadPathInput.value = "";
    importDialog.close();
    await refreshWorkspaceData();
  } catch (error) {
    uploadResult.textContent = error.message;
  } finally {
    uploadConfirmButton.disabled = false;
  }
});

invoiceUploadButton.addEventListener("click", async () => {
  if (currentWorkspaceId === null) {
    invoiceUploadResult.textContent = "Creeaza sau alege mai intai firma in care vrei sa incarci facturile.";
    return;
  }
  const path = invoicePathInput.value.trim();
  if (!path) {
    invoiceUploadResult.textContent = "Introdu o cale reala catre un fisier sau un folder care contine facturi PDF, JSON sau CSV.";
    return;
  }

  try {
    const payload = await requestJson("/api/invoices/upload", {
      method: "POST",
      body: JSON.stringify({
        path,
        workspace_id: currentWorkspaceId,
        role: invoiceRoleSelect.value,
      }),
    });
    invoiceUploadResult.textContent = `Facturi importate: ${payload.result.inserted}. Matching nou: ${(payload.matches || []).length}. Change review: ${(payload.change_review_items || []).length}.`;
    await refreshWorkspaceData();
    setActiveTab("invoices");
  } catch (error) {
    invoiceUploadResult.textContent = error.message;
  }
});

resetButton.addEventListener("click", async () => {
  if (!window.confirm("Sterg toate importurile si toate datele salvate?")) {
    return;
  }
  try {
    await requestJson("/api/reset", { method: "POST", body: JSON.stringify({}) });
    activeImportId = null;
    uploadFileInput.value = "";
    uploadPathInput.value = "";
    invoicePathInput.value = "";
    uploadResult.textContent = "Toate datele salvate au fost sterse.";
    invoiceUploadResult.textContent = "Facturile salvate au fost sterse.";
    await refreshWorkspaceData();
  } catch (error) {
    uploadResult.textContent = error.message;
  }
});

importSelect.addEventListener("change", async () => {
  activeImportId = importSelect.value ? Number(importSelect.value) : null;
  try {
    await refreshWorkspaceData();
  } catch (error) {
    answerBox.textContent = error.message;
  }
});

transactionsRefreshButton.addEventListener("click", async () => {
  try {
    await loadTransactions();
  } catch (error) {
    transactionsList.innerHTML = `<p class="muted">${escapeHtml(error.message)}</p>`;
  }
});

questionButton.addEventListener("click", async () => {
  if (currentWorkspaceId === null) {
    answerBox.textContent = "Creeaza sau alege mai intai firma pe care vrei sa o intrebi.";
    return;
  }
  const transactionImportId = currentTransactionImportId();
  try {
    const payload = await requestJson("/api/chat", {
      method: "POST",
      body: JSON.stringify({
        question: questionInput.value,
        import_batch_id: transactionImportId,
        workspace_id: currentWorkspaceId,
      }),
    });
    answerBox.textContent = payload.answer;
    renderChatRows(payload.transaction_rows && payload.transaction_rows.length ? payload.transaction_rows : payload.rows);
  } catch (error) {
    answerBox.textContent = error.message;
  }
});

refreshReviewButton.addEventListener("click", async () => {
  try {
    await loadReview();
  } catch (error) {
    reviewList.innerHTML = `<p class="muted">${escapeHtml(error.message)}</p>`;
  }
});

categoriesRefreshButton.addEventListener("click", async () => {
  try {
    await loadCategoryCatalog();
  } catch (error) {
    categoriesList.innerHTML = `<p class="muted">${escapeHtml(error.message)}</p>`;
  }
});

invoicesRefreshButton.addEventListener("click", async () => {
  try {
    await loadInvoices();
    await loadInvoiceMatches();
  } catch (error) {
    invoicesSummary.textContent = error.message;
  }
});

businessMemoryRefreshButton.addEventListener("click", async () => {
  try {
    const factCount = await loadBusinessMemory();
    updateOnboardingChecklist({ factCount });
  } catch (error) {
    businessMemoryFacts.innerHTML = `<p class="muted">${escapeHtml(error.message)}</p>`;
  }
});

changeReviewRefreshButton.addEventListener("click", async () => {
  try {
    const changeReviewCount = await loadChangeReview();
    updateOnboardingChecklist({ changeReviewCount });
  } catch (error) {
    changeReviewList.innerHTML = `<p class="muted">${escapeHtml(error.message)}</p>`;
  }
});

businessMemoryForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  if (currentWorkspaceId === null) {
    businessMemoryResult.textContent = "Selecteaza mai intai firma curenta.";
    return;
  }
  const text = businessMemoryInput.value.trim();
  if (!text) {
    businessMemoryResult.textContent = "Scrie mai intai instructiunea naturala.";
    return;
  }
  try {
    businessMemorySubmit.disabled = true;
    const payload = await requestJson("/api/business-memory", {
      method: "POST",
      body: JSON.stringify({
        workspace_id: currentWorkspaceId,
        text,
      }),
    });
    businessMemoryResult.textContent = `Salvat. ${payload.fact_count} fapte extrase.`;
    businessMemoryInput.value = "";
    await refreshWorkspaceData();
  } catch (error) {
    businessMemoryResult.textContent = error.message;
  } finally {
    businessMemorySubmit.disabled = false;
  }
});

reviewList.addEventListener("click", async (event) => {
  const button = event.target.closest("button");
  const transactionImportId = currentTransactionImportId();
  if (!button || transactionImportId === null) {
    return;
  }

  try {
    if (button.dataset.action === "category-group") {
      const groupKey = button.dataset.groupKey;
      const select = document.getElementById(`category-group-select-${groupKey}`);
      const newInput = document.getElementById(`category-group-new-${groupKey}`);
      const categoryName = select.value === "__new__" ? newInput.value.trim() : select.value.trim();
      if (!categoryName) {
        uploadResult.textContent = "Alege o categorie sau scrie numele categoriei noi.";
        return;
      }
      const ids = String(button.dataset.ids || "").split(",").filter(Boolean).map((value) => Number(value));
      await requestJson("/api/review/category", {
        method: "POST",
        body: JSON.stringify({
          category_name: categoryName,
          transaction_ids: ids,
          apply_to_similar: true,
          import_batch_id: transactionImportId,
        }),
      });
      uploadResult.textContent = `Categoria "${categoryName}" a fost aplicata pe grup.`;
    }

    if (button.dataset.action === "category-bulk") {
      const select = document.getElementById("bulk-category-select");
      const newInput = document.getElementById("bulk-category-new");
      const categoryName = select.value === "__new__" ? newInput.value.trim() : select.value.trim();
      if (!categoryName) {
        uploadResult.textContent = "Alege o categorie sau scrie numele categoriei noi pentru selectie.";
        return;
      }
      const ids = Array.from(reviewList.querySelectorAll(".review-group-checkbox:checked"))
        .flatMap((checkbox) => String(checkbox.dataset.ids || "").split(","))
        .filter(Boolean)
        .map((value) => Number(value));
      if (!ids.length) {
        uploadResult.textContent = "Bifeaza cel putin un grup inainte sa aplici categoria.";
        return;
      }
      await requestJson("/api/review/category", {
        method: "POST",
        body: JSON.stringify({
          category_name: categoryName,
          transaction_ids: ids,
          apply_to_similar: true,
          import_batch_id: transactionImportId,
        }),
      });
      uploadResult.textContent = `Categoria "${categoryName}" a fost aplicata pe selectia curenta.`;
    }

    await refreshWorkspaceData();
  } catch (error) {
    answerBox.textContent = error.message;
  }
});

reviewList.addEventListener("change", (event) => {
  const select = event.target.closest(".category-select");
  if (!select) {
    return;
  }
  const inputId = select.id.replace("-select-", "-new-");
  const input = select.id === "bulk-category-select"
    ? document.getElementById("bulk-category-new")
    : document.getElementById(inputId);
  if (input) {
    input.hidden = select.value !== "__new__";
    if (!input.hidden) {
      input.focus();
    }
  }
});

categoriesList.addEventListener("click", async (event) => {
  const button = event.target.closest("button");
  if (!button) {
    return;
  }

  try {
    if (button.dataset.action === "save-category-meta") {
      const categoryId = button.dataset.categoryId;
      const categoryName = button.dataset.categoryName;
      const description = document.getElementById(`category-description-${categoryId}`).value.trim();
      const operationalScope = document.getElementById(`category-scope-${categoryId}`).value;
      await requestJson("/api/categories/update", {
        method: "POST",
        body: JSON.stringify({
          category_name: categoryName,
          description,
          operational_scope: operationalScope,
        }),
      });
      uploadResult.textContent = `Categoria "${categoryName}" a fost actualizata.`;
    }

    if (button.dataset.action === "move-category-transaction") {
      const transactionId = Number(button.dataset.id);
      const currentCategory = button.dataset.currentCategory;
      const select = document.getElementById(`category-move-${transactionId}`);
      const newInput = document.getElementById(`category-move-${transactionId}-new`);
      const categoryName = select.value === "__new__" ? newInput.value.trim() : select.value.trim();
      if (!categoryName) {
        uploadResult.textContent = "Alege categoria destinatie sau scrie una noua.";
        return;
      }
      await requestJson("/api/review/category", {
        method: "POST",
        body: JSON.stringify({
          category_name: categoryName,
          transaction_ids: [transactionId],
          apply_to_similar: true,
          replace_existing: true,
          import_batch_id: currentTransactionImportId(),
        }),
      });
      uploadResult.textContent = `Tranzactia a fost mutata din "${currentCategory}" in "${categoryName}".`;
    }

    await refreshWorkspaceData();
  } catch (error) {
    answerBox.textContent = error.message;
  }
});

categoriesList.addEventListener("change", (event) => {
  const select = event.target.closest(".category-inline-select");
  if (!select) {
    return;
  }
  const input = document.getElementById(`${select.id}-new`);
  if (input) {
    input.hidden = select.value !== "__new__";
    if (!input.hidden) {
      input.focus();
    }
  }
});

changeReviewList.addEventListener("click", async (event) => {
  const button = event.target.closest('[data-action="change-review-decision"]');
  if (!button) {
    return;
  }
  try {
    await requestJson("/api/change-review/decision", {
      method: "POST",
      body: JSON.stringify({
        item_id: Number(button.dataset.id),
        decision: button.dataset.decision,
      }),
    });
    await refreshWorkspaceData();
  } catch (error) {
    answerBox.textContent = error.message;
  }
});

workspaceCreateForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const name = workspaceNameInput.value.trim();
  if (!name) {
    workspaceCurrent.textContent = "Scrie mai intai numele firmei.";
    return;
  }
  try {
    const payload = await requestJson("/api/workspaces", {
      method: "POST",
      body: JSON.stringify({ name }),
    });
    currentWorkspaceId = Number(payload.workspace_id);
    workspaceNameInput.value = "";
    setActiveTab("questions");
    await refreshWorkspaceData();
    uploadResult.textContent = `Firma "${currentWorkspaceName}" a fost creata. Poti importa primul extras.`;
  } catch (error) {
    workspaceCurrent.textContent = error.message;
  }
});

workspaceList.addEventListener("click", async (event) => {
  const button = event.target.closest("[data-workspace-id]");
  if (!button) {
    return;
  }
  currentWorkspaceId = Number(button.dataset.workspaceId);
  currentWorkspaceName = button.dataset.workspaceName || null;
  activeImportId = null;
  try {
    await refreshWorkspaceData();
  } catch (error) {
    workspaceCurrent.textContent = error.message;
  }
});

setActiveTab("questions");
loadWorkspaces()
  .then(async () => {
    await refreshWorkspaceData();
  })
  .catch((error) => {
    importMeta.textContent = error.message;
    setEmptySessionState(error.message);
  });
