"use client";

import React, { memo, useMemo } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { motion } from "framer-motion";
import { ShieldCheck, AlertTriangle, Copy, Check } from "lucide-react";
import { cn, SPRING } from "@/lib/utils";
import { useAIMStore } from "@/stores/aim-store";
import type { Message } from "@/types/aim";

// ── Streaming cursor ─────────────────────────────────────────────────────────

function StreamingCursor() {
  return (
    <motion.span
      animate={{ opacity: [1, 0, 1] }}
      transition={{ duration: 1.1, repeat: Infinity, ease: "easeInOut" }}
      className="inline-block w-[1.5px] h-[14px] bg-blue-400/80 ml-0.5 align-middle rounded-full"
      aria-label="Generating response"
    />
  );
}

// ── Copy button for code blocks ──────────────────────────────────────────────

function CopyButton({ text }: { text: string }) {
  const [copied, setCopied] = React.useState(false);

  const handleCopy = async () => {
    await navigator.clipboard.writeText(text);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <button
      onClick={handleCopy}
      className="absolute top-2 right-2 p-1.5 rounded-lg bg-white/[0.06] hover:bg-white/[0.12] text-slate-500 hover:text-slate-300 transition-all opacity-0 group-hover:opacity-100"
      aria-label="Copy code"
    >
      {copied ? <Check size={12} /> : <Copy size={12} />}
    </button>
  );
}

// ── Citation tag parser ──────────────────────────────────────────────────────

const SRC_TAG_RE = /\[SRC:([\w-]+)\]/g;

/**
 * Strips `[SRC:id]` tags from content and returns clean text plus
 * citation IDs in order of appearance for footnote rendering.
 */
function parseCitations(raw: string): { clean: string; citeIds: string[] } {
  const citeIds: string[] = [];
  const clean = raw.replace(SRC_TAG_RE, (_match, id: string) => {
    if (!citeIds.includes(id)) citeIds.push(id);
    const idx = citeIds.indexOf(id) + 1;
    return `[[${idx}]](aim-source:${encodeURIComponent(id)})`;
  });
  return { clean, citeIds };
}

function getSourceIdFromHref(href?: string): string | null {
  if (!href?.startsWith("aim-source:")) return null;
  try {
    return decodeURIComponent(href.slice("aim-source:".length));
  } catch {
    return null;
  }
}

// ── Markdown renderer with dark theme ────────────────────────────────────────
// Memoized to prevent full markdown re-parse on every streaming render tick.

const MarkdownContent = memo(function MarkdownContent({ content }: { content: string }) {
  const { clean, citeIds } = useMemo(() => parseCitations(content), [content]);
  const sources = useAIMStore((s) => s.activeSources);
  const provenanceSources = useAIMStore((s) => s.provenance?.sources);
  const sourceById = useMemo(
    () => new Map(sources.map((source) => [source.source_id, source])),
    [sources],
  );

  const selectSource = (id: string) => {
    const store = useAIMStore.getState();
    store.setSelectedSource(id);
    const idx = store.activeSources.findIndex((s) => s.source_id === id);
    if (idx >= 0) store.setActiveSourceIndex(idx);
  };

  const sourceLabel = (id: string) => {
    const source = sourceById.get(id) ?? provenanceSources?.[id];
    return source?.title || source?.source_type || id;
  };

  return (
    <>
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        className="prose prose-sm prose-aim max-w-none"
        components={{
          pre({ children, ...props }) {
            const child = children as React.ReactElement<{
              children?: React.ReactNode;
            }>;
            const codeStr =
              React.isValidElement(children) &&
              typeof child.props?.children === "string"
                ? child.props.children
                : "";
            return (
              <div className="relative group">
                {codeStr && <CopyButton text={codeStr} />}
                <pre {...props}>{children}</pre>
              </div>
            );
          },
          a({ children, href, ...props }) {
            const src = getSourceIdFromHref(href);
            if (src) {
              return (
                <button
                  type="button"
                  onClick={() => selectSource(src)}
                  className="not-italic inline-flex items-center justify-center min-w-[16px] h-4 px-1 mx-0.5 rounded bg-blue-500/15 border border-blue-500/25 text-[9px] font-bold text-blue-400 cursor-pointer align-super leading-none hover:bg-blue-500/25 hover:border-blue-500/40 transition-colors"
                  title={`Source: ${sourceLabel(src)}`}
                >
                  {children}
                </button>
              );
            }
            return (
              <a href={href} rel="noreferrer" target="_blank" {...props}>
                {children}
              </a>
            );
          },
        }}
      >
        {clean}
      </ReactMarkdown>

      {/* Citation footnotes */}
      {citeIds.length > 0 && (
        <div className="mt-2 pt-2 border-t border-white/[0.05] flex flex-wrap gap-1.5">
          {citeIds.map((id, i) => (
            <button
              key={id}
              type="button"
              onClick={() => selectSource(id)}
              className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded bg-white/[0.03] border border-white/[0.06] text-[8px] font-mono text-slate-500 hover:bg-blue-500/10 hover:border-blue-500/20 hover:text-slate-400 transition-colors cursor-pointer"
              title={id}
            >
              <span className="text-blue-400 font-bold">[{i + 1}]</span>
              <span className="truncate max-w-[120px]">{sourceLabel(id)}</span>
            </button>
          ))}
        </div>
      )}
    </>
  );
});

