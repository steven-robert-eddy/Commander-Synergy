const input = document.getElementById("card-input");
const suggestionsEl = document.getElementById("suggestions");
const searchBtn = document.getElementById("search-btn");
const sameCiEl = document.getElementById("same-ci");
const topNEl = document.getElementById("top-n");
const statusEl = document.getElementById("status");
const sourceCardEl = document.getElementById("source-card");
const resultsEl = document.getElementById("results");

let debounceTimer = null;
let activeSuggestionIndex = -1;

function debounce(fn, delayMs) {
  return (...args) => {
    clearTimeout(debounceTimer);
    debounceTimer = setTimeout(() => fn(...args), delayMs);
  };
}

async function fetchSuggestions(query) {
  if (!query || query.length < 2) {
    hideSuggestions();
    return;
  }
  const res = await fetch(`/api/cards/search?q=${encodeURIComponent(query)}&limit=8`);
  if (!res.ok) {
    hideSuggestions();
    return;
  }
  const data = await res.json();
  renderSuggestions(data.results);
}

function renderSuggestions(names) {
  suggestionsEl.innerHTML = "";
  activeSuggestionIndex = -1;
  if (!names.length) {
    hideSuggestions();
    return;
  }
  names.forEach((name) => {
    const li = document.createElement("li");
    li.textContent = name;
    li.addEventListener("mousedown", (event) => {
      // mousedown fires before input blur, so we can steal the click.
      event.preventDefault();
      input.value = name;
      hideSuggestions();
      runSearch();
    });
    suggestionsEl.appendChild(li);
  });
  suggestionsEl.classList.remove("hidden");
}

function hideSuggestions() {
  suggestionsEl.classList.add("hidden");
  suggestionsEl.innerHTML = "";
  activeSuggestionIndex = -1;
}

function moveSuggestionSelection(delta) {
  const items = Array.from(suggestionsEl.children);
  if (!items.length) return;
  items[activeSuggestionIndex]?.classList.remove("active");
  activeSuggestionIndex = (activeSuggestionIndex + delta + items.length) % items.length;
  const active = items[activeSuggestionIndex];
  active.classList.add("active");
  active.scrollIntoView({ block: "nearest" });
}

input.addEventListener("input", debounce((event) => fetchSuggestions(event.target.value.trim()), 200));

input.addEventListener("keydown", (event) => {
  const suggestionsVisible = !suggestionsEl.classList.contains("hidden");
  if (event.key === "ArrowDown" && suggestionsVisible) {
    event.preventDefault();
    moveSuggestionSelection(1);
  } else if (event.key === "ArrowUp" && suggestionsVisible) {
    event.preventDefault();
    moveSuggestionSelection(-1);
  } else if (event.key === "Enter") {
    event.preventDefault();
    const items = Array.from(suggestionsEl.children);
    if (suggestionsVisible && activeSuggestionIndex >= 0 && items[activeSuggestionIndex]) {
      input.value = items[activeSuggestionIndex].textContent;
    }
    hideSuggestions();
    runSearch();
  } else if (event.key === "Escape") {
    hideSuggestions();
  }
});

document.addEventListener("click", (event) => {
  if (!event.target.closest(".autocomplete")) {
    hideSuggestions();
  }
});

searchBtn.addEventListener("click", runSearch);

function setStatus(message, isError = false) {
  if (!message) {
    statusEl.classList.add("hidden");
    statusEl.textContent = "";
    return;
  }
  statusEl.textContent = message;
  statusEl.classList.remove("hidden");
  statusEl.classList.toggle("error", isError);
}

async function runSearch() {
  const name = input.value.trim();
  if (!name) return;

  hideSuggestions();
  setStatus("Searching...");
  sourceCardEl.classList.add("hidden");
  resultsEl.innerHTML = "";

  const params = new URLSearchParams({
    name,
    top: topNEl.value || "20",
    same_color_identity: sameCiEl.checked ? "true" : "false",
  });

  let res;
  try {
    res = await fetch(`/api/synergy?${params.toString()}`);
  } catch (err) {
    setStatus("Could not reach the server.", true);
    return;
  }

  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    setStatus(body.detail || `Request failed (${res.status})`, true);
    return;
  }

  const data = await res.json();
  setStatus("");
  renderResults(data);
}

function renderResults(data) {
  sourceCardEl.innerHTML = `
    <div class="result-name">${escapeHtml(data.source.name)}</div>
    <div class="type-line">${escapeHtml(data.source.type_line)}</div>
  `;
  sourceCardEl.classList.remove("hidden");

  if (!data.matches.length) {
    setStatus("No synergistic cards found.");
    return;
  }

  resultsEl.innerHTML = "";
  data.matches.forEach((m, index) => {
    const li = document.createElement("li");
    li.innerHTML = `
      <div class="result-header">
        <span class="result-name">${index + 1}. ${escapeHtml(m.name)}</span>
        <span class="result-score">score ${m.score}</span>
      </div>
      <div class="result-type-line">${escapeHtml(m.type_line)}</div>
      <div class="result-explanation">${escapeHtml(m.explanation)}</div>
    `;
    resultsEl.appendChild(li);
  });
}

function escapeHtml(str) {
  const div = document.createElement("div");
  div.textContent = str ?? "";
  return div.innerHTML;
}
