/**
 * Tests for SSE Transport layer.
 */
import { describe, it, expect } from "vitest";

// ── SSE Chunk type validation tests ─────────────────────────────────────────

import type { SSEChunk, SourceSummary, CostInfo, ProvenanceData } from "@/types/aim";

describe("SSE Chunk Types", () => {
  it("validates sub_query chunk shape", () => {
    const chunk: SSEChunk = {
      chunk_type: "sub_query",
      content: "Who owns Auth Service?",
      query_id: "q-001",
      sequence: 1,
    };
    expect(chunk.chunk_type).toBe("sub_query");
    expect(chunk.content).toContain("Auth");
  });

  it("validates token chunk shape", () => {
    const chunk: SSEChunk = {
      chunk_type: "token",
      content: "The authentication",
      sequence: 5,
    };
    expect(chunk.chunk_type).toBe("token");
  });

  it("validates done chunk with provenance", () => {
    const prov: ProvenanceData = {
      overall_confidence: 0.92,
      citation_spans: [{ start: 0, end: 20, text: "The auth service..." }],
      resolved_entities: [
        { canonical_name: "Auth Service", source_ids: ["s1"], source_types: ["neo4j_graph"] },
      ],
      temporal_chain: [],
      sub_query_traces: [{
        sub_query_id: "sq1",
        sub_query_text: "Who owns Auth?",
        source_ids: ["s1"],
        graph_node_ids: ["e1"],
      }],
      reasoning_steps: ["Decomposed into 2 sub-queries", "Evaluation: score=0.85"],
    };

    const chunk: SSEChunk = {
      chunk_type: "done",
      content: "",
      confidence: 0.92,
      provenance: prov,
      sources: [{
        source_id: "s1",
        source_type: "neo4j_graph",
        title: "Auth Service",
        uri: "neo4j://entity/auth",
        confidence: 0.95,
        snippet: "Core authentication microservice",
      }],
    };

    expect(chunk.chunk_type).toBe("done");
    expect(chunk.provenance?.overall_confidence).toBe(0.92);
    expect(chunk.sources).toHaveLength(1);
  });

  it("validates error chunk", () => {
    const chunk: SSEChunk = {
      chunk_type: "error",
      content: "Query timeout after 60s",
    };
    expect(chunk.chunk_type).toBe("error");
    expect(chunk.content).toContain("timeout");
  });
});

describe("Source Summary", () => {
  it("validates source shape", () => {
    const source: SourceSummary = {
      source_id: "pinecone-001",
      source_type: "pinecone_vector",
      title: "Architecture Decision Record",
      uri: "https://confluence.company.com/adr-001",
      confidence: 0.87,
      snippet: "We decided to migrate to event-driven...",
    };
    expect(source.confidence).toBeGreaterThan(0.5);
    expect(source.confidence).toBeLessThanOrEqual(1.0);
  });
});

describe("Cost Info", () => {
  it("calculates reasonable cost range", () => {
    const cost: CostInfo = {
      input_tokens: 2500,
      output_tokens: 800,
      embedding_tokens: 150,
      estimated_cost_usd: 0.0385,
    };
    expect(cost.estimated_cost_usd).toBeGreaterThan(0);
    expect(cost.estimated_cost_usd).toBeLessThan(1.0);
    expect(cost.input_tokens + cost.output_tokens).toBeGreaterThan(0);
  });
});