// ── Relative time ────────────────────────────────────────────────────────────

function RelativeTime({ ts }: { ts: number }) {
  const [label, setLabel] = React.useState("just now");

  React.useEffect(() => {
    const diff = Math.round((Date.now() - ts) / 1000);
    setLabel(
      diff < 5 ? "just now" :
      diff < 60 ? `${diff}s ago` :
      diff < 3600 ? `${Math.floor(diff / 60)}m ago` :
      `${Math.floor(diff / 3600)}h ago`,
    );
  }, [ts]);

  return (
    <span className="text-[8px] font-mono text-slate-700 tabular-nums">
      {label}
    </span>
  );
}

// ── Message bubble ───────────────────────────────────────────────────────────

interface MessageBubbleProps {
  msg: Message;
}

export const MessageBubble = memo(function MessageBubble({
  msg,
}: MessageBubbleProps) {
  const isUser = msg.role === "user";
  const isError = msg.source === "Error";

  return (
    <motion.div
      layout
      initial={{ opacity: 0, y: 12, scale: 0.96 }}
      animate={{ opacity: 1, y: 0, scale: 1 }}
      transition={SPRING.bouncy}
      className={cn("flex", isUser ? "justify-end" : "justify-start")}
    >
      <motion.div
        whileHover={{ scale: 1.003 }}
        transition={SPRING.snappy}
        className={cn(
          "max-w-[88%] px-4 py-3 rounded-2xl text-[13px] leading-relaxed",
          isUser
            ? "bg-blue-600/90 text-white rounded-br-md shadow-lg shadow-blue-900/20"
            : isError
              ? "bg-red-500/[0.08] border border-red-500/20 text-red-300 rounded-bl-md"
              : "bg-white/[0.04] border border-white/[0.07] text-slate-300 rounded-bl-md"
        )}
      >
        {/* Empty streaming state */}
        {msg.isStreaming && !msg.content && (
          <span className="text-slate-600 text-xs italic">Synthesizing…</span>
        )}

        {/* Content */}
        {msg.content && (
          isUser ? (
            <span>{msg.content}</span>
          ) : (
            <MarkdownContent content={msg.content} />
          )
        )}

        {/* Streaming cursor */}
        {msg.isStreaming && msg.content && <StreamingCursor />}

        {/* Footer: source badge + timestamp */}
        {!msg.isStreaming && (msg.source || msg.timestamp) && (
          <motion.div
            initial={{ opacity: 0, y: 4 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ ...SPRING.gentle, delay: 0.1 }}
            className="mt-2.5 flex items-center justify-between gap-3"
          >
            {msg.source && msg.source !== "Error" && (
              <div className="flex items-center gap-1.5 text-[8px] font-bold uppercase tracking-[0.15em] text-blue-400/80">
                {isError ? (
                  <AlertTriangle size={9} />
                ) : (
                  <ShieldCheck size={9} />
                )}
                {msg.source}
                {msg.confidence != null && (
                  <span className="text-slate-600 font-normal ml-1">
                    {Math.round(msg.confidence * 100)}%
                  </span>
                )}
              </div>
            )}
            {!isUser && <RelativeTime ts={msg.timestamp} />}
          </motion.div>
        )}
      </motion.div>
    </motion.div>
  );
});
