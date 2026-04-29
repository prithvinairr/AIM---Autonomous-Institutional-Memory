"use client";

import React from "react";
import { motion, AnimatePresence, LayoutGroup } from "framer-motion";
import {
  Activity, Zap, DollarSign, Loader2,
  Link2, Clock, GitBranch, ShieldCheck, AlertTriangle,
} from "lucide-react";
import { useAIMStore } from "@/stores/aim-store";
import { cn, SPRING, formatTokens, formatCost } from "@/lib/utils";
import type { ProvenanceData } from "@/types/aim";

// ── Component ────────────────────────────────────────────────────────────────

// ── Provenance: Resolved Entities ───────────────────────────────────────────

function ResolvedEntities({ provenance }: { provenance: ProvenanceData }) {
  if (!provenance.resolved_entities?.length) return null;
  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={SPRING.gentle}
      className="glass-panel-subtle p-4"
    >
      <div className="flex items-center gap-1.5 mb-3">
        <Link2 size={10} className="text-emerald-400/70" />
        <span className="text-[8px] font-semibold uppercase tracking-[0.2em] text-emerald-400/70">
          Cross-System Entities
        </span>
      </div>
      <div className="flex flex-wrap gap-1.5">
        {provenance.resolved_entities.map((ent, i) => (
          <motion.span
            key={ent.canonical_name}
            initial={{ opacity: 0, scale: 0.8 }}
            animate={{ opacity: 1, scale: 1 }}
            transition={{ ...SPRING.bouncy, delay: i * 0.04 }}
            className="inline-flex items-center gap-1 px-2 py-0.5 rounded-md bg-emerald-500/[0.08] border border-emerald-500/20 text-[9px] font-mono text-emerald-300"
            title={`Sources: ${ent.source_types.join(", ")}`}
          >
            {ent.canonical_name}
            <span className="text-emerald-500/50 text-[7px]">
              {ent.source_ids.length}×
            </span>
          </motion.span>
        ))}
      </div>
    </motion.div>
  );
}

// ── Provenance: Temporal Chain ──────────────────────────────────────────────

function TemporalChain({ provenance }: { provenance: ProvenanceData }) {
  if (!provenance.temporal_chain?.length) return null;
  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ ...SPRING.gentle, delay: 0.05 }}
      className="glass-panel-subtle p-4"
    >
      <div className="flex items-center gap-1.5 mb-3">
        <Clock size={10} className="text-amber-400/70" />
        <span className="text-[8px] font-semibold uppercase tracking-[0.2em] text-amber-400/70">
          Temporal Chain
        </span>
      </div>
      <div className="relative pl-3 border-l border-amber-500/20 space-y-2">
        {provenance.temporal_chain.map((evt, i) => (
          <motion.div
            key={`${evt.source_id}-${i}`}
            initial={{ opacity: 0, x: -6 }}
            animate={{ opacity: 1, x: 0 }}
            transition={{ ...SPRING.snappy, delay: i * 0.05 }}
            className="relative"
          >
            <div className="absolute -left-[13.5px] top-1 h-2 w-2 rounded-full bg-amber-500/40 border border-amber-500/60" />
            <div className="text-[8px] font-mono text-amber-500/60 mb-0.5">
              {evt.timestamp} · {evt.source_type}
            </div>
            <div className="text-[10px] text-slate-400 leading-relaxed">
              {evt.summary}
            </div>
          </motion.div>
        ))}
      </div>
    </motion.div>
  );
}

// ── Provenance: Governed Claims ─────────────────────────────────────────────

