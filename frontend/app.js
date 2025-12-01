const apiSelect = document.getElementById("api-select");
const apiKeyInput = document.getElementById("api-key");
const chatWindow = document.getElementById("chat-window");
const userInput = document.getElementById("user-input");
const sendBtn = document.getElementById("send-btn");
const baseUrlEl = document.getElementById("base-url");
const authTypeEl = document.getElementById("auth-type");
const authKeyEl = document.getElementById("auth-key");
const endpointList = document.getElementById("endpoint-list");
const apiNameEl = document.getElementById("api-name");
const authPill = document.getElementById("auth-pill");
const promptButtons = document.getElementById("prompt-buttons");
const backendUrlInput = document.getElementById("backend-url");
const refreshBtn = document.getElementById("refresh-btn");
const statusDot = document.getElementById("status-dot");
const statusText = document.getElementById("status-text");
const apiCount = document.getElementById("api-count");
const emptyState = document.getElementById("empty-state");
const verboseToggle = document.getElementById("verbose-toggle");
const verboseControl = document.getElementById("verbose-control");
const modeSelect = document.getElementById("mode-select");
const systemPromptField = document.getElementById("system-prompt-field");
const systemPromptInput = document.getElementById("system-prompt");

const STORAGE_KEYS = {
  backendUrl: "chatmyapi.backendUrl",
};

const state = {
  apis: [],
  selectedApi: null,
};

const DEFAULT_BACKEND = `${window.location.protocol}//${window.location.hostname || "localhost"}:8000`;

function getBackendUrl() {
  return backendUrlInput.value.trim() || DEFAULT_BACKEND;
}

function persistBackendUrl() {
  localStorage.setItem(STORAGE_KEYS.backendUrl, backendUrlInput.value.trim());
}

function setStatus(message, tone = "neutral") {
  statusText.textContent = message;
  statusDot.className = `status-dot ${tone}`;
}

function fetchWithBase(path, options) {
  const base = getBackendUrl().replace(/\/$/, "");
  const url = `${base}${path}`;
  return fetch(url, options);
}

function renderApiCount() {
  apiCount.textContent = `${state.apis.length} API${state.apis.length === 1 ? "" : "s"} loaded`;
}

function renderApiOptions() {
  apiSelect.innerHTML = "";
  state.apis.forEach((api, index) => {
    const option = document.createElement("option");
    option.value = api.name;
    option.textContent = api.name;
    if (index === 0 && !state.selectedApi) {
      option.selected = true;
      state.selectedApi = api.name;
    } else if (api.name === state.selectedApi) {
      option.selected = true;
    }
    apiSelect.appendChild(option);
  });
  renderApiCount();
}

function setApiKeyState(api) {
  const requiresKey = api && api.auth_type !== "none";
  apiKeyInput.disabled = !requiresKey;
  apiKeyInput.placeholder = requiresKey ? "Paste your API key" : "No API key required";
  if (!requiresKey) {
    apiKeyInput.value = "";
  }
}

function renderApiDetails() {
  const api = state.apis.find((item) => item.name === state.selectedApi);
  if (!api) {
    apiNameEl.textContent = "No API selected";
    baseUrlEl.textContent = "—";
    authTypeEl.textContent = "—";
    authKeyEl.textContent = "—";
    setApiKeyState(null);
    endpointList.innerHTML = "<li class=\"muted\">No endpoints available yet.</li>";
    promptButtons.innerHTML = "";
    return;
  }

  apiNameEl.textContent = api.name;
  baseUrlEl.textContent = api.base_url;
  authTypeEl.textContent = api.auth_type.toUpperCase();
  authKeyEl.textContent = api.auth_key_name;
  authPill.textContent = api.auth_type === "none" ? "No Auth" : `${api.auth_type} auth`;
  setApiKeyState(api);

  endpointList.innerHTML = "";
  if (api.example_endpoints.length === 0) {
    const empty = document.createElement("li");
    empty.className = "muted";
    empty.textContent = "No examples provided for this API yet.";
    endpointList.appendChild(empty);
  } else {
    api.example_endpoints.forEach((endpoint) => {
      const item = document.createElement("li");
      item.innerHTML = `<div><strong>${endpoint.name}</strong><p>${endpoint.description || ""}</p></div><code>${endpoint.method} ${endpoint.path}</code>`;
      endpointList.appendChild(item);
    });
  }

  renderPromptIdeas(api);
}

function renderPromptIdeas(api) {
  promptButtons.innerHTML = "";
  const ideas = api?.example_endpoints?.slice(0, 4).map((endpoint) => {
    const description = endpoint.description || endpoint.name;
    return `Find the top rated ${description?.toLowerCase()} using ${api.name}`;
  });

  const fallback = [
    "What are the top-rated movies this week?",
    "Show me the cheapest coin by market cap",
    "Give me tomorrow's weather forecast in Berlin",
    "List the most popular items right now",
  ];

  (ideas && ideas.length > 0 ? ideas : fallback).forEach((text) => {
    const button = document.createElement("button");
    button.className = "ghost";
    button.type = "button";
    button.textContent = text;
    button.addEventListener("click", () => {
      userInput.value = text;
      userInput.focus();
    });
    promptButtons.appendChild(button);
  });
}

