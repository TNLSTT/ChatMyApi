const apiSelect = document.getElementById("api-select");
const apiKeyInput = document.getElementById("api-key");
const chatWindow = document.getElementById("chat-window");
const userInput = document.getElementById("user-input");
const sendBtn = document.getElementById("send-btn");

async function fetchApis() {
  try {
    const res = await fetch("/apis");
    const data = await res.json();
    apiSelect.innerHTML = "";
    data.forEach((api) => {
      const option = document.createElement("option");
      option.value = api.name;
      option.textContent = api.name;
      apiSelect.appendChild(option);
    });
  } catch (err) {
    console.error("Failed to fetch APIs", err);
  }
}

function addMessage(role, content) {
  const bubble = document.createElement("div");
  bubble.className = `bubble ${role}`;
  bubble.textContent = content;
  chatWindow.appendChild(bubble);
  chatWindow.scrollTop = chatWindow.scrollHeight;
}

function addResponseBlock(apiCall, responseText, responseJson) {
  const container = document.createElement("div");
  container.className = "response-block";

  const summary = document.createElement("p");
  summary.textContent = responseText;
  container.appendChild(summary);

  const apiCallDetails = document.createElement("pre");
  apiCallDetails.textContent = JSON.stringify(apiCall, null, 2);
  apiCallDetails.className = "api-call";
  container.appendChild(apiCallDetails);

  const toggleBtn = document.createElement("button");
  toggleBtn.textContent = "Show Raw JSON";
  toggleBtn.className = "toggle";

  const raw = document.createElement("pre");
  raw.textContent = JSON.stringify(responseJson, null, 2);
  raw.className = "raw hidden";

  toggleBtn.addEventListener("click", () => {
    const isHidden = raw.classList.toggle("hidden");
    toggleBtn.textContent = isHidden ? "Show Raw JSON" : "Hide Raw JSON";
  });

  container.appendChild(toggleBtn);
  container.appendChild(raw);
  chatWindow.appendChild(container);
  chatWindow.scrollTop = chatWindow.scrollHeight;
}

async function saveKey(apiName, apiKey) {
  if (!apiKey) return;
  try {
    await fetch("/save_key", {
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
    const res = await fetch("/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message, selected_api: selectedApi }),
    });

    const data = await res.json();
    if (!res.ok) {
      addMessage("bot", data.detail || "Something went wrong");
      return;
    }
    addMessage("bot", `API call prepared for ${selectedApi}`);
    addResponseBlock(data.api_call, data.response_text, data.response_json);
  } catch (err) {
    console.error(err);
    addMessage("bot", "Failed to reach backend");
  } finally {
    sendBtn.disabled = false;
  }
}

sendBtn.addEventListener("click", sendMessage);
userInput.addEventListener("keydown", (e) => {
  if (e.key === "Enter" && !e.shiftKey) {
    e.preventDefault();
    sendMessage();
  }
});

fetchApis();
