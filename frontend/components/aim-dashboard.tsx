"use client";

import React, { useEffect, useState } from "react";
import dynamic from "next/dynamic";
import { motion, AnimatePresence } from "framer-motion";
import { Cpu, Activity, Plus, MessageSquare, FileText, Network, Brain } from "lucide-react";
import { useAIMStore } from "@/stores/aim-store";
import SourcePanel from "@/components/source-panel";
import ReasoningPanel from "@/components/reasoning-panel";
import ConsolePanel from "@/components/console-panel";
import KnowledgeGraph from "@/components/knowledge-graph";
import ErrorBoundary from "@/components/error-boundary";
import { SPRING } from "@/lib/utils";

// Lazy-load Three.js scene — no SSR, loads after first paint
const BackgroundScene = dynamic(
  () => import("@/components/background-scene"),
  { ssr: false }
);

// ── Mobile tab type ──────────────────────────────────────────────────────────

type MobileTab = "chat" | "sources" | "graph" | "reasoning";

// ── Status indicator dot ─────────────────────────────────────────────────────

function StatusDot() {
  const status = useAIMStore((s) => s.status);
  const color =
    status === "idle"
      ? "#10b981"
      : status === "error"
        ? "#ef4444"
        : "#60a5fa";

  return (
    <motion.div
      animate={{
        backgroundColor: color,
        scale: status !== "idle" ? [1, 1.4, 1] : 1,
      }}
      transition={
        status !== "idle"
          ? { scale: { duration: 1.2, repeat: Infinity, ease: "easeInOut" } }
          : SPRING.snappy
      }
      className="h-1.5 w-1.5 rounded-full"
      role="status"
      aria-label={`System status: ${status}`}
    >
      <span className="sr-only">{status}</span>
    </motion.div>
  );
}

// ── Header ───────────────────────────────────────────────────────────────────

