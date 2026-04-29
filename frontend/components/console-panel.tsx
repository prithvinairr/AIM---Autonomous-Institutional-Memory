"use client";

import React, { useState, useRef, useEffect } from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  MessageSquare, X, Loader2, Send, AlertTriangle, Sparkles,
} from "lucide-react";
import { useAIMStore } from "@/stores/aim-store";
import { useAIMQuery } from "@/hooks/useAIMQuery";
import { MessageBubble } from "@/components/message-bubble";
import { cn, SPRING } from "@/lib/utils";
import type { ReasoningDepth } from "@/types/aim";

// ── Suggested queries for empty state ────────────────────────────────────────

const SUGGESTIONS = [
  "Who owns the Auth Service and what incidents has it had?",
  "What is Project Aurora and who is leading it?",
  "How does the deployment pipeline work at Nexus?",
];

// ── Depth selector pills ─────────────────────────────────────────────────────

const DEPTH_OPTIONS: { value: ReasoningDepth; label: string }[] = [
  { value: "shallow", label: "Quick" },
  { value: "standard", label: "Standard" },
  { value: "deep", label: "Deep" },
];

function DepthSelector() {
  const depth = useAIMStore((s) => s.reasoningDepth);
  const setDepth = useAIMStore((s) => s.setReasoningDepth);
  const busy = useAIMStore((s) => s.status !== "idle");

  return (
    <div className="flex items-center gap-1 p-0.5 rounded-lg bg-white/[0.03] border border-white/[0.05]">
      {DEPTH_OPTIONS.map(({ value, label }) => {
        const on = depth === value;
        return (
          <button
            key={value}
            disabled={busy}
            onClick={() => setDepth(value)}
            className={cn(
              "relative px-2.5 py-1 text-[9px] font-semibold uppercase tracking-wider rounded-md transition-colors disabled:opacity-40",
              on ? "text-white" : "text-slate-600 hover:text-slate-400"
            )}
            aria-label={`Reasoning depth: ${label}`}
            aria-pressed={on}
          >
            {on && (
              <motion.div
                layoutId="depth-pill"
                className="absolute inset-0 rounded-md bg-blue-500/20 border border-blue-500/30"
                transition={SPRING.snappy}
              />
            )}
            <span className="relative">{label}</span>
          </button>
        );
      })}
    </div>
  );
}

// ── Console panel ────────────────────────────────────────────────────────────

