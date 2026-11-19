import { useEffect, useMemo, useRef, useState } from "react";
import BackgroundWakeListener from "./BackgroundWakeListener.jsx";
import "./HomeScreen.css";

const DEFAULT_CHIPS = [
  { label: "Open an app", icon: "app" },
  { label: "Find a file", icon: "file" },
  { label: "Set a reminder", icon: "reminder" },
  { label: "System controls", icon: "system" },
];

const ADMIN_COMMAND = { label: "Run a command…", group: "Admin", badge: "HIGH", icon: "lock", admin: true };

const COMMANDS = [
  { label: "Open Spotify", group: "Apps" },
  { label: "Open Slack", group: "Apps" },
  { label: "Find launch deck", group: "Files" },
  { label: "Find invoices", group: "Files" },
  { label: "Set reminder: ship tonight", group: "Reminders" },
  { label: "Mute microphone", group: "System" },
  { label: "Toggle night mode", group: "System" },
  ADMIN_COMMAND,
  { label: "Restart background sync", group: "Admin" },
];

function Icon({ name, size = 22 }) {
  const paths = {
    home: <><path d="m3 10 9-7 9 7" /><path d="M5 9v11h14V9" /><path d="M9 20v-6h6v6" /></>,
    whatsapp: <><path d="M21 11.5a8.4 8.4 0 0 1-.9 3.8 8.5 8.5 0 0 1-7.6 4.7 8.4 8.4 0 0 1-3.8-.9L3 21l1.9-5.7a8.4 8.4 0 0 1-.9-3.8 8.5 8.5 0 0 1 4.7-7.6 8.4 8.4 0 0 1 3.8-.9h.5a8.5 8.5 0 0 1 8 8z" /><path d="M9 9a5 5 0 0 0 6 6l1-1-2-2-1 1a3 3 0 0 1-2-2l1-1-2-2z" /></>,
    tools: <><path d="M14.7 6.3a5 5 0 0 0-6.4 6.4L3 18l3 3 5.3-5.3a5 5 0 0 0 6.4-6.4L15 12l-3-3z" /><path d="m15 6 3-3 3 3-3 3" /></>,
    settings: <><circle cx="12" cy="12" r="3" /><path d="m19.4 15 .1.1 1.4 1.1-1.4 2.4-1.7-.6a8 8 0 0 1-1.7 1l-.3 1.8h-2.8l-.3-1.8a8 8 0 0 1-1.7-1l-1.7.6-1.4-2.4 1.4-1.1a7 7 0 0 1 0-2l-1.4-1.1 1.4-2.4 1.7.6a8 8 0 0 1 1.7-1l.3-1.8h2.8l.3 1.8a8 8 0 0 1 1.7 1l1.7-.6 1.4 2.4-1.4 1.1a7 7 0 0 1 0 2Z" /></>,
    message: <><path d="M21 11.5a8.4 8.4 0 0 1-.9 3.8 8.5 8.5 0 0 1-7.6 4.7 8.4 8.4 0 0 1-3.8-.9L3 21l1.9-5.7a8.4 8.4 0 0 1-.9-3.8 8.5 8.5 0 0 1 4.7-7.6 8.4 8.4 0 0 1 3.8-.9h.5a8.5 8.5 0 0 1 8 8z" /></>,
    search: <><circle cx="11" cy="11" r="7" /><path d="m20 20-4-4" /></>,
    x: <><path d="m18 6-12 12M6 6l12 12" /></>,
    shield: <><path d="M12 3 5 6v5c0 4.3 2.8 8.3 7 10 4.2-1.7 7-5.7 7-10V6l-7-3Z" /><path d="M9.5 12.5 11.3 14.4l3.2-4.2" /></>,
    check: <><path d="m5 12 4 4L19 6" /></>,
    lock: <><rect x="5" y="11" width="14" height="9" rx="2" /><path d="M8 11V8a4 4 0 1 1 8 0v3" /></>,
    stop: <><rect x="7" y="7" width="10" height="10" rx="2" /></>,
    clock: <><circle cx="12" cy="12" r="8" /><path d="M12 7v5l3 2" /></>,
    app: <><rect x="4" y="5" width="16" height="14" rx="2" /><path d="M8 9h8M8 13h5" /></>,
    file: <><path d="M14 3h5v5" /><path d="M14 3v5h5" /><path d="M5 7h7v13H5z" /><path d="M12 7h5v5h-5" /></>,
    reminder: <><path d="M12 2.5v3" /><path d="M12 22a6 6 0 1 1 0-12 6 6 0 0 1 0 12Z" /><path d="M12 7v5l3 2" /></>,
    system: <><path d="M12 3v4" /><path d="M12 17v4" /><path d="M4.93 4.93l2.83 2.83" /><path d="M16.24 16.24l2.83 2.83" /><path d="M3 12h4" /><path d="M17 12h4" /><path d="M4.93 19.07l2.83-2.83" /><path d="M16.24 7.76l2.83-2.83" /><circle cx="12" cy="12" r="3.5" /></>,
    alert: <><path d="M12 3 2.5 19h19L12 3Z" /><path d="M12 9v4" /><path d="M12 16h.01" /></>,
    camera: <><path d="M23 19a2 2 0 0 1-2 2H3a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h4l2-3h6l2 3h4a2 2 0 0 1 2 2Z" /><circle cx="12" cy="13" r="5" /></>,
    mic: <><path d="M12 3a3 3 0 0 1 3 3v6a3 3 0 1 1-6 0V6a3 3 0 0 1 3-3Z" /><path d="M19 10a7 7 0 0 1-14 0" /><path d="M12 17v4" /></>,
    bolt: <><path d="M13 2 5 13h5l-1 9 8-11h-5l1-9Z" /></>,
    spark: <><path d="m12 2 1.5 4.5L18 8l-4.5 1.5L12 14l-1.5-4.5L6 8l4.5-1.5L12 2Z" /></>,
    chevron: <><path d="m9 18 6-6-6-6" /></>,
    dot: <><circle cx="12" cy="12" r="6" /></>,
  };

  return (
    <svg
      aria-hidden="true"
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      {paths[name] || null}
    </svg>
  );
}

