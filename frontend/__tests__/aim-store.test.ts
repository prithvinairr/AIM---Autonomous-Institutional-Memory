/**
 * Tests for the Zustand AIM store — state transitions, message management,
 * session persistence, and conversation lifecycle.
 */
import { describe, it, expect, beforeEach, vi } from "vitest";
import { act } from "@testing-library/react";

// Mock sessionStorage and localStorage
const storage: Record<string, string> = {};
const mockStorage = {
  getItem: vi.fn((key: string) => storage[key] ?? null),
  setItem: vi.fn((key: string, val: string) => { storage[key] = val; }),
  removeItem: vi.fn((key: string) => { delete storage[key]; }),
  clear: vi.fn(() => Object.keys(storage).forEach((k) => delete storage[k])),
  length: 0,
  key: vi.fn(() => null),
};

Object.defineProperty(window, "sessionStorage", { value: mockStorage, writable: true });
Object.defineProperty(window, "localStorage", { value: mockStorage, writable: true });

// Import store after mocks are set up
import { useAIMStore, type AIMState } from "@/stores/aim-store";

function getState(): AIMState {
  return useAIMStore.getState();
}

describe("AIM Store", () => {
  beforeEach(() => {
    mockStorage.clear();
    vi.clearAllMocks();
  });

  describe("System Status", () => {
    it("starts with idle status", () => {
      expect(getState().status).toBe("idle");
    });

    it("transitions through status values", () => {
      act(() => getState().setStatus("thinking"));
      expect(getState().status).toBe("thinking");

      act(() => getState().setStatus("streaming"));
      expect(getState().status).toBe("streaming");

      act(() => getState().setStatus("error"));
      expect(getState().status).toBe("error");

      act(() => getState().setStatus("idle"));
      expect(getState().status).toBe("idle");
    });
  });

  describe("Message Management", () => {
    it("adds a user message", () => {
      const id = act(() =>
        getState().addMessage({ role: "user", content: "Hello AIM" }),
      );
      const msgs = getState().messages;
      const last = msgs[msgs.length - 1];
      expect(last.role).toBe("user");
      expect(last.content).toBe("Hello AIM");
      expect(last.timestamp).toBeGreaterThan(0);
    });

    it("appends text to a streaming message", () => {
      // ``act()`` from @testing-library/react v16 doesn't forward a sync
      // callback's return value — it returns void. Capture the id via a
      // mutable binding written inside the callback instead.
      let id = 0;
      act(() => {
        id = getState().addMessage({ role: "assistant", content: "", isStreaming: true });
      });
      act(() => getState().appendToMessage(id, "Hello"));
      act(() => getState().appendToMessage(id, " world"));

      const msgs = getState().messages;
      const msg = msgs.find((m) => m.id === id);
      expect(msg?.content).toBe("Hello world");
    });

    it("finalizes a message and removes streaming flag", () => {
      let id = 0;
      act(() => {
        id = getState().addMessage({ role: "assistant", content: "done", isStreaming: true });
      });
      act(() => getState().finalizeMessage(id, { confidence: 0.95 }));

      const msg = getState().messages.find((m) => m.id === id);
      expect(msg?.isStreaming).toBe(false);
      expect(msg?.confidence).toBe(0.95);
    });

    it("appendToMessage is a no-op for unknown IDs", () => {
      const before = getState().messages.length;
      act(() => getState().appendToMessage(99999, "ghost"));
      expect(getState().messages.length).toBe(before);
    });
  });

  describe("Conversation Lifecycle", () => {
    it("initializes with a thread ID", () => {
      expect(getState().threadId).toBeTruthy();
    });

    it("creates a new conversation with fresh state", () => {
      act(() => getState().addMessage({ role: "user", content: "test" }));
      act(() => getState().setStatus("thinking"));

      act(() => getState().newConversation());

      expect(getState().status).toBe("idle");
      expect(getState().messages.length).toBe(1);
      expect(getState().messages[0].role).toBe("assistant");
      expect(getState().subQueries).toEqual([]);
      expect(getState().provenance).toBeNull();
      expect(getState().activeSources).toEqual([]);
    });
  });

  describe("Reasoning", () => {
    it("sets reasoning depth", () => {
      act(() => getState().setReasoningDepth("deep"));
      expect(getState().reasoningDepth).toBe("deep");
    });

    it("adds and clears sub-queries", () => {
      act(() => getState().addSubQuery("Who owns Auth?"));
      act(() => getState().addSubQuery("What incidents?"));
      expect(getState().subQueries).toHaveLength(2);

      act(() => getState().clearSubQueries());
      expect(getState().subQueries).toEqual([]);
    });
  });

  describe("Sources & Provenance", () => {
    it("sets active sources", () => {
      const sources = [
        { source_id: "s1", source_type: "neo4j_graph", title: "Test", uri: "", confidence: 0.9, snippet: "..." },
      ];
      act(() => getState().setActiveSources(sources));
      expect(getState().activeSources).toHaveLength(1);
    });

    it("selects and deselects source", () => {
      act(() => getState().setSelectedSource("s1"));
      expect(getState().selectedSourceId).toBe("s1");

      act(() => getState().setSelectedSource(null));
      expect(getState().selectedSourceId).toBeNull();
    });

    it("sets provenance data", () => {
      const prov = {
        overall_confidence: 0.85,
        citation_spans: [],
        resolved_entities: [],
        temporal_chain: [],
        sub_query_traces: [],
        reasoning_steps: ["Step 1"],
      };
      act(() => getState().setProvenance(prov));
      expect(getState().provenance?.overall_confidence).toBe(0.85);
    });
  });

  describe("Metrics", () => {
    it("sets latency", () => {
      act(() => getState().setLatency(450));
      expect(getState().latencyMs).toBe(450);
    });

    it("sets cost info", () => {
      const cost = { input_tokens: 100, output_tokens: 50, embedding_tokens: 20, estimated_cost_usd: 0.001 };
      act(() => getState().setCostInfo(cost));
      expect(getState().costInfo?.estimated_cost_usd).toBe(0.001);
    });
  });

  describe("Retry State", () => {
    it("tracks retry count", () => {
      act(() => getState().setRetryCount(2));
      expect(getState().retryCount).toBe(2);
    });

    it("tracks retrying status", () => {
      act(() => getState().setIsRetrying(true));
      expect(getState().isRetrying).toBe(true);
    });
  });
});
