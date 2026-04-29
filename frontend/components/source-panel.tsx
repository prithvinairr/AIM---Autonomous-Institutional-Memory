"use client";

import React from "react";
import { motion, AnimatePresence, LayoutGroup } from "framer-motion";
import {
  Slack, Github, Database, Terminal, GitBranch, DollarSign,
  ExternalLink, FileSearch,
} from "lucide-react";
import type { LucideIcon } from "lucide-react";
import { useAIMStore } from "@/stores/aim-store";
import { cn, SPRING, formatTokens, formatCost } from "@/lib/utils";
import type { AIMState } from "@/stores/aim-store";
import type { SourceSummary } from "@/types/aim";

// ── Source type → icon mapping ───────────────────────────────────────────────

const SOURCE_ICON: Record<string, LucideIcon> = {
  slack_mcp: Slack,
  neo4j_graph: Database,
  pinecone_vector: Terminal,
  jira_mcp: GitBranch,
};

const SKELETON_SOURCES: Array<{ label: string; Icon: LucideIcon }> = [
  { label: "Slack / Engineering", Icon: Slack },
  { label: "GitHub / Production", Icon: Github },
  { label: "Jira / Sprint Board", Icon: GitBranch },
  { label: "Vector Store", Icon: Terminal },
];

// ── Component ────────────────────────────────────────────────────────────────

function SourcePreview({ source }: { source: SourceSummary | null }) {
  if (!source) {
    return (
      <div className="mt-4 glass-panel-subtle p-3.5">
        <div className="flex items-center gap-1.5 mb-1">
          <FileSearch size={10} className="text-slate-700" />
          <span className="mono-xs">Evidence Detail</span>
        </div>
        <p className="text-[10px] leading-relaxed text-slate-700">
          Select a retrieved source or citation to inspect its evidence.
        </p>
      </div>
    );
  }

  const confidence = Math.round(source.confidence * 100);
  const Icon = SOURCE_ICON[source.source_type] ?? Database;

  return (
    <motion.div
      key={source.source_id}
      initial={{ opacity: 0, y: 8, scale: 0.98 }}
      animate={{ opacity: 1, y: 0, scale: 1 }}
      exit={{ opacity: 0, y: -4 }}
      transition={SPRING.gentle}
      className="mt-4 glass-panel-subtle p-3.5"
    >
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <div className="flex items-center gap-1.5 mb-1">
            <Icon size={10} className="text-blue-400/80" />
            <span className="mono-xs">Evidence Detail</span>
          </div>
          <h3 className="truncate text-[11px] font-semibold text-slate-300">
            {source.title || source.source_type}
          </h3>
        </div>
        <span className="rounded-md border border-emerald-500/20 bg-emerald-500/[0.08] px-1.5 py-0.5 text-[8px] font-mono text-emerald-300">
          {confidence}%
        </span>
      </div>

      {source.snippet && (
        <p className="mt-2 max-h-24 overflow-y-auto pr-1 text-[10px] leading-relaxed text-slate-500 scrollbar-thin">
          {source.snippet}
        </p>
      )}

      <div className="mt-2 flex items-center justify-between gap-2 border-t border-white/[0.04] pt-2">
        <span className="truncate text-[8px] font-mono text-slate-600">
          {source.source_id}
        </span>
        {source.uri && (
          <a
            href={source.uri}
            target="_blank"
            rel="noreferrer"
            className="inline-flex items-center gap-1 rounded-md border border-white/[0.06] bg-white/[0.03] px-1.5 py-1 text-[8px] font-mono text-slate-500 transition-colors hover:border-blue-500/30 hover:text-blue-300"
            title={source.uri}
          >
            <ExternalLink size={9} />
            Open
          </a>
        )}
      </div>
    </motion.div>
  );
}