function greetingFor(hour) {
  if (hour < 12) return "Good morning";
  if (hour < 18) return "Good afternoon";
  return "Good evening";
}

function Rail({ onNavigate, onOpenActivity, activeWorkspace }) {
  return (
    <aside className="home-rail" aria-label="Main navigation">
      <button className="rail-logo" type="button" aria-label="JARVIS home" onClick={() => onNavigate("Home")}>J</button>
      <nav className="rail-navigation" aria-label="Navigation items">
        <button className={`rail-button ${activeWorkspace === "Home" ? "is-active" : ""}`} type="button" aria-label="Home" onClick={() => onNavigate("Home")}><Icon name="home" size={18} /></button>
        <button className="rail-button" type="button" aria-label="Chat" onClick={() => onNavigate("Chat")}><Icon name="message" size={18} /></button>
        <button className={`rail-button ${activeWorkspace === "WhatsApp" ? "is-active" : ""}`} type="button" aria-label="WhatsApp" onClick={() => onNavigate("WhatsApp")}><Icon name="whatsapp" size={18} /></button>
        <button className={`rail-button ${activeWorkspace === "Tools & Utilities" ? "is-active" : ""}`} type="button" aria-label="Tools" onClick={() => onNavigate("Tools & Utilities")}><Icon name="tools" size={18} /></button>
        <button className={`rail-button ${activeWorkspace === "Settings" ? "is-active" : ""}`} type="button" aria-label="Settings" onClick={() => onNavigate("Settings")}><Icon name="settings" size={18} /></button>
        <button className="rail-button activity-button" type="button" aria-label="Activity" onClick={onOpenActivity}><Icon name="clock" size={18} /></button>
      </nav>
      <div className="rail-spacer" />
      <div className="rail-avatar" aria-label="Newton">N</div>
    </aside>
  );
}

function TrustPill({ status, onOpen }) {
  const text = {
    unverified: "Admin unverified",
    verifying: "Verifying…",
    locked: "Locked",
  };

  return (
    <button type="button" className={`trust-pill trust-pill--${status}`} onClick={onOpen} aria-label={`Trust status: ${text[status]}`}>
      {status === "unverified" && <Icon name="shield" size={14} />}
      {status === "verifying" && <span className="trust-dot" />}
      {status === "locked" && <Icon name="lock" size={13} />}
      <span>{text[status]}</span>
    </button>
  );
}

function ModelMenu({ models, activeModel, provider, open, onSelect, onClose }) {
  if (!open) return null;

  return (
    <div className="home-model-menu" role="dialog" aria-label="Model menu">
      {models.length ? models.map((name) => (
        <button type="button" key={name} className={name === activeModel ? "is-active" : ""} onClick={() => { onSelect(name); onClose(); }}>
          <span>{name}</span>
          <span className="menu-tag">{provider === "ollama" ? "Local" : "Cloud"}</span>
          {name === activeModel && <span className="speed-tag">Speed: 8 tok/s</span>}
        </button>
      )) : <p>No local models are available.</p>}
      <button type="button" className="menu-disabled" disabled>Coming soon · Add API key</button>
    </div>
  );
}

function TopBar({ health, models, onSelectModel, trustState, onOpenTrust, onStop }) {
  const [now, setNow] = useState(() => new Date());
  const [pickerOpen, setPickerOpen] = useState(false);
  const model = health?.model || "Model unavailable";
  const providerName = health?.ai_provider === "ollama" ? "Local" : health?.ai_provider ? "Cloud" : "Unavailable";

  useEffect(() => {
    const timer = window.setInterval(() => setNow(new Date()), 30_000);
    return () => window.clearInterval(timer);
  }, []);

  const dateParts = new Intl.DateTimeFormat("en-US", {
    weekday: "short",
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  }).formatToParts(now).reduce((parts, item) => ({ ...parts, [item.type]: item.value }), {});
  const date = `${dateParts.weekday} · ${dateParts.month} ${dateParts.day} · ${dateParts.hour}:${dateParts.minute} ${dateParts.dayPeriod}`.toUpperCase();

  return (
    <header className="home-topbar">
      <div className="home-wordmark">JARVIS</div>
      <time className="home-date" dateTime={now.toISOString()}>{date}</time>
      <div className="home-actions-right">
        <button className="stop-button" type="button" aria-label="Stop" onClick={onStop}><Icon name="stop" size={14} />Stop</button>
        <TrustPill status={trustState} onOpen={onOpenTrust} />
        <div className="model-control">
          <button className="model-pill" type="button" aria-expanded={pickerOpen} onClick={() => setPickerOpen((open) => !open)}>
            <span className={`model-dot ${health?.status === "ok" ? "is-ready" : ""}`} />
            <span>{model}</span>
            <strong>{providerName}</strong>
          </button>
          <ModelMenu models={models} activeModel={model} provider={providerName.toLowerCase()} open={pickerOpen} onSelect={onSelectModel} onClose={() => setPickerOpen(false)} />
        </div>
      </div>
    </header>
  );
}

function QuickChips({ chips = DEFAULT_CHIPS, contextual = [], onRunAction, isLocked = false }) {
  return (
    <div className="quick-chips" aria-label="Quick actions">
      {contextual.map((item, index) => (
        <button type="button" key={`ctx-${index}`} className="contextual-chip" disabled={isLocked} aria-label={isLocked ? `${item.label} — locked` : item.label} onClick={() => onRunAction(item.label)}>
          <span className="chip-dot" />
          {isLocked && <Icon name="lock" size={14} />}
          <span>{item.label}</span>
        </button>
      ))}
      {chips.map((chip) => (
        <button type="button" key={chip.label} disabled={isLocked} aria-label={isLocked ? `${chip.label} — locked` : chip.label} onClick={() => onRunAction(chip.label)}>
          <Icon name={isLocked ? "lock" : chip.icon} size={15} />
          <span>{chip.label}</span>
        </button>
      ))}
    </div>
  );
}

