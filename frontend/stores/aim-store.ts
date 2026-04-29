import { create } from "zustand";
import type {
  SystemStatus,
  ReasoningDepth,
  Message,
  SourceSummary,
  CostInfo,
  ProvenanceData,
} from "@/types/aim";

let _seq = 0;
const nextId = () => ++_seq;

const THREAD_KEY = "aim:thread_id";
const MSG_KEY = "aim:messages";
const MSG_ID_KEY = "aim:msg_seq";

// ── Persistence helpers ─────────────────────────────────────────────────────

// Stable default for SSR — prevents hydration mismatch since
// server render always uses this value, and client hydrates from storage after mount.
const SSR_DEFAULT_THREAD = "aim-default-thread";

function loadThreadId(): string {
  if (typeof window === "undefined") return SSR_DEFAULT_THREAD;
  const stored = sessionStorage.getItem(THREAD_KEY);
  if (stored) return stored;
  const fresh = crypto.randomUUID();
  sessionStorage.setItem(THREAD_KEY, fresh);
  return fresh;
}

function persistThreadId(id: string) {
  if (typeof window !== "undefined") sessionStorage.setItem(THREAD_KEY, id);
}

function loadMessages(): Message[] | null {
  if (typeof window === "undefined") return null;
  try {
    const raw = localStorage.getItem(MSG_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as Message[];
    // Restore _seq to avoid id collisions
    const maxId = parsed.reduce((max, m) => Math.max(max, m.id), 0);
    _seq = maxId;
    return parsed;
  } catch {
    return null;
  }
}

function persistMessages(messages: Message[]) {
  if (typeof window === "undefined") return;
  try {
    // Only persist finalized messages (not streaming ones)
    const toSave = messages
      .filter((m) => !m.isStreaming)
      .slice(-50); // keep last 50 messages
    localStorage.setItem(MSG_KEY, JSON.stringify(toSave));
  } catch {
    // localStorage full — silently ignore
  }
}

function loadSeq(): number {
  if (typeof window === "undefined") return 0;
  const stored = localStorage.getItem(MSG_ID_KEY);
  return stored ? parseInt(stored, 10) : 0;
}

function persistSeq() {
  if (typeof window !== "undefined") {
    localStorage.setItem(MSG_ID_KEY, String(_seq));
  }
}

// ── State shape ──────────────────────────────────────────────────────────────

export interface AIMState {
  // System
  status: SystemStatus;
  setStatus: (s: SystemStatus) => void;

  // Conversation
  threadId: string;
  messages: Message[];
  addMessage: (msg: Omit<Message, "id" | "timestamp">) => number;
  appendToMessage: (id: number, text: string) => void;
  finalizeMessage: (id: number, extra?: Partial<Message>) => void;
  newConversation: () => void;

  // Reasoning
  reasoningDepth: ReasoningDepth;
  setReasoningDepth: (d: ReasoningDepth) => void;
  subQueries: string[];
  addSubQuery: (q: string) => void;
  clearSubQueries: () => void;

  // Metrics
  latencyMs: number | null;
  setLatency: (ms: number) => void;
  costInfo: CostInfo | null;
  setCostInfo: (c: CostInfo | null) => void;

  // Sources
  activeSourceIndex: number;
  setActiveSourceIndex: (i: number) => void;
  activeSources: SourceSummary[];
  setActiveSources: (s: SourceSummary[]) => void;
  selectedSourceId: string | null;
  setSelectedSource: (id: string | null) => void;

  // Provenance
  provenance: ProvenanceData | null;
  setProvenance: (p: ProvenanceData | null) => void;

  // Retry state
  retryCount: number;
  setRetryCount: (n: number) => void;
  isRetrying: boolean;
  setIsRetrying: (v: boolean) => void;

  // Client hydration
  hydrateClientState: () => void;
}

// ── Store ────────────────────────────────────────────────────────────────────

export const useAIMStore = create<AIMState>((set, get) => {
  const initialThread = SSR_DEFAULT_THREAD;
  const initialMessages: Message[] = [
    {
      id: nextId(),
      role: "assistant",
      content:
        "Neural link established. AIM is online and synchronized with your enterprise knowledge graph. Ask anything.",
      source: "System",
      timestamp: Date.now(),
    },
  ];

  return {
    // System
    status: "idle",
    setStatus: (status) => set({ status }),

    // Conversation
    threadId: initialThread,
    messages: initialMessages,

    addMessage: (msg) => {
      const id = nextId();
      persistSeq();
      set((s) => ({
        messages: [...s.messages, { ...msg, id, timestamp: Date.now() }],
      }));
      return id;
    },

    appendToMessage: (id, text) =>
      set((s) => {
        // Performance: find the message, mutate its content, shallow-copy array.
        // This avoids O(n) map + string concat per streaming token.
        const idx = s.messages.findIndex((m) => m.id === id);
        if (idx === -1) return s;
        const msg = s.messages[idx];
        const updated = { ...msg, content: msg.content + text };
        const newMessages = s.messages.slice();
        newMessages[idx] = updated;
        return { messages: newMessages };
      }),

    finalizeMessage: (id, extra) => {
      set((s) => ({
        messages: s.messages.map((m) =>
          m.id === id ? { ...m, isStreaming: false, ...extra } : m
        ),
      }));
      // Persist after finalization
      persistMessages(get().messages);
    },

    newConversation: () => {
      const newThread = crypto.randomUUID();
      persistThreadId(newThread);
      _seq = 0;
      persistSeq();
      // Clear persisted messages
      if (typeof window !== "undefined") {
        localStorage.removeItem(MSG_KEY);
      }
      set({
        threadId: newThread,
        messages: [
          {
            id: nextId(),
            role: "assistant",
            content:
              "New session initialized. How can I help?",
            source: "System",
            timestamp: Date.now(),
          },
        ],
        subQueries: [],
        latencyMs: null,
        costInfo: null,
        activeSources: [],
        activeSourceIndex: -1,
        selectedSourceId: null,
        provenance: null,
        status: "idle",
      });
    },

    // Reasoning
    reasoningDepth: "shallow",
    setReasoningDepth: (reasoningDepth) => set({ reasoningDepth }),
    subQueries: [],
    addSubQuery: (q) => set((s) => ({ subQueries: [...s.subQueries, q] })),
    clearSubQueries: () => set({ subQueries: [] }),

    // Metrics
    latencyMs: null,
    setLatency: (latencyMs) => set({ latencyMs }),
    costInfo: null,
    setCostInfo: (costInfo) => set({ costInfo }),

    // Sources
    activeSourceIndex: -1,
    setActiveSourceIndex: (activeSourceIndex) => set({ activeSourceIndex }),
    activeSources: [],
    setActiveSources: (activeSources) => set({ activeSources }),
    selectedSourceId: null,
    setSelectedSource: (selectedSourceId) => set({ selectedSourceId }),

    // Provenance
    provenance: null,
    setProvenance: (provenance) => set({ provenance }),

    // Retry state
    retryCount: 0,
    setRetryCount: (retryCount) => set({ retryCount }),
    isRetrying: false,
    setIsRetrying: (isRetrying) => set({ isRetrying }),

    hydrateClientState: () => {
      if (typeof window === "undefined") return;
      const hydratedThread = loadThreadId();
      const savedSeq = loadSeq();
      if (savedSeq > _seq) _seq = savedSeq;
      const savedMessages = loadMessages();

      set({
        threadId: hydratedThread,
        messages:
          savedMessages && savedMessages.length > 0
            ? savedMessages
            : get().messages,
      });
    },
  };
});