function Header() {
  const status = useAIMStore((s) => s.status);
  const latencyMs = useAIMStore((s) => s.latencyMs);
  const isRetrying = useAIMStore((s) => s.isRetrying);
  const retryCount = useAIMStore((s) => s.retryCount);
  const newConversation = useAIMStore((s) => s.newConversation);

  return (
    <motion.header
      initial={{ y: -60, opacity: 0 }}
      animate={{ y: 0, opacity: 1 }}
      transition={SPRING.gentle}
      className="absolute top-0 left-0 right-0 z-50 flex items-center justify-between px-4 sm:px-6 md:px-8 py-3 sm:py-4 border-b border-white/[0.04] bg-black/10 backdrop-blur-2xl safe-area-top"
    >
      {/* Logo */}
      <motion.div
        whileHover={{ scale: 1.02 }}
        transition={SPRING.snappy}
        className="flex items-center gap-2.5 sm:gap-3.5 cursor-default select-none"
      >
        <div className="relative flex h-8 w-8 sm:h-9 sm:w-9 items-center justify-center rounded-xl bg-blue-500/10 border border-blue-500/20">
          <Cpu size={16} className="text-blue-400 sm:hidden" />
          <Cpu size={18} className="text-blue-400 hidden sm:block" />
          <motion.div
            animate={{
              opacity: status !== "idle" ? [0.4, 1, 0.4] : 0,
            }}
            transition={{
              duration: 1.5,
              repeat: Infinity,
              ease: "easeInOut",
            }}
            className="absolute inset-0 rounded-xl bg-blue-400/10 blur-sm"
          />
        </div>
        <div>
          <h1 className="text-[11px] sm:text-[12px] font-black tracking-[0.3em] uppercase text-white leading-none">
            AIM Engine
          </h1>
          <p className="text-[7px] sm:text-[8px] font-mono text-blue-500/50 uppercase tracking-[0.2em] mt-0.5">
            Autonomous Memory
          </p>
        </div>
      </motion.div>

      {/* Center: status */}
      <div className="hidden md:flex items-center gap-6">
        <div className="flex items-center gap-2">
          <StatusDot />
          <span className="text-[9px] font-mono uppercase tracking-widest text-slate-500">
            System
          </span>
          <motion.span
            key={status}
            initial={{ opacity: 0, y: -4 }}
            animate={{ opacity: 1, y: 0 }}
            transition={SPRING.snappy}
            className="text-[9px] font-mono uppercase tracking-widest text-slate-300 capitalize"
          >
            {status}
          </motion.span>
        </div>

        <AnimatePresence>
          {isRetrying && (
            <motion.div
              initial={{ opacity: 0, scale: 0.8, x: -8 }}
              animate={{ opacity: 1, scale: 1, x: 0 }}
              exit={{ opacity: 0, scale: 0.8 }}
              transition={SPRING.bouncy}
              className="flex items-center gap-1.5 text-[9px] font-mono text-amber-400/80 uppercase tracking-widest"
            >
              <motion.div
                animate={{ rotate: 360 }}
                transition={{ duration: 1, repeat: Infinity, ease: "linear" }}
                className="h-2.5 w-2.5 rounded-full border border-amber-400/60 border-t-transparent"
              />
              Retry {retryCount}/{3}
            </motion.div>
          )}
          {latencyMs != null && (
            <motion.div
              initial={{ opacity: 0, scale: 0.8, x: 8 }}
              animate={{ opacity: 1, scale: 1, x: 0 }}
              exit={{ opacity: 0, scale: 0.8 }}
              transition={SPRING.bouncy}
              className="flex items-center gap-1.5 text-[9px] font-mono text-slate-500 uppercase tracking-widest tabular-nums"
            >
              <Activity size={10} className="text-emerald-500/70" />
              TTFT {latencyMs}ms
            </motion.div>
          )}
        </AnimatePresence>
      </div>

      {/* Right: status dot (mobile) + new conversation */}
      <div className="flex items-center gap-3">
        <div className="md:hidden flex items-center gap-1.5">
          <StatusDot />
          <span className="text-[8px] font-mono uppercase text-slate-500 capitalize">
            {status}
          </span>
        </div>
        <motion.button
          whileHover={{ scale: 1.05 }}
          whileTap={{ scale: 0.95 }}
          transition={SPRING.snappy}
          onClick={newConversation}
          className="flex items-center gap-1.5 px-2.5 sm:px-3 py-1.5 rounded-lg bg-white/[0.04] border border-white/[0.07] text-[9px] font-semibold uppercase tracking-wider text-slate-400 hover:text-white hover:bg-white/[0.08] transition-colors min-h-[36px] sm:min-h-0"
          aria-label="Start new conversation"
          title="New conversation"
        >
          <Plus size={12} />
          <span className="hidden sm:inline">New Chat</span>
        </motion.button>
      </div>
    </motion.header>
  );
}

// ── Mobile tab bar ───────────────────────────────────────────────────────────

function MobileTabBar({
  activeTab,
  onChange,
}: {
  activeTab: MobileTab;
  onChange: (tab: MobileTab) => void;
}) {
  const tabs: { id: MobileTab; icon: React.ReactNode; label: string }[] = [
    { id: "chat", icon: <MessageSquare size={18} />, label: "Chat" },
    { id: "sources", icon: <FileText size={18} />, label: "Sources" },
    { id: "graph", icon: <Network size={18} />, label: "Graph" },
    { id: "reasoning", icon: <Brain size={18} />, label: "Reasoning" },
  ];

  return (
    <nav
      className="lg:hidden fixed bottom-0 left-0 right-0 z-50 flex items-center justify-around px-2 py-1 bg-black/80 backdrop-blur-2xl border-t border-white/[0.06] safe-area-bottom"
      role="tablist"
      aria-label="Panel navigation"
    >
      {tabs.map(({ id, icon, label }) => (
        <button
          key={id}
          role="tab"
          aria-selected={activeTab === id}
          aria-controls={`panel-${id}`}
          onClick={() => onChange(id)}
          className={`flex flex-col items-center gap-0.5 px-3 py-2 rounded-lg min-w-[56px] min-h-[44px] transition-colors ${
            activeTab === id
              ? "text-blue-400 bg-blue-500/10"
              : "text-slate-600 hover:text-slate-400"
          }`}
        >
          {icon}
          <span className="text-[8px] font-semibold uppercase tracking-wider">
            {label}
          </span>
        </button>
      ))}
    </nav>
  );
}

// ── Dashboard layout ─────────────────────────────────────────────────────────

