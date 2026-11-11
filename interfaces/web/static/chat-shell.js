(() => {
  const STORAGE_KEY = "cynx-core-conversations-v1";
  const CURRENT_KEY = "cynx-core-current-conversation";
  const MAX_CONVERSATIONS = 40;
  const MAX_MESSAGES = 500;
  let conversations = [];
  let activeId = null;
  let restoring = false;
  let busy = false;
  let storeAvailable = true;
  let currentModel = null;
  const $ = (selector, root=document) => root.querySelector(selector);
  const chat = () => $("#chat");
  const safeUUID = () => window.crypto?.randomUUID?.() || "xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx".replace(/[xy]/g, char => {
    const random = Math.random() * 16 | 0;
    return (char === "x" ? random : (random & 3 | 8)).toString(16);
  });

  function readStore() {
    try {
      const parsed = JSON.parse(localStorage.getItem(STORAGE_KEY) || "[]");
      conversations = Array.isArray(parsed) ? parsed.filter(item => item && typeof item.id === "string" && Array.isArray(item.messages)) : [];
      activeId = localStorage.getItem(CURRENT_KEY);
    } catch {
      storeAvailable = false;
      conversations = [];
    }
  }
  function persist() {
    try {
      conversations.sort((a, b) => (b.updatedAt || 0) - (a.updatedAt || 0));
      conversations = conversations.slice(0, MAX_CONVERSATIONS);
      localStorage.setItem(STORAGE_KEY, JSON.stringify(conversations));
      if (activeId) localStorage.setItem(CURRENT_KEY, activeId);
      storeAvailable = true;
    } catch {
      storeAvailable = false;
      const note = $(".cx-local-note");
      if (note) note.textContent = "Browser storage is full or unavailable; this conversation may not be saved.";
    }
  }
  function activeConversation() {
    return conversations.find(item => item.id === activeId);
  }
  function titleFrom(message) {
    return String(message || "").replace(/^You:\s*/, "").replace(/\s+/g, " ").trim().slice(0, 52) || "New conversation";
  }
  function updateWelcome() {
    const welcome = $("#welcome-screen"), messageList = chat();
    const hasMessages = Boolean(messageList?.children.length);
    if (welcome) welcome.hidden = hasMessages;
    if (messageList) messageList.classList.toggle("has-messages", hasMessages);
  }
  function setHeading(title) {
    const heading = $("#conversation-heading");
    if (heading) heading.textContent = title || "New conversation";
  }
  function displayMessage(message) {
    if (typeof window.addMessage === "function") window.addMessage(message);
  }
  function renderConversationHistory(filter="") {
    const list = $("#chat-history");
    if (!list) return;
    list.replaceChildren();
    const normalized = filter.trim().toLowerCase();
    const filtered = conversations.filter(item => (item.messages.length || item.id === activeId) && (!normalized || `${item.title} ${item.messages.join(" ")}`.toLowerCase().includes(normalized)));
    if (!filtered.length) {
      const empty = document.createElement("div");
      empty.className = "cx-history-empty";
      empty.textContent = normalized ? "No conversations match that search." : "Your conversations will appear here.";
      list.append(empty);
      return;
    }
    for (const item of filtered) {
      const row = document.createElement("div");
      row.className = "cx-history-row";
      const open = document.createElement("button");
      open.type = "button";
      open.className = "cx-history-item";
      open.setAttribute("aria-current", String(item.id === activeId));
      open.disabled = busy;
      const title = document.createElement("span");
      title.className = "cx-history-title";
      title.textContent = item.title || "New conversation";
      const time = document.createElement("span");
      time.className = "cx-history-time";
      time.textContent = item.updatedAt ? new Date(item.updatedAt).toLocaleString([], {month:"short", day:"numeric", hour:"numeric", minute:"2-digit"}) : "Just now";
      open.append(title, time);
      open.addEventListener("click", () => openConversation(item.id));
      row.append(open);
      const remove = document.createElement("button");
      remove.type = "button";
      remove.className = "cx-history-delete";
      remove.setAttribute("aria-label", `Delete ${item.title || "conversation"} from this browser`);
      remove.textContent = "×";
      remove.disabled = busy;
      remove.addEventListener("click", () => deleteConversation(item.id));
      row.append(remove);
      list.append(row);
    }
  }
  function ensureConversation() {
    if (!activeConversation()) {
      activeId = safeUUID();
      conversations.unshift({id:activeId, title:"New conversation", messages:[], updatedAt:Date.now()});
      persist();
    }
  }
  function newConversation() {
    if (busy) return;
    conversations = conversations.filter(item => item.messages?.length || item.id !== activeId);
    activeId = safeUUID();
    conversations.unshift({id:activeId, title:"New conversation", messages:[], updatedAt:Date.now()});
    persist();
    if (chat()) chat().replaceChildren();
    setHeading("New conversation");
    updateWelcome();
    renderConversationHistory($("#history-search")?.value || "");
    $("#message")?.focus();
    closeSidebar();
  }
  function openConversation(id) {
    if (busy || id === activeId) return;
    const item = conversations.find(conversation => conversation.id === id);
    if (!item) return;
    activeId = id;
    persist();
    restoring = true;
    if (chat()) chat().replaceChildren();
    setHeading(item.title);
    item.messages.slice(-MAX_MESSAGES).forEach(displayMessage);
    restoring = false;
    updateWelcome();
    renderConversationHistory($("#history-search")?.value || "");
    closeSidebar();
    chat()?.scrollTo({top:chat().scrollHeight, behavior:"auto"});
  }
  function deleteConversation(id) {
    if (busy) return;
    const existing = conversations.find(item => item.id === id);
    if (!window.confirm(`Remove “${existing?.title || "this conversation"}” from this browser? This cannot be undone.`)) return;
    conversations = conversations.filter(item => item.id !== id);
    if (activeId === id) {
      activeId = null;
      newConversation();
    } else {
      persist();
      renderConversationHistory($("#history-search")?.value || "");
    }
  }
  function recordMessage(message) {
    if (restoring || typeof message !== "string") return;
    ensureConversation();
    const item = activeConversation();
    if (!item) return;
    item.messages.push(message.slice(0, 50000));
    item.messages = item.messages.slice(-MAX_MESSAGES);
    if (message.startsWith("You:") && (item.title === "New conversation" || !item.title)) {
      item.title = titleFrom(message);
      setHeading(item.title);
    }
    item.updatedAt = Date.now();
    persist();
    updateWelcome();
    renderConversationHistory($("#history-search")?.value || "");
  }
  function setRequestBusy(value) {
    busy = Boolean(value);
    const button = $("#new-conversation");
    if (button) button.disabled = busy;
    const stop = $("#stop-generation");
    if (stop) stop.hidden = !busy;
    const send = $("#sendButton");
    if (send) send.disabled = busy;
    renderConversationHistory($("#history-search")?.value || "");
  }
  function closeSidebar() {
    $("#chat-sidebar")?.classList.remove("is-open");
    $("#sidebar-toggle")?.setAttribute("aria-expanded", "false");
    const scrim = $("#sidebar-scrim");
    if (scrim) scrim.hidden = true;
  }
  async function loadCoreStatus() {
    const select = $("#model-select"), status = $("#model-status"), toolStatus = $("#tool-availability");
    try {
      const response = await fetch("/api/dx/health", {headers:{"Accept":"application/json"}});
      if (!response.ok) throw new Error("Core status is unavailable.");
      const health = await response.json();
      currentModel = health.model || null;
      if (select) {
        const models = Array.isArray(health.models) ? [...health.models] : [];
        if (health.model && !models.includes(health.model)) models.unshift(health.model);
        select.replaceChildren();
        if (!models.length) {
          const option = document.createElement("option"); option.textContent = health.model || "Model unavailable"; option.value = health.model || ""; select.append(option); select.disabled = true;
        } else {
          for (const model of models) { const option = document.createElement("option"); option.value = model; option.textContent = model; option.selected = model === health.model; select.append(option); }
          select.disabled = false;
        }
      }
      if (status) { status.dataset.state = health.ollama === "online" ? "ok" : "error"; status.textContent = health.ollama === "online" ? "Connected to your local CYN-X core" : "Local model service is offline"; }
      if (toolStatus) toolStatus.textContent = `${Number(health.tool_count || 0)} tools available when useful`;
      const pill = $("#top-model-pill"); if (pill) pill.textContent = health.model || "LOCAL CORE";
    } catch {
      if (status) { status.dataset.state = "error"; status.textContent = "Could not reach local core status"; }
      if (toolStatus) toolStatus.textContent = "Tool availability unavailable";
    }
  }
  async function selectModel(event) {
    const status = $("#model-status"), select = event.currentTarget;
    if (busy) { if (currentModel) select.value = currentModel; status.textContent = "Wait for the current response to finish before switching models."; return; }
    const model = select.value;
    if (status) { status.textContent = "Switching model…"; status.dataset.state = ""; }
    select.disabled = true;
    try {
      const response = await fetch("/api/dx/model", {method:"POST", headers:{"Content-Type":"application/json"}, body:JSON.stringify({model})});
      const result = await response.json();
      if (!response.ok || !result.ok) throw new Error(result.detail || "Model change was not confirmed.");
      currentModel = result.model;
      if (status) { status.dataset.state = "ok"; status.textContent = `Active model: ${result.model}`; }
      const pill = $("#top-model-pill"); if (pill) pill.textContent = result.model;
    } catch (error) {
      if (status) { status.dataset.state = "error"; status.textContent = error.message || "Model change failed."; }
      await loadCoreStatus();
    } finally { select.disabled = false; }
  }
  function initialize() {
    readStore();
    ensureConversation();
    const existing = activeConversation();
    if (existing?.messages?.length) {
      restoring = true;
      existing.messages.slice(-MAX_MESSAGES).forEach(displayMessage);
      restoring = false;
      setHeading(existing.title);
    }
    updateWelcome();
    renderConversationHistory();
    if (!storeAvailable) { const note = $(".cx-local-note"); if (note) note.textContent = "Browser storage is unavailable; conversation history will only last for this page."; }

    $("#new-conversation")?.addEventListener("click", newConversation);
    $("#history-search")?.addEventListener("input", event => renderConversationHistory(event.target.value));
    $("#model-select")?.addEventListener("change", selectModel);
    $("#stop-generation")?.addEventListener("click", () => window.cancelActiveRequest?.());
    $("#sidebar-toggle")?.addEventListener("click", () => {
      const sidebar = $("#chat-sidebar"), scrim = $("#sidebar-scrim"), open = !sidebar.classList.contains("is-open");
      sidebar.classList.toggle("is-open", open);
      scrim.hidden = !open;
      $("#sidebar-toggle").setAttribute("aria-expanded", String(open));
      $("#sidebar-toggle").setAttribute("aria-label", open ? "Close navigation" : "Open navigation");
    });
    $("#sidebar-scrim")?.addEventListener("click", closeSidebar);
    $("#sidebar-scrim")?.addEventListener("keydown", event => { if (event.key === "Escape") closeSidebar(); });
    document.addEventListener("keydown", event => { if (event.key === "Escape" && $("#chat-sidebar")?.classList.contains("is-open")) closeSidebar(); });
    document.querySelectorAll("[data-prompt]").forEach(button => button.addEventListener("click", () => {
      const input = $("#message"); if (!input) return; input.value = button.dataset.prompt || ""; input.dispatchEvent(new Event("input", {bubbles:true})); input.focus();
    }));
    const input = $("#message");
    if (input) {
      const resize = () => { input.style.height = "auto"; input.style.height = `${Math.min(input.scrollHeight, 190)}px`; };
      input.addEventListener("input", resize);
      resize();
    }
    loadCoreStatus();
  }
  window.CynxShell = {conversationId:() => activeId, recordMessage, setRequestBusy, newConversation};
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", initialize, {once:true}); else initialize();
})();
