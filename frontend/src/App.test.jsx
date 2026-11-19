import { fireEvent, render, screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import App from "./App.jsx";

const healthyStatus = {
  status: "ok",
  ai_configured: true,
  ai_available: true,
  ai_provider: "ollama",
  model: "llama3.2:1b",
};

const voiceReady = {
  speech_recognition_available: true,
  wake_word_available: false,
  wake_word_listening: false,
};

function installFetch({ health = healthyStatus, voice = voiceReady, history = [], conversations = {}, models = ["llama3.2:1b", "qwen2.5:1.5b"] } = {}) {
  const fetchMock = vi.fn(async (url, options) => {
    if (url === "/api/health") return { ok: true, json: async () => health };
    if (url === "/api/system/metrics") return { ok: true, json: async () => ({ cpu_percent: 24, memory_percent: 62, memory_used: 620, memory_total: 1000 }) };
    if (url === "/api/ai/status") return { ok: true, json: async () => ({ available: health.ai_available, models }) };
    if (url === "/api/voice/status") return { ok: true, json: async () => voice };
    if (url === "/api/conversations") return { ok: true, json: async () => history };
    if (url === "/api/memory" || url === "/api/actions") return { ok: true, json: async () => [] };
    if (url === "/api/ai/model") return { ok: true, json: async () => ({ model: JSON.parse(options.body).model }) };
    if (url === "/api/chat/stream") {
      const payload = new TextEncoder().encode(
        'event: meta\ndata: {"conversation_id":"conversation-1","task_id":"task-1"}\n\n' +
        'event: delta\ndata: {"text":"Hello from JARVIS."}\n\n' +
        "event: done\ndata: {}\n\n",
      );
      let sent = false;
      return {
        ok: true,
        body: {
          getReader: () => ({
            read: async () => {
              if (sent) return { done: true };
              sent = true;
              return { done: false, value: payload };
            },
            cancel: async () => {},
          }),
        },
      };
    }
    if (typeof url === "string" && url.startsWith("/api/conversations/")) {
      const id = url.split("/").at(-1);
      return { ok: true, json: async () => conversations[id] };
    }
    return { ok: true, json: async () => ({}) };
  });
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

describe("JARVIS voice-first home", () => {
  it("renders the clean idle home without push-to-talk or generated paragraphs", async () => {
    installFetch();
    render(<App />);

    expect(await screen.findByRole("heading", { name: /good (morning|afternoon|evening), newton/i })).toBeInTheDocument();
    expect(screen.getByText("BACKGROUND LISTENING UNAVAILABLE")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Talk to Jarvis" })).not.toBeInTheDocument();
    expect(screen.queryByText(/planning your day can be a great way/i)).not.toBeInTheDocument();
    expect(screen.getByText("Admin unverified")).toBeInTheDocument();
    expect(screen.queryByText("Admin verified")).not.toBeInTheDocument();
    expect(screen.queryByText("How can I help?")).not.toBeInTheDocument();
    expect(screen.getByRole("textbox", { name: "Message JARVIS" })).toBeInTheDocument();
    expect(screen.queryByText("System Online")).not.toBeInTheDocument();
    expect(screen.getAllByRole("button", { name: /open an app|find a file|set a reminder|system controls/i })).toHaveLength(4);
    expect(screen.getAllByRole("img", { name: /jarvis core idle/i })).toHaveLength(1);
    expect(screen.getByText("CPU")).toBeInTheDocument();
    expect(screen.getByText("24%")).toBeInTheDocument();
    expect(screen.getByText("62%")).toBeInTheDocument();
  });

  it("opens the command palette with Ctrl+K and filters its real quick actions", async () => {
    installFetch();
    render(<App />);
    await screen.findByRole("heading", { name: /newton/i });

    fireEvent.keyDown(window, { key: "k", ctrlKey: true });

    const palette = screen.getByRole("dialog", { name: "Command palette" });
    fireEvent.change(within(palette).getByRole("textbox", { name: "Search actions" }), {
      target: { value: "slack" },
    });
    expect(within(palette).getByRole("button", { name: /Open Slack/ })).toBeInTheDocument();
    expect(within(palette).queryByRole("button", { name: /Run a command/i })).not.toBeInTheDocument();
  });

  it("shows the live model and allows switching between local models", async () => {
    const fetchMock = installFetch();
    render(<App />);

    fireEvent.click(await screen.findByRole("button", { name: /llama3.2:1b.*Local/i }));
    fireEvent.click(screen.getByRole("button", { name: /qwen2.5:1.5b/i }));

    expect(fetchMock).toHaveBeenCalledWith("/api/ai/model", expect.objectContaining({ method: "PUT" }));
    expect(await screen.findByRole("button", { name: /qwen2.5:1.5b.*Local/i })).toBeInTheDocument();
  });

  it("opens actual saved conversation history from the Recent card", async () => {
    const conversationId = "12345678-1234-1234-1234-123456789012";
    installFetch({
      history: [{ id: conversationId, title: "Launch copy review" }],
      conversations: {
        [conversationId]: {
          id: conversationId,
          title: "Launch copy review",
          messages: [{ id: "m1", role: "user", content: "Review this launch copy", created_at: new Date().toISOString() }],
          tasks: [],
        },
      },
    });
    render(<App />);

    fireEvent.click(await screen.findByRole("button", { name: "Launch copy review" }));

    expect(await screen.findByText("Review this launch copy")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Your conversations ." })).toBeInTheDocument();
    const historyPanel = screen.getByRole("complementary", { name: "Chat history" });
    expect(within(historyPanel).getByRole("button", { name: "Launch copy review" })).toHaveClass("active");
    fireEvent.click(within(historyPanel).getByRole("button", { name: "New chat" }));
    expect(screen.getByText("READY WHEN YOU ARE")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Return to home" })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Return to home" }));
    expect(await screen.findByRole("heading", { name: /newton/i })).toBeInTheDocument();
  });

  it("opens chat from the home menu and returns home from the chat screen", async () => {
    installFetch();
    render(<App />);

    fireEvent.click(await screen.findByRole("button", { name: "Chat" }));
    expect(await screen.findByRole("heading", { name: "Your conversations ." })).toBeInTheDocument();
    expect(screen.queryByRole("navigation", { name: "Primary navigation" })).not.toBeInTheDocument();
    expect(screen.getByRole("complementary", { name: "Chat history" })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Return to home" }));
    expect(await screen.findByRole("heading", { name: /newton/i })).toBeInTheDocument();
  });

  it("opens WhatsApp inside the JARVIS shell and returns without restarting assistant state", async () => {
    const fetchMock = installFetch();
    render(<App />);

    await screen.findByRole("heading", { name: /newton/i });
    expect(screen.getByText("Unavailable")).toBeInTheDocument();
    expect(screen.queryByText("Listening in background...")).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "WhatsApp", exact: true }));
    expect(await screen.findByText("WhatsApp integration unavailable")).toBeInTheDocument();
    expect(screen.getByText(/no authorized WhatsApp adapter configured/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Send message" })).toBeDisabled();
    fireEvent.click(screen.getByRole("button", { name: "Back to dashboard" }));
    expect(await screen.findByRole("heading", { name: /newton/i })).toBeInTheDocument();
    expect(fetchMock.mock.calls.filter(([url]) => url === "/api/health")).toHaveLength(1);
  });

  it("opens settings and tools inside the same JARVIS shell", async () => {
    installFetch();
    render(<App />);

    fireEvent.click(await screen.findByRole("button", { name: "Settings" }));
    expect(await screen.findByRole("heading", { name: "Settings" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Turn on background listening" })).toBeDisabled();

    fireEvent.click(screen.getByRole("button", { name: "Back to dashboard" }));
    fireEvent.click(screen.getByRole("button", { name: "Tools" }));
    expect(await screen.findByRole("heading", { name: "Tools & Utilities" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Live device status" })).toBeInTheDocument();
  });

  it("sends a typed message to the existing assistant chat endpoint", async () => {
    const fetchMock = installFetch();
    render(<App />);

    const input = await screen.findByRole("textbox", { name: "Message JARVIS" });
    fireEvent.change(input, { target: { value: "Hello Jarvis" } });
    fireEvent.click(screen.getByRole("button", { name: "Send" }));

    expect(fetchMock).toHaveBeenCalledWith(
      "/api/chat/stream",
      expect.objectContaining({
        method: "POST",
        body: expect.stringContaining('"message":"Hello Jarvis"'),
      }),
    );
    expect(await screen.findByRole("heading", { name: "Your conversations ." })).toBeInTheDocument();
    expect(await screen.findByText("Hello from JARVIS.")).toBeInTheDocument();
    expect(screen.queryByRole("region", { name: "Recent chat messages" })).not.toBeInTheDocument();
  });

  it("shows a simulated PIN success while keeping admin unverified when no PIN is configured", async () => {
    installFetch();
    render(<App />);

    fireEvent.click(await screen.findByRole("button", { name: "Trust status: Admin unverified" }));

    const verifier = screen.getByRole("dialog", { name: "Verification panel" });
    const pinInput = within(verifier).getByLabelText("PIN");
    for (const digit of [1, 2, 3, 4]) {
      fireEvent.click(within(verifier).getByRole("button", { name: `Enter PIN digit ${digit}` }));
    }
    expect(pinInput).toHaveValue("1234");

    expect(within(verifier).getByRole("button", { name: "Verifying Code..." })).toBeInTheDocument();
    expect(await within(verifier).findByText("Verified Successfully", {}, { timeout: 2000 })).toBeInTheDocument();
    expect(within(verifier).getByRole("button", { name: "Verified & Secured" })).toBeInTheDocument();
    expect(within(verifier).getByText(
      "Demo only — no PIN was checked. Admin actions remain unverified.",
    )).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Trust status: Admin unverified" })).toBeInTheDocument();
    expect(pinInput).toHaveValue("");
  });
});