function GovernedClaims({ provenance }: { provenance: ProvenanceData }) {
  const facts = provenance.institutional_facts ?? [];
  if (!facts.length) return null;

  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ ...SPRING.gentle, delay: 0.08 }}
      className="glass-panel-subtle p-4"
    >
      <div className="flex items-center gap-1.5 mb-3">
        <ShieldCheck size={10} className="text-sky-400/70" />
        <span className="text-[8px] font-semibold uppercase tracking-[0.2em] text-sky-400/70">
          Governed Claims
        </span>
      </div>
      <div className="space-y-2">
        {facts.slice(0, 6).map((fact, i) => {
          const contested = fact.truth_status === "contested";
          const superseded = fact.truth_status === "superseded";
          const stale = fact.stale || fact.truth_status === "stale";
          return (
            <motion.div
              key={fact.fact_id}
              initial={{ opacity: 0, x: -6 }}
              animate={{ opacity: 1, x: 0 }}
              transition={{ ...SPRING.snappy, delay: i * 0.04 }}
              className={cn(
                "p-2 rounded-lg border bg-white/[0.02]",
                contested
                  ? "border-red-500/20"
                  : superseded
                    ? "border-slate-500/20 opacity-80"
                  : stale
                    ? "border-amber-500/20"
                    : "border-sky-500/15",
              )}
            >
              <div className="flex items-center justify-between gap-2 mb-1">
                <span className="text-[8px] font-mono text-slate-500 truncate">
                  {fact.predicate}
                </span>
                <span
                  className={cn(
                    "inline-flex items-center gap-1 text-[7px] font-bold uppercase tracking-wider",
                    contested ? "text-red-400/80" : stale ? "text-amber-400/80" : superseded ? "text-slate-400/80" : "text-emerald-400/80",
                  )}
                >
                  {(contested || stale || superseded) && <AlertTriangle size={8} />}
                  {fact.truth_status}
                </span>
              </div>
              <p className="text-[10px] text-slate-400 leading-relaxed">
                {fact.statement}
              </p>
              <div className="mt-1.5 flex items-center justify-between gap-2 text-[7px] font-mono text-slate-600">
                <span className="truncate">
                  {fact.verification_status} · {fact.source_authority}
                </span>
                <span>{Math.round((fact.authority_score ?? fact.confidence) * 100)}%</span>
              </div>
              {fact.resolution_reason && (
                <div className="mt-1 text-[7px] leading-relaxed text-slate-600">
                  {fact.resolution_reason}
                </div>
              )}
            </motion.div>
          );
        })}
      </div>
    </motion.div>
  );
}

// ── Provenance: Sub-Query Traces ────────────────────────────────────────────

function SubQueryTraces({ provenance }: { provenance: ProvenanceData }) {
  if (!provenance.sub_query_traces?.length) return null;
  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ ...SPRING.gentle, delay: 0.1 }}
      className="glass-panel-subtle p-4"
    >
      <div className="flex items-center gap-1.5 mb-3">
        <GitBranch size={10} className="text-violet-400/70" />
        <span className="text-[8px] font-semibold uppercase tracking-[0.2em] text-violet-400/70">
          Sub-Query Traces
        </span>
      </div>
      <div className="space-y-2">
        {provenance.sub_query_traces.map((trace, i) => (
          <motion.div
            key={trace.sub_query_id}
            initial={{ opacity: 0, x: -8 }}
            animate={{ opacity: 1, x: 0 }}
            transition={{ ...SPRING.snappy, delay: i * 0.05 }}
            className="flex items-start gap-2 p-2 rounded-lg bg-white/[0.02]"
          >
            <span className="flex-shrink-0 mt-0.5 h-4 w-4 rounded-full bg-violet-500/15 border border-violet-500/25 flex items-center justify-center text-[7px] font-bold text-violet-400">
              {i + 1}
            </span>
            <div className="min-w-0">
              <p className="text-[10px] text-slate-400 font-mono leading-relaxed truncate">
                {trace.sub_query_text}
              </p>
              <div className="flex items-center gap-2 mt-1">
                <span className="text-[8px] text-slate-600">
                  {trace.source_ids.length} source{trace.source_ids.length !== 1 && "s"}
                </span>
                {trace.graph_node_ids.length > 0 && (
                  <span className="text-[8px] text-slate-600">
                    · {trace.graph_node_ids.length} node{trace.graph_node_ids.length !== 1 && "s"}
                  </span>
                )}
              </div>
            </div>
          </motion.div>
        ))}
      </div>
    </motion.div>
  );
}

// ── Component ────────────────────────────────────────────────────────────────

