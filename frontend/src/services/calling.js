async function request(path, token, options = {}) {
  const response = await fetch(`/api/calling${path}`, {
    ...options,
    headers: {
      ...(options.body ? { "Content-Type": "application/json" } : {}),
      ...(token ? { "X-Calling-Token": token } : {}),
      ...options.headers,
    },
  });
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new Error(body.detail || `Calling request failed (${response.status}).`);
  }
  return response.status === 204 ? null : response.json();
}

export function getCallingStatus(signal) {
  return request("/status", null, { signal });
}

export function getCallingData(token, signal) {
  return Promise.all([
    request("/schedules", token, { signal }),
    request("/preferences", token, { signal }),
    request("/sessions?limit=50", token, { signal }),
    request("/webrtc-config", token, { signal }),
  ]);
}

export function saveSchedule(token, id, schedule) {
  return request(`/schedules/${encodeURIComponent(id)}`, token, {
    method: "PUT",
    body: JSON.stringify(schedule),
  });
}

export function savePreferences(token, preferences) {
  return request("/preferences", token, {
    method: "PUT",
    body: JSON.stringify(preferences),
  });
}

export function callingWebSocketUrl() {
  const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
  return `${protocol}//${window.location.host}/api/calling/ws`;
}