export default function AIMDashboard() {
  const [mobileTab, setMobileTab] = useState<MobileTab>("chat");

  useEffect(() => {
    useAIMStore.getState().hydrateClientState();
  }, []);

  return (
    <main className="relative h-screen w-full overflow-hidden bg-aim-bg text-slate-300 font-sans antialiased noise-overlay">
      <BackgroundScene />
      <Header />

      {/* Desktop: Three-column grid. Each column is h-full min-h-0 so its
          children can scroll independently instead of overflowing the page.
          pb-5 pairs with pt-[5.5rem] so the bottom edge has consistent gutter. */}
      <div className="hidden lg:grid relative z-10 h-full grid-cols-12 gap-4 px-5 pt-[5.5rem] pb-5">
        {/* Sources — left column */}
        <div className="col-span-3 h-full min-h-0 flex flex-col">
          <ErrorBoundary panelName="Sources">
            <SourcePanel />
          </ErrorBoundary>
        </div>

        {/* Center column: Knowledge Graph (60%) + Reasoning (40%) split */}
        <div className="col-span-4 h-full min-h-0 flex flex-col gap-4">
          <div className="flex-[3] min-h-0">
            <ErrorBoundary panelName="Knowledge Nebula">
              <KnowledgeGraph />
            </ErrorBoundary>
          </div>
          <div className="flex-[2] min-h-0 flex flex-col">
            <ErrorBoundary panelName="Reasoning">
              <ReasoningPanel />
            </ErrorBoundary>
          </div>
        </div>

        {/* Console — right column */}
        <div className="col-span-5 h-full min-h-0 flex flex-col">
          <ErrorBoundary panelName="Console">
            <ConsolePanel />
          </ErrorBoundary>
        </div>
      </div>

      {/* Mobile/Tablet: Single panel with tab bar */}
      <div className="lg:hidden relative z-10 h-full p-3 sm:p-4 pt-16 sm:pt-20 pb-20">
        <AnimatePresence mode="wait">
          {mobileTab === "chat" && (
            <motion.div
              key="chat"
              id="panel-chat"
              role="tabpanel"
              initial={{ opacity: 0, x: -20 }}
              animate={{ opacity: 1, x: 0 }}
              exit={{ opacity: 0, x: 20 }}
              transition={SPRING.snappy}
              className="h-full flex flex-col min-h-0"
            >
              <ErrorBoundary fallbackLabel="Console encountered an error.">
                <ConsolePanel />
              </ErrorBoundary>
            </motion.div>
          )}
          {mobileTab === "sources" && (
            <motion.div
              key="sources"
              id="panel-sources"
              role="tabpanel"
              initial={{ opacity: 0, x: -20 }}
              animate={{ opacity: 1, x: 0 }}
              exit={{ opacity: 0, x: 20 }}
              transition={SPRING.snappy}
              className="h-full"
            >
              <ErrorBoundary fallbackLabel="Source panel encountered an error.">
                <SourcePanel />
              </ErrorBoundary>
            </motion.div>
          )}
          {mobileTab === "graph" && (
            <motion.div
              key="graph"
              id="panel-graph"
              role="tabpanel"
              initial={{ opacity: 0, x: -20 }}
              animate={{ opacity: 1, x: 0 }}
              exit={{ opacity: 0, x: 20 }}
              transition={SPRING.snappy}
              className="h-full"
            >
              <ErrorBoundary fallbackLabel="Knowledge graph encountered an error.">
                <KnowledgeGraph />
              </ErrorBoundary>
            </motion.div>
          )}
          {mobileTab === "reasoning" && (
            <motion.div
              key="reasoning"
              id="panel-reasoning"
              role="tabpanel"
              initial={{ opacity: 0, x: -20 }}
              animate={{ opacity: 1, x: 0 }}
              exit={{ opacity: 0, x: 20 }}
              transition={SPRING.snappy}
              className="h-full overflow-y-auto"
            >
              <ErrorBoundary fallbackLabel="Reasoning panel encountered an error.">
                <ReasoningPanel />
              </ErrorBoundary>
            </motion.div>
          )}
        </AnimatePresence>
      </div>

      <MobileTabBar activeTab={mobileTab} onChange={setMobileTab} />
    </main>
  );
}
