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
const ollamaInput = document.getElementById("ollama-input");
const ollamaSystem = document.getElementById("ollama-system");
const ollamaSendBtn = document.getElementById("ollama-send-btn");
const ollamaStatus = document.getElementById("ollama-status");
const ollamaResponse = document.getElementById("ollama-response");

const STORAGE_KEYS = {
  backendUrl: "chatmyapi.backendUrl",
};

const state = {
  apis: [],
  selectedApi: null,
};

function getBackendUrl() {
  return backendUrlInput.value.trim() || window.location.origin;
}

function persistBackendUrl() {
  localStorage.setItem(STORAGE_KEYS.backendUrl, backendUrlInput.value.trim());
}

function setStatus(message, tone = "neutral") {
  statusText.textContent = message;
  statusDot.className = `status-dot ${tone}`;
}

function setOllamaStatus(message, tone = "muted") {
  ollamaStatus.textContent = message;
  ollamaStatus.className = `muted ${tone}`;
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

function renderApiDetails() {
  const api = state.apis.find((item) => item.name === state.selectedApi);
  if (!api) {
    apiNameEl.textContent = "No API selected";
    baseUrlEl.textContent = "—";
    authTypeEl.textContent = "—";
    authKeyEl.textContent = "—";
    endpointList.innerHTML = "<li class=\"muted\">No endpoints available yet.</li>";
    promptButtons.innerHTML = "";
    return;
  }

  apiNameEl.textContent = api.name;
  baseUrlEl.textContent = api.base_url;
  authTypeEl.textContent = api.auth_type.toUpperCase();
  authKeyEl.textContent = api.auth_key_name;
  authPill.textContent = api.auth_type === "none" ? "No Auth" : `${api.auth_type} auth`;

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
    return `Can you call ${api.name} ${description?.toLowerCase()}`;
  });

  const fallback = [
    "What's trending this week?",
    "Summarize the latest results for me",
    "Find an example request I can try",
    "List endpoints that require authentication",
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

function addResponseBlock(apiCall, responseText, responseJson) {
  const container = document.createElement("div");
  container.className = "response-block";

  const summary = document.createElement("p");
  summary.className = "response-summary";
  summary.textContent = responseText;
  container.appendChild(summary);

  const callDetails = document.createElement("pre");
  callDetails.textContent = JSON.stringify(apiCall, null, 2);
  callDetails.className = "api-call";
  container.appendChild(callDetails);

  const toggleBtn = document.createElement("button");
  toggleBtn.textContent = "Show raw JSON";
  toggleBtn.className = "toggle ghost";

  const raw = document.createElement("pre");
  raw.textContent = JSON.stringify(responseJson, null, 2);
  raw.className = "raw hidden";

  toggleBtn.addEventListener("click", () => {
    const isHidden = raw.classList.toggle("hidden");
    toggleBtn.textContent = isHidden ? "Show raw JSON" : "Hide raw JSON";
  });

  container.appendChild(toggleBtn);
  container.appendChild(raw);
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

async function sendMessage() {
  const message = userInput.value.trim();
  if (!message) return;
  const selectedApi = apiSelect.value;
  const apiKey = apiKeyInput.value.trim();

  addMessage("user", message);
  userInput.value = "";
  sendBtn.disabled = true;

  try {
    await saveKey(selectedApi, apiKey);
    const res = await fetchWithBase("/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message, selected_api: selectedApi }),
    });

    const data = await res.json();
    if (!res.ok) {
      addMessage("bot", data.detail || "Something went wrong. Check your backend URL.");
      return;
    }
    addMessage("bot", `API call prepared for ${selectedApi}`);
    addResponseBlock(data.api_call, data.response_text, data.response_json);
  } catch (err) {
    console.error(err);
    addMessage("bot", "Failed to reach backend. Confirm the URL and try again.");
  } finally {
    sendBtn.disabled = false;
  }
}

async function sendOllamaMessage() {
  const message = ollamaInput.value.trim();
  const systemPrompt = ollamaSystem.value.trim();
  if (!message) return;

  setOllamaStatus("Sending to Ollama…");
  ollamaSendBtn.disabled = true;

  try {
    const res = await fetchWithBase("/ollama_chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message, system_prompt: systemPrompt || null }),
    });

    const data = await res.json();
    if (!res.ok) {
      setOllamaStatus(data.detail || "Ollama request failed", "danger");
      ollamaResponse.textContent = "";
      return;
    }

    ollamaResponse.textContent = data.response_text;
    ollamaResponse.classList.remove("muted");
    setOllamaStatus("Response received", "success");
  } catch (err) {
    console.error(err);
    setOllamaStatus("Failed to reach backend", "danger");
  } finally {
    ollamaSendBtn.disabled = false;
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
  backendUrlInput.value = storedUrl || "http://localhost:8000";
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

  ollamaSendBtn.addEventListener("click", sendOllamaMessage);
  ollamaInput.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      sendOllamaMessage();
    }
  });
}

function bootstrap() {
  initBackendInput();
  wireEvents();
  fetchApis();
  checkHealth();
}

bootstrap();
