"use strict";

const $ = (id) => document.getElementById(id);

const form = $("analysis-form");
const input = $("email-input");
const errorBox = $("error-message");
const liveStatus = $("live-status");
const runButton = $("run-button");
const reportSection = $("results-section");
const tableBody = $("results-body");
const domainList = $("domain-list");

const state = {
  report: null,
  filter: "all",
  search: "",
  expanded: new Set(),
  printing: false
};

const labels = {
  likely_delivered: "LIKELY DELIVERED",
  likely_bounce: "LIKELY BOUNCE",
  unknown: "UNKNOWN"
};

const signalLabels = {
  pass: "PASS",
  fail: "FAIL",
  unknown: "INCONCLUSIVE",
  skip: "NOT CHECKED"
};

function element(tag, className = "", content = null) {
  const node = document.createElement(tag);

  if (className) node.className = className;
  if (content !== null) node.textContent = String(content);

  return node;
}

function parseAddresses(text) {
  const addresses = [];
  const seen = new Set();

  for (const part of text.split(/[\s,;]+/)) {
    const email = part.trim();
    const key = email.toLowerCase();

    if (email && !seen.has(key)) {
      seen.add(key);
      addresses.push(email);
    }
  }

  return addresses;
}

function updateInputCount() {
  const count = parseAddresses(input.value).length;
  $("address-count").textContent =
    `${String(count).padStart(2, "0")} / 50`;

  $("address-count").style.color =
    count > 50 ? "#b54e43" : "";
}

function showError(message) {
  errorBox.textContent = message;
  errorBox.hidden = !message;
}

function setBusy(busy) {
  runButton.disabled = busy;
  $("demo-button").disabled = busy;

  runButton.textContent = busy
    ? "ANALYZING..."
    : "RUN ANALYSIS ↗";

  liveStatus.textContent = busy
    ? "Inspecting syntax and DNS mail-routing signals..."
    : "";
}

function metric(id, number) {
  $(id).textContent = String(number).padStart(2, "0");
}

function drawSummary(summary) {
  metric("metric-total", summary.total);
  metric("metric-delivered", summary.likely_delivered);
  metric("metric-bounce", summary.likely_bounce);
  metric("metric-unknown", summary.unknown);

  $("batch-time").textContent =
    `${summary.duration_ms} MS / ${summary.domains} DOMAINS`;

  const total = Math.max(summary.total, 1);

  const percentage = (value) =>
    `${(value / total) * 100}%`;

  $("bar-delivered").style.width =
    percentage(summary.likely_delivered);

  $("bar-bounce").style.width =
    percentage(summary.likely_bounce);

  $("bar-unknown").style.width =
    percentage(summary.unknown);

  const distribution = document.querySelector(".distribution");

  distribution.setAttribute(
    "aria-label",
    `${summary.likely_delivered} likely delivered, ` +
    `${summary.likely_bounce} likely bounce, ` +
    `${summary.unknown} unknown`
  );
}

function traceRow(result, index) {
  const row = element("tr", "detail-row");
  row.id = `trace-${index}`;

  const cell = document.createElement("td");
  cell.colSpan = 4;

  const title = element(
    "div", "trace-title",
    `SIGNAL TRACE / ${result.email}`
  );

  const grid = element("div", "trace-grid");

  result.trace.forEach((item, position) => {
    const step = element("div", "trace-step");

    step.appendChild(element(
      "span", "step-number",
      String(position + 1).padStart(2, "0")
    ));

    step.appendChild(element("strong", "", item.label));

    step.appendChild(element(
      "span",
      `step-state ${item.state}`,
      signalLabels[item.state] || item.state
    ));

    step.appendChild(element("p", "", item.detail));
    grid.appendChild(step);
  });

  const note = element(
    "div", "trace-note",
    "CONCLUSION / " + result.reason
  );

  cell.append(title, grid, note);
  row.appendChild(cell);

  return row;
}

function renderRows() {
  if (!state.report) return;

  tableBody.replaceChildren();

  let count = 0;

  state.report.results.forEach((result, index) => {
    const allowedStatus =
      state.printing ||
      state.filter === "all" ||
      state.filter === result.status;

    const allowedSearch =
      state.printing ||
      result.email.toLowerCase().includes(state.search) ||
      (result.domain || "").toLowerCase().includes(state.search);

    if (!allowedStatus || !allowedSearch) return;

    count++;

    const row = element("tr", "result-row");
    row.appendChild(
      element("td", "", String(index + 1).padStart(3, "0"))
    );

    const addressCell = document.createElement("td");
    const addressButton = element(
      "button", "inspect-button", result.email
    );

    const expanded = state.printing || state.expanded.has(index);

    addressButton.type = "button";
    addressButton.setAttribute("aria-expanded", String(expanded));
    addressButton.setAttribute("aria-controls", `trace-${index}`);
    addressButton.setAttribute(
      "aria-label",
      `${expanded ? "Hide" : "View"} diagnostic trace for ${result.email}`
    );

    addressButton.addEventListener("click", () => {
      if (state.expanded.has(index)) {
        state.expanded.delete(index);
      } else {
        state.expanded.add(index);
      }
      renderRows();
    });

    addressCell.appendChild(addressButton);
    row.appendChild(addressCell);

    const classificationCell = document.createElement("td");
    classificationCell.appendChild(
      element(
        "span",
        `classification ${result.status}`,
        labels[result.status] || "UNKNOWN"
      )
    );
    row.appendChild(classificationCell);

    row.appendChild(element("td", "", result.reason));
    tableBody.appendChild(row);

    if (expanded) {
      tableBody.appendChild(traceRow(result, index));
    }
  });

  $("visible-count").textContent =
    `${count} OF ${state.report.results.length} SHOWN`;

  $("empty-filter").hidden = count > 0;
}

