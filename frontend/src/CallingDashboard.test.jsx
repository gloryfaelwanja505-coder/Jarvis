import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import CallingDashboard from "./CallingDashboard.jsx";

const accessToken = "test-calling-token-that-is-at-least-32-chars";

const callingStatus = {
  authentication_configured: true,
  scheduler_running: true,
  ai_provider: "ollama",
  ai_available: true,
  webrtc_signaling_available: true,
  webrtc_media_available: true,
  speech_to_text_available: true,
  text_to_speech_available: true,
  telephone_provider: "none",
  telephone_credentials_configured: false,
  telephone_live_calls_enabled: false,
  test_mode: true,
  timezone: "Africa/Nairobi",
  connected_clients: 0,
};

const schedules = [
  { id: "morning", local_time: "07:00:00", enabled: true, prompt_context: "morning" },
  { id: "evening", local_time: "17:00:00", enabled: true, prompt_context: "evening" },
];

const preferences = {
  enabled: false,
  do_not_disturb: false,
  timezone: "Africa/Nairobi",
  retry_limit: 1,
  retry_delay_seconds: 300,
  telephone_fallback_enabled: false,
  telephone_billing_confirmed: false,
  transcript_retention_enabled: false,
};

const responses = {
  "/api/calling/status": callingStatus,
  "/api/calling/schedules": schedules,
  "/api/calling/preferences": preferences,
  "/api/calling/sessions?limit=50": [],
  "/api/calling/webrtc-config": [],
};

class MockWebSocket {
  static OPEN = 1;
  static instances = [];

  constructor(url, protocols) {
    this.url = url;
    this.protocols = protocols;
    this.readyState = 0;
    this.sent = [];
    MockWebSocket.instances.push(this);
    queueMicrotask(() => {
      this.readyState = MockWebSocket.OPEN;
      this.onopen?.();
    });
  }

  send(message) {
    this.sent.push(JSON.parse(message));
  }

  close() {
    this.readyState = 3;
    this.onclose?.();
  }
}

class MockPeerConnection {
  static instances = [];

  constructor() {
    this.remoteDescription = null;
    this.addIceCandidate = vi.fn();
    this.addTrack = vi.fn();
    MockPeerConnection.instances.push(this);
  }

  async createOffer() {
    return { type: "offer", sdp: "v=0\r\ns=browser\r\n" };
  }

  async setLocalDescription(description) {
    this.localDescription = description;
    this.onicecandidate?.({
      candidate: {
        toJSON: () => ({
          candidate: "candidate:1 1 UDP 1 127.0.0.1 9999 typ host",
          sdpMid: "0",
          sdpMLineIndex: 0,
        }),
      },
    });
  }

  async setRemoteDescription(description) {
    this.remoteDescription = description;
  }

  close() {}
}

describe("calling dashboard", () => {
  let originalMediaDevices;

  afterEach(() => {
    vi.unstubAllGlobals();
    if (originalMediaDevices) {
      Object.defineProperty(window.navigator, "mediaDevices", originalMediaDevices);
    } else {
      delete window.navigator.mediaDevices;
    }
    originalMediaDevices = undefined;
    MockWebSocket.instances = [];
    MockPeerConnection.instances = [];
    window.sessionStorage.clear();
  });

  it("authenticates, receives a call, and sends queued local ICE candidates", async () => {
    const stream = {
      getTracks: () => [{ stop: vi.fn() }],
      getAudioTracks: () => [{ enabled: true, stop: vi.fn() }],
    };
    originalMediaDevices = Object.getOwnPropertyDescriptor(
      window.navigator,
      "mediaDevices",
    );
    Object.defineProperty(window.navigator, "mediaDevices", {
      configurable: true,
      value: { getUserMedia: vi.fn().mockResolvedValue(stream) },
    });
    vi.stubGlobal("WebSocket", MockWebSocket);
    vi.stubGlobal("RTCPeerConnection", MockPeerConnection);
    const fetchMock = vi.fn(async (url, options = {}) => {
        const path = new URL(url, "http://localhost").pathname +
          (new URL(url, "http://localhost").search || "");
        if (options.method === "PUT") {
          if (path === "/api/calling/preferences") {
            return { ok: true, status: 200, json: async () => JSON.parse(options.body) };
          }
          return { ok: true, status: 200, json: async () => schedules[0] };
        }
        return { ok: true, status: 200, json: async () => responses[path] };
      });
    vi.stubGlobal("fetch", fetchMock);

    render(<CallingDashboard onBack={() => {}} />);
    fireEvent.change(screen.getByLabelText("Calling access token"), {
      target: { value: accessToken },
    });
    fireEvent.click(screen.getByRole("button", { name: "Unlock calling dashboard" }));

    await screen.findByRole("heading", { name: "Daily schedule" });
    await screen.findByText("CONNECTED");
    fireEvent.change(screen.getByLabelText("Retry delay"), { target: { value: "900" } });
    await waitFor(() => {
      const preferenceSave = fetchMock.mock.calls.find(
        ([url, options]) =>
          new URL(url, "http://localhost").pathname === "/api/calling/preferences" &&
          options?.method === "PUT",
      );
      expect(preferenceSave).toBeDefined();
      expect(JSON.parse(preferenceSave[1].body).retry_delay_seconds).toBe(900);
    });
    const socket = MockWebSocket.instances.at(-1);
    act(() => {
      socket.onmessage({
        data: JSON.stringify({
          type: "incoming_call",
          call_id: "12345678-1234-1234-1234-123456789012",
          context: "morning",
        }),
      });
    });

    fireEvent.click(screen.getByRole("button", { name: "Answer call" }));
    await screen.findByText("Connecting");
    await waitFor(() =>
      expect(socket.sent.some((message) => message.type === "offer")).toBe(true),
    );
    const peer = MockPeerConnection.instances[0];
    await act(async () => {
      socket.onmessage({
        data: JSON.stringify({
          type: "answer_sdp",
          call_id: "12345678-1234-1234-1234-123456789012",
          payload: { sdp: "v=0\r\ns=server\r\n" },
        }),
      });
    });

    expect(
      socket.sent.some(
        (message) =>
          message.type === "ice_candidate" &&
          message.payload.candidate.startsWith("candidate:"),
      ),
    ).toBe(true);
    expect(peer.addIceCandidate).not.toHaveBeenCalled();

    act(() => socket.onclose());
    expect(await screen.findByText("Interrupted")).toBeInTheDocument();
    expect(screen.getByText(/won't be restarted automatically/i)).toBeInTheDocument();
  });
});
