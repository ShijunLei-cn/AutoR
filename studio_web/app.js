const state = {
  runIds: [],
  selectedRunId: null,
  selectedStageSlug: null,
  runSummary: null,
  artifactIndex: null,
  fileTree: null,
};

const elements = {
  connectionStatus: document.getElementById("connection-status"),
  reloadButton: document.getElementById("reload-button"),
  runCount: document.getElementById("run-count"),
  runsList: document.getElementById("runs-list"),
  stageRail: document.getElementById("stage-rail"),
  runStatus: document.getElementById("run-status"),
  runTitle: document.getElementById("run-title"),
  documentTitle: document.getElementById("document-title"),
  documentMeta: document.getElementById("document-meta"),
  stageDocument: document.getElementById("stage-document"),
  artifactTotal: document.getElementById("artifact-total"),
  runSummary: document.getElementById("run-summary"),
  artifactSummary: document.getElementById("artifact-summary"),
  fileTree: document.getElementById("file-tree"),
};

elements.reloadButton.addEventListener("click", () => {
  void loadRuns();
});

void loadRuns();

async function loadRuns() {
  setConnection("Loading");
  const payload = await api("/api/runs");
  state.runIds = payload.run_ids || [];
  elements.runCount.textContent = String(state.runIds.length);
  renderRuns();
  if (!state.runIds.length) {
    setConnection("No Runs");
    renderEmptyWorkspace("No runs found under the configured runs directory.");
    return;
  }
  if (!state.selectedRunId || !state.runIds.includes(state.selectedRunId)) {
    state.selectedRunId = state.runIds[state.runIds.length - 1];
  }
  await loadRun(state.selectedRunId);
  setConnection("Connected");
}

async function loadRun(runId) {
  state.selectedRunId = runId;
  const [summary, artifacts, fileTree] = await Promise.all([
    api(`/api/runs/${runId}`),
    api(`/api/runs/${runId}/artifacts`),
    api(`/api/runs/${runId}/files/tree?root=workspace&depth=2`),
  ]);
  state.runSummary = summary;
  state.artifactIndex = artifacts;
  state.fileTree = fileTree;
  if (!state.selectedStageSlug) {
    state.selectedStageSlug = summary.current_stage_slug || summary.stages.at(-1)?.slug || null;
  }
  if (!summary.stages.some((stage) => stage.slug === state.selectedStageSlug)) {
    state.selectedStageSlug = summary.current_stage_slug || summary.stages[0]?.slug || null;
  }
  renderRuns();
  renderSummary();
  renderStages();
  renderArtifacts();
  renderFileTree();
  if (state.selectedStageSlug) {
    await loadStageDocument(state.selectedStageSlug);
  }
}

async function loadStageDocument(stageSlug) {
  if (!state.selectedRunId) {
    return;
  }
  state.selectedStageSlug = stageSlug;
  renderStages();
  const payload = await api(`/api/runs/${state.selectedRunId}/stages/${stageSlug}`);
  const stage = state.runSummary.stages.find((item) => item.slug === stageSlug);
  elements.documentTitle.textContent = stage ? stage.title : stageSlug;
  elements.documentMeta.textContent = `${stage?.status || "unknown"} · attempts ${stage?.attempt_count || 0}`;
  elements.stageDocument.textContent = payload.markdown;
  elements.stageDocument.classList.remove("empty-state");
}

function renderRuns() {
  elements.runsList.innerHTML = "";
  for (const runId of state.runIds) {
    const card = document.createElement("button");
    card.type = "button";
    card.className = `run-card${runId === state.selectedRunId ? " is-active" : ""}`;
    card.innerHTML = `
      <div class="run-card-title">${escapeHtml(runId)}</div>
      <div class="run-card-meta">Open run workspace</div>
    `;
    card.addEventListener("click", () => {
      void loadRun(runId);
    });
    elements.runsList.appendChild(card);
  }
}

function renderSummary() {
  const summary = state.runSummary;
  if (!summary) {
    return;
  }
  elements.runTitle.textContent = summary.run_id;
  elements.runStatus.textContent = summary.run_status;
  elements.runSummary.innerHTML = "";
  const rows = [
    ["Model", summary.model],
    ["Venue", summary.venue],
    ["Status", summary.run_status],
    ["Updated", summary.updated_at],
    ["Current", summary.current_stage_slug || "none"],
  ];
  for (const [label, value] of rows) {
    const dt = document.createElement("dt");
    dt.textContent = label;
    const dd = document.createElement("dd");
    dd.textContent = value;
    elements.runSummary.append(dt, dd);
  }
}

function renderStages() {
  elements.stageRail.innerHTML = "";
  const stages = state.runSummary?.stages || [];
  for (const stage of stages) {
    const item = document.createElement("button");
    item.type = "button";
    item.className = `stage-item${stage.slug === state.selectedStageSlug ? " is-active" : ""}`;
    item.innerHTML = `
      <div class="stage-title">${escapeHtml(stage.title)}</div>
      <div class="stage-meta">updated ${escapeHtml(stage.updated_at || "unknown")}</div>
      <span class="stage-status status-${escapeHtml(stage.status)}">${escapeHtml(stage.status)}</span>
    `;
    item.addEventListener("click", () => {
      void loadStageDocument(stage.slug);
    });
    elements.stageRail.appendChild(item);
  }
}

function renderArtifacts() {
  const counts = state.artifactIndex?.counts_by_category || {};
  const total = state.artifactIndex?.artifact_count || 0;
  elements.artifactTotal.textContent = `${total} artifacts`;
  elements.artifactSummary.innerHTML = "";
  for (const [label, count] of Object.entries(counts)) {
    const item = document.createElement("li");
    item.textContent = `${label}: ${count}`;
    elements.artifactSummary.appendChild(item);
  }
}

function renderFileTree() {
  elements.fileTree.innerHTML = "";
  if (!state.fileTree) {
    return;
  }
  elements.fileTree.appendChild(renderTreeNode(state.fileTree));
}

function renderTreeNode(node) {
  const wrapper = document.createElement("div");
  wrapper.className = "tree-node";
  const label = document.createElement("div");
  label.className = "tree-label";
  label.textContent = `${node.node_type === "directory" ? "▾" : "•"} ${node.name}`;
  wrapper.appendChild(label);
  if (node.children?.length) {
    const children = document.createElement("div");
    children.className = "tree-children";
    for (const child of node.children) {
      children.appendChild(renderTreeNode(child));
    }
    wrapper.appendChild(children);
  }
  return wrapper;
}

function renderEmptyWorkspace(message) {
  elements.runTitle.textContent = "No run selected";
  elements.documentTitle.textContent = "Stage Document";
  elements.documentMeta.textContent = "";
  elements.stageDocument.textContent = message;
  elements.stageDocument.classList.add("empty-state");
  elements.stageRail.innerHTML = "";
  elements.runSummary.innerHTML = "";
  elements.artifactSummary.innerHTML = "";
  elements.fileTree.innerHTML = "";
}

function setConnection(text) {
  elements.connectionStatus.textContent = text;
}

async function api(path) {
  const response = await fetch(path);
  if (!response.ok) {
    const payload = await response.json().catch(() => ({}));
    throw new Error(payload.error || `Request failed: ${response.status}`);
  }
  return response.json();
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}