export default function ConsolePanel() {
  const status = useAIMStore((s) => s.status);
  const messages = useAIMStore((s) => s.messages);
  const addMessage = useAIMStore((s) => s.addMessage);
  const { submit, abort } = useAIMQuery();
  const [input, setInput] = useState("");
  const scrollRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  const busy = status === "thinking" || status === "streaming";

  // Auto-scroll when new messages arrive
  const prevLen = useRef(messages.length);
  useEffect(() => {
    const el = scrollRef.current;
    if (!el) return;
    const nearBottom =
      el.scrollHeight - el.scrollTop - el.clientHeight < 140;
    if (nearBottom || messages.length !== prevLen.current) {
      el.scrollTo({ top: el.scrollHeight, behavior: "smooth" });
    }
    prevLen.current = messages.length;
  }, [messages]);

  // Keyboard shortcuts
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.key === "Escape" && busy) {
        abort();
      }
      // Cmd/Ctrl+K → focus input
      if ((e.metaKey || e.ctrlKey) && e.key === "k") {
        e.preventDefault();
        inputRef.current?.focus();
      }
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [busy, abort]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    const query = input.trim();
    if (!query || busy) return;
    setInput("");
    addMessage({ role: "user", content: query });
    await submit(query);
  };

  const handleSuggestion = async (query: string) => {
    if (busy) return;
    addMessage({ role: "user", content: query });
    await submit(query);
  };

  // Show suggestions only when there's just the welcome message
  const showSuggestions = messages.length <= 1 && status === "idle";

  return (
    <motion.aside
      initial={{ opacity: 0, x: 24 }}
      animate={{ opacity: 1, x: 0 }}
      transition={{ ...SPRING.gentle, delay: 0.15 }}
      className="flex flex-col glass-panel overflow-hidden"
      aria-label="Decision console"
    >
      {/* Header */}
      <div className="px-5 py-4 border-b border-white/[0.05] flex items-center justify-between">
        <div className="flex items-center gap-2.5">
          <MessageSquare size={15} className="text-blue-400/80" />
          <span className="text-[10px] font-bold uppercase tracking-[0.22em] text-slate-300">
            Decision Console
          </span>
        </div>
        <div className="flex items-center gap-2">
          <DepthSelector />
          <AnimatePresence>
            {busy && (
              <motion.button
                initial={{ opacity: 0, scale: 0.7 }}
                animate={{ opacity: 1, scale: 1 }}
                exit={{ opacity: 0, scale: 0.7 }}
                transition={SPRING.bouncy}
                whileHover={{ scale: 1.1 }}
                whileTap={{ scale: 0.9 }}
                onClick={abort}
                className="p-1.5 rounded-lg hover:bg-white/10 text-slate-600 hover:text-white transition-colors"
                aria-label="Cancel query (Esc)"
                title="Cancel (Esc)"
              >
                <X size={13} />
              </motion.button>
            )}
          </AnimatePresence>
        </div>
      </div>

      {/* Messages — aria-live announces new responses for screen readers */}
      <div
        ref={scrollRef}
        className="flex-1 overflow-y-auto px-5 py-4 space-y-3 scrollbar-thin"
        aria-live="polite"
        aria-atomic="false"
        aria-relevant="additions"
        role="log"
      >
        <AnimatePresence initial={false}>
          {messages.map((msg) => (
            <MessageBubble key={msg.id} msg={msg} />
          ))}
        </AnimatePresence>

        {/* Suggestions */}
        <AnimatePresence>
          {showSuggestions && (
            <motion.div
              initial={{ opacity: 0, y: 12 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -8 }}
              transition={{ ...SPRING.gentle, delay: 0.3 }}
              className="flex flex-col gap-2 pt-2"
            >
              <div className="flex items-center gap-1.5 mb-1">
                <Sparkles size={10} className="text-slate-600" />
                <span className="mono-xs">Try asking</span>
              </div>
              {SUGGESTIONS.map((q) => (
                <motion.button
                  key={q}
                  whileHover={{ scale: 1.01, x: 2 }}
                  whileTap={{ scale: 0.99 }}
                  transition={SPRING.snappy}
                  onClick={() => handleSuggestion(q)}
                  className="text-left text-[11px] text-slate-500 hover:text-slate-300 glass-panel-subtle px-3.5 py-2.5 transition-colors"
                >
                  {q}
                </motion.button>
              ))}
            </motion.div>
          )}
        </AnimatePresence>

        {/* Error banner */}
        <AnimatePresence>
          {status === "error" && (
            <motion.div
              initial={{ opacity: 0, y: 8, scale: 0.97 }}
              animate={{ opacity: 1, y: 0, scale: 1 }}
              exit={{ opacity: 0, scale: 0.95 }}
              transition={SPRING.bouncy}
              className="flex items-center gap-2 text-[11px] text-red-400 bg-red-500/[0.08] border border-red-500/20 rounded-xl p-3"
            >
              <AlertTriangle size={11} />
              Pipeline error — check server logs
            </motion.div>
          )}
        </AnimatePresence>
      </div>

      {/* Input area */}
      <div className="px-4 pb-4 pt-3 border-t border-white/[0.04]">
        <form onSubmit={handleSubmit}>
          <div className="relative">
            <motion.input
              ref={inputRef}
              disabled={busy}
              value={input}
              onChange={(e) => setInput(e.target.value)}
              placeholder={busy ? "Processing…" : "Ask anything… (⌘K)"}
              aria-label="Query input"
              whileFocus={{ scale: 1.005 }}
              transition={SPRING.snappy}
              className="w-full glass-input px-4 py-3 pr-12 text-[13px] disabled:opacity-40"
            />
            <AnimatePresence mode="wait">
              {busy ? (
                <motion.div
                  key="spinner"
                  initial={{ opacity: 0, scale: 0.6, rotate: -90 }}
                  animate={{ opacity: 1, scale: 1, rotate: 0 }}
                  exit={{ opacity: 0, scale: 0.6 }}
                  transition={SPRING.bouncy}
                  className="absolute right-3 top-1/2 -translate-y-1/2"
                >
                  <Loader2
                    size={16}
                    className="text-blue-400/60 animate-spin"
                  />
                </motion.div>
              ) : (
                <motion.button
                  key="send"
                  type="submit"
                  disabled={!input.trim()}
                  initial={{ opacity: 0, scale: 0.6 }}
                  animate={{
                    opacity: input.trim() ? 1 : 0.3,
                    scale: 1,
                  }}
                  exit={{ opacity: 0, scale: 0.6 }}
                  whileHover={{ scale: 1.15 }}
                  whileTap={{ scale: 0.88 }}
                  transition={SPRING.bouncy}
                  aria-label="Submit query"
                  className="absolute right-3 top-1/2 -translate-y-1/2 p-1.5 rounded-lg text-blue-400 hover:text-blue-300 disabled:cursor-not-allowed transition-colors"
                >
                  <Send size={15} />
                </motion.button>
              )}
            </AnimatePresence>
          </div>
        </form>

        <div className="mt-2 flex items-center justify-center gap-1.5">
          <div className="h-1 w-1 rounded-full bg-emerald-500/40" />
          <span className="mono-xs">
            AIM v0.2.0 · Secured
          </span>
        </div>
      </div>
    </motion.aside>
  );
}