export default function SourcePanel() {
  const activeIdx = useAIMStore((s: AIMState) => s.activeSourceIndex);
  const sources = useAIMStore((s: AIMState) => s.activeSources);
  const costInfo = useAIMStore((s: AIMState) => s.costInfo);
  const status = useAIMStore((s: AIMState) => s.status);
  const selectedSourceId = useAIMStore((s: AIMState) => s.selectedSourceId);
  const setSelectedSource = useAIMStore((s: AIMState) => s.setSelectedSource);
  const setActiveSourceIndex = useAIMStore((s: AIMState) => s.setActiveSourceIndex);

  const hasSources = sources.length > 0;
  const selectedIdx = sources.findIndex((src) => src.source_id === selectedSourceId);
  const previewSource =
    selectedIdx >= 0 ? sources[selectedIdx] : activeIdx >= 0 ? sources[activeIdx] : null;

  return (
    <motion.aside
      initial={{ opacity: 0, x: -24 }}
      animate={{ opacity: 1, x: 0 }}
      transition={{ ...SPRING.gentle, delay: 0.05 }}
      className="h-full min-h-0 flex flex-col gap-3 min-w-0"
      aria-label="Sources and cost"
    >
      {/* Sources card — scrolls internally when many sources retrieved */}
      <div className="flex-1 min-h-0 glass-panel p-5 flex flex-col overflow-hidden">
        <div className="flex items-center justify-between mb-5 flex-shrink-0">
          <span className="label-xs">
            {hasSources ? "Retrieved Sources" : "Ingress Channels"}
          </span>
          <motion.div
            animate={{ opacity: status !== "idle" ? 1 : 0.3 }}
            className="h-1.5 w-1.5 rounded-full bg-blue-400"
            transition={SPRING.snappy}
          />
        </div>

        <LayoutGroup>
          {/* Source list scrolls when many; cap so Evidence/Cost sections
              below stay visible. */}
          <div className="space-y-2 max-h-[34vh] overflow-y-auto pr-1 scrollbar-thin">
            <AnimatePresence mode="popLayout">
              {hasSources
                ? sources.slice(0, 6).map((src, i) => {
                    const Icon = SOURCE_ICON[src.source_type] ?? Database;
                    const on = i === activeIdx || src.source_id === selectedSourceId;
                    const pct = Math.round(src.confidence * 100);
                    return (
                      <motion.button
                        type="button"
                        layout
                        key={src.source_id}
                        onClick={() => {
                          setActiveSourceIndex(i);
                          setSelectedSource(src.source_id);
                        }}
                        initial={{ opacity: 0, y: 8, scale: 0.97 }}
                        animate={{
                          opacity: 1,
                          y: 0,
                          scale: src.source_id === selectedSourceId ? 1.02 : 1,
                        }}
                        exit={{ opacity: 0, scale: 0.95 }}
                        transition={{ ...SPRING.bouncy, delay: i * 0.04 }}
                        whileHover={{ scale: 1.015, y: -1 }}
                        className={cn(
                          "relative flex w-full items-center justify-between rounded-xl border p-3.5 text-left transition-colors",
                          src.source_id === selectedSourceId
                            ? "border-blue-400/50 bg-blue-500/[0.12] ring-1 ring-blue-500/20"
                            : on
                              ? "border-blue-500/30 bg-blue-500/[0.07]"
                              : "border-white/[0.05] bg-white/[0.02]"
                        )}
                      >
                        {on && (
                          <motion.div
                            layoutId="source-glow"
                            className="absolute inset-0 rounded-xl bg-blue-500/10 blur-sm"
                            transition={SPRING.gentle}
                          />
                        )}
                        <div className="relative flex items-center gap-2.5 min-w-0">
                          <Icon
                            size={13}
                            className={cn(
                              "flex-shrink-0",
                              on ? "text-blue-400" : "text-slate-600"
                            )}
                          />
                          <span
                            className={cn(
                              "text-[11px] truncate font-medium",
                              on ? "text-slate-200" : "text-slate-500"
                            )}
                          >
                            {src.title || src.source_type}
                          </span>
                        </div>

                        {/* Confidence bar + percentage */}
                        <div className="relative flex items-center gap-2 flex-shrink-0 ml-2">
                          <div className="w-12 h-[3px] rounded-full bg-white/[0.04] overflow-hidden">
                            <motion.div
                              initial={{ scaleX: 0 }}
                              animate={{ scaleX: pct / 100 }}
                              transition={{ ...SPRING.slow, delay: i * 0.04 }}
                              style={{ originX: 0 }}
                              className="h-full rounded-full bg-blue-500/60"
                            />
                          </div>
                          <span className="text-[9px] font-mono text-slate-600 w-7 text-right tabular-nums">
                            {pct}%
                          </span>
                        </div>
                      </motion.button>
                    );
                  })
                : SKELETON_SOURCES.map(({ label, Icon }, i) => {
                    const on = status !== "idle" && i % 2 === 0;
                    return (
                      <motion.div
                        layout
                        key={label}
                        animate={{
                          borderColor: on
                            ? "rgba(59,130,246,0.25)"
                            : "rgba(255,255,255,0.04)",
                          backgroundColor: on
                            ? "rgba(59,130,246,0.05)"
                            : "rgba(255,255,255,0.015)",
                        }}
                        transition={SPRING.slow}
                        className="flex items-center justify-between rounded-xl border p-3.5"
                      >
                        <div className="flex items-center gap-2.5">
                          <Icon
                            size={13}
                            className={cn(
                              "transition-colors",
                              on ? "text-blue-400/70" : "text-slate-700"
                            )}
                          />
                          <span
                            className={cn(
                              "text-[11px] font-medium transition-colors",
                              on ? "text-slate-400" : "text-slate-600"
                            )}
                          >
                            {label}
                          </span>
                        </div>
                        <div className="flex items-center gap-1.5">
                          {on && (
                            <motion.span
                              initial={{ scale: 0 }}
                              animate={{ scale: 1 }}
                              transition={SPRING.bouncy}
                              className="h-1 w-1 rounded-full bg-blue-400/60 animate-ping"
                            />
                          )}
                          <span className="mono-xs">
                            {on ? "Active" : "Standby"}
                          </span>
                        </div>
                      </motion.div>
                    );
                  })}
            </AnimatePresence>
          </div>
        </LayoutGroup>

        <AnimatePresence mode="wait">
          <SourcePreview source={previewSource} />
        </AnimatePresence>

        {/* Cost breakdown */}
        <AnimatePresence>
          {costInfo ? (
            <motion.div
              initial={{ opacity: 0, y: 8, scale: 0.98 }}
              animate={{ opacity: 1, y: 0, scale: 1 }}
              exit={{ opacity: 0, y: -4 }}
              transition={SPRING.gentle}
              className="mt-4 glass-panel-subtle p-3.5"
            >
              <div className="flex items-center gap-1.5 mb-2.5">
                <DollarSign size={9} className="text-slate-600" />
                <span className="mono-xs">Query Cost</span>
              </div>
              {[
                { label: "Input", value: formatTokens(costInfo.input_tokens) + " tok" },
                { label: "Output", value: formatTokens(costInfo.output_tokens) + " tok" },
                { label: "Embed", value: formatTokens(costInfo.embedding_tokens) + " tok" },
                { label: "Total", value: formatCost(costInfo.estimated_cost_usd) },
              ].map(({ label, value }, i) => (
                <motion.div
                  key={label}
                  initial={{ opacity: 0, x: -6 }}
                  animate={{ opacity: 1, x: 0 }}
                  transition={{ ...SPRING.snappy, delay: i * 0.04 }}
                  className="flex justify-between items-center py-[3px]"
                >
                  <span className="text-[10px] text-slate-600">{label}</span>
                  <span className="text-[10px] font-mono text-slate-400 tabular-nums">
                    {value}
                  </span>
                </motion.div>
              ))}
            </motion.div>
          ) : (
            <div className="mt-4 glass-panel-subtle p-3.5">
              <div className="flex items-center gap-1.5 mb-1">
                <DollarSign size={9} className="text-slate-700" />
                <span className="mono-xs">Query Cost</span>
              </div>
              <div className="text-[10px] font-mono text-slate-700 italic">
                —
              </div>
            </div>
          )}
        </AnimatePresence>
      </div>
    </motion.aside>
  );
}