function addMessage(role, content) {
  const bubble = document.createElement("div");
  bubble.className = `bubble ${role}`;

  const header = document.createElement("div");
  header.className = "bubble-header";
  header.textContent = role === "user" ? "You" : "ChatMyAPI";
  bubble.appendChild(header);

  const body = document.createElement("div");
  body.className = "bubble-body";
  body.textContent = content;
  bubble.appendChild(body);

  chatWindow.appendChild(bubble);
  emptyState.classList.add("hidden");
  chatWindow.scrollTop = chatWindow.scrollHeight;
}

function formatJsonValue(value) {
  if (value === null || value === undefined) return "—";
  if (Array.isArray(value)) return `${value.length} item(s)`;
  if (typeof value === "object") return `${Object.keys(value).length} key(s)`;
  if (typeof value === "string" && value.length > 120) return `${value.slice(0, 117)}...`;
  return value;
}

function formatMilliseconds(value) {
  if (!value && value !== 0) return "—";
  return `${Number(value).toFixed(2)} ms`;
}

function createMetaItem(label, value) {
  const block = document.createElement("div");
  block.className = "meta-block";
  const dt = document.createElement("dt");
  dt.textContent = label;
  const dd = document.createElement("dd");
  dd.textContent = value ?? "—";
  block.appendChild(dt);
  block.appendChild(dd);
  return block;
}

function createDetailsPanel(title, contentEl) {
  const details = document.createElement("details");
  details.className = "collapsible";
  const summary = document.createElement("summary");
  summary.textContent = title;
  details.appendChild(summary);
  details.appendChild(contentEl);
  return details;
}

function renderRanking(rankedItems = []) {
  if (!rankedItems || rankedItems.length === 0) return null;
  const wrapper = document.createElement("div");
  wrapper.className = "ranking";
  const heading = document.createElement("div");
  heading.className = "insights-title";
  heading.textContent = "Top results";
  wrapper.appendChild(heading);

  const list = document.createElement("ol");
  list.className = "ranking-list";

  rankedItems.slice(0, 5).forEach((item) => {
    const li = document.createElement("li");
    li.className = "ranking-item";

    const badge = document.createElement("span");
    badge.className = "rank-pill";
    badge.textContent = `#${item.rank}`;

    const text = document.createElement("div");
    text.className = "ranking-text";
    const label = document.createElement("strong");
    label.textContent = item.name;
    const meta = document.createElement("div");
    meta.className = "muted";
    const score = item.score_key ? `${item.score_key}: ${formatJsonValue(item.score)}` : "";
    const extras = [];
    ["market_cap", "current_price", "regularMarketPrice", "popularity", "vote_count"].forEach((key) => {
      if (item.metadata?.[key]) extras.push(`${key}: ${formatJsonValue(item.metadata[key])}`);
    });
    const timeHint = item.metadata?.release_date || item.metadata?.first_air_date;
    meta.textContent = [score, ...extras, timeHint]
      .filter(Boolean)
      .join(" • ");

    text.appendChild(label);
    if (meta.textContent) {
      text.appendChild(meta);
    }

    li.appendChild(badge);
    li.appendChild(text);
    list.appendChild(li);
  });

  wrapper.appendChild(list);
  return wrapper;
}

function renderReasoningBlock(reasoning, verboseEnabled) {
  const text = reasoning || (verboseEnabled ? "Model did not return explicit reasoning." : "Enable verbose mode to request the model's step-by-step thinking.");

  const paragraph = document.createElement("p");
  paragraph.className = "muted reasoning-text";
  paragraph.textContent = text;

  const panel = createDetailsPanel("Chain-of-thought", paragraph);
  panel.open = Boolean(reasoning);
  return panel;
}