export default function ReasoningPanel() {
  const status = useAIMStore((s) => s.status);
  const subQueries = useAIMStore((s) => s.subQueries);
  const latencyMs = useAIMStore((s) => s.latencyMs);
  const costInfo = useAIMStore((s) => s.costInfo);
  const provenance = useAIMStore((s) => s.provenance);

  const metrics = [
    {
      label: "TTFT",
      value: latencyMs != null ? `${latencyMs}ms` : "—",
      icon: <Activity size={11} />,
      accent:
        latencyMs != null && latencyMs < 800 ? "#34d399" : latencyMs != null ? "#fbbf24" : "#475569",
    },
    {
      label: "Tokens",
      value: costInfo
        ? formatTokens(costInfo.input_tokens + costInfo.output_tokens)
        : "—",
      icon: <Zap size={11} />,
      accent: "#60a5fa",
    },
    {
      label: "Cost",
      value: costInfo ? formatCost(costInfo.estimated_cost_usd) : "—",
      icon: <DollarSign size={11} />,
      accent: "#a78bfa",
    },
  ];

  return (
    <motion.section
      initial={{ opacity: 0, y: 24 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ ...SPRING.gentle, delay: 0.1 }}
      className="flex flex-col gap-3 min-w-0"
      aria-label="Reasoning trace and metrics"
    >
      {/* Metric strip — compact single-row layout, ~36px tall */}
      <div className="grid grid-cols-3 gap-2">
        {metrics.map(({ label, value, icon, accent }, i) => (
          <motion.div
            key={label}
            initial={{ opacity: 0, y: 8, scale: 0.96 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            transition={{ ...SPRING.bouncy, delay: 0.12 + i * 0.05 }}
            whileHover={{ scale: 1.02, y: -1 }}
            className="glass-panel-subtle px-3 py-2 cursor-default flex items-center justify-between gap-2 min-w-0"
          >
            <div
              className="flex items-center gap-1.5 min-w-0"
              style={{ color: accent }}
            >
              {icon}
              <span className="text-[8px] font-semibold uppercase tracking-[0.18em] opacity-70 truncate">
                {label}
              </span>
            </div>
            <motion.div
              key={value}
              initial={{ opacity: 0, y: 2 }}
              animate={{ opacity: 1, y: 0 }}
              transition={SPRING.snappy}
              className="text-[12px] font-bold font-mono text-white tabular-nums truncate"
            >
              {value}
            </motion.div>
          </motion.div>
        ))}
      </div>

      {/* Retrieval quality indicators (real metrics from provenance) */}
      {provenance && (
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ delay: 0.25 }}
          className="glass-panel-subtle px-4 py-3"
        >
          <div className="flex items-center justify-between mb-2">
            <span className="mono-xs">Retrieval Quality</span>
            <span className="mono-xs" style={{ color: (provenance.overall_confidence ?? 0) > 0.7 ? "#34d399" : (provenance.overall_confidence ?? 0) > 0.4 ? "#fbbf24" : "#ef4444" }}>
              {((provenance.overall_confidence ?? 0) * 100).toFixed(0)}%
            </span>
          </div>
          <div className="space-y-1.5">
            {[
              { label: "Confidence", value: provenance.overall_confidence ?? 0, color: "from-emerald-600 to-emerald-400" },
              { label: "Citation Coverage", value: provenance.citation_coverage ?? 0, color: "from-blue-600 to-blue-400" },
              { label: "Query Coverage", value: provenance.query_coverage ?? 0, color: "from-violet-600 to-violet-400" },
            ].map(({ label, value, color }) => (
              <div key={label}>
                <div className="flex items-center justify-between mb-0.5">
                  <span className="text-[7px] font-mono text-slate-600 uppercase tracking-wider">{label}</span>
                  <span className="text-[7px] font-mono text-slate-500">{(value * 100).toFixed(0)}%</span>
                </div>
                <div className="h-[3px] w-full rounded-full bg-white/[0.04] overflow-hidden">
                  <motion.div
                    initial={{ scaleX: 0 }}
                    animate={{ scaleX: value }}
                    transition={SPRING.slow}
                    style={{ originX: 0 }}
                    className={`h-full w-full rounded-full bg-gradient-to-r ${color}`}
                  />
                </div>
              </div>
            ))}
          </div>
        </motion.div>
      )}
      {!provenance && (
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ delay: 0.25 }}
          className="glass-panel-subtle px-4 py-3"
        >
          <div className="flex items-center justify-between mb-2">
            <span className="mono-xs">System Status</span>
            <motion.span
              animate={{ color: status === "idle" ? "#475569" : "#60a5fa" }}
              transition={SPRING.snappy}
              className="mono-xs"
            >
              {status === "idle" ? "Standby" : "Processing"}
            </motion.span>
          </div>
          <div className="h-[3px] w-full rounded-full bg-white/[0.04] overflow-hidden">
            <motion.div
              animate={{ scaleX: status === "thinking" ? 0.5 : status === "streaming" ? 0.85 : 0.1 }}
              transition={SPRING.slow}
              style={{
                originX: 0,
                boxShadow: "0 0 12px rgba(99,102,241,0.6)",
              }}
              className="h-full w-full rounded-full bg-gradient-to-r from-blue-600 via-indigo-500 to-violet-400"
            />
          </div>
        </motion.div>
      )}

      {/* Reasoning trace */}
      <div className="flex-1 glass-panel p-5 overflow-hidden">
        <div className="flex items-center justify-between mb-4">
          <span className="label-xs">Reasoning Trace</span>

          <AnimatePresence mode="wait">
            {status === "thinking" && (
              <motion.div
                key="decomposing"
                initial={{ opacity: 0, x: 8 }}
                animate={{ opacity: 1, x: 0 }}
                exit={{ opacity: 0, x: -8 }}
                transition={SPRING.snappy}
                className="flex items-center gap-1.5 mono-xs text-blue-400/70"
              >
                <Loader2 size={9} className="animate-spin" />
                Decomposing
              </motion.div>
            )}
            {status === "streaming" && (
              <motion.div
                key="synthesizing"
                initial={{ opacity: 0, x: 8 }}
                animate={{ opacity: 1, x: 0 }}
                exit={{ opacity: 0, x: -8 }}
                transition={SPRING.snappy}
                className="flex items-center gap-1.5 mono-xs text-indigo-400/70"
              >
                <motion.div
                  animate={{ scale: [1, 1.3, 1] }}
                  transition={{
                    duration: 1.2,
                    repeat: Infinity,
                    ease: "easeInOut",
                  }}
                  className="h-1.5 w-1.5 rounded-full bg-indigo-400/60"
                />
                Synthesizing
              </motion.div>
            )}
          </AnimatePresence>
        </div>

        <LayoutGroup>
          <AnimatePresence mode="popLayout">
            {subQueries.length === 0 ? (
              <motion.div
                key="empty"
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                exit={{ opacity: 0, scale: 0.97 }}
                transition={SPRING.gentle}
                className="flex flex-col items-center justify-center gap-2 py-14 text-center"
              >
                <motion.div
                  animate={{ opacity: [0.3, 0.6, 0.3] }}
                  transition={{
                    duration: 2.4,
                    repeat: Infinity,
                    ease: "easeInOut",
                  }}
                  className="mono-xs tracking-[0.5em]"
                >
                  Awaiting Query
                </motion.div>
                <p className="text-[9px] text-slate-700 max-w-[200px] leading-relaxed">
                  Sub-queries will appear here as the pipeline decomposes your
                  input into targeted retrieval tasks.
                </p>
              </motion.div>
            ) : (
              <div className="space-y-2">
                {subQueries.map((q, i) => (
                  <motion.div
                    layout
                    key={`${q}-${i}`}
                    initial={{ opacity: 0, x: -12, scale: 0.97 }}
                    animate={{ opacity: 1, x: 0, scale: 1 }}
                    transition={{ ...SPRING.bouncy, delay: i * 0.06 }}
                    className="flex items-start gap-3 p-3 glass-panel-subtle"
                  >
                    <motion.div
                      initial={{ scale: 0 }}
                      animate={{ scale: 1 }}
                      transition={{
                        ...SPRING.bouncy,
                        delay: i * 0.06 + 0.08,
                      }}
                      className="mt-0.5 flex-shrink-0 h-4 w-4 rounded-full bg-blue-500/15 border border-blue-500/25 flex items-center justify-center"
                    >
                      <span className="text-[8px] font-bold text-blue-400">
                        {i + 1}
                      </span>
                    </motion.div>
                    <p className="text-[11px] text-slate-400 leading-relaxed font-mono">
                      {q}
                    </p>
                  </motion.div>
                ))}
              </div>
            )}
          </AnimatePresence>
        </LayoutGroup>
      </div>

      {/* Provenance visualization — appears after query completes */}
      <AnimatePresence>
        {provenance && status === "idle" && (
          <motion.div
            initial={{ opacity: 0, height: 0 }}
            animate={{ opacity: 1, height: "auto" }}
            exit={{ opacity: 0, height: 0 }}
            transition={SPRING.gentle}
            className="flex flex-col gap-3 overflow-hidden"
          >
            <ResolvedEntities provenance={provenance} />
            <TemporalChain provenance={provenance} />
            <GovernedClaims provenance={provenance} />
            <SubQueryTraces provenance={provenance} />
          </motion.div>
        )}
      </AnimatePresence>
    </motion.section>
  );
}
