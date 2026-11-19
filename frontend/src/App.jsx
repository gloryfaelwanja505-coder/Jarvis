import { useEffect, useRef, useState } from "react";
import {
  Activity,
  ArrowDown,
  AudioLines,
  Bot,
  Check,
  ChevronDown,
  CircleHelp,
  Command,
  Cpu,
  History,
  Menu,
  MessageSquareText,
  PhoneCall,
  Plus,
  Radio,
  Send,
  Settings2,
  ShieldCheck,
  Sparkles,
  StopCircle,
  UserRound,
  Wifi,
  WifiOff,
  Volume2,
  VolumeX,
  Home,
  Brain,
  Mail,
  MessagesSquare,
  Users,
  Search,
  FileText,
  Workflow,
  Cable,
  ScrollText,
  Mic,
  ChevronRight,
} from "lucide-react";
import {
  approveActionDraft,
  chooseAIModel,
  createActionDraft,
  deleteMemory,
  fetchAIStatus,
  fetchAIProviders,
  testAIProvider,
  chooseAIProvider,
  fetchActionDrafts,
  fetchConversation,
  fetchConversations,
  fetchHealth,
  fetchMemories,
  fetchSystemMetrics,
  fetchVoiceStatus,
  saveMemory,
  savePersonality,
  streamChat,
  synthesizeSpeech,
} from "./services/api.js";
import CallingDashboard from "./CallingDashboard.jsx";
import VoiceCapture from "./VoiceCapture.jsx";
import HomeScreen from "./HomeScreen.jsx";

const STORAGE_KEY = "jarvis.activeConversation";

function readStoredConversation() {
  try {
    return window.localStorage.getItem(STORAGE_KEY);
  } catch {
    return null;
  }
}

function formatTime(value) {
  return new Intl.DateTimeFormat(undefined, { hour: "2-digit", minute: "2-digit" }).format(
    new Date(value),
  );
}