function addResponseBlock(payload) {
  const {
    api_call: apiCall,
    human_summary,
    raw_json,
    notes,
    ranked_items,
    metadata,
    reasoning,
  } = payload;
  const container = document.createElement("div");
  container.className = "response-block";

  const summary = document.createElement("p");
  summary.className = "response-summary";
  summary.textContent = human_summary;
  container.appendChild(summary);

  const meta = document.createElement("dl");
  meta.className = "meta meta-grid";
  meta.appendChild(createMetaItem("Endpoint", apiCall.endpoint));
  meta.appendChild(createMetaItem("Method", apiCall.method));
  meta.appendChild(
    createMetaItem("Duration", formatMilliseconds(metadata?.duration_ms ?? metadata?.pipeline_ms))
  );
  meta.appendChild(createMetaItem("Status", metadata?.status_code ?? "—"));
  meta.appendChild(createMetaItem("Cache", metadata?.from_cache ? "Cached" : "Live"));
  container.appendChild(meta);

  const ranking = renderRanking(ranked_items);
  if (ranking) {
    container.appendChild(ranking);
  }

  if (metadata?.metrics) {
    const metrics = document.createElement("div");
    metrics.className = "metrics";
    const header = document.createElement("div");
    header.className = "insights-title";
    header.textContent = "Auto-ranked highlights";
    const list = document.createElement("ul");
    list.className = "metrics-list";
    Object.entries(metadata.metrics).forEach(([label, value]) => {
      const li = document.createElement("li");
      const name = value?.name || "Item";
      const val = value?.value || value?.raw?.value;
      li.textContent = `${label.replace(/_/g, " ")}: ${name}${val ? ` (${val})` : ""}`;
      list.appendChild(li);
    });
    metrics.appendChild(header);
    metrics.appendChild(list);
    container.appendChild(metrics);
  }

  const notePara = document.createElement("p");
  notePara.textContent = notes || "No explicit reasoning provided by the model.";
  notePara.className = "muted";
  const reason = createDetailsPanel("Reasoning", notePara);
  reason.open = Boolean(notes);
  container.appendChild(reason);

  container.appendChild(renderReasoningBlock(reasoning, metadata?.verbose));

  const callPre = document.createElement("pre");
  callPre.textContent = JSON.stringify(apiCall, null, 2);
  callPre.className = "api-call";
  container.appendChild(createDetailsPanel("API call payload", callPre));

  const rawPre = document.createElement("pre");
  rawPre.textContent = JSON.stringify(raw_json, null, 2);
  rawPre.className = "raw";
  container.appendChild(createDetailsPanel("Raw JSON", rawPre));

  chatWindow.appendChild(container);
  chatWindow.scrollTop = chatWindow.scrollHeight;
}

async function saveKey(apiName, apiKey) {
  if (!apiKey) return;
  try {
    await fetchWithBase("/save_key", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ api_name: apiName, api_key: apiKey }),
    });
  } catch (err) {
    console.error("Failed to save key", err);
  }
}

function updateModeUi() {
  const isOllama = modeSelect.value === "ollama";
  systemPromptField.classList.toggle("hidden", !isOllama);
  verboseControl.classList.toggle("hidden", isOllama);
  sendBtn.textContent = isOllama ? "Send to Ollama" : "Send";
  userInput.placeholder = isOllama
    ? "Ask anything—response will come directly from your local model"
    : "Ask something like 'Show me today's weather in Tokyo'";
}

async function sendMessage() {
  const message = userInput.value.trim();
  if (!message) return;
  const selectedApi = apiSelect.value;
  const apiKey = apiKeyInput.value.trim();
  const mode = modeSelect.value;

  addMessage("user", message);
  userInput.value = "";
  sendBtn.disabled = true;

  try {
    if (mode === "ollama") {
      const systemPrompt = systemPromptInput.value.trim();
      const res = await fetchWithBase("/ollama_chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message, system_prompt: systemPrompt || null }),
      });

      const data = await res.json();
      if (!res.ok) {
        addMessage("bot", data.detail || "Ollama request failed. Check the backend.");
        return;
      }

      addMessage("bot", data.response_text || "No response from Ollama.");
    } else {
      await saveKey(selectedApi, apiKey);
      const res = await fetchWithBase("/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message, selected_api: selectedApi, verbose: verboseToggle?.checked || false }),
      });

      const data = await res.json();
      if (!res.ok) {
        addMessage("bot", data.detail || "Something went wrong. Check your backend URL.");
        return;
      }
      addMessage("bot", `API call prepared for ${selectedApi}`);
      addResponseBlock(data);
    }
  } catch (err) {
    console.error(err);
    addMessage("bot", "Failed to reach backend. Confirm the URL and try again.");
  } finally {
    sendBtn.disabled = false;
  }
}

async function checkHealth() {
  try {
    const res = await fetchWithBase("/health");
    if (!res.ok) throw new Error("Health check failed");
    setStatus("Backend reachable", "success");
  } catch (err) {
    console.error(err);
    setStatus("Cannot reach backend. Update the URL and refresh.", "danger");
  }
}

async function fetchApis() {
  setStatus("Loading APIs…", "neutral");
  try {
    const res = await fetchWithBase("/apis");
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || "Failed to load APIs");

    state.apis = data;
    renderApiOptions();
    renderApiDetails();
    setStatus("APIs loaded", "success");
  } catch (err) {
    console.error("Failed to fetch APIs", err);
    state.apis = [];
    renderApiOptions();
    renderApiDetails();
    setStatus("Unable to load APIs. Check the backend URL.", "danger");
  }
}

function initBackendInput() {
  const storedUrl = localStorage.getItem(STORAGE_KEYS.backendUrl);
  backendUrlInput.value = storedUrl || DEFAULT_BACKEND;
  backendUrlInput.addEventListener("change", () => {
    persistBackendUrl();
    fetchApis();
    checkHealth();
  });
}

function wireEvents() {
  sendBtn.addEventListener("click", sendMessage);
  userInput.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      sendMessage();
    }
  });

  apiSelect.addEventListener("change", (e) => {
    state.selectedApi = e.target.value;
    renderApiDetails();
  });

  refreshBtn.addEventListener("click", () => {
    fetchApis();
    checkHealth();
  });

  modeSelect.addEventListener("change", updateModeUi);
}

function bootstrap() {
  initBackendInput();
  wireEvents();
  updateModeUi();
  fetchApis();
  checkHealth();
}

bootstrap();
