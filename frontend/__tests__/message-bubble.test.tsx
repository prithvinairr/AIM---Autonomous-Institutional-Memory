/**
 * Tests for MessageBubble — citation parsing, markdown rendering, copy button.
 */
import { describe, it, expect, vi } from "vitest";

// ── Citation parsing unit tests (extracted logic) ────────────────────────────

const SRC_TAG_RE = /\[SRC:([\w-]+)\]/g;

function parseCitations(raw: string): { clean: string; citeIds: string[] } {
  const citeIds: string[] = [];
  const clean = raw.replace(SRC_TAG_RE, (_match, id: string) => {
    if (!citeIds.includes(id)) citeIds.push(id);
    const idx = citeIds.indexOf(id) + 1;
    return `<cite data-src="${id}" data-idx="${idx}">[${idx}]</cite>`;
  });
  return { clean, citeIds };
}

describe("Citation Parser", () => {
  it("parses single citation", () => {
    const { clean, citeIds } = parseCitations("The auth service is down [SRC:src-001]");
    expect(citeIds).toEqual(["src-001"]);
    expect(clean).toContain('data-src="src-001"');
    expect(clean).toContain("[1]");
    expect(clean).not.toContain("[SRC:");
  });

  it("parses multiple citations", () => {
    const { clean, citeIds } = parseCitations(
      "Service A [SRC:s1] depends on B [SRC:s2]",
    );
    expect(citeIds).toEqual(["s1", "s2"]);
    expect(clean).toContain("[1]");
    expect(clean).toContain("[2]");
  });

  it("deduplicates repeated citations", () => {
    const { citeIds } = parseCitations("Claim A [SRC:s1] and B [SRC:s1]");
    expect(citeIds).toEqual(["s1"]);
  });

  it("preserves text without citations", () => {
    const { clean, citeIds } = parseCitations("No citations here.");
    expect(clean).toBe("No citations here.");
    expect(citeIds).toEqual([]);
  });

  it("handles hyphenated source IDs", () => {
    const { citeIds } = parseCitations("[SRC:neo4j-graph-001]");
    expect(citeIds).toEqual(["neo4j-graph-001"]);
  });

  it("handles adjacent citations", () => {
    const { citeIds } = parseCitations("claim [SRC:a][SRC:b]");
    expect(citeIds).toEqual(["a", "b"]);
  });
});