function CommandPalette({ open, onClose, onRunAction }) {
  const [query, setQuery] = useState("");
  const searchRef = useRef(null);
  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    return COMMANDS.filter((item) => !q || `${item.label} ${item.group}`.toLowerCase().includes(q));
  }, [query]);

  useEffect(() => {
    if (!open) {
      setQuery("");
      return undefined;
    }
    searchRef.current?.focus();
    const onKeyDown = (event) => {
      if (event.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [open, onClose]);

  if (!open) return null;

  return (
    <div className="palette-backdrop" onMouseDown={(event) => { if (event.target === event.currentTarget) onClose(); }}>
      <section className="command-palette" role="dialog" aria-modal="true" aria-label="Command palette">
        <div className="palette-search">
          <Icon name="search" size={18} />
          <input ref={searchRef} aria-label="Search actions" value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search actions..." />
          <button type="button" aria-label="Close command palette" onClick={onClose}><Icon name="x" size={18} /></button>
        </div>
        <div className="palette-groups">
          {!filtered.length && <p className="palette-empty">No matching actions.</p>}
          {Object.entries({ Apps: [], Files: [], Reminders: [], System: [], Admin: [] }).map(([group, items]) => {
            const matches = filtered.filter((item) => item.group === group);
            if (!matches.length) return null;
            return (
              <div key={group} className="palette-group">
                <div className="palette-group-label">{group}</div>
                {matches.slice(0, 4).map((item) => (
                  <button key={item.label} type="button" className={item.admin ? "admin-result" : ""} onClick={() => { onRunAction(item.label); onClose(); }}>
                    <span>{item.label}</span>
                    {item.badge && <em>{item.badge}</em>}
                  </button>
                ))}
              </div>
            );
          })}
          <div className="palette-footer">+{Math.max(0, filtered.length - 8)} more, keep typing</div>
        </div>
      </section>
    </div>
  );
}

function ActivityDrawer({ open, onClose, history, onOpenConversation }) {
  if (!open) return null;
  const rows = (history || []).slice(0, 7);

  return (
    <div className="activity-drawer-backdrop" onMouseDown={(event) => { if (event.target === event.currentTarget) onClose(); }}>
      <aside className="activity-drawer" role="dialog" aria-modal="true" aria-label="Activity log drawer">
        <div className="drawer-header">
          <div>
            <span className="mono-label">ACTIVITY</span>
            <h2>Recent conversations</h2>
          </div>
          <button type="button" className="drawer-close" aria-label="Close activity" onClick={onClose}><Icon name="x" size={18} /></button>
        </div>
        <div className="drawer-list">
          {rows.map((conversation) => (
            <button key={conversation.id} type="button" className="drawer-row" onClick={() => { onOpenConversation(conversation.id); onClose(); }}>
              <time>{conversation.updated_at ? new Date(conversation.updated_at).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }) : "Saved"}</time>
              <div className="drawer-message">
                <strong>{conversation.title || "Untitled conversation"}</strong>
                <span>Saved conversation</span>
              </div>
              <Icon name="chevron" size={15} />
            </button>
          ))}
          {!rows.length && <p className="recent-empty">No saved conversations yet.</p>}
        </div>
      </aside>
    </div>
  );
}

