"use client";

import { useRef, useCallback, useEffect } from "react";
import { useAIMStore } from "@/stores/aim-store";
import { API_BASE } from "@/lib/utils";
import type { SSEChunk } from "@/types/aim";

// ── Retry + backpressure constants ──────────────────────────────────────────

const MAX_RETRIES = 3;
const INITIAL_BACKOFF_MS = 1000;
const MAX_BACKOFF_MS = 8000;
const STREAM_TIMEOUT_MS = 240_000;
const INACTIVITY_TIMEOUT_MS = 90_000;

/** Exponential backoff: 1s, 2s, 4s (capped at 8s). */
function backoffMs(attempt: number): number {
  return Math.min(INITIAL_BACKOFF_MS * 2 ** attempt, MAX_BACKOFF_MS);
}

/** Resolves after ms. */
function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

/**
 * SSE streaming hook — submits a query to the AIM backend and
 * progressively updates the store as chunks arrive.
 *
 * Features:
 *   - 240s stream timeout for local-model seed demos
 *   - Exponential backoff retry (up to 3 attempts)
 *   - requestAnimationFrame token batching (reduces DOM thrash)
 *   - SSE reconnection on stream drop (resumes mid-stream)
 *   - Abort on unmount / new query
 */
export function useAIMQuery() {
  const abortRef = useRef<AbortController | null>(null);
  const rafRef = useRef<number | null>(null);
  const pendingTokensRef = useRef<string>("");

  // Flush pending tokens via rAF batching
  const flushTokens = useCallback((msgId: number) => {
    if (rafRef.current !== null) return; // already scheduled
    rafRef.current = requestAnimationFrame(() => {
      rafRef.current = null;
      const batch = pendingTokensRef.current;
      if (batch) {
        pendingTokensRef.current = "";
        useAIMStore.getState().appendToMessage(msgId, batch);
      }
    });
  }, []);

  // Clean up on unmount
  useEffect(() => {
    return () => {
      abortRef.current?.abort();
      if (rafRef.current !== null) cancelAnimationFrame(rafRef.current);
    };
  }, []);

  const submit = useCallback(
    async (query: string) => {
      // Cancel any in-flight request
      abortRef.current?.abort();
      abortRef.current = new AbortController();

      const s = useAIMStore.getState();
      s.clearSubQueries();
      s.setCostInfo(null);
      s.setActiveSources([]);
      s.setActiveSourceIndex(-1);
      s.setStatus("thinking");
      s.setRetryCount(0);
      s.setIsRetrying(false);

      const t0 = performance.now();
      let firstToken = false;
      const msgId = s.addMessage({
        role: "assistant",
        content: "",
        isStreaming: true,
      });

      const queryId = crypto.randomUUID();
      let lastAttemptError: string | null = null;

      // ── Retry loop ──────────────────────────────────────────────────────
      for (let attempt = 0; attempt <= MAX_RETRIES; attempt++) {
        if (attempt > 0) {
          // Backoff before retry
          const delay = backoffMs(attempt - 1);
          const cur = useAIMStore.getState();
          cur.setIsRetrying(true);
          cur.setRetryCount(attempt);
          cur.setStatus("thinking");

          await sleep(delay);

          // Check if aborted during backoff
          if (abortRef.current?.signal.aborted) return;
        }

        try {
          // Local Qwen seed demos can be quiet for a while during retrieval
          // and synthesis, so keep this budget above benchmark p95 latency.
          const timeoutId = setTimeout(() => {
            abortRef.current?.abort();
          }, STREAM_TIMEOUT_MS);

          const res = await fetch(`${API_BASE}/api/v1/query/stream`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
              query,
              query_id: queryId,
              thread_id: useAIMStore.getState().threadId,
              reasoning_depth: useAIMStore.getState().reasoningDepth,
            }),
            signal: abortRef.current!.signal,
          });

          clearTimeout(timeoutId);

          if (!res.ok) {
            const detail =
              res.status === 401
                ? "Invalid or missing API key."
                : res.status === 429
                  ? "Rate limit exceeded. Please wait and try again."
                  : res.status === 403
                    ? "Access denied — thread belongs to another session."
                    : `Server error (${res.status})`;

            // 4xx errors are not retryable (except 429)
            if (res.status >= 400 && res.status < 500 && res.status !== 429) {
              throw new Error(detail);
            }

            // 429 and 5xx are retryable
            lastAttemptError = detail;
            if (attempt < MAX_RETRIES) continue;
            throw new Error(detail);
          }

          if (!res.body) throw new Error("Empty response body");

          useAIMStore.getState().setStatus("streaming");
          useAIMStore.getState().setIsRetrying(false);

          const reader = res.body.getReader();
          const decoder = new TextDecoder();
          let buf = "";

          // ── Inactivity timeout: reconnect if the stream truly stalls ───

          /** Read with inactivity guard — Promise.race ensures the timeout
           *  fires even when reader.read() is blocking on a stalled stream. */
          const readWithTimeout = (): Promise<ReadableStreamReadResult<Uint8Array>> => {
            const timeout = new Promise<ReadableStreamReadResult<Uint8Array>>(
              (_, reject) =>
                setTimeout(
                  () => reject(new Error("__INACTIVITY__")),
                  INACTIVITY_TIMEOUT_MS,
                ),
            );
            return Promise.race([reader.read(), timeout]);
          };

          while (true) {
            let done: boolean;
            let value: Uint8Array | undefined;
            try {
              ({ done, value } = await readWithTimeout());
            } catch (inactivityErr) {
              if (
                inactivityErr instanceof Error &&
                inactivityErr.message === "__INACTIVITY__"
              ) {
                reader.cancel();
                lastAttemptError = "Stream stalled — no data received";
                break; // break inner loop, retry outer loop
              }
              throw inactivityErr;
            }
            if (done) break;
            buf += decoder.decode(value, { stream: true });
            const lines = buf.split("\n");
            buf = lines.pop() ?? "";

            for (const line of lines) {
              if (!line.startsWith("data: ")) continue;
              const raw = line.slice(6).trim();
              if (!raw) continue;

              let chunk: SSEChunk;
              try {
                chunk = JSON.parse(raw);
              } catch {
                continue;
              }

              const cur = useAIMStore.getState();

              switch (chunk.chunk_type) {
                case "sub_query":
                  cur.addSubQuery(chunk.content);
                  break;

                case "token":
                  if (!firstToken) {
                    cur.setLatency(Math.round(performance.now() - t0));
                    firstToken = true;
                  }
                  // Batch tokens via requestAnimationFrame
                  pendingTokensRef.current += chunk.content;
                  flushTokens(msgId);
                  break;

                case "error":
                  throw new Error(chunk.content || "Stream error");

                case "done": {
                  // Flush any remaining batched tokens
                  if (pendingTokensRef.current) {
                    cur.appendToMessage(msgId, pendingTokensRef.current);
                    pendingTokensRef.current = "";
                  }
                  if (chunk.cost_info) cur.setCostInfo(chunk.cost_info);
                  if (chunk.sources?.length) {
                    cur.setActiveSources(chunk.sources);
                    cur.setActiveSourceIndex(0);
                  }
                  if (chunk.provenance) {
                    cur.setProvenance(chunk.provenance);
                  }
                  cur.setSelectedSource(null);
                  cur.finalizeMessage(msgId, {
                    source: "AIM",
                    confidence: chunk.confidence,
                  });
                  cur.setStatus("idle");
                  cur.setRetryCount(0);
                  cur.setIsRetrying(false);
                  return; // success — exit retry loop
                }
              }
            }
          }

          // Stream ended without done chunk — retry if attempts remain
          if (attempt < MAX_RETRIES) {
            lastAttemptError = "Stream ended unexpectedly";
            continue; // retry
          }

          // Final attempt: finalize gracefully
          if (pendingTokensRef.current) {
            useAIMStore.getState().appendToMessage(
              msgId,
              pendingTokensRef.current
            );
            pendingTokensRef.current = "";
          }
          useAIMStore.getState().finalizeMessage(msgId, { source: "AIM" });
          useAIMStore.getState().setStatus("idle");
          useAIMStore.getState().setRetryCount(0);
          useAIMStore.getState().setIsRetrying(false);
          return;
        } catch (err: unknown) {
          if (err instanceof Error && err.name === "AbortError") {
            // Distinguish timeout-abort from user-abort
            if (attempt < MAX_RETRIES) {
              lastAttemptError = "Request timed out";
              // Reset abort controller for retry
              abortRef.current = new AbortController();
              continue;
            }
            return; // user abort
          }

          // Non-retryable error or final attempt
          if (attempt >= MAX_RETRIES || (err instanceof Error && !isRetryable(err))) {
            const msg =
              err instanceof Error ? err.message : "An unexpected error occurred";
            const cur = useAIMStore.getState();

            // Flush any batched tokens
            if (pendingTokensRef.current) {
              cur.appendToMessage(msgId, pendingTokensRef.current);
              pendingTokensRef.current = "";
            }

            const assistantMsg = cur.messages.find((m) => m.id === msgId);
            if (assistantMsg && !assistantMsg.content) {
              cur.appendToMessage(msgId, msg);
              cur.finalizeMessage(msgId, { source: "Error" });
            } else {
              cur.finalizeMessage(msgId);
              cur.addMessage({
                role: "assistant",
                content: msg,
                source: "Error",
              });
            }

            cur.setStatus("error");
            cur.setRetryCount(0);
            cur.setIsRetrying(false);
            setTimeout(
              () => useAIMStore.getState().setStatus("idle"),
              4000
            );
            return;
          }

          lastAttemptError =
            err instanceof Error ? err.message : "Unknown error";
        }
      }
    },
    [flushTokens]
  );

  const abort = useCallback(() => {
    abortRef.current?.abort();
    if (rafRef.current !== null) cancelAnimationFrame(rafRef.current);
    pendingTokensRef.current = "";
    const cur = useAIMStore.getState();
    cur.setStatus("idle");
    cur.setRetryCount(0);
    cur.setIsRetrying(false);
  }, []);

  return { submit, abort };
}

/** Determine if an error is worth retrying. */
function isRetryable(err: Error): boolean {
  const msg = err.message.toLowerCase();
  // Don't retry auth, forbidden, or validation errors
  if (msg.includes("api key") || msg.includes("access denied")) return false;
  // Retry network errors, timeouts, server errors
  return true;
}
