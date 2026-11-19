import { useCallback, useEffect, useRef, useState } from "react";
import {
  ArrowLeft,
  AudioLines,
  CalendarClock,
  Check,
  CircleAlert,
  Clock3,
  History,
  Mic,
  MicOff,
  Moon,
  Phone,
  PhoneCall,
  PhoneIncoming,
  PhoneOff,
  Radio,
  ShieldCheck,
  Volume2,
  VolumeX,
  Wifi,
  WifiOff,
} from "lucide-react";
import {
  callingWebSocketUrl,
  getCallingData,
  getCallingStatus,
  savePreferences,
  saveSchedule,
} from "./services/calling.js";

const TOKEN_KEY = "jarvis.callingToken";
const DEFAULT_SCHEDULES = [
  { id: "morning", local_time: "07:00:00", enabled: true, prompt_context: "morning" },
  { id: "evening", local_time: "17:00:00", enabled: true, prompt_context: "evening" },
];

function readToken() {
  try {
    return window.sessionStorage.getItem(TOKEN_KEY) || "";
  } catch {
    return "";
  }
}

function formatCallDate(value) {
  return new Intl.DateTimeFormat(undefined, {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(new Date(value));
}

function statusLabel(status) {
  return {
    completed: "Completed",
    active: "Connected",
    interrupted: "Interrupted",
    ringing: "Ringing",
    connecting: "Connecting",
    accepted: "Accepted",
    missed: "Missed",
    declined: "Declined",
    skipped: "Skipped",
    failed: "Failed",
    unknown: "Unconfirmed",
    cancelled: "Cancelled",
  }[status] || status;
}

export default function CallingDashboard({ onBack }) {
  const [status, setStatus] = useState(null);
  const [token, setToken] = useState(readToken);
  const [tokenInput, setTokenInput] = useState(readToken);
  const [authorized, setAuthorized] = useState(false);
  const [schedules, setSchedules] = useState(DEFAULT_SCHEDULES);
  const [draftSchedules, setDraftSchedules] = useState({});
  const [preferences, setPreferences] = useState(null);
  const [calls, setCalls] = useState([]);
  const [iceServers, setIceServers] = useState([]);
  const [socketState, setSocketState] = useState("disconnected");
  const [incomingCall, setIncomingCall] = useState(null);
  const [activeCall, setActiveCall] = useState(null);
  const [microphoneEnabled, setMicrophoneEnabled] = useState(true);
  const [speakerEnabled, setSpeakerEnabled] = useState(true);
  const [busy, setBusy] = useState(false);
  const [refreshingCalls, setRefreshingCalls] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const socketRef = useRef(null);
  const peerRef = useRef(null);
  const streamRef = useRef(null);
  const audioRef = useRef(null);
  const candidateQueue = useRef([]);
  const activeCallRef = useRef(null);
  const incomingCallRef = useRef(null);
  const interruptedCallRef = useRef(null);
  const closePeer = useCallback(() => {
    peerRef.current?.close();
    peerRef.current = null;
    streamRef.current?.getTracks().forEach((track) => track.stop());
    streamRef.current = null;
    candidateQueue.current = [];
  }, []);

  const refresh = useCallback(async (currentToken = token) => {
    if (!currentToken) return [];
    const [nextSchedules, nextPreferences, nextCalls, nextIceServers] =
      await getCallingData(currentToken);
    setSchedules(nextSchedules);
    setDraftSchedules(Object.fromEntries(nextSchedules.map((item) => [item.id, {
      local_time: item.local_time.slice(0, 5),
      enabled: item.enabled,
    }])));
    setPreferences(nextPreferences);
    setCalls(nextCalls);
    setIceServers(nextIceServers);
    setAuthorized(true);
    return nextCalls;
  }, [token]);

  const refreshSafely = useCallback(async () => {
    try {
      return await refresh();
    } catch (requestError) {
      setError(requestError.message);
      return null;
    }
  }, [refresh]);

  const refreshCallHistory = async () => {
    setRefreshingCalls(true);
    setError("");
    try {
      await refresh();
      setNotice("Call information is up to date.");
    } catch (requestError) {
      setError(requestError.message);
    } finally {
      setRefreshingCalls(false);
    }
  };

  const reconcileInterruptedCall = useCallback(async () => {
    const interruptedCall = interruptedCallRef.current;
    if (!interruptedCall) return;
    const savedCalls = await refreshSafely();
    if (!savedCalls) return;
    const savedCall = savedCalls.find((call) => call.id === interruptedCall.call_id);
    interruptedCallRef.current = null;
    if (!savedCall) {
      closePeer();
      setActiveCall(null);
      activeCallRef.current = null;
      setIncomingCall(null);
      incomingCallRef.current = null;
      setNotice("The calling service no longer has that call. It wasn't restarted.");
      return;
    }
    if (["completed", "cancelled", "declined", "missed", "failed", "skipped", "unknown"].includes(savedCall.status)) {
      closePeer();
      setActiveCall(null);
      activeCallRef.current = null;
      setIncomingCall(null);
      incomingCallRef.current = null;
      setNotice(`That call ended while the connection was away: ${statusLabel(savedCall.status).toLowerCase()}. It wasn't restarted.`);
      return;
    }
    if (savedCall.status === "ringing") {
      closePeer();
      setActiveCall(null);
      activeCallRef.current = null;
      const restoredIncoming = {
        call_id: savedCall.id,
        context: savedCall.schedule_id || "morning",
      };
      incomingCallRef.current = restoredIncoming;
      setIncomingCall(restoredIncoming);
      setNotice("A call is still waiting. Answer it when you're ready.");
      return;
    }
    setIncomingCall(null);
    incomingCallRef.current = null;
    const restoredActive = {
      ...interruptedCall,
      status: savedCall.status,
      context: savedCall.schedule_id || interruptedCall.context,
    };
    activeCallRef.current = restoredActive;
    setActiveCall(restoredActive);
    setNotice("The call is still active. I've restored its saved status.");
  }, [closePeer, refreshSafely]);

  useEffect(() => {
    activeCallRef.current = activeCall;
  }, [activeCall]);

  useEffect(() => {
    incomingCallRef.current = incomingCall;
  }, [incomingCall]);

  useEffect(() => {
    const controller = new AbortController();
    getCallingStatus(controller.signal).then(setStatus).catch((requestError) => {
      if (!controller.signal.aborted) setError(requestError.message);
    });
    return () => controller.abort();
  }, []);

  useEffect(() => {
    if (!token || !authorized) return undefined;
    let stopped = false;
    let retryTimer;
    let retryDelay = 1000;
    let socket;

    const connect = () => {
      if (stopped) return;
      setSocketState("connecting");
      socket = new WebSocket(callingWebSocketUrl(), [
        "jarvis.v1",
        `jarvis-token.${token}`,
      ]);
      socketRef.current = socket;
      socket.onopen = () => {
        retryDelay = 1000;
        setSocketState("connected");
        setError("");
        if (interruptedCallRef.current) void reconcileInterruptedCall();
      };
      socket.onmessage = async (event) => {
        let message;
        try {
          message = JSON.parse(event.data);
        } catch {
          setError("The calling server sent an invalid message.");
          return;
        }
        if (message.type === "incoming_call") {
          incomingCallRef.current = message;
          setIncomingCall(message);
          setNotice("JARVIS is calling.");
        } else if (message.type === "answer_sdp" && peerRef.current) {
          try {
            await peerRef.current.setRemoteDescription({
              type: "answer",
              sdp: message.payload.sdp,
            });
            for (const candidate of candidateQueue.current.splice(0)) {
              send({
                type: "ice_candidate",
                call_id: message.call_id,
                payload: candidate,
              });
            }
          } catch {
            setError("WebRTC negotiation failed. Check your STUN/TURN network settings.");
          }
        } else if (message.type === "call_status") {
          setActiveCall((current) =>
            current?.call_id === message.call_id ? { ...current, status: message.status } : current,
          );
          if (["completed", "cancelled", "declined", "missed", "failed", "unknown"].includes(message.status)) {
            closePeer();
            setIncomingCall(null);
            incomingCallRef.current = null;
            setActiveCall(null);
            activeCallRef.current = null;
            interruptedCallRef.current = null;
            void refreshSafely();
          }
        } else if (message.type === "error") {
          setError(message.message || "Calling operation failed.");
        }
      };
      socket.onclose = () => {
        if (stopped) return;
        setSocketState("disconnected");
        const active = activeCallRef.current;
        const incoming = incomingCallRef.current;
        if (active || incoming) {
          interruptedCallRef.current = active || incoming;
          if (active) {
            const interrupted = { ...active, status: "interrupted" };
            activeCallRef.current = interrupted;
            setActiveCall(interrupted);
            setNotice("The connection dropped during the call. I'm checking its status; it won't be restarted automatically.");
          } else {
            setIncomingCall(null);
            incomingCallRef.current = null;
            setNotice("The connection dropped before you answered. The call won't be answered automatically.");
          }
        }
        retryTimer = window.setTimeout(connect, retryDelay);
        retryDelay = Math.min(retryDelay * 2, 30_000);
      };
      socket.onerror = () => socket.close();
    };

    connect();
    return () => {
      stopped = true;
      window.clearTimeout(retryTimer);
      socket?.close();
      socketRef.current = null;
    };
  }, [authorized, closePeer, reconcileInterruptedCall, refresh, refreshSafely, token]);

  useEffect(() => () => closePeer(), [closePeer]);

  const send = (payload) => {
    const socket = socketRef.current;
    if (!socket || socket.readyState !== WebSocket.OPEN) {
      throw new Error("Calling connection is offline. Reconnect before sending controls.");
    }
    socket.send(JSON.stringify(payload));
  };

  const signIn = async (event) => {
    event.preventDefault();
    const cleanToken = tokenInput.trim();
    if (cleanToken.length < 32) {
      setError("The calling access token must contain at least 32 characters.");
      return;
    }
    setBusy(true);
    setError("");
    try {
      await refresh(cleanToken);
      setToken(cleanToken);
      window.sessionStorage.setItem(TOKEN_KEY, cleanToken);
    } catch (requestError) {
      setAuthorized(false);
      setError(requestError.message);
    } finally {
      setBusy(false);
    }
  };

  const signOut = () => {
    closePeer();
    socketRef.current?.close();
    setAuthorized(false);
    setToken("");
    setTokenInput("");
    setCalls([]);
    setPreferences(null);
    setIncomingCall(null);
    setActiveCall(null);
    try {
      window.sessionStorage.removeItem(TOKEN_KEY);
    } catch {
      setNotice("Signed out. Browser storage could not be cleared.");
    }
  };

  const updateScheduleDraft = (id, patch) => {
    setDraftSchedules((current) => ({
      ...current,
      [id]: { ...current[id], ...patch },
    }));
  };

  const commitSchedule = async (id) => {
    const draft = draftSchedules[id];
    if (!draft) return;
    setBusy(true);
    setError("");
    try {
      const saved = await saveSchedule(token, id, {
        local_time: `${draft.local_time}:00`,
        enabled: draft.enabled,
      });
      setSchedules((current) => current.map((item) => item.id === id ? saved : item));
      setNotice(`${id === "morning" ? "Morning" : "Evening"} schedule saved.`);
      await refresh();
    } catch (requestError) {
      setError(requestError.message);
    } finally {
      setBusy(false);
    }
  };

  const commitPreferences = async (patch) => {
    if (!preferences) return;
    const next = { ...preferences, ...patch };
    setBusy(true);
    setError("");
    try {
      const saved = await savePreferences(token, next);
      setPreferences(saved);
      const nextStatus = await getCallingStatus();
      setStatus(nextStatus);
      setNotice("Calling preferences saved.");
    } catch (requestError) {
      setError(requestError.message);
    } finally {
      setBusy(false);
    }
  };

  const answerCall = async () => {
    if (!incomingCall || !status?.webrtc_media_available) return;
    setBusy(true);
    setError("");
    try {
      if (!navigator.mediaDevices?.getUserMedia) {
        throw new Error("Microphone calls require a secure browser context and media support.");
      }
      const localStream = await navigator.mediaDevices.getUserMedia({
        audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true },
      });
      streamRef.current = localStream;
      const peer = new RTCPeerConnection({ iceServers });
      peerRef.current = peer;
      localStream.getTracks().forEach((track) => peer.addTrack(track, localStream));
      peer.ontrack = (event) => {
        if (audioRef.current) {
          audioRef.current.srcObject = event.streams[0];
          audioRef.current.play().catch(() => {
            setNotice("Tap the speaker control to allow audio playback.");
          });
        }
      };
      peer.onicecandidate = (event) => {
        if (!event.candidate) return;
        const candidate = event.candidate.toJSON();
        if (!peer.remoteDescription) candidateQueue.current.push(candidate);
        else send({ type: "ice_candidate", call_id: incomingCall.call_id, payload: candidate });
      };
      peer.onconnectionstatechange = () => {
        if (peer.connectionState === "failed") {
          setError("Internet call connection failed. Check your network or TURN configuration.");
        }
      };
      send({ type: "answer", call_id: incomingCall.call_id, payload: {} });
      const offer = await peer.createOffer();
      await peer.setLocalDescription(offer);
      setActiveCall({ ...incomingCall, status: "connecting" });
      activeCallRef.current = { ...incomingCall, status: "connecting" };
      setIncomingCall(null);
      incomingCallRef.current = null;
      send({
        type: "offer",
        call_id: incomingCall.call_id,
        payload: { sdp: peer.localDescription.sdp },
      });
    } catch (requestError) {
      closePeer();
      setError(requestError.message || "Could not start the microphone call.");
      if (incomingCall) {
        try {
          send({ type: "decline", call_id: incomingCall.call_id, payload: {} });
          setIncomingCall(null);
          incomingCallRef.current = null;
        } catch {
          setError(`${requestError.message} Calling service is disconnected.`);
        }
      }
      incomingCallRef.current = null;
    } finally {
      setBusy(false);
    }
  };

  const declineCall = () => {
    if (!incomingCall) return;
    try {
      send({ type: "decline", call_id: incomingCall.call_id, payload: {} });
      setIncomingCall(null);
      incomingCallRef.current = null;
    } catch (requestError) {
      setError(requestError.message);
    }
  };

  const endCall = () => {
    if (!activeCall) return;
    try {
      send({ type: "end", call_id: activeCall.call_id, payload: {} });
      closePeer();
      setActiveCall(null);
      activeCallRef.current = null;
      interruptedCallRef.current = null;
    } catch (requestError) {
      setError(requestError.message);
    }
  };

  const toggleMicrophone = () => {
    const track = streamRef.current?.getAudioTracks()[0];
    if (!track) return;
    track.enabled = !track.enabled;
    setMicrophoneEnabled(track.enabled);
  };

  const toggleSpeaker = () => {
    if (!audioRef.current) return;
    audioRef.current.muted = !audioRef.current.muted;
    setSpeakerEnabled(!audioRef.current.muted);
  };

  const statusReady = status?.scheduler_running && status?.authentication_configured;
  const callingMode = status === null
    ? "CHECKING STATUS"
    : status.test_mode
      ? "TEST MODE"
      : status.telephone_live_calls_enabled || status.webrtc_media_available
        ? "LIVE CALLING READY"
        : "LIVE CALLING UNAVAILABLE";

  return (
    <main className="calling-shell">
      <header className="calling-header">
        <button className="call-back-button" onClick={onBack} aria-label="Back to assistant">
          <ArrowLeft size={17} /><span>Assistant</span>
        </button>
        <div className="call-brand"><span className="call-brand-mark"><AudioLines size={17} /></span> JARVIS <span>CALLING</span></div>
        <div className={`call-connection ${socketState}`}>
          {socketState === "connected" ? <Wifi size={14} /> : <WifiOff size={14} />}
          <span>{socketState.toUpperCase()}</span>
        </div>
      </header>

      <div className="calling-content">
        <section className="calling-main">
          <div className="calling-title-row">
            <div>
              <div className="call-eyebrow"><span /> PERSONAL CALLING</div>
              <h1>Scheduled calls<span>.</span></h1>
              <p>Daily check-ins, on your terms.</p>
            </div>
            {authorized && (
              <button className="sign-out-button" onClick={signOut}>
                <ShieldCheck size={14} /> Secure session · Sign out
              </button>
            )}
          </div>

          {!authorized ? (
            <section className="call-auth-card">
              <div className="call-auth-icon"><ShieldCheck size={22} /></div>
              <h2>Private calling controls</h2>
              <p>Enter the local calling token configured in <code>backend/.env</code>. It stays in this browser tab and is never sent to any third-party service.</p>
              <form onSubmit={signIn}>
                <label htmlFor="calling-token">Calling access token</label>
                <input
                  id="calling-token"
                  type="password"
                  autoComplete="current-password"
                  value={tokenInput}
                  onChange={(event) => setTokenInput(event.target.value)}
                  placeholder="At least 32 characters"
                />
                <button className="call-primary-button" disabled={busy || !tokenInput.trim()}>
                  {busy ? "Verifying…" : "Unlock calling dashboard"}
                </button>
              </form>
              <div className="call-auth-foot"><ShieldCheck size={13} /> Token required for all schedule and call-history access.</div>
            </section>
          ) : (
            <>
              {preferences && (
                <section className="call-settings-card">
                  <div className="call-card-heading">
                    <div className="call-card-icon"><Radio size={16} /></div>
                    <div><h2>Calling preferences</h2><p>Choose when and how JARVIS can reach you.</p></div>
                  </div>
                  <div className="call-preference-grid">
                    <label className="call-toggle-row">
                      <span className="toggle-copy"><strong>Scheduled calls</strong><small>Allow daily check-ins</small></span>
                      <input type="checkbox" checked={preferences.enabled} disabled={busy || !statusReady} onChange={(event) => commitPreferences({ enabled: event.target.checked })} />
                    </label>
                    <label className="call-toggle-row">
                      <span className="toggle-copy"><strong>Do Not Disturb</strong><small>Pause all scheduled calls</small></span>
                      <input type="checkbox" checked={preferences.do_not_disturb} disabled={busy} onChange={(event) => commitPreferences({ do_not_disturb: event.target.checked })} />
                    </label>
                    <label className="call-select-row">
                      <span><strong>Timezone</strong><small>Schedule wall-clock times</small></span>
                      <select value={preferences.timezone} disabled={busy} onChange={(event) => commitPreferences({ timezone: event.target.value })}>
                        <option value="Africa/Nairobi">Africa/Nairobi (EAT)</option>
                        <option value="UTC">UTC</option>
                        <option value="Europe/London">Europe/London</option>
                        <option value="America/New_York">America/New_York</option>
                      </select>
                    </label>
                    <label className="call-select-row">
                      <span><strong>Retry attempts</strong><small>After an unanswered call</small></span>
                      <select value={preferences.retry_limit} disabled={busy} onChange={(event) => commitPreferences({ retry_limit: Number(event.target.value) })}>
                        <option value={0}>No retry</option>
                        {[1, 2, 3, 4, 5].map((attempts) => (
                          <option value={attempts} key={attempts}>
                            {attempts} {attempts === 1 ? "retry" : "retries"}
                          </option>
                        ))}
                      </select>
                    </label>
                    <label className="call-select-row">
                      <span><strong>Retry delay</strong><small>Wait between attempts</small></span>
                      <select
                        aria-label="Retry delay"
                        value={preferences.retry_delay_seconds}
                        disabled={busy}
                        onChange={(event) => commitPreferences({
                          retry_delay_seconds: Number(event.target.value),
                        })}
                      >
                        <option value={60}>1 minute</option>
                        <option value={300}>5 minutes</option>
                        <option value={900}>15 minutes</option>
                        <option value={1800}>30 minutes</option>
                        <option value={3600}>1 hour</option>
                        <option value={21600}>6 hours</option>
                        <option value={86400}>24 hours</option>
                      </select>
                    </label>
                    <label className="call-toggle-row transcript-toggle">
                      <span className="toggle-copy"><strong>Save transcripts</strong><small>Text only; audio is never retained</small></span>
                      <input type="checkbox" checked={preferences.transcript_retention_enabled} disabled={busy} onChange={(event) => commitPreferences({ transcript_retention_enabled: event.target.checked })} />
                    </label>
                  </div>
                  <div className="sim-gate">
                    <div className="sim-gate-icon"><Phone size={15} /></div>
                    <div className="sim-gate-copy">
                      <strong>Telephone fallback <span>{status?.telephone_live_calls_enabled ? "AVAILABLE" : "LOCKED"}</span></strong>
                      <small>{status?.telephone_credentials_configured ? "Twilio credentials detected; billing consent is still required." : "Disabled until a telephony provider, billing, and secure callback are configured."}</small>
                      {status?.telephone_live_calls_enabled && (
                        <label className="sim-consent">
                          <input
                            type="checkbox"
                            checked={preferences.telephone_fallback_enabled && preferences.telephone_billing_confirmed}
                            disabled={busy}
                            onChange={(event) => commitPreferences({
                              telephone_fallback_enabled: event.target.checked,
                              telephone_billing_confirmed: event.target.checked,
                            })}
                          />
                          I explicitly approve potentially chargeable telephone calls as fallback.
                        </label>
                      )}
                    </div>
                    <span className={`sim-lock ${status?.telephone_live_calls_enabled ? "ready" : ""}`}>
                      {status?.telephone_live_calls_enabled ? <Check size={15} /> : <PhoneOff size={15} />}
                    </span>
                  </div>
                </section>
              )}

              <section className="schedule-section">
                <div className="section-heading">
                  <div><h2>Daily schedule</h2><p>Times are interpreted in {preferences?.timezone || "Africa/Nairobi"}.</p></div>
                  <span className={`scheduler-state ${status?.scheduler_running ? "running" : ""}`}>
                    <i /> {status?.scheduler_running ? "SCHEDULER RUNNING" : "SCHEDULER OFFLINE"}
                  </span>
                </div>
                <div className="schedule-grid">
                  {(schedules.length ? schedules : DEFAULT_SCHEDULES).map((schedule) => {
                    const draft = draftSchedules[schedule.id] || {
                      local_time: schedule.local_time.slice(0, 5),
                      enabled: schedule.enabled,
                    };
                    const morning = schedule.id === "morning";
                    return (
                      <article className={`schedule-card ${morning ? "morning-card" : "evening-card"}`} key={schedule.id}>
                        <div className="schedule-card-top">
                          <span className="schedule-icon">{morning ? <CalendarClock size={17} /> : <Moon size={17} />}</span>
                          <span className="schedule-context">{morning ? "MORNING BRIEFING" : "EVENING REFLECTION"}</span>
                          <label className="switch" aria-label={`Enable ${schedule.id} schedule`}>
                            <input type="checkbox" checked={draft.enabled} disabled={busy} onChange={(event) => updateScheduleDraft(schedule.id, { enabled: event.target.checked })} />
                            <span />
                          </label>
                        </div>
                        <h3>{morning ? "Start the day" : "Close the day"}</h3>
                        <p>{morning ? "Sleep, plans, reminders, and a little motivation." : "Reflect, review priorities, and plan for tomorrow."}</p>
                        <div className="schedule-time">
                          <Clock3 size={15} />
                          <input
                            type="time"
                            aria-label={`${schedule.id} call time`}
                            value={draft.local_time}
                            disabled={busy}
                            onChange={(event) => updateScheduleDraft(schedule.id, { local_time: event.target.value })}
                          />
                          <span>{preferences?.timezone === "Africa/Nairobi" ? "EAT" : preferences?.timezone || "EAT"}</span>
                        </div>
                        <button className="schedule-save" disabled={busy} onClick={() => commitSchedule(schedule.id)}>
                          <Check size={14} /> Save {schedule.id} schedule
                        </button>
                      </article>
                    );
                  })}
                </div>
              </section>

              {incomingCall && (
                <section className="incoming-call-card" role="alert">
                  <div className="incoming-pulse"><PhoneIncoming size={20} /></div>
                  <div className="incoming-copy"><span>WAITING FOR YOUR PERMISSION</span><strong>{incomingCall.context === "evening" ? "Evening reflection" : "Morning briefing"}</strong><small>Allow microphone access when you answer.</small></div>
                  <button className="answer-call-button" disabled={busy || !status?.webrtc_media_available || socketState !== "connected"} onClick={answerCall} aria-label="Answer call"><Phone size={17} /></button>
                  <button className="decline-call-button" disabled={socketState !== "connected"} onClick={declineCall} aria-label="Decline call"><PhoneOff size={17} /></button>
                </section>
              )}

              {activeCall && (
                <section className="active-call-card" aria-live="polite">
                  <div className="active-call-status"><span /><strong>{statusLabel(activeCall.status)}</strong><small>{activeCall.context === "evening" ? "Evening reflection" : "Morning briefing"}</small></div>
                  <div className="audio-controls">
                    <button disabled={!peerRef.current || activeCall.status === "interrupted"} onClick={toggleMicrophone} aria-label={microphoneEnabled ? "Mute microphone" : "Unmute microphone"}>{microphoneEnabled ? <Mic size={17} /> : <MicOff size={17} />}</button>
                    <button disabled={!peerRef.current || activeCall.status === "interrupted"} onClick={toggleSpeaker} aria-label={speakerEnabled ? "Mute speaker" : "Unmute speaker"}>{speakerEnabled ? <Volume2 size={17} /> : <VolumeX size={17} />}</button>
                    <button className="end-call-button" disabled={socketState !== "connected" || activeCall.status === "interrupted"} onClick={endCall} aria-label="End call"><PhoneOff size={17} /></button>
                  </div>
                  <audio ref={audioRef} autoPlay playsInline muted={!speakerEnabled} />
                </section>
              )}

              <section className="call-history-section">
                <div className="section-heading">
                  <div><h2>Call history</h2><p>Missed calls, call outcomes, and consented transcripts.</p></div>
                  <button className="refresh-calls" disabled={busy || refreshingCalls} onClick={() => void refreshCallHistory()}>
                    <History size={15} /> {refreshingCalls ? "Refreshing…" : "Refresh"}
                  </button>
                </div>
                {calls.length ? (
                  <div className="call-history-list">
                    {calls.map((call) => (
                      <details className="call-history-item" key={call.id}>
                        <summary>
                          <span className={`call-history-icon ${call.status}`}><PhoneCall size={15} /></span>
                          <span className="history-summary-copy">
                            <strong>{call.schedule_id ? `${call.schedule_id} check-in` : "Assistant call"}</strong>
                            <small>{formatCallDate(call.created_at)}</small>
                          </span>
                          <span className={`call-result ${call.status}`}>{statusLabel(call.status)}</span>
                          <span className="call-duration">{call.duration_seconds ? `${Math.floor(call.duration_seconds / 60)}m` : ""}</span>
                        </summary>
                        <div className="call-history-detail">
                          <p>{call.summary || call.outcome || "No summary is available."}</p>
                          {call.transcript ? <pre>{call.transcript}</pre> : <small>Transcript not saved. Enable transcript retention before a call to keep text notes.</small>}
                          {call.attempts?.length > 0 && <small>{call.attempts.length} attempt{call.attempts.length === 1 ? "" : "s"} · {call.attempts.map((attempt) => `${attempt.channel}: ${attempt.result || attempt.status}`).join(" · ")}</small>}
                        </div>
                      </details>
                    ))}
                  </div>
                ) : (
                  <div className="call-history-empty"><History size={18} /><span>No calls have been scheduled yet.</span></div>
                )}
              </section>
            </>
          )}

          {(error || notice) && (
            <div className={`call-message ${error ? "error" : "notice"}`} role={error ? "alert" : "status"}>
              {error ? <CircleAlert size={15} /> : <Check size={15} />}
              <span>{error || notice}</span>
              <button onClick={() => { setError(""); setNotice(""); }} aria-label="Dismiss message">×</button>
            </div>
          )}
        </section>

        <aside className="calling-sidebar">
          <section className="call-live-card">
            <div className="call-side-heading"><span>CALLING STATUS</span><span className={`call-live-badge ${statusReady ? "ready" : ""}`}><i /> {statusReady ? "CONTROL READY" : "SETUP"}</span></div>
            <div className="call-signal-orb"><span><AudioLines size={25} /></span></div>
            <strong className="call-live-title">{status?.ai_available ? "AI provider available" : "AI provider offline"}</strong>
            <p className="call-live-caption">{status?.ai_available ? `${status.ai_provider} is responding.` : "The scheduler will record failures instead of pretending a call was placed."}</p>
            <div className="call-runtime-row"><span><i className={status?.scheduler_running ? "good" : ""} /> Scheduler</span><strong>{status?.scheduler_running ? "Online" : "Offline"}</strong></div>
            <div className="call-runtime-row"><span><i className={status?.ai_available ? "good" : ""} /> {status?.ai_provider || "Ollama"}</span><strong>{status?.ai_available ? "Available" : "Not detected"}</strong></div>
            <div className="call-runtime-row"><span><i className={status?.webrtc_media_available ? "good" : ""} /> WebRTC audio</span><strong>{status?.webrtc_media_available ? "Available" : "Not configured"}</strong></div>
            <div className="call-runtime-row"><span><i className={status?.telephone_live_calls_enabled ? "good" : ""} /> Telephone</span><strong>{status?.telephone_live_calls_enabled ? "Consent gated" : "Disabled"}</strong></div>
          </section>

          <section className="call-security-note">
            <ShieldCheck size={18} />
            <div><strong>Private by default</strong><p>Audio is processed live and never recorded. Speech text goes to {status?.ai_provider || "the configured AI provider"}; cloud AI providers send it off-device. Transcript retention is opt-in.</p></div>
          </section>
          <section className="call-availability-note">
            <WifiOff size={16} />
            <div><strong>Availability matters</strong><p>A browser cannot receive a call while closed. Keep this dashboard connected, or host the scheduler and configure a push-capable mobile companion.</p></div>
          </section>
          <div className="calling-footer"><span>JARVIS CALLING · {callingMode}</span><span>{status?.timezone || "Africa/Nairobi"}</span></div>
        </aside>
      </div>
    </main>
  );
}