function renderDomains(domains) {
  domainList.replaceChildren();

  $("domain-count").textContent =
    `${domains.length} DOMAINS`;

  $("domain-empty").hidden = domains.length > 0;

  domains.forEach((domain) => {
    const card = element("article", "domain-card");

    const header = element("div", "domain-card-header");
    const title = element("h3", "", domain.domain);

    const status = element(
      "span", "domain-status",
      domain.routing === "routable"
        ? "ROUTING FOUND"
        : domain.routing === "bounce"
          ? "ROUTING FAILED"
          : "INCONCLUSIVE"
    );

    header.append(title, status);

    const subtitle = element(
      "p", "domain-subtitle",
      `${domain.address_count} ADDRESS${domain.address_count === 1 ? "" : "ES"} IN BATCH`
    );

    const data = element("div", "domain-data");

    const method = element("div");
    method.append(
      element("span", "", "ROUTING METHOD"),
      element("strong", "", domain.method)
    );

    const elapsed = element("div");
    elapsed.append(
      element("span", "", "LOOKUP TIME"),
      element("strong", "", `${domain.lookup_ms} MS`)
    );

    data.append(method, elapsed);

    const hosts = domain.mx_hosts.length
      ? domain.mx_hosts
          .map(item => `${item.priority}  ${item.host}`)
          .join("\n")
      : "No MX hostnames returned.";

    const mx = element("div", "mx-hosts", hosts);
    mx.style.whiteSpace = "pre-line";

    card.append(
      header,
      subtitle,
      data,
      mx,
      element("p", "domain-reason", domain.reason)
    );

    domainList.appendChild(card);
  });
}

function showReport(data) {
  state.report = data;
  state.filter = "all";
  state.search = "";
  state.expanded.clear();

  $("result-search").value = "";

  document.querySelectorAll(".filter").forEach(button => {
    const active = button.dataset.filter === "all";
    button.classList.toggle("active", active);
    button.setAttribute("aria-pressed", String(active));
  });

  drawSummary(data.summary);
  renderRows();
  renderDomains(data.domains);

  reportSection.hidden = false;
  reportSection.scrollIntoView({
    behavior: window.matchMedia("(prefers-reduced-motion: reduce)").matches
      ? "auto" : "smooth",
    block: "start"
  });
}

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  showError("");

  const addresses = parseAddresses(input.value);

  if (addresses.length === 0) {
    showError("Enter at least one email address.");
    return;
  }

  if (addresses.length > 50) {
    showError("Maximum 50 unique email addresses allowed.");
    return;
  }

  reportSection.hidden = true;
  state.report = null;
  setBusy(true);

  try {
    const response = await fetch("/api/analyze", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ emails: addresses })
    });

    const data = await response.json();

    if (!response.ok) {
      throw new Error(data.error || "Analysis failed.");
    }

    showReport(data);

  } catch (error) {
    showError(error.message || "Unable to complete analysis.");
  } finally {
    setBusy(false);
  }
});

$("demo-button").addEventListener("click", () => {
  input.value = [
    "hello@gmail.com",
    "support@github.com",
    "invalid-email",
    "person@nonexistent-mailsense-987654321.example"
  ].join("\n");

  updateInputCount();
  showError("");
  input.focus();
  liveStatus.textContent = "Example addresses loaded. Run analysis to perform real checks.";
});

$("clear-button").addEventListener("click", () => {
  input.value = "";
  state.report = null;
  reportSection.hidden = true;
  showError("");
  liveStatus.textContent = "";
  updateInputCount();
  input.focus();
});

input.addEventListener("input", updateInputCount);

input.addEventListener("keydown", (event) => {
  if (event.key === "Enter" && (event.metaKey || event.ctrlKey)) {
    event.preventDefault();
    form.requestSubmit();
  }
});

document.querySelectorAll(".filter").forEach(button => {
  button.addEventListener("click", () => {
    state.filter = button.dataset.filter;

    document.querySelectorAll(".filter").forEach(item => {
      const active = item === button;
      item.classList.toggle("active", active);
      item.setAttribute("aria-pressed", String(active));
    });

    renderRows();
  });
});

$("result-search").addEventListener("input", (event) => {
  state.search = event.target.value.trim().toLowerCase();
  renderRows();
});

function csvCell(value) {
  let text = String(value ?? "");

  // Protect spreadsheet applications from formula injection.
  if (/^[\s\u0000-\u001f]*[=+\-@]/u.test(text)) {
    text = "'" + text;
  }

  return `"${text.replace(/"/g, '""')}"`;
}

$("export-button").addEventListener("click", () => {
  if (!state.report) return;

  const rows = [[
    "Email Address",
    "Classification",
    "Domain",
    "Reason",
    "Syntax",
    "Domain Signal",
    "Routing Signal",
    "Mailbox Signal"
  ]];

  state.report.results.forEach(result => {
    rows.push([
      result.email,
      labels[result.status],
      result.domain || "",
      result.reason,
      ...result.trace.map(step => step.state)
    ]);
  });

  const csv = rows
    .map(row => row.map(csvCell).join(","))
    .join("\r\n");

  const blob = new Blob(
    ["\uFEFF" + csv],
    { type: "text/csv;charset=utf-8" }
  );

  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");

  link.href = url;
  link.download = "shieldnex-mailsense-analysis.csv";
  document.body.appendChild(link);
  link.click();
  link.remove();

  setTimeout(() => URL.revokeObjectURL(url), 1000);
});

$("print-button").addEventListener("click", () => {
  if (!state.report) return;

  state.printing = true;
  renderRows();

  window.print();
});

window.addEventListener("afterprint", () => {
  state.printing = false;
  renderRows();
});

updateInputCount();
