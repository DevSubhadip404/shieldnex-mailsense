const form = document.getElementById("analysis-form");
const input = document.getElementById("email-input");
const countLabel = document.getElementById("address-count");
const runButton = document.getElementById("run-button");
const errorBox = document.getElementById("error-message");
const report = document.getElementById("results-section");
const tableBody = document.getElementById("results-body");
const exportButton = document.getElementById("export-button");

let latestResults = [];

const statusLabels = {
  likely_delivered: "LIKELY DELIVERED",
  likely_bounce: "LIKELY BOUNCE",
  unknown: "UNKNOWN"
};

function parseAddresses(value) {
  const parts = value.split(/[\s,;]+/);
  const addresses = [];
  const seen = new Set();

  for (const part of parts) {
    const address = part.trim();
    const key = address.toLowerCase();

    if (address && !seen.has(key)) {
      seen.add(key);
      addresses.push(address);
    }
  }

  return addresses;
}

function showError(message) {
  errorBox.textContent = message;
  errorBox.hidden = !message;
}

function showCount() {
  const count = parseAddresses(input.value).length;
  countLabel.textContent = `${count} / 50 ADDRESSES`;
  countLabel.style.color = count > 50 ? "#b45045" : "";
}

function setLoading(loading) {
  runButton.disabled = loading;
  runButton.textContent = loading
    ? "ANALYZING..."
    : "RUN ANALYSIS ↗";
}

function addCell(row, text, className = "") {
  const cell = document.createElement("td");
  cell.textContent = text;

  if (className) {
    cell.className = className;
  }

  row.appendChild(cell);
  return cell;
}

function renderResults(data) {
  latestResults = data.results;
  tableBody.replaceChildren();

  document.getElementById("total-count").textContent =
    String(data.summary.total).padStart(2, "0");

  document.getElementById("delivered-count").textContent =
    String(data.summary.likely_delivered).padStart(2, "0");

  document.getElementById("bounce-count").textContent =
    String(data.summary.likely_bounce).padStart(2, "0");

  document.getElementById("unknown-count").textContent =
    String(data.summary.unknown).padStart(2, "0");

  for (let index = 0; index < data.results.length; index++) {
    const result = data.results[index];
    const row = document.createElement("tr");

    addCell(row, String(index + 1).padStart(3, "0"));
    addCell(row, result.email);

    const statusCell = document.createElement("td");
    const badge = document.createElement("span");

    badge.className = `status-badge ${result.status}`;
    badge.textContent = statusLabels[result.status] || "UNKNOWN";

    statusCell.appendChild(badge);
    row.appendChild(statusCell);

    addCell(row, result.reason);
    tableBody.appendChild(row);
  }

  report.hidden = false;
  report.scrollIntoView({
    behavior: "smooth",
    block: "start"
  });
}

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  showError("");

  const addresses = parseAddresses(input.value);

  if (!addresses.length) {
    showError("Enter at least one email address.");
    return;
  }

  if (addresses.length > 50) {
    showError("You can analyze a maximum of 50 unique addresses.");
    return;
  }

  report.hidden = true;
  latestResults = [];
  setLoading(true);

  try {
    const response = await fetch("/api/analyze", {
      method: "POST",
      headers: {
        "Content-Type": "application/json"
      },
      body: JSON.stringify({
        emails: addresses
      })
    });

    const data = await response.json();

    if (!response.ok) {
      throw new Error(data.error || "Analysis failed.");
    }

    renderResults(data);

  } catch (error) {
    showError(error.message || "Unable to complete the analysis.");
  } finally {
    setLoading(false);
  }
});

input.addEventListener("input", showCount);

function csvCell(value) {
  let text = String(value ?? "");

  // Prevent CSV spreadsheet formula injection.
  if (/^\s*[=+\-@]/.test(text)) {
    text = "'" + text;
  }

  return `"${text.replace(/"/g, '""')}"`;
}

exportButton.addEventListener("click", () => {
  if (!latestResults.length) {
    return;
  }

  const rows = [
    ["Email Address", "Classification", "Explanation"]
  ];

  for (const result of latestResults) {
    rows.push([
      result.email,
      statusLabels[result.status] || "UNKNOWN",
      result.reason
    ]);
  }

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
  link.download = "shieldnex-mailsense-report.csv";

  document.body.appendChild(link);
  link.click();
  link.remove();

  setTimeout(() => URL.revokeObjectURL(url), 1000);
});

showCount();