function createTaskId() {
  if (window.crypto?.randomUUID) return window.crypto.randomUUID();
  const bytes = new Uint8Array(16);
  if (window.crypto?.getRandomValues) window.crypto.getRandomValues(bytes);
  else bytes.forEach((_, index) => { bytes[index] = Math.floor(Math.random() * 256); });
  bytes[6] = (bytes[6] & 0x0f) | 0x40;
  bytes[8] = (bytes[8] & 0x3f) | 0x80;
  const hex = Array.from(bytes, (byte) => byte.toString(16).padStart(2, "0")).join("");
  return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`;
}

export default function App() {
  const [health, setHealth] = useState(null);
  const [aiStatus, setAIStatus] = useState(null);
  const [providerCatalog, setProviderCatalog] = useState(null);
  const [voiceStatus, setVoiceStatus] = useState(null);
  const [systemMetrics, setSystemMetrics] = useState(null);
  const [memories, setMemories] = useState([]);
  const [memoryKey, setMemoryKey] = useState("");
  const [memoryValue, setMemoryValue] = useState("");
  const [memoryApproved, setMemoryApproved] = useState(false);
  const [personalityDraft, setPersonalityDraft] = useState("");
  const [actionDrafts, setActionDrafts] = useState([]);
  const [draftType, setDraftType] = useState("email");
  const [draftRecipient, setDraftRecipient] = useState("");
  const [draftSubject, setDraftSubject] = useState("");
  const [draftBody, setDraftBody] = useState("");
  const [speakingMessage, setSpeakingMessage] = useState(null);
  const [history, setHistory] = useState([]);
  const [conversationId, setConversationId] = useState(readStoredConversation);
  const [messages, setMessages] = useState([]);
  const [draft, setDraft] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [menuOpen, setMenuOpen] = useState(false);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [helpOpen, setHelpOpen] = useState(false);
  const [optionsOpen, setOptionsOpen] = useState(false);
  const [mobileNavOpen, setMobileNavOpen] = useState(false);
  const [callingOpen, setCallingOpen] = useState(false);
  const [activePage, setActivePage] = useState("Home");
  const [homePanel, setHomePanel] = useState("Home");
  const [collapsedGroups, setCollapsedGroups] = useState({});
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const [selectedConversation, setSelectedConversation] = useState(null);
  const [taskRecovery, setTaskRecovery] = useState(null);
  const [responsePhase, setResponsePhase] = useState("idle");
  const [aiToolsOpen, setAiToolsOpen] = useState(true);
  const activeRequest = useRef(null);
  const loadedConversation = useRef(null);
  const bottomRef = useRef(null);
  const inputRef = useRef(null);
  const speechAudio = useRef(null);
  const speechUrl = useRef(null);

  useEffect(() => {
    const controller = new AbortController();
    fetchHealth(controller.signal)
      .then(setHealth)
      .catch(() => {
        if (!controller.signal.aborted) {
          setHealth({ status: "offline" });
          setError("I'm having trouble reaching the local assistant service.");
        }
      });
    fetchConversations(controller.signal)
      .then(setHistory)
      .catch(() => {
        if (!controller.signal.aborted) setError("I couldn't load your recent conversations.");
      });
    fetchAIStatus(controller.signal).then(setAIStatus).catch(() => {});
    fetchVoiceStatus(controller.signal).then(setVoiceStatus).catch(() => {});
    fetchMemories(controller.signal).then(setMemories).catch(() => {});
    fetchActionDrafts(controller.signal).then(setActionDrafts).catch(() => {});

    return () => {
      controller.abort();
      speechAudio.current?.pause();
      if (speechUrl.current) URL.revokeObjectURL(speechUrl.current);
    };
  }, []);

  useEffect(() => {
    if (activePage !== "Settings") return undefined;
    const controller = new AbortController();
    fetchAIProviders(controller.signal).then(setProviderCatalog).catch(() => {});
    return () => controller.abort();
  }, [activePage]);

  useEffect(() => {
    let active = true;
    let controller = new AbortController();
    const refresh = () => {
      controller.abort();
      const requestController = new AbortController();
      controller = requestController;
      fetchSystemMetrics(requestController.signal)
        .then((metrics) => {
          if (active) setSystemMetrics(metrics);
        })
        .catch(() => {
          if (active && !requestController.signal.aborted) setSystemMetrics(null);
        });
    };
    refresh();
    const timer = window.setInterval(refresh, 5000);
    return () => {
      active = false;
      window.clearInterval(timer);
      controller.abort();
    };
  }, []);

  useEffect(() => {
    bottomRef.current?.scrollIntoView?.({ behavior: "smooth", block: "end" });
  }, [messages, busy]);

  useEffect(() => {
    const input = inputRef.current;
    if (!input) return;
    input.style.height = "auto";
    input.style.height = `${Math.min(input.scrollHeight, 130)}px`;
  }, [draft]);

  useEffect(() => {
    if (!conversationId || selectedConversation || loadedConversation.current === conversationId) {
      return undefined;
    }
    const controller = new AbortController();
    fetchConversation(conversationId, controller.signal)
      .then((conversation) => {
        loadedConversation.current = conversation.id;
        setMessages(conversation.messages);
        const latestTask = conversation.tasks?.[0];
        const recoverable = latestTask && ["interrupted", "failed"].includes(latestTask.status)
          ? latestTask
          : null;
        setTaskRecovery(recoverable ? {
          ...recoverable,
          message: conversation.messages.find(
            (message) => message.id === recoverable.user_message_id,
          )?.content || "",
        } : null);
      })
      .catch(() => {
        if (controller.signal.aborted) return;
        setConversationId(null);
        loadedConversation.current = null;
        setMessages([]);
        setTaskRecovery(null);
        setError("I couldn't restore that conversation. Your saved history is still available.");
        try {
          window.localStorage.removeItem(STORAGE_KEY);
        } catch {
          // Storage can be disabled by browser privacy settings.
        }
      });
    return () => controller.abort();
  }, [conversationId, selectedConversation]);

  const newConversation = () => {
    activeRequest.current?.abort();
    activeRequest.current = null;
    setBusy(false);
    setError("");
    setMessages([]);
    setTaskRecovery(null);
    setResponsePhase("idle");
    setConversationId(null);
    loadedConversation.current = null;
    setSelectedConversation(null);
    setMobileNavOpen(false);
    try {
      window.localStorage.removeItem(STORAGE_KEY);
    } catch {
      // The active conversation still works when local storage is unavailable.
    }
    inputRef.current?.focus();
  };

  const openConversation = async (id) => {
    activeRequest.current?.abort();
    activeRequest.current = null;
    setBusy(false);
    setResponsePhase("idle");
    setSelectedConversation(id);
    setError("");
    try {
      const conversation = await fetchConversation(id);
      loadedConversation.current = conversation.id;
      setConversationId(conversation.id);
      setMessages(conversation.messages);
      const latestTask = conversation.tasks?.[0];
      const recoverable = latestTask && ["interrupted", "failed"].includes(latestTask.status)
        ? latestTask
        : null;
      setTaskRecovery(recoverable ? {
        ...recoverable,
        message: conversation.messages.find(
          (message) => message.id === recoverable.user_message_id,
        )?.content || "",
      } : null);
      setSelectedConversation(null);
      setActivePage("Conversation History");
      setMobileNavOpen(false);
      try {
        window.localStorage.setItem(STORAGE_KEY, conversation.id);
      } catch {
        // History remains usable for the current browser session.
      }
    } catch (requestError) {
      setError(requestError.message);
      setSelectedConversation(null);
    }
  };

  const sendMessage = async (text, retryTask = null) => {
    if (!text || busy) return;
    if (!retryTask) setDraft("");
    setError("");
    setTaskRecovery(null);
    const requestId = retryTask?.id || createTaskId();
    let userMessageId = `local-${requestId}`;
    const assistantId = `pending-${requestId}`;
    if (retryTask) {
      setMessages((current) => [
        ...current,
        { id: assistantId, role: "assistant", content: "", created_at: new Date().toISOString() },
      ]);
    } else {
      setMessages((current) => [
        ...current,
        { id: `local-${requestId}`, role: "user", content: text, created_at: new Date().toISOString() },
        { id: assistantId, role: "assistant", content: "", created_at: new Date().toISOString() },
      ]);
    }

    const controller = new AbortController();
    activeRequest.current = controller;
    setBusy(true);
    setResponsePhase("thinking");
    try {
      await streamChat(text, conversationId, {
        signal: controller.signal,
        taskId: requestId,
        onMeta: ({ conversation_id: id, task_id: taskId, user_message_id: savedUserMessageId }) => {
          userMessageId = savedUserMessageId || `local-${taskId}`;
          loadedConversation.current = id;
          setConversationId(id);
          setTaskRecovery({
            id: taskId,
            user_message_id: userMessageId,
            status: "running",
            attempt_count: retryTask?.attempt_count || 1,
            message: text,
          });
          try {
            window.localStorage.setItem(STORAGE_KEY, id);
          } catch {
            // Persisting chat server-side does not depend on browser storage.
          }
        },
        onDelta: (delta) => {
          setResponsePhase("speaking");
          setMessages((current) =>
            current.map((item) =>
              item.id === assistantId ? { ...item, content: item.content + delta } : item,
            ),
          );
        },
      });
      try {
        setHistory(await fetchConversations());
      } catch {
        setError("Your response is saved, but I couldn't refresh the conversation list.");
      }
      setTaskRecovery(null);
    } catch (requestError) {
      if (activeRequest.current !== controller) return;
      setMessages((current) => current.filter((item) => item.id !== assistantId));
      setTaskRecovery({
        id: requestId,
        user_message_id: userMessageId,
        status: requestError.name === "AbortError" ? "interrupted" : "failed",
        attempt_count: retryTask?.attempt_count || 1,
        message: text,
        error_message: requestError.name === "AbortError"
          ? "I stopped before finishing. Your message is saved; I won't repeat it unless you ask."
          : requestError.message,
      });
      if (requestError.name !== "AbortError") {
        setError(requestError.message);
      }
    } finally {
      if (activeRequest.current === controller) {
        setBusy(false);
        setResponsePhase("idle");
        activeRequest.current = null;
        inputRef.current?.focus();
      }
    }
  };

  const submit = (event) => {
    event.preventDefault();
    void sendMessage(draft.trim());
  };

  const retryResponse = () => {
    if (taskRecovery?.message) void sendMessage(taskRecovery.message, taskRecovery);
  };

  const refreshAIStatus = async () => {
    try {
      setAIStatus(await fetchAIStatus());
    } catch (requestError) {
      setError(requestError.message);
    }
  };

  const selectModel = async (model) => {
    try {
      await chooseAIModel(model);
      setHealth((current) => ({ ...current, model }));
      setAIStatus((current) => ({ ...current, model }));
      setMenuOpen(false);
      setError("");
    } catch (requestError) {
      setError(requestError.message);
    }
  };

  const submitMemory = async (event) => {
    event.preventDefault();
    if (!memoryApproved) {
      setError("Confirm that you'd like me to save this preference first.");
      return;
    }
    try {
      await saveMemory({ key: memoryKey, value: memoryValue, approved: true });
      setMemories(await fetchMemories());
      setMemoryKey("");
      setMemoryValue("");
      setMemoryApproved(false);
      setNotice("I’ll remember that preference.");
    } catch (requestError) {
      setError(requestError.message);
    }
  };

  const submitPersonality = async (event) => {
    event.preventDefault();
    try {
      const saved = await persistPersonality(personalityDraft);
      setAIStatus((current) => ({ ...current, personality: saved.personality }));
      setPersonalityDraft("");
      setNotice("I’ll use that personality from now on.");
    } catch (requestError) {
      setError(requestError.message);
    }
  };

  const persistPersonality = (personality) => savePersonality(personality);

  const removeMemory = async (id) => {
    const memory = memories.find((item) => item.id === id);
    if (memory && !window.confirm(`Remove the saved preference “${memory.key}”?`)) return;
    try {
      await deleteMemory(id);
      setMemories(await fetchMemories());
    } catch (requestError) {
      setError(requestError.message);
    }
  };

  const submitActionDraft = async (event, actionType = draftType) => {
    event.preventDefault();
    try {
      const created = await createActionDraft({
        action_type: actionType,
        recipient: draftRecipient,
        subject: actionType === "email" ? draftSubject : null,
        body: draftBody,
      });
      setActionDrafts((current) => [created, ...current]);
      setDraftRecipient("");
      setDraftSubject("");
      setDraftBody("");
      setNotice("Draft saved locally. Nothing was sent.");
    } catch (requestError) {
      setError(requestError.message);
    }
  };

  const approveDraft = async (id) => {
    try {
      const approved = await approveActionDraft(id);
      setActionDrafts((current) => current.map((item) => item.id === id ? approved : item));
      setNotice("Draft approved and recorded. No message was sent.");
    } catch (requestError) {
      setError(requestError.message);
    }
  };

  const speakMessage = async (message) => {
    if (speakingMessage === message.id) {
      speechAudio.current?.pause();
      if (speechUrl.current) URL.revokeObjectURL(speechUrl.current);
      speechUrl.current = null;
      speechAudio.current = null;
      setSpeakingMessage(null);
      return;
    }
    try {
      speechAudio.current?.pause();
      const blob = await synthesizeSpeech(message.content);
      const url = URL.createObjectURL(blob);
      speechUrl.current = url;
      const audio = new Audio(url);
      speechAudio.current = audio;
      setSpeakingMessage(message.id);
      audio.onended = () => {
        URL.revokeObjectURL(url);
        speechUrl.current = null;
        speechAudio.current = null;
        setSpeakingMessage(null);
      };
      audio.onerror = () => {
        URL.revokeObjectURL(url);
        speechUrl.current = null;
        speechAudio.current = null;
        setSpeakingMessage(null);
        setError("I couldn't play that spoken response.");
      };
      await audio.play();
    } catch (requestError) {
      setSpeakingMessage(null);
      setError(requestError.message);
    }
  };

  const configured = health?.ai_configured === true;
  const available = health?.ai_available === true
    || (health?.ai_provider === "openai" && configured && health?.status === "ok");
  const canChat = configured && available;
  const localProvider = health?.ai_provider === "ollama";
  const providerStatus = !health || health.status === "offline"
    ? "Unknown"
    : !configured
      ? "Setup required"
      : localProvider
        ? available ? "Available" : "Offline"
        : "Configured";
  const assistantState = voiceStatus?.microphone_active
    ? "Listening"
    : busy
    ? responsePhase === "speaking" ? "Speaking" : "Thinking"
    : taskRecovery
      ? taskRecovery.status === "interrupted" ? "Interrupted" :
        taskRecovery.status === "failed" ? "Error" : "Recovering"
      : error ? "Error"
        : health?.status === "offline" || (configured && !available) ? "Error"
          : health ? canChat ? "Idle" : "Error" : "Connecting";
  const greetingHour = new Date().getHours();
  const greeting = greetingHour < 12 ? "Good morning" : greetingHour < 18 ? "Good afternoon" : "Good evening";

  const navigation = [
    { group: "MAIN", items: [["Home", Home], ["Chat", MessageSquareText], ["WhatsApp", MessagesSquare], ["Quick Actions", Command], ["AI Tools", Sparkles], ["Applications", Workflow], ["Tools & Utilities", Search], ["Settings", Settings2], ["Help & Support", CircleHelp], ["Exit", Activity]] },
  ];

  const providerRows = [
    { name: "OpenAI", online: health?.ai_provider === "openai" && health?.status === "ok", label: health?.ai_provider === "openai" ? "Connected" : "Offline" },
    { name: "Gemini", online: false, label: "Not configured" },
    { name: "Claude", online: false, label: "Not configured" },
    { name: "DeepSeek", online: false, label: "Not configured" },
  ];

  const isConversationPage = activePage === "Home" || activePage === "Conversations" || activePage === "Conversation History";
  const isChatPage = activePage === "Conversations" || activePage === "Conversation History";

  const openPage = (page) => {
    if (page === "Chat") {
      setActivePage("Conversations");
      setMobileNavOpen(false);
    } else if (page === "WhatsApp") {
      setHomePanel("WhatsApp");
      setActivePage("Home");
      setMobileNavOpen(false);
    } else if (page === "Settings" || page === "Tools & Utilities") {
      setHomePanel(page);
      setActivePage("Home");
      setMobileNavOpen(false);
    } else if (page === "Home") {
      setHomePanel("Home");
      setActivePage("Home");
      setMobileNavOpen(false);
    } else if (page === "Help & Support") {
      setHelpOpen((current) => !current);
      setActivePage("Help & Support");
    } else if (page === "Exit") {
      setActivePage("Home");
    } else {
      setActivePage(page);
      setMobileNavOpen(false);
    }
  };

  if (callingOpen) {
    return <CallingDashboard onBack={() => setCallingOpen(false)} />;
  }

  if (activePage === "Home") {
    return (
      <HomeScreen
        activeWorkspace={homePanel}
        health={health}
        systemMetrics={systemMetrics}
        aiStatus={aiStatus}
        voiceStatus={voiceStatus}
        history={history}
        busy={busy}
        canChat={canChat}
        responsePhase={responsePhase}
        error={error}
        onRunAction={(action) => void sendMessage(action)}
        onOpenConversation={openConversation}
        onNavigate={(page) => {
          if (page === "Chat") {
            setActivePage("Conversations");
          } else if (["WhatsApp", "Home", "Settings", "Tools & Utilities"].includes(page)) {
            setHomePanel(page);
            setActivePage("Home");
          } else {
            setActivePage(page);
          }
        }}
        onSelectModel={(model) => void selectModel(model)}
        onSavePersonality={async (personality) => {
          const saved = await persistPersonality(personality);
          setAIStatus((current) => ({ ...current, personality: saved.personality }));
          setNotice("Assistant personality saved.");
        }}
        onBackgroundState={(listening) => setVoiceStatus((current) => ({ ...(current || {}), wake_word_listening: listening, microphone_active: listening }))}
        onSendMessage={(text) => {
          setActivePage("Conversations");
          void sendMessage(text);
        }}
        onError={setError}
        onDismissError={() => setError("")}
      />
    );
  }

  return (
    <main className={`app-shell ${isChatPage ? "chat-mode" : ""}`}>
      {!isChatPage && <aside className={`sidebar ${mobileNavOpen ? "mobile-open" : ""} ${sidebarCollapsed ? "collapsed" : ""}`}>
        <button className="brand" onClick={() => openPage("Home")} aria-label="JARVIS home">
          <span className="brand-mark"><AudioLines size={20} /></span>
          <span className="brand-word">JARVIS<span className="brand-dot">.</span><small>PERSONAL INTELLIGENCE</small></span>
        </button>

        <nav className="primary-navigation" aria-label="Primary navigation">
          {navigation.map(({ group, items }) => (
            <section className="nav-group" key={group}>
              {items.map(([label, Icon]) => (
                label === "AI Tools" ? (
                  <div className="nav-ai-tools" key={label}>
                    <button className={`nav-link ${activePage === label ? "active" : ""}`} onClick={() => { setAiToolsOpen((open) => !open); setActivePage(label); }}>
                      <Icon size={16} /><span>{label}</span>
                      <ChevronRight size={12} className={aiToolsOpen ? "expanded" : ""} />
                    </button>
                    {aiToolsOpen && (
                      <div className="ai-tool-submenu">
                        {providerRows.map((provider) => (
                          <button key={provider.name} className="subnav-item" type="button" onClick={() => setActivePage("AI Tools")}>
                            <span className={`status-dot ${provider.online ? "online" : "offline"}`} />
                            {provider.name}
                          </button>
                        ))}
                        <button className="subnav-item add-more" type="button" onClick={() => setActivePage("AI Tools")}>Add More...</button>
                      </div>
                    )}
                  </div>
                ) : (
                  <button key={label} className={`nav-link ${activePage === label || (label === "Chat" && activePage !== "Home" && isConversationPage) ? "active" : ""}`} onClick={() => openPage(label)}>
                    <Icon size={16} /><span>{label}</span>
                    {label === "WhatsApp" && <span className="nav-badge">4</span>}
                  </button>
                )
              ))}
            </section>
          ))}
        </nav>

        <div className="sidebar-bottom">
          <div className="system-status-card">
            <div className="status-row"><span className="system-online" /><strong>System Online</strong></div>
            <div className="status-meta">Ubuntu 24.04 LTS</div>
            <div className="status-meta">CPU {Number.isFinite(systemMetrics?.cpu_percent) ? `${Math.round(systemMetrics.cpu_percent)}%` : "Unavailable"} · RAM {Number.isFinite(systemMetrics?.memory_percent) ? `${Math.round(systemMetrics.memory_percent)}%` : "Unavailable"}</div>
            <div className="status-meta">JARVIS: {health?.status === "ok" ? "Connected" : "Disconnected"}</div>
          </div>
          <div className="profile-button" aria-label="Local session">
            <span className="profile-avatar">N</span>
            <span className="profile-label"><strong>Newton</strong><small>Always here. Always working.</small></span>
            <button className="collapse-sidebar" onClick={() => { if (mobileNavOpen) setMobileNavOpen(false); else setSidebarCollapsed((value) => !value); }} aria-label={sidebarCollapsed ? "Expand navigation" : "Collapse navigation"}><ChevronDown size={15} /></button>
          </div>
        </div>
      </aside>}
      {!isChatPage && mobileNavOpen && (
        <button
          className="mobile-nav-scrim"
          aria-label="Close conversation history"
          onClick={() => setMobileNavOpen(false)}
        />
      )}

      <section className="main-panel">
        <header className="topbar">
          <button
            className="mobile-menu-button"
            aria-label="Open navigation"
            onClick={() => setMobileNavOpen(true)}
          >
            <Menu size={18} />
          </button>
          <div className="breadcrumb"><span>Personal Intelligence</span><span className="crumb-slash">/</span><strong>{activePage}</strong></div>
          <div className="topbar-right">
            <button
              className={`background-listening-toggle ${voiceStatus?.wake_word_listening ? "active" : "muted"}`}
              type="button"
              disabled
              aria-label={voiceStatus?.wake_word_listening ? "Background listening active" : "Background listening unavailable"}
            >
              <span className="wave wave-one" />
              <span className="wave wave-two" />
              <span className="wave wave-three" />
              <span>{voiceStatus?.wake_word_listening ? "Listening locally" : "Wake word unavailable"}</span>
            </button>
            <div className={`connection-pill ${health?.status === "ok" ? "online" : "offline"}`}>
              {health?.status === "ok" ? <Wifi size={13} /> : <WifiOff size={13} />}
              <span>{health === null ? "CONNECTING" : health.status === "ok" ? "BACKEND ONLINE" : "BACKEND OFFLINE"}</span>
              <i />
            </div>
            <div className="date-pill">{new Date().toLocaleString([], { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" })}</div>
            <button
              className="icon-button calling-nav-button"
              aria-label="Open calling dashboard"
              title="Scheduled calls"
              onClick={() => setCallingOpen(true)}
            >
              <PhoneCall size={17} />
            </button>
            <button
              className="icon-button"
              aria-label="Settings shortcut"
              title="Settings"
              aria-expanded={settingsOpen}
              onClick={() => openPage("Settings")}
            >
              <Settings2 size={17} />
            </button>
            <button
              className="help-button"
              aria-label="Help"
              aria-expanded={helpOpen}
              onClick={() => setHelpOpen((open) => !open)}
            >
              <CircleHelp size={17} />
            </button>
            {helpOpen && (
              <section className="settings-popover help-popover" role="dialog" aria-label="JARVIS help">
                <div className="settings-head">
                  <strong>How can I help?</strong>
                  <button onClick={() => setHelpOpen(false)} aria-label="Close help">×</button>
                </div>
                <p className="settings-note">
                  Send a message to start a conversation. Your chat is stored in this
                  device's SQLite database. Voice input and computer control are not
                  available yet; scheduled calling is in the phone section.
                </p>
              </section>
            )}
          </div>
          {settingsOpen && (
            <section className="settings-popover" role="dialog" aria-label="JARVIS settings">
              <div className="settings-head">
                <strong>Assistant settings</strong>
                <button onClick={() => setSettingsOpen(false)} aria-label="Close settings">×</button>
              </div>
              <div className="settings-row">
                <span>AI service</span>
                <strong className={canChat ? "setting-good" : "setting-warning"}>
                  {providerStatus}
                </strong>
              </div>
              <div className="settings-row">
                <span>{localProvider ? "Local model" : "Model"}</span><strong>{health?.model || "Not available"}</strong>
              </div>
              <p className="settings-note">
                {localProvider
                  ? <>Chat uses Ollama{available ? " on your configured model" : ", which is currently unavailable"}. When Ollama runs on this device, chat stays local. Conversation history is saved by your backend.</>
                  : health?.ai_provider === "openai"
                    ? <>Chat uses OpenAI. Configure <code>OPENAI_API_KEY</code> in <code>backend/.env</code>; conversation history is saved by your backend.</>
                    : <>Provider details are unavailable until the local backend responds. Conversation history is saved by your backend.</>}
                {" "}Phase 1 has no computer-control permissions.
              </p>
              <div className="settings-row">
                <span>Offline speech recognition</span>
                <strong className={voiceStatus?.speech_recognition_available ? "setting-good" : "setting-warning"}>
                  {voiceStatus?.speech_recognition_available ? "Available" : "Model needed"}
                </strong>
              </div>
              <div className="settings-row">
                <span>Wake word · {voiceStatus?.wake_word_phrase || "Hello JARVIS Scott here"}</span>
                <strong className={voiceStatus?.wake_word_available ? "setting-good" : "setting-warning"}>
                  {voiceStatus?.wake_word_available ? "Available" : "Not configured"}
                </strong>
              </div>
              <div className="settings-row">
                <span>Offline speech</span>
                <strong className={voiceStatus?.text_to_speech_available ? "setting-good" : "setting-warning"}>
                  {voiceStatus?.text_to_speech_available ? "Piper ready" : "Piper model needed"}
                </strong>
              </div>
              <p className="settings-note">Background listening is opt-in and requires a configured local wake-word model and offline speech recognizer.</p>
              <form className="personality-form" onSubmit={submitPersonality}>
                <label htmlFor="personality">Assistant personality</label>
                <textarea id="personality" value={personalityDraft} onChange={(event) => setPersonalityDraft(event.target.value)} placeholder={aiStatus?.personality || "Warm, confident, and helpful"} maxLength={500} required />
                <button type="submit">Save personality</button>
              </form>
              <div className="memory-settings">
                <strong>Preferences I can remember</strong>
                {memories.map((memory) => (
                  <div className="settings-row" key={memory.id}>
                    <span><b>{memory.key}</b> · {memory.value}</span>
                    <button className="icon-button" aria-label={`Forget ${memory.key}`} onClick={() => void removeMemory(memory.id)}>×</button>
                  </div>
                ))}
                <form onSubmit={submitMemory}>
                  <input aria-label="Preference name" placeholder="Preference name" value={memoryKey} maxLength={80} onChange={(event) => setMemoryKey(event.target.value)} required />
                  <input aria-label="Preference value" placeholder="What should I remember?" value={memoryValue} maxLength={500} onChange={(event) => setMemoryValue(event.target.value)} required />
                  <label><input type="checkbox" checked={memoryApproved} onChange={(event) => setMemoryApproved(event.target.checked)} /> I approve saving this preference</label>
                  <button type="submit" disabled={!memoryApproved}>Save preference</button>
                </form>
              </div>
            </section>
          )}
        </header>

        {isConversationPage ? <div className={`content-grid ${activePage === "Conversations" || activePage === "Conversation History" ? "history-workspace" : ""}`}>
          {(activePage === "Conversations" || activePage === "Conversation History") && (
            <aside className="chat-history-sidebar" aria-label="Chat history">
              <div className="chat-history-header">
                <div><History size={15} /><strong>Previous chats</strong></div>
                <button type="button" className="new-chat-button" onClick={newConversation}>
                  <Plus size={14} /> New chat
                </button>
              </div>
              <div className="chat-history-list">
                {history.length ? history.map((conversation) => (
                  <button
                    type="button"
                    key={conversation.id}
                    className={`chat-history-item ${conversation.id === conversationId ? "active" : ""}`}
                    onClick={() => void openConversation(conversation.id)}
                    title={conversation.title || "Untitled conversation"}
                  >
                    <MessageSquareText size={14} />
                    <span>{conversation.title || "Untitled conversation"}</span>
                  </button>
                )) : <p className="chat-history-empty">Your saved chats will appear here.</p>}
              </div>
            </aside>
          )}
          <section className="conversation-column">
            <div className="session-heading">
              <div>
                <div className="eyebrow"><span className="eyebrow-line" /> {activePage === "Home" ? "YOUR PERSONAL AI" : "PERSONAL · CONVERSATION HISTORY"}</div>
                <h1>{activePage === "Home" ? <>{greeting}<span className="heading-comma">,</span> <em>how can I help?</em></> : <>Your conversations<span className="heading-comma">.</span></>}</h1>
              </div>
              {activePage !== "Home" && (
                <button
                  type="button"
                  className="return-home-button"
                  onClick={() => {
                    setHomePanel("Home");
                    setActivePage("Home");
                  }}
                >
                  <Home size={15} /> Return to home
                </button>
              )}
              <button
                className={`model-selector ${menuOpen ? "open" : ""}`}
                onClick={() => {
                  setMenuOpen((open) => !open);
                  void refreshAIStatus();
                }}
                aria-expanded={menuOpen}
              >
                <span className="model-spark"><Sparkles size={14} /></span>
                <span>{health?.model || "JARVIS AI"}</span>
                <ChevronDown size={13} />
              </button>
            </div>

            {menuOpen && (
              <div className="model-popover">
                <div><Sparkles size={15} /><span><strong>{health?.model || "JARVIS AI"}</strong><small>{aiStatus?.available ? "Ollama is responding" : "Model availability follows Ollama status"}</small></span><Check size={15} /></div>
                {localProvider && aiStatus?.models?.map((model) => (
                  <button className="model-option" key={model} disabled={model === health?.model} onClick={() => void selectModel(model)}>
                    {model === health?.model ? <Check size={14} /> : <span className="model-option-spacer" />}
                    {model}
                  </button>
                ))}
                {localProvider && !aiStatus?.models?.length && <p>No local Ollama models were found.</p>}
                {!localProvider && <p>Model selection is managed by your local backend settings.</p>}
              </div>
            )}

            <div className="conversation-scroll">
              {messages.length === 0 ? (
                <div className="welcome-stage">
                  <div className="orb-wrap" aria-label={`JARVIS ${assistantState.toLowerCase()}`}>
                    <div className="orb-ring ring-one" />
                    <div className="orb-ring ring-two" />
                    <div className="orb-ring ring-three" />
                    <div className="orb-core"><div className="orb-glow" /><AudioLines size={34} strokeWidth={1.4} /></div>
                    <span className="orb-spark spark-a" /><span className="orb-spark spark-b" /><span className="orb-spark spark-c" />
                  </div>
                  <div className="ready-label"><span className="ready-dot" />
                    {assistantState === "Idle" ? "READY WHEN YOU ARE" :
                      assistantState === "Connecting" ? "CONNECTING TO JARVIS" :
                        assistantState === "Error" ? "SERVICE UNAVAILABLE" : assistantState.toUpperCase()}
                  </div>
                </div>
              ) : (
                <div className="message-list" aria-live="polite">
                  {messages.map((message) => (
                    <article className={`message ${message.role}`} key={message.id}>
                      <div className="message-avatar">{message.role === "assistant" ? <Bot size={17} /> : <UserRound size={16} />}</div>
                      <div className="message-body">
                        <div className="message-meta">
                          <strong>{message.role === "assistant" ? "JARVIS" : "YOU"}</strong>
                          <time>{formatTime(message.created_at)}</time>
                        </div>
                        <p>{message.content || (busy ? <span className="typing-dots"><i /><i /><i /></span> : "")}</p>
                        {message.role === "assistant" && message.content && voiceStatus?.text_to_speech_available && (
                          <button
                            className="message-speak"
                            onClick={() => void speakMessage(message)}
                            aria-label={speakingMessage === message.id ? "Stop speaking response" : "Speak response"}
                          >
                            {speakingMessage === message.id ? <VolumeX size={14} /> : <Volume2 size={14} />}
                            {speakingMessage === message.id ? "Stop speaking" : "Listen"}
                          </button>
                        )}
                      </div>
                    </article>
                  ))}
                  <div ref={bottomRef} />
                </div>
              )}
              {taskRecovery && taskRecovery.status !== "running" && (
                <section className="recovery-notice" role="status">
                  <div>
                    <strong>{taskRecovery.status === "interrupted" ? "We were interrupted." : "That response didn't finish."}</strong>
                    <p>{taskRecovery.error_message || "Your message is saved. I won't repeat anything unless you ask me to retry."}</p>
                  </div>
                  {taskRecovery.message && taskRecovery.attempt_count < 2 && (
                    <button onClick={retryResponse} disabled={busy}>Retry response</button>
                  )}
                  <button className="recovery-dismiss" onClick={() => setTaskRecovery(null)} aria-label="Dismiss recovery notice">×</button>
                </section>
              )}
              {error && <div className="error-banner" role="alert">{error}</div>}
              {notice && <div className="notice-banner" role="status">{notice}<button onClick={() => setNotice("")} aria-label="Dismiss notification">×</button></div>}
            </div>

            <div className="composer-wrap">
              <form className="composer" onSubmit={submit}>
                <button
                  className="composer-add"
                  type="button"
                  aria-label="More options"
                  aria-expanded={optionsOpen}
                  title="More options"
                  onClick={() => setOptionsOpen((open) => !open)}
                >
                  <Plus size={19} />
                </button>
                {optionsOpen && (
                  <div className="composer-options" role="status">
                    Attachments aren't available yet. You can paste text directly into your message.
                    <button type="button" onClick={() => setOptionsOpen(false)} aria-label="Dismiss attachment notice">×</button>
                  </div>
                )}
                <textarea
                  ref={inputRef}
                  aria-label="Message JARVIS"
                  placeholder={canChat ? "Message JARVIS..." : localProvider ? "Start Ollama to chat" : "Configure your API key to start chatting"}
                  value={draft}
                  onChange={(event) => setDraft(event.target.value)}
                  onKeyDown={(event) => {
                    if (event.key === "Enter" && !event.shiftKey) {
                      event.preventDefault();
                      event.currentTarget.form.requestSubmit();
                    }
                  }}
                  rows={1}
                  disabled={!canChat || busy || voiceStatus?.microphone_active}
                />
                <div className="composer-actions">
                  <VoiceCapture
                    disabled={!canChat || busy || !voiceStatus?.speech_recognition_available}
                    onTranscript={(text) => void sendMessage(text)}
                    onError={setError}
                    onState={(listening) => setVoiceStatus((current) => ({ ...current, microphone_active: listening }))}
                  />
                  {busy ? (
                    <button className="send-button stop-button" type="button" onClick={() => activeRequest.current?.abort()} aria-label="Stop response">
                      <StopCircle size={17} />
                    </button>
                  ) : (
                    <button className="send-button" type="submit" disabled={!draft.trim() || !canChat || voiceStatus?.microphone_active} aria-label="Send message">
                      <Send size={16} />
                    </button>
                  )}
                </div>
              </form>
              <div className="composer-footnote">
                <span><ShieldCheck size={12} /> {voiceStatus?.microphone_active ? `Listening on this device · click stop to send` : localProvider ? "Messages handled by Ollama" : health?.ai_provider === "openai" ? "Messages sent to OpenAI" : "AI provider status unavailable"} · History saved by your backend</span>
                <span><kbd>↵</kbd> to send <kbd>⇧ ↵</kbd> for new line</span>
              </div>
            </div>
          </section>

          <aside className="insights-column">
            <div className="insight-top">
              <div className="panel-title">
                <span>ASSISTANT STATE</span>
                <span className={`live-tag state-${assistantState.toLowerCase()}`}>
                  <i /> {assistantState.toUpperCase()}
                </span>
              </div>
              <div className="signal-visual">
                <div className="signal-orbit"><span /><span /><span /></div>
                <div className="signal-center"><AudioLines size={21} /></div>
              </div>
              <div className={`system-state state-${assistantState.toLowerCase()}`}>
                <span className="state-dot" /> JARVIS · {assistantState.toUpperCase()}
              </div>
              <p className="system-caption">
                {assistantState === "Idle" ? "Ready when you are." :
                  assistantState === "Thinking" ? "Working through your message." :
                    assistantState === "Speaking" ? "Writing a response now." :
                      assistantState === "Interrupted" ? "Paused. Nothing will be replayed automatically." :
                        assistantState === "Recovering" ? "Checking where we left off." :
                          assistantState === "Error" ? "The local service needs attention." : "Waiting for your message."}
              </p>
            </div>

            <div className="panel-block communication-panel">
              <div className="panel-title">COMMUNICATION DRAFTS <span className="subtle-count">NOT SENT</span></div>
              <form onSubmit={submitActionDraft}>
                <label>
                  Type
                  <select value={draftType} onChange={(event) => setDraftType(event.target.value)}>
                    <option value="email">Email draft</option>
                    <option value="message">Message draft</option>
                  </select>
                </label>
                <label>
                  {draftType === "email" ? "Email address" : "Recipient"}
                  <input value={draftRecipient} onChange={(event) => setDraftRecipient(event.target.value)} required maxLength={320} />
                </label>
                {draftType === "email" && (
                  <label>
                    Subject
                    <input value={draftSubject} onChange={(event) => setDraftSubject(event.target.value)} required maxLength={300} />
                  </label>
                )}
                <label>
                  Draft
                  <textarea value={draftBody} onChange={(event) => setDraftBody(event.target.value)} required maxLength={10_000} rows={3} />
                </label>
                <button type="submit">Save draft</button>
              </form>
              <div className="action-draft-list">
                {actionDrafts.map((draft) => (
                  <article key={draft.id} className="action-draft">
                    <div><strong>{draft.action_type === "email" ? `Email · ${draft.subject}` : "Message draft"}</strong><span>To {draft.recipient} · {draft.status === "draft" ? "Awaiting review" : "Approved, not sent"}</span></div>
                    <p>{draft.body}</p>
                    {draft.status === "draft" && <button onClick={() => void approveDraft(draft.id)}>Approve draft</button>}
                  </article>
                ))}
              </div>
              <p className="settings-note">Approval records your decision; it never sends.</p>
            </div>

            <div className="panel-block provider-panel">
              <div className="panel-title-row">
                <span>AI Platforms</span>
                <button type="button" className="mini-action">Manage</button>
              </div>
              <div className="provider-list">
                {providerRows.map((provider) => (
                  <div key={provider.name} className="provider-item">
                    <div className="provider-logo">{provider.name.slice(0, 1)}</div>
                    <div className="provider-copy">
                      <strong>{provider.name}</strong>
                      <small>{provider.label}</small>
                    </div>
                    <span className={`provider-status ${provider.online ? "online" : "offline"}`} />
                  </div>
                ))}
              </div>
              <button type="button" className="add-provider">Add New API</button>
            </div>

            <div className="panel-block whatsapp-panel">
              <div className="panel-title-row">
                <span>WhatsApp</span>
                <button type="button" className="mini-action" onClick={() => openPage("WhatsApp")}>Open workspace</button>
              </div>
              <div className="whatsapp-list">
                <p className="empty-state">No authorized WhatsApp integration is configured. Messages cannot be loaded or sent.</p>
              </div>
            </div>

            <div className="panel-block media-panel">
              <div className="media-art" aria-label="Media artwork">N</div>
              <div className="media-copy">
                <strong>Never Fade</strong>
                <small>Solar Echo</small>
              </div>
              <div className="media-controls">
                <button type="button" aria-label="Previous track">⏮</button>
                <button type="button" className="play-button" aria-label="Play or pause">▶</button>
                <button type="button" aria-label="Next track">⏭</button>
              </div>
            </div>

            <div className="panel-block system-panel">
              <div className="panel-title-row">
                <span>System</span>
              </div>
              <div className="system-grid">
                <div><small>CPU</small><strong>42%</strong></div>
                <div><small>RAM</small><strong>68%</strong></div>
                <div><small>SYSTEM</small><strong>{health?.status === "ok" ? "Connected" : "Disconnected"}</strong></div>
                <div><small>VOICE</small><strong>{voiceStatus?.wake_word_listening ? "Listening" : "Unavailable"}</strong></div>
              </div>
            </div>

            <div className="backend-foot">
              <span><span className={`backend-led ${health?.status === "ok" ? "good" : ""}`} /> LOCAL BACKEND</span>
              <span>v0.1.0 · PHASE ONE</span>
            </div>
          </aside>
        </div> : <section className="workspace-page">
          <div className="workspace-heading"><div className="eyebrow"><span className="eyebrow-line" /> PERSONAL INTELLIGENCE</div><h1>{activePage}</h1><p>Live capabilities and configuration from your JARVIS backend.</p></div>
          {activePage === "Memory" && <div className="workspace-card"><div className="workspace-card-head"><div><h2>Remembered preferences</h2><p>These approved entries are stored locally and can inform future conversations.</p></div><button className="secondary-action" onClick={() => void fetchMemories().then(setMemories).catch((e) => setError(e.message))}>Refresh</button></div><form className="memory-page-form" onSubmit={submitMemory}><input aria-label="Preference name" placeholder="Preference name" value={memoryKey} maxLength={80} onChange={(event) => setMemoryKey(event.target.value)} required /><input aria-label="Preference value" placeholder="What should JARVIS remember?" value={memoryValue} maxLength={500} onChange={(event) => setMemoryValue(event.target.value)} required /><label><input type="checkbox" checked={memoryApproved} onChange={(event) => setMemoryApproved(event.target.checked)} /> I approve saving this preference</label><button disabled={!memoryApproved}>Add memory</button></form><div className="memory-list">{memories.map((memory) => <article key={memory.id}><div><strong>{memory.key}</strong><p>{memory.value}</p><small>Saved preference · local backend</small></div><button className="secondary-action danger-action" onClick={() => void removeMemory(memory.id)}>Remove</button></article>)}{!memories.length && <p className="empty-state">No approved preferences saved yet.</p>}</div></div>}
          {activePage === "AI Models" && <div className="workspace-card"><div className="workspace-card-head"><div><h2>Model runtime</h2><p>Provider availability comes directly from the assistant service.</p></div><button className="secondary-action" onClick={() => void refreshAIStatus()}>Test connection</button></div><div className="status-grid"><div><small>PROVIDER</small><strong>{health?.ai_provider || "Checking…"}</strong><span>{localProvider ? "Local runtime" : health?.ai_provider === "openai" ? "Cloud provider" : "Not reported"}</span></div><div><small>ACTIVE MODEL</small><strong>{health?.model || "Unavailable"}</strong><span>{canChat ? "Available" : "Not available"}</span></div><div><small>CONNECTION</small><strong>{aiStatus?.available ? "Connected" : "Unavailable"}</strong><span>{aiStatus?.error || (aiStatus?.available ? "Runtime responded" : "Check backend and provider configuration")}</span></div></div>{localProvider && <div className="model-list"><h3>Installed Ollama models</h3>{(aiStatus?.models || []).map((model) => <button key={model} className={`model-row ${model === health?.model ? "selected" : ""}`} onClick={() => void selectModel(model)}><span>{model}</span><span>{model === health?.model ? "ACTIVE" : "Select model"}</span></button>)}{!aiStatus?.models?.length && <p className="empty-state">No installed models reported by Ollama.</p>}</div>}</div>}
          {activePage === "Voice" && <div className="workspace-card voice-workspace"><div className={`orb-wrap voice-orb state-${assistantState.toLowerCase()}`} aria-label={`JARVIS ${assistantState}`}><div className="orb-ring ring-one"/><div className="orb-ring ring-two"/><div className="orb-ring ring-three"/><div className="orb-core"><div className="orb-glow"/><AudioLines size={34}/></div></div><h2>Hands-free voice</h2><p>Enable background listening in Settings. Audio stays on the configured local backend.</p><div className="status-grid"><div><small>SPEECH RECOGNITION</small><strong>{voiceStatus?.speech_recognition_available ? "Available" : "Unavailable"}</strong><span>{voiceStatus?.speech_recognition_method || "Configure Vosk model or optional Whisper dependencies"}</span></div><div><small>SPEECH OUTPUT</small><strong>{voiceStatus?.text_to_speech_available ? "Available" : "Unavailable"}</strong><span>{voiceStatus?.text_to_speech_method || "Configure Piper binary and voice model"}</span></div><div><small>WAKE WORD</small><strong>{voiceStatus?.wake_word_listening ? "Listening" : voiceStatus?.wake_word_available ? "Ready · off" : "Not configured"}</strong><span>{voiceStatus?.wake_word_phrase || "Hello JARVIS Scott here"}</span></div></div>{error && <p className="error-banner">{error}</p>}</div>}
          {(activePage === "Messages" || activePage === "Email") && <div className="workspace-card"><div className="workspace-card-head"><div><h2>{activePage === "Email" ? "Email drafts" : "Message drafts"}</h2><p>Drafts are saved locally for review. No delivery service is configured, and approval never sends.</p></div></div><form className="communication-form" onSubmit={(event) => void submitActionDraft(event, activePage === "Email" ? "email" : "message")}><label>Recipient<input value={draftRecipient} onChange={(event) => setDraftRecipient(event.target.value)} required maxLength={320}/></label>{activePage === "Email" && <label>Subject<input value={draftSubject} onChange={(event) => setDraftSubject(event.target.value)} required maxLength={300}/></label>}<label>Draft<textarea value={draftBody} onChange={(event) => setDraftBody(event.target.value)} required maxLength={10000} rows={5}/></label><button>Save draft</button></form><div className="memory-list">{actionDrafts.filter((item) => item.action_type === (activePage === "Email" ? "email" : "message")).map((item) => <article key={item.id}><div><strong>{item.subject || `${activePage} draft`}</strong><p>To {item.recipient} · {item.status === "draft" ? "Awaiting review" : "Approved, not sent"}</p><small>{item.body}</small></div>{item.status === "draft" && <button className="secondary-action" onClick={() => void approveDraft(item.id)}>Approve draft</button>}</article>)}</div></div>}
          {(activePage === "Settings") && <div className="workspace-card"><div className="workspace-card-head"><div><h2>Assistant preferences</h2><p>Settings below persist through the existing backend.</p></div></div><form className="settings-page-form" onSubmit={submitPersonality}><label>Personality instructions<textarea id="personality-page" value={personalityDraft} onChange={(event) => setPersonalityDraft(event.target.value)} placeholder={aiStatus?.personality || "Warm, confident, and helpful"} maxLength={500} required/></label><button>Save personality</button></form><section className="provider-management"><div className="workspace-card-head"><div><h3>AI providers</h3><p>Credentials are configured only in backend/.env and are never shown here.</p></div><select aria-label="Default AI provider" value={providerCatalog?.default_provider || "auto"} onChange={(event) => void chooseAIProvider(event.target.value).then(() => fetchAIProviders().then(setProviderCatalog)).catch((e) => setError(e.message))}><option value="auto">Auto</option><option value="openai">OpenAI</option><option value="gemini">Gemini</option><option value="ollama">Ollama</option></select></div>{(providerCatalog?.providers || []).map((provider) => <div className="provider-row" key={provider.provider}><div><strong>{provider.provider}</strong><span>{provider.model} · {provider.configured ? "Credentials configured" : "Not configured"} · {provider.available ? "Connected" : "Unavailable"}</span></div><button type="button" className="secondary-action" onClick={() => void testAIProvider(provider.provider).then((result) => setProviderCatalog((current) => ({ ...current, providers: (current.providers || []).map((item) => item.provider === provider.provider ? result : item) }))).catch((e) => setError(e.message))}>Test</button></div>)}{providerCatalog?.usage && <p className="workspace-note">Usage: {Object.entries(providerCatalog.usage).map(([name, usage]) => `${name} ${usage.prompt_tokens + usage.completion_tokens} tokens · $${usage.estimated_cost.toFixed(4)}`).join(" · ")}</p>}</section><div className="status-grid"><div><small>AI SERVICE</small><strong>{canChat ? "Available" : "Unavailable"}</strong><span>{health?.ai_provider || "Provider details unavailable"} · {health?.model || "No model reported"}</span></div><div><small>APPEARANCE</small><strong>Cinematic dark</strong><span>Forest green accent · reduced motion supported</span></div><div><small>PRIVACY</small><strong>{localProvider ? "Local runtime" : health?.ai_provider || "Unknown"}</strong><span>{localProvider ? "Prompts stay on device when Ollama is local" : "Provider-reported processing"}</span></div><div><small>VOICE</small><strong>{voiceStatus?.wake_word_phrase || "Hello JARVIS Scott here"}</strong><span>{voiceStatus?.wake_word_listening ? "Listening locally" : "Background listening is off"}</span></div></div></div>}
          {(activePage === "Device & System Monitor" || activePage === "Activity Logs") && <div className="workspace-card"><div className="workspace-card-head"><div><h2>{activePage === "Device & System Monitor" ? "Service health" : "Recent service state"}</h2><p>Only health signals exposed by the backend are shown. Host metrics and detailed logs are not currently available through an API.</p></div><button className="secondary-action" onClick={() => void fetchHealth().then(setHealth).catch((e) => setError(e.message))}>Refresh health</button></div><div className="status-grid"><div><small>FASTAPI BACKEND</small><strong>{health?.status === "ok" ? "Healthy" : health?.status || "Unknown"}</strong><span>GET /api/health</span></div><div><small>AI PROVIDER</small><strong>{providerStatus}</strong><span>{health?.ai_provider || "Not reported"} · {health?.model || "No model reported"}</span></div><div><small>VOICE SERVICE</small><strong>{voiceStatus?.speech_recognition_available ? "Recognition ready" : "Optional dependencies missing"}</strong><span>{voiceStatus?.text_to_speech_available ? "Speech output ready" : "Piper voice not configured"}</span></div></div>{error && <p className="error-banner">{error}</p>}</div>}
          {(activePage === "Integrations" || ["WhatsApp", "Research", "Files & Documents", "Tasks & Automations", "Scheduled Activities", "Contacts"].includes(activePage)) && <div className="workspace-card unavailable-card"><div className="unavailable-icon"><Activity size={20}/></div><h2>{activePage} is not connected</h2><p>This installation does not expose a backend service for {activePage.toLowerCase()} yet. JARVIS will show this workspace as available when a real integration is configured.</p><span className="cap-status unavailable">NOT AVAILABLE IN THIS BACKEND</span></div>}
          {error && !["Voice", "Device & System Monitor", "Activity Logs"].includes(activePage) && <p className="error-banner">{error}</p>}
        </section>}
        <button className="scroll-hint" aria-label="Scroll to latest" onClick={() => bottomRef.current?.scrollIntoView?.({ behavior: "smooth" })}>
          <ArrowDown size={15} />
        </button>
      </section>
    </main>
  );
}
