export async function fetchHealth(signal) {
  const response = await fetch("/api/health", { signal });
  if (!response.ok) throw new Error(`Health check failed (${response.status}).`);
  return response.json();
}

export async function fetchSystemMetrics(signal) {
  const response = await fetch("/api/system/metrics", { signal });
  if (!response.ok) throw new Error(`System metrics failed (${response.status}).`);
  return response.json();
}

export async function fetchAIStatus(signal) {
  const response = await fetch("/api/ai/status", { signal });
  if (!response.ok) throw new Error(`AI status failed (${response.status}).`);
  return response.json();
}

export async function chooseAIModel(model) {
  const response = await fetch("/api/ai/model", {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ model }),
  });
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new Error(body.detail || `Model selection failed (${response.status}).`);
  }
  return response.json();
}

export async function fetchAIProviders(signal) {
  const response = await fetch("/api/ai/providers", { signal });
  if (!response.ok) throw new Error(`AI providers failed (${response.status}).`);
  return response.json();
}

export async function testAIProvider(provider) {
  const response = await fetch(`/api/ai/providers/${encodeURIComponent(provider)}/test`, { method: "POST" });
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new Error(body.detail || `Provider test failed (${response.status}).`);
  }
  return response.json();
}

export async function chooseAIProvider(provider) {
  const response = await fetch("/api/ai/provider", {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ provider }),
  });
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new Error(body.detail || `Provider selection failed (${response.status}).`);
  }
  return response.json();
}

export async function savePersonality(personality) {
  const response = await fetch("/api/ai/personality", {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ personality }),
  });
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new Error(body.detail || `Personality update failed (${response.status}).`);
  }
  return response.json();
}

export async function fetchMemories(signal) {
  const response = await fetch("/api/memory", { signal });
  if (!response.ok) throw new Error(`Saved preferences failed (${response.status}).`);
  const memories = await response.json();
  if (!Array.isArray(memories)) throw new Error("The saved preferences response was invalid.");
  return memories;
}

export async function saveMemory(memory) {
  const response = await fetch("/api/memory", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(memory),
  });
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new Error(body.detail || `Preference save failed (${response.status}).`);
  }
  return response.json();
}

export async function deleteMemory(id) {
  const response = await fetch(`/api/memory/${encodeURIComponent(id)}`, { method: "DELETE" });
  if (!response.ok) throw new Error(`Preference removal failed (${response.status}).`);
}

export async function fetchVoiceStatus(signal) {
  const response = await fetch("/api/voice/status", { signal });
  if (!response.ok) throw new Error(`Voice status failed (${response.status}).`);
  return response.json();
}

export async function transcribeAudio(pcm, sampleRate) {
  const response = await fetch(`/api/voice/transcribe?sample_rate=${sampleRate}`, {
    method: "POST",
    headers: { "Content-Type": "application/octet-stream" },
    body: pcm,
  });
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new Error(body.detail || `Speech recognition failed (${response.status}).`);
  }
  return response.json();
}

export async function createActionDraft(draft) {
  const response = await fetch("/api/actions/drafts", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(draft),
  });
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new Error(body.detail || `Draft could not be saved (${response.status}).`);
  }
  return response.json();
}

export async function fetchActionDrafts(signal) {
  const response = await fetch("/api/actions", { signal });
  if (!response.ok) throw new Error(`Drafts could not be loaded (${response.status}).`);
  const drafts = await response.json();
  if (!Array.isArray(drafts)) throw new Error("The saved drafts response was invalid.");
  return drafts;
}

export async function approveActionDraft(id) {
  const response = await fetch(`/api/actions/${encodeURIComponent(id)}/approve`, { method: "POST" });
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new Error(body.detail || `Draft approval failed (${response.status}).`);
  }
  return response.json();
}

export async function synthesizeSpeech(text) {
  const response = await fetch("/api/voice/speak", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ text }),
  });
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new Error(body.detail || `Speech synthesis failed (${response.status}).`);
  }
  return response.blob();
}

export async function fetchConversations(signal) {
  const response = await fetch("/api/conversations", { signal });
  if (!response.ok) throw new Error(`Conversation history failed (${response.status}).`);
  return response.json();
}

export async function fetchConversation(id, signal) {
  const response = await fetch(`/api/conversations/${encodeURIComponent(id)}`, { signal });
  if (!response.ok) throw new Error(`Conversation could not be loaded (${response.status}).`);
  return response.json();
}

export async function streamChat(message, conversationId, { signal, taskId, onMeta, onDelta }) {
  const response = await fetch("/api/chat/stream", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ message, conversation_id: conversationId, task_id: taskId }),
    signal,
  });
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new Error(body.detail || `The request failed (${response.status}).`);
  }
  if (!response.body) throw new Error("Streaming is unavailable in this browser.");

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let finished = false;

  const dispatch = (frame) => {
    let eventName = "message";
    const data = [];
    for (const line of frame.split(/\r?\n/)) {
      if (line.startsWith("event:")) eventName = line.slice(6).trim();
      else if (line.startsWith("data:")) data.push(line.slice(5).trimStart());
    }
    if (!data.length) return;
    const payload = JSON.parse(data.join("\n"));
    if (eventName === "meta") onMeta(payload);
    if (eventName === "delta") onDelta(payload.text);
    if (eventName === "error") throw new Error(payload.message);
    if (eventName === "done") finished = true;
  };

  try {
    while (true) {
      const { value, done } = await reader.read();
      buffer += decoder.decode(value || new Uint8Array(), { stream: !done });
      const frames = buffer.split(/\r?\n\r?\n/);
      buffer = frames.pop() || "";
      for (const frame of frames) dispatch(frame);
      if (done) break;
    }
    if (buffer.trim()) dispatch(buffer);
    if (!finished) throw new Error("The response stream ended before completion.");
  } finally {
    if (!finished) await reader.cancel().catch(() => {});
  }
}