function VerifyPanel({ open, onClose }) {
  const [cameraError, setCameraError] = useState("");
  const [pinEntry, setPinEntry] = useState("");
  const [pinFeedback, setPinFeedback] = useState("");
  const [pinStatus, setPinStatus] = useState("input");
  const videoRef = useRef(null);
  const pinInputRef = useRef(null);
  const onCloseRef = useRef(onClose);

  useEffect(() => {
    if (open) {
      setPinEntry("");
      setPinFeedback("");
      setPinStatus("input");
    }
  }, [open]);

  useEffect(() => {
    if (pinEntry.length === 4 && pinStatus === "input") {
      setPinStatus("verifying");
    }
  }, [pinEntry, pinStatus]);

  useEffect(() => {
    if (pinStatus !== "verifying") return undefined;
    const timer = window.setTimeout(() => {
      setPinEntry("");
      setPinFeedback("Demo only — no PIN was checked. Admin actions remain unverified.");
      setPinStatus("verified");
    }, 2650);
    return () => window.clearTimeout(timer);
  }, [pinStatus]);

  useEffect(() => {
    onCloseRef.current = onClose;
  }, [onClose]);

  useEffect(() => {
    if (!open) return undefined;
    let active = true;
    let stream;
    if (!navigator.mediaDevices?.getUserMedia) {
      setCameraError("Camera access is unavailable in this browser.");
      return undefined;
    }

    setCameraError("");
    navigator.mediaDevices.getUserMedia({ video: { facingMode: "user" }, audio: false })
      .then((cameraStream) => {
        if (!active) {
          cameraStream.getTracks().forEach((track) => track.stop());
          return;
        }
        stream = cameraStream;
        if (videoRef.current) videoRef.current.srcObject = cameraStream;
      })
      .catch((error) => {
        if (!active) return;
        setCameraError(error.name === "NotAllowedError"
          ? "Camera permission was denied. Allow camera access to continue."
          : "Could not open the camera. Check that it is connected and available.");
      });

    const onKeyDown = (event) => {
      if (event.key === "Escape") onCloseRef.current();
    };
    window.addEventListener("keydown", onKeyDown);
    return () => {
      active = false;
      window.removeEventListener("keydown", onKeyDown);
      stream?.getTracks().forEach((track) => track.stop());
      if (videoRef.current) videoRef.current.srcObject = null;
    };
  }, [open]);

  if (!open) return null;

  return (
    <div className="verification-backdrop" onMouseDown={(event) => { if (event.target === event.currentTarget) onClose(); }}>
      <div className="verification-ambient" aria-hidden="true">
        <span className="verification-hud-ring verification-hud-ring--outer" />
        <span className="verification-hud-ring verification-hud-ring--inner" />
        <span className="verification-light-ribbon verification-light-ribbon--amber" />
        <span className="verification-light-ribbon verification-light-ribbon--cyan" />
        <span className="verification-light-ribbon verification-light-ribbon--emerald" />
      </div>
      <section className="verification-panel" role="dialog" aria-modal="true" aria-label="Verification panel">
        <div className="verification-header">
          <div>
            <span className="mono-label">VERIFY</span>
            <h2>Confirm it is you</h2>
          </div>
          <button type="button" className="panel-close" aria-label="Close verification" onClick={onClose}><Icon name="x" size={18} /></button>
        </div>

        <div className="verification-grid">
          <div className="verify-card">
            <div className="verify-card-head">
              <span className="mono-label">Face</span>
              <span className="verify-state">Not configured</span>
            </div>
            <div className="face-visual">
              <div className="camera-preview">
                <video ref={videoRef} className="camera-feed" autoPlay muted playsInline aria-label="Live camera preview" />
                <div className="camera-ring" />
              </div>
            </div>
            <p>Look at the camera</p>
            <small>Turn your head left, then blink</small>
            {cameraError && <small className="camera-error" role="alert">{cameraError}</small>}
            <div className="pin-steps"><span>Camera preview</span><span>Face matching unavailable</span></div>
            <button type="button" disabled>Face verification unavailable</button>
          </div>

          <div className="verify-card">
            <div className="verify-card-head">
              <span className="mono-label">Voice</span>
              <span className="verify-state">Not configured</span>
            </div>
            <div className="voice-wave-wrap" aria-label="Voice waveform">
              {[...Array(18)].map((_, index) => (<span key={index} style={{ height: `${16 + ((index * 7) % 10) * 5}px` }} />))}
            </div>
            <p>Read this phrase aloud</p>
            <strong>Voice matching is not configured.</strong>
            <button type="button" disabled>Voice verification unavailable</button>
          </div>

          <div className={`verify-card pin-card pin-card--${pinStatus}`}>
            <div className="verify-card-head">
              <span className="mono-label">PIN</span>
              <span className="verify-state">{pinStatus === "verified" ? "Demo state" : "Not configured"}</span>
            </div>
            <p className="pin-stage-title" aria-live="polite">
              {pinStatus === "verifying" ? "Verifying Code..." : pinStatus === "verified" ? "Verified Successfully" : "Verify PIN"}
            </p>
            <div className="pin-code-stage">
              <button
                type="button"
                className="pin-slots"
                aria-label="Enter four-digit PIN"
                onClick={() => pinInputRef.current?.focus()}
                disabled={pinStatus !== "input"}
              >
                {[0, 1, 2, 3].map((index) => (
                  <span className={`pin-slot ${pinEntry.length > index ? "is-filled" : ""}`} key={index}>
                    <span className="pin-slot-digit">{pinEntry[index] || ""}</span>
                  </span>
                ))}
              </button>
              <input
                ref={pinInputRef}
                className="pin-native-input"
                aria-label="PIN"
                type="password"
                inputMode="numeric"
                autoComplete="one-time-code"
                maxLength={4}
                value={pinEntry}
                disabled={pinStatus !== "input"}
                onChange={(event) => {
                  setPinEntry(event.target.value.replace(/\D/g, "").slice(0, 4));
                  setPinFeedback("");
                }}
              />
              <div className="pin-security-mark" aria-hidden="true">
                <Icon name={pinStatus === "verified" ? "check" : "shield"} size={28} />
              </div>
            </div>
            <div className="pin-grid">
              {[1,2,3,4,5,6,7,8,9,0].map((value) => (
                <button
                  key={value}
                  type="button"
                  className="pin-key"
                  aria-label={`Enter PIN digit ${value}`}
                  disabled={pinStatus !== "input" || pinEntry.length >= 4}
                  onClick={() => {
                    setPinEntry((current) => current.length < 4 ? `${current}${value}` : current);
                    setPinFeedback("");
                  }}
                >
                  {value}
                </button>
              ))}
            </div>
            <button
              type="button"
              className="pin-submit"
              disabled={pinStatus !== "input" || pinEntry.length < 4}
              onClick={() => {
                if (pinEntry.length === 4) setPinStatus("verifying");
              }}
            >
              {pinStatus === "verifying" && <span className="pin-spinner" aria-hidden="true" />}
              {pinStatus === "verifying" ? "Verifying Code..." : pinStatus === "verified" ? <><Icon name="check" size={16} /> Verified &amp; Secured</> : "Verify PIN"}
            </button>
            {pinFeedback && <small className="pin-feedback" role="alert">{pinFeedback}</small>}
          </div>
        </div>

        <div className="verify-rule">No verification method is configured. Admin actions remain unverified.</div>
        <div className="verification-footer"><span><Icon name="lock" size={12} /> Face and voice data stay on this device.</span></div>
      </section>
    </div>
  );
}

