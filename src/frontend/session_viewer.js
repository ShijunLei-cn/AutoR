/**
 * Session Viewer — ES module served from src/frontend/session_viewer.js
 * under the /studio/ext/ route.
 *
 * Renders a Claude-Code-style event timeline for a single stage session.
 * Host page supplies the container element and the events list; this module
 * owns the DOM structure and styling class names.
 *
 * Usage:
 *   import { renderSession } from "/studio/ext/session_viewer.js";
 *   renderSession(containerEl, events);
 */

const KIND_META = {
  stage_start:  { icon: "▶",  label: "Stage start",  klass: "session-event event-system" },
  stage_end:    { icon: "■",  label: "Stage end",    klass: "session-event event-system" },
  system:       { icon: "⚙",  label: "System",       klass: "session-event event-system" },
  assistant:    { icon: "◆",  label: "Assistant",    klass: "session-event event-assistant" },
  user:         { icon: "◇",  label: "User",         klass: "session-event event-user" },
  tool_use:     { icon: "⚡", label: "Tool call",    klass: "session-event event-tool-use" },
  tool_result:  { icon: "↩",  label: "Tool result",  klass: "session-event event-tool-result" },
  approval:     { icon: "✅", label: "Approved",     klass: "session-event event-approval" },
  feedback:     { icon: "✍︎", label: "Feedback",     klass: "session-event event-feedback" },
};

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

function formatTime(iso) {
  if (!iso) return "";
  const t = iso.split("T")[1] || iso;
  return t.slice(0, 8);
}

function renderToolInput(input) {
  if (input === null || input === undefined) return "";
  try {
    return JSON.stringify(input, null, 2);
  } catch {
    return String(input);
  }
}

function renderOne(event) {
  const meta = KIND_META[event.kind] || {
    icon: "·",
    label: event.kind || "event",
    klass: "session-event event-other",
  };

  const header = `
    <div class="session-event-header">
      <span class="session-event-icon">${meta.icon}</span>
      <span class="session-event-label">${escapeHtml(meta.label)}</span>
      <span class="session-event-time">${escapeHtml(formatTime(event.ts))}${
    event.attempt ? " · attempt " + event.attempt : ""
  }</span>
    </div>
  `;

  let body = "";
  if (event.kind === "tool_use" && event.tool) {
    body = `
      <div class="session-tool-call">
        <span class="session-tool-name">${escapeHtml(event.tool.name || "tool")}</span>
        <pre class="session-tool-input">${escapeHtml(renderToolInput(event.tool.input))}</pre>
      </div>
    `;
  } else if (event.kind === "tool_result") {
    body = `<pre class="session-tool-output">${escapeHtml(event.output || "")}</pre>`;
  } else if (event.content) {
    body = `<div class="session-event-body">${escapeHtml(event.content)}</div>`;
  }

  return `<li class="${meta.klass}">${header}${body}</li>`;
}

export function renderSession(container, events) {
  if (!container) return;
  if (!events || events.length === 0) {
    container.innerHTML =
      '<div class="session-empty">No session trace yet for this stage. The runner will populate it as the stage executes.</div>';
    return;
  }
  const html = events.map(renderOne).join("");
  container.innerHTML = `<ol class="session-event-list">${html}</ol>`;
}

// Also expose on window as a fallback for non-module hosts.
if (typeof window !== "undefined") {
  window.__AutoRSessionViewer = { renderSession };
}