function ConfirmCard({ open, action, onConfirm, onCancel }) {
  if (!open || !action) return null;

  const [progress, setProgress] = useState(0);
  const [holding, setHolding] = useState(false);

  useEffect(() => {
    if (!holding || !action.highRisk) return undefined;
    const frame = window.requestAnimationFrame(function tick() {
      setProgress((value) => {
        const next = Math.min(1, value + 0.04);
        if (next >= 1) {
          onConfirm();
          return 1;
        }
        window.requestAnimationFrame(tick);
        return next;
      });
    });
    return () => window.cancelAnimationFrame(frame);
  }, [holding, action.highRisk, onConfirm]);

  useEffect(() => {
    const onKeyDown = (event) => {
      if (event.key === "Escape") onCancel();
      if (event.key === "Enter" && !action.highRisk) onConfirm();
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [action, onCancel, onConfirm]);

  const targetText = action.targets?.slice(0, 3).join(", ") || "This device";

  return (
    <div className="confirm-overlay" role="alertdialog" aria-live="assertive">
      <div className="confirm-card" style={{ borderColor: action.highRisk ? "var(--danger-red)" : "var(--accent-green)" }}>
        <div className="confirm-header">
          <span className={`tier-badge ${action.highRisk ? "high" : "low"}`}>{action.highRisk ? "HIGH" : "LOW"}</span>
          <h3>{action.title}</h3>
        </div>
        <p className="confirm-description">{action.description}</p>
        <div className="confirm-targets"><span>{targetText}</span>{action.targets?.length > 3 && <span>+{action.targets.length - 3} more</span>}</div>
        <div className="confirm-source">Requested by: you (voice)</div>
        <div className="confirm-actions">
          {action.highRisk ? (
            <button type="button" className="confirm-button high" onMouseDown={() => setHolding(true)} onMouseUp={() => setHolding(false)} onMouseLeave={() => setHolding(false)}>
              <span className="confirm-ring" style={{ background: `conic-gradient(var(--danger-red) ${progress * 360}deg, rgba(255,255,255,0.12) ${progress * 360}deg)` }} />
              Hold to confirm
            </button>
          ) : (
            <button type="button" className="confirm-button low" onClick={onConfirm}>Confirm</button>
          )}
          <button type="button" className="cancel-button" onClick={onCancel}>Cancel</button>
        </div>
      </div>
    </div>
  );
}

function PipelineIndicator({ activeStep }) {
  const steps = ["Listening", "Transcribing", "Thinking", "Speaking"];
  const activeIndex = steps.indexOf(activeStep);

  return (
    <div className="pipeline-indicator" aria-live="polite">
      {steps.map((step, index) => {
        const status = index < activeIndex ? "done" : index === activeIndex ? "active" : "pending";
        return (
          <div key={step} className={`pipeline-step ${status}`}>
            <span className="step-bullet">{index < activeIndex ? "✓" : index === activeIndex ? "•" : ""}</span>
            <span>{step}</span>
          </div>
        );
      })}
    </div>
  );
}

function CoreArtwork({ state, level }) {
  const bars = [246, 259, 272, 285, 298, 311, 324, 337, 350];
  const accent = state === "locked" ? "var(--warning-amber)" : state === "thinking" ? "var(--accent-thinking)" : "var(--accent-green)";

  return (
    <svg className={`core-artwork state-${state}`} viewBox="0 0 600 600" role="img" aria-label={`JARVIS core ${state}`}>
      <defs>
        <radialGradient id="core-glow">
          <stop offset="0%" stopColor={accent} stopOpacity=".55" />
          <stop offset="60%" stopColor={accent} stopOpacity=".12" />
          <stop offset="100%" stopColor={accent} stopOpacity="0" />
        </radialGradient>
        <filter id="core-node-glow" x="-200%" y="-200%" width="500%" height="500%">
          <feGaussianBlur stdDeviation="5" result="blur" />
          <feMerge><feMergeNode in="blur" /><feMergeNode in="SourceGraphic" /></feMerge>
        </filter>
      </defs>
      <circle className="core-aura" cx="300" cy="300" r="190" fill="url(#core-glow)" />
      <g className="core-ring core-ring-one"><circle cx="300" cy="300" r="285" fill="none" stroke="var(--border-strong)" strokeWidth="1.5" strokeDasharray="2 10" /><circle cx="300" cy="300" r="262" fill="none" stroke={accent} strokeOpacity=".5" strokeWidth="10" strokeDasharray="1 17" /></g>
      <g className="core-ring core-ring-two"><circle cx="300" cy="300" r="236" fill="none" stroke={accent} strokeWidth="3" strokeDasharray="150 70 40 90 220 60" strokeLinecap="round" /></g>
      <g className="core-ring core-ring-three"><circle cx="300" cy="300" r="205" fill="none" stroke="var(--border-pill)" strokeWidth="2" /><circle cx="300" cy="95" r="8" fill={accent} filter="url(#core-node-glow)" /><circle cx="478" cy="403" r="5" fill={accent} filter="url(#core-node-glow)" /><circle cx="122" cy="403" r="5" fill={accent} filter="url(#core-node-glow)" /></g>
      <g className="core-ring core-ring-four"><circle cx="300" cy="300" r="165" fill="none" stroke={accent} strokeOpacity=".7" strokeWidth="1.5" strokeDasharray="6 6" /><path d="M300 135a165 165 0 0 1 143 82" fill="none" stroke={accent} strokeWidth="5" strokeLinecap="round" /></g>
      <circle className="core-disc" cx="300" cy="300" r="105" fill="var(--core-disc)" stroke={state === "stopped" ? "var(--danger-red)" : accent} strokeWidth="2" />
      <g className="core-waveform" style={{ "--mic-level": level }}>
        {bars.map((x, index) => (
          <rect
            key={x}
            className="core-wave-bar"
            x={x}
            y="260"
            width="7"
            height="80"
            rx="3.5"
            fill={accent}
            style={{ "--bar-delay": `${index * 0.13}s`, "--bar-level": level, transformOrigin: `${x + 3.5}px 300px` }}
          />
        ))}
      </g>
    </svg>
  );
}

function SideCards({ history, systemMetrics, onWhatsApp, onOpenConversation, isLocked }) {
  const recent = (history || [])
    .filter((conversation) => !/plan my day|check whatsapp/i.test(conversation.title || ""))
    .slice(0, 3);
  return (
      <section className={`side-column right-side ${isLocked ? "is-locked" : ""}`} aria-label="WhatsApp, system, and recent conversations">
        <button className="home-card whatsapp-card" type="button" onClick={onWhatsApp}>
          <span className="mono-label">WHATSAPP</span>
          <strong className="whatsapp-value">Unavailable</strong>
          <span className="card-description">No authorized WhatsApp integration is configured</span>
        </button>
        <section className="home-card system-card">
          <span className="mono-label">SYSTEM</span>
          <div className="metric-row"><div className="metric-label"><span>CPU</span><strong>{Number.isFinite(systemMetrics?.cpu_percent) ? `${Math.round(systemMetrics.cpu_percent)}%` : "Unavailable"}</strong></div><div className="metric-track"><span style={{ width: `${Math.min(100, Math.max(0, systemMetrics?.cpu_percent || 0))}%` }} /></div></div>
          <div className="metric-row"><div className="metric-label"><span>RAM</span><strong>{Number.isFinite(systemMetrics?.memory_percent) ? `${Math.round(systemMetrics.memory_percent)}%` : "Unavailable"}</strong></div><div className="metric-track"><span style={{ width: `${Math.min(100, Math.max(0, systemMetrics?.memory_percent || 0))}%` }} /></div></div>
        </section>
        <section className="home-card recent-card">
          <span className="mono-label">RECENT</span>
          {recent.length ? recent.map((conversation) => (
            <button className="recent-row" key={conversation.id} type="button" onClick={() => onOpenConversation(conversation.id)} title={conversation.title || "Conversation"}>
              <Icon name="message" size={16} />
              <span>{conversation.title || "Untitled conversation"}</span>
            </button>
          )) : <p className="recent-empty">No saved conversations yet.</p>}
        </section>
      </section>
  );
}

function WhatsAppWorkspace({ onBack }) {
  return (
    <section className="whatsapp-workspace" aria-label="WhatsApp workspace">
      <aside className="whatsapp-conversations">
        <div className="whatsapp-workspace-heading">
          <div>
            <span className="mono-label">INTEGRATED WORKSPACE</span>
            <h1>WhatsApp</h1>
          </div>
          <button type="button" className="whatsapp-back" onClick={onBack}>Back to dashboard</button>
        </div>
        <label className="whatsapp-search">
          <Icon name="search" size={16} />
          <input type="search" aria-label="Search WhatsApp conversations" placeholder="Search conversations" disabled />
        </label>
        <div className="whatsapp-empty-list">
          <Icon name="message" size={20} />
          <strong>No conversations available</strong>
          <span>Connect an authorized WhatsApp integration to load chats.</span>
        </div>
      </aside>
      <section className="whatsapp-conversation" aria-label="Selected conversation">
        <div className="whatsapp-connection-status">
          <span className="connection-indicator" />
          <div>
            <strong>WhatsApp integration unavailable</strong>
            <p>The backend has no authorized WhatsApp adapter configured. JARVIS cannot read or send messages.</p>
          </div>
        </div>
        <div className="whatsapp-no-selection">
          <Icon name="whatsapp" size={34} />
          <strong>Select a conversation</strong>
          <span>Messages will appear here when an authorized integration is available.</span>
        </div>
        <form className="whatsapp-composer" onSubmit={(event) => event.preventDefault()}>
          <input aria-label="WhatsApp message" placeholder="Messaging unavailable until WhatsApp is connected" disabled />
          <button type="button" aria-label="Attach file" disabled>+</button>
          <button type="submit" aria-label="Send message" disabled><Icon name="message" size={16} /></button>
        </form>
      </section>
    </section>
  );
}

function HomeWorkspace({
  workspace,
  health,
  systemMetrics,
  aiStatus,
  voiceStatus,
  backgroundListening,
  backgroundEnabled,
  backgroundAvailable,
  onBack,
  onRunAction,
  onSavePersonality,
  onError,
  onToggleBackgroundListening,
}) {
  const [personality, setPersonality] = useState(aiStatus?.personality || "");

  useEffect(() => {
    setPersonality(aiStatus?.personality || "");
  }, [aiStatus?.personality]);

  const cpu = Number.isFinite(systemMetrics?.cpu_percent) ? `${Math.round(systemMetrics.cpu_percent)}%` : "Unavailable";
  const ram = Number.isFinite(systemMetrics?.memory_percent) ? `${Math.round(systemMetrics.memory_percent)}%` : "Unavailable";
  return (
    <section className="home-workspace" aria-label={`${workspace} workspace`}>
      <header className="home-workspace-heading">
        <div>
          <span className="mono-label">JARVIS WORKSPACE</span>
          <h1>{workspace}</h1>
        </div>
        <button type="button" className="whatsapp-back" onClick={onBack}>Back to dashboard</button>
      </header>
      {workspace === "Tools & Utilities" ? (
        <div className="home-workspace-grid">
          <section className="home-workspace-card">
            <span className="mono-label">ASSISTANT TOOLS</span>
            <h2>Ask JARVIS</h2>
            <p>These actions are handled through the configured assistant. The backend determines whether each capability is available.</p>
            <div className="tool-action-list">
              {DEFAULT_CHIPS.map((chip) => (
                <button key={chip.label} type="button" onClick={() => onRunAction(chip.label)}>
                  <Icon name={chip.icon} size={16} /><span>{chip.label}</span><Icon name="chevron" size={15} />
                </button>
              ))}
            </div>
          </section>
          <section className="home-workspace-card">
            <span className="mono-label">SYSTEM MONITOR</span>
            <h2>Live device status</h2>
            <div className="workspace-metric"><span>CPU</span><strong>{cpu}</strong></div>
            <div className="workspace-metric"><span>RAM</span><strong>{ram}</strong></div>
            <div className="workspace-metric"><span>Assistant backend</span><strong>{health?.status === "ok" ? "Connected" : "Unavailable"}</strong></div>
          </section>
        </div>
      ) : (
        <div className="home-workspace-grid">
          <section className="home-workspace-card">
            <span className="mono-label">ASSISTANT</span>
            <h2>Personality</h2>
            <form className="home-settings-form" onSubmit={async (event) => {
              event.preventDefault();
              try {
                await onSavePersonality?.(personality);
              } catch (error) {
                onError?.(error.message);
              }
            }}>
              <label htmlFor="home-personality">Instructions</label>
              <textarea id="home-personality" value={personality} onChange={(event) => setPersonality(event.target.value)} placeholder="Set the assistant's response style" maxLength={500} required />
              <button type="submit">Save personality</button>
            </form>
          </section>
          <section className="home-workspace-card">
            <span className="mono-label">VOICE & PRIVACY</span>
            <h2>Background listening</h2>
            <p>Wake phrase: <strong>{voiceStatus?.wake_word_phrase || "Hello JARVIS Scott here"}</strong></p>
            <button
              type="button"
              className={`background-listening-control ${backgroundListening ? "is-active" : ""}`}
              disabled={!backgroundEnabled && !backgroundAvailable}
              aria-pressed={backgroundListening}
              aria-label={backgroundListening ? "Turn off background listening" : "Turn on background listening"}
              onClick={onToggleBackgroundListening}
            >
              {backgroundEnabled && !backgroundListening
                ? "Connecting to local listener…"
                : backgroundListening
                  ? "Turn off background listening"
                  : "Turn on background listening"}
            </button>
            <p className="workspace-note" role="status">
              {backgroundListening
                ? `Listening locally for “${voiceStatus?.wake_word_phrase || "Hello JARVIS Scott here"}”.`
                : backgroundEnabled
                  ? "Connecting to the configured local wake-word detector."
                : backgroundAvailable
                  ? "Off. Turn it on to listen for the local wake phrase."
                  : (voiceStatus?.background_listening_reason || "Configure the local wake-word model and speech recognizer before enabling microphone capture.")}
            </p>
            <div className="workspace-metric"><span>Speech recognition</span><strong>{voiceStatus?.speech_recognition_available ? "Available" : "Not configured"}</strong></div>
            <div className="workspace-metric"><span>Wake-word detector</span><strong>{voiceStatus?.wake_word_available ? "Ready" : "Not configured"}</strong></div>
          </section>
          <section className="home-workspace-card">
            <span className="mono-label">SERVICE STATUS</span>
            <h2>Connected services</h2>
            <div className="workspace-metric"><span>AI provider</span><strong>{health?.ai_provider || "Unavailable"}</strong></div>
            <div className="workspace-metric"><span>Model</span><strong>{health?.model || "Unavailable"}</strong></div>
            <div className="workspace-metric"><span>Backend</span><strong>{health?.status === "ok" ? "Connected" : "Unavailable"}</strong></div>
            {aiStatus?.error && <p className="workspace-note">{aiStatus.error}</p>}
          </section>
        </div>
      )}
    </section>
  );
}

export default function HomeScreen({
  activeWorkspace = "Home",
  health,
  systemMetrics,
  aiStatus,
  voiceStatus,
  history,
  busy,
  canChat,
  responsePhase,
  error,
  onRunAction,
  onOpenConversation,
  onNavigate,
  onSelectModel,
  onSavePersonality,
  onBackgroundState,
  onSendMessage,
  onError,
  onDismissError,
}) {
  const [now, setNow] = useState(() => new Date());
  const [commandOpen, setCommandOpen] = useState(false);
  const [activityOpen, setActivityOpen] = useState(false);
  const trustState = "unverified";
  const [verificationOpen, setVerificationOpen] = useState(false);
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [confirmAction, setConfirmAction] = useState(null);
  const [demoState, setDemoState] = useState("idle");
  const [actionPrompt, setActionPrompt] = useState("Which app?");
  const [messageDraft, setMessageDraft] = useState("");
  const [backgroundEnabled, setBackgroundEnabled] = useState(false);
  const [backgroundListening, setBackgroundListening] = useState(false);
  const [backgroundStream, setBackgroundStream] = useState(null);
  const backgroundStreamRef = useRef(null);
  const contextual = [];

  const effectiveState = demoState === "idle" ? (busy ? (responsePhase === "speaking" ? "speaking" : "thinking") : "idle") : demoState;
  const isLocked = effectiveState === "locked";
  const backgroundAvailable = Boolean(voiceStatus?.wake_word_available && voiceStatus?.speech_recognition_available);

  useEffect(() => {
    const timer = window.setInterval(() => setNow(new Date()), 30_000);
    return () => window.clearInterval(timer);
  }, []);

  useEffect(() => () => {
    backgroundStreamRef.current?.getTracks().forEach((track) => track.stop());
  }, []);

  useEffect(() => {
    const onKeyDown = (event) => {
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "k") {
        event.preventDefault();
        setCommandOpen(true);
      } else if (event.key === "Escape") {
        setCommandOpen(false);
        setActivityOpen(false);
        setVerificationOpen(false);
        setConfirmOpen(false);
        if (["listening", "thinking", "speaking"].includes(effectiveState)) {
          setDemoState("stopped");
          setTimeout(() => setDemoState("idle"), 600);
        }
      }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [effectiveState]);

  const statusText = effectiveState === "locked"
    ? "LOCKED · SAY YOUR PASSPHRASE OR LOOK AT THE CAMERA"
    : effectiveState === "verifying"
      ? "VERIFYING…"
      : effectiveState === "thinking"
        ? "THINKING…"
        : effectiveState === "speaking"
          ? "SPEAKING…"
          : effectiveState === "stopped"
            ? "STOPPED"
            : effectiveState === "listening"
              ? `LISTENING · ${actionPrompt.toUpperCase()}`
              : backgroundListening
                ? `LISTENING FOR “${(voiceStatus?.wake_word_phrase || "Hello JARVIS Scott here").toUpperCase()}”`
                : backgroundAvailable
                  ? "BACKGROUND LISTENING OFF"
                  : (voiceStatus?.background_listening_reason || "BACKGROUND LISTENING UNAVAILABLE").toUpperCase();

  const toggleBackgroundListening = async () => {
    if (backgroundEnabled) {
      setBackgroundEnabled(false);
      setBackgroundListening(false);
      backgroundStreamRef.current?.getTracks().forEach((track) => track.stop());
      backgroundStreamRef.current = null;
      setBackgroundStream(null);
      return;
    }
    if (!backgroundAvailable) return;
    if (!navigator.mediaDevices?.getUserMedia) {
      onError?.("This browser can't access a microphone.");
      return;
    }
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      backgroundStreamRef.current = stream;
      setBackgroundStream(stream);
      setBackgroundEnabled(true);
    } catch (error) {
      onError?.(error.name === "NotAllowedError"
        ? "Microphone permission was denied. Allow microphone access to enable background listening."
        : "Could not open the microphone for background listening.");
    }
  };

  const handleChipAction = (label) => {
    const nextPrompt = label.toLowerCase().includes("app") ? "Which app?"
      : label.toLowerCase().includes("file") ? "Which file?"
      : label.toLowerCase().includes("reminder") ? "When should I remind you?"
      : label.toLowerCase().includes("system") ? "Which system control?"
      : "What do you need?";

    setActionPrompt(nextPrompt);
    onRunAction?.(label);
  };

  const handleStop = () => {
    setDemoState("stopped");
    setActionPrompt("Stopped");
    setTimeout(() => {
      setDemoState("idle");
      setActionPrompt("Which app?");
    }, 600);
  };

  const handleAdminCommand = (label) => {
    if (label.includes("Run a command")) {
      setConfirmAction({
        title: "Run a command",
        description: "This will launch a shell command in the terminal for your account.",
        targets: ["bash", "jarvis-admin"],
        highRisk: true,
      });
      setConfirmOpen(true);
      return;
    }
    handleChipAction(label);
  };

  const submitTextMessage = (event) => {
    event.preventDefault();
    const text = messageDraft.trim();
    if (!text || busy || !canChat) return;
    setMessageDraft("");
    onSendMessage?.(text);
  };

  return (
    <main className={`jarvis-home ${isLocked ? "is-locked" : ""} ${activeWorkspace !== "Home" ? "is-workspace" : ""}`}>
      <div className="home-backdrop" aria-hidden="true" />
      <Rail onNavigate={onNavigate} onOpenActivity={() => setActivityOpen(true)} activeWorkspace={activeWorkspace} />
      <div className="home-main">
        <TopBar health={health} models={aiStatus?.models || []} onSelectModel={onSelectModel} trustState={trustState} onOpenTrust={() => setVerificationOpen(true)} onStop={handleStop} />
        <div className={`home-center-stage ${activeWorkspace !== "Home" ? "is-workspace" : ""}`}>
          {activeWorkspace === "WhatsApp" ? (
            <WhatsAppWorkspace onBack={() => onNavigate("Home")} />
          ) : activeWorkspace === "Settings" || activeWorkspace === "Tools & Utilities" ? (
            <HomeWorkspace
              workspace={activeWorkspace}
              health={health}
              systemMetrics={systemMetrics}
              aiStatus={aiStatus}
              voiceStatus={voiceStatus}
              backgroundListening={backgroundListening}
              backgroundEnabled={backgroundEnabled}
              backgroundAvailable={backgroundAvailable}
              onBack={() => onNavigate("Home")}
              onRunAction={onRunAction}
              onSavePersonality={onSavePersonality}
              onError={onError}
              onToggleBackgroundListening={() => void toggleBackgroundListening()}
            />
          ) : (
            <>
              <SideCards
                history={history}
                systemMetrics={systemMetrics}
                isLocked={isLocked}
                onWhatsApp={() => onNavigate("WhatsApp")}
                onOpenConversation={onOpenConversation}
              />
              <section className="core-column" aria-label="JARVIS voice assistant">
            <h1>{isLocked ? "Jarvis is locked" : `${greetingFor(now.getHours())}, Newton`}</h1>
            <div className={`home-core-button state-${effectiveState}`} aria-label={`JARVIS ${effectiveState}`}>
              <CoreArtwork state={effectiveState} level={0} />
            </div>
            <div className={`core-status state-${effectiveState}`}><span />{statusText}</div>
            {["listening", "thinking", "speaking"].includes(effectiveState) && (
              <PipelineIndicator activeStep={effectiveState === "thinking" ? "Thinking" : effectiveState === "speaking" ? "Speaking" : "Listening"} />
            )}
            {error && <div className="home-error" role="alert">{error}<button type="button" onClick={onDismissError}>Dismiss</button></div>}
              </section>
            </>
          )}
        </div>
        {activeWorkspace === "Home" && <footer className="home-bottom">
          <QuickChips
            chips={DEFAULT_CHIPS}
            contextual={contextual}
            isLocked={isLocked}
            onRunAction={(label) => {
              if (label.includes("Run a command")) handleAdminCommand(label);
              else handleChipAction(label);
            }}
          />
          <form className="home-chat-composer" onSubmit={submitTextMessage}>
            <input
              aria-label="Message JARVIS"
              type="text"
              value={messageDraft}
              onChange={(event) => setMessageDraft(event.target.value)}
              placeholder={canChat ? "Type a message to JARVIS…" : "Configure the assistant to chat"}
              disabled={!canChat || busy}
            />
            <button type="submit" disabled={!messageDraft.trim() || !canChat || busy}>Send</button>
          </form>
        </footer>}
      </div>
      <ActivityDrawer open={activityOpen} onClose={() => setActivityOpen(false)} history={history} onOpenConversation={onOpenConversation} />
      <CommandPalette open={commandOpen} onClose={() => setCommandOpen(false)} onRunAction={(label) => {
        if (label.includes("Run a command")) handleAdminCommand(label);
        else handleChipAction(label);
      }} />
      <VerifyPanel open={verificationOpen} onClose={() => setVerificationOpen(false)} />
      <ConfirmCard open={confirmOpen} action={confirmAction} onConfirm={() => { setConfirmOpen(false); setActionPrompt("Action confirmed"); setTimeout(() => setActionPrompt("Which app?"), 1400); }} onCancel={() => setConfirmOpen(false)} />
      <BackgroundWakeListener
        enabled={backgroundEnabled}
        stream={backgroundStream}
        onTranscript={(text) => onRunAction?.(text)}
        onError={(message) => {
          setBackgroundEnabled(false);
          setBackgroundListening(false);
          backgroundStreamRef.current?.getTracks().forEach((track) => track.stop());
          backgroundStreamRef.current = null;
          setBackgroundStream(null);
          onError?.(message);
        }}
        onState={(listening) => {
          setBackgroundListening(listening);
          onBackgroundState?.(listening);
        }}
      />
      <div aria-live="polite" className="sr-only">{effectiveState === "stopped" ? "Action stopped." : "Admin unverified."}</div>
    </main>
  );
}
