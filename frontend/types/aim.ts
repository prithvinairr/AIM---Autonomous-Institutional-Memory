// ── Domain types aligned with the AIM backend schemas ───────────────────────

export type SystemStatus = "idle" | "thinking" | "streaming" | "error";
export type ReasoningDepth = "shallow" | "standard" | "deep";

export interface SourceSummary {
  source_id: string;
  source_type: string;
  title: string;
  uri: string;
  confidence: number;
  snippet: string;
}

export interface CostInfo {
  input_tokens: number;
  output_tokens: number;
  embedding_tokens: number;
  estimated_cost_usd: number;
}

/** Shape of each SSE `data:` payload from POST /api/v1/query/stream */
export interface SSEChunk {
  chunk_type: "sub_query" | "token" | "done" | "error" | "citation";
  content: string;
  query_id?: string;
  sequence?: number;
  request_id?: string;
  thread_id?: string;
  sources?: SourceSummary[];
  confidence?: number;
  cost_info?: CostInfo;
  provenance?: ProvenanceData;
}

export interface Message {
  id: number;
  role: "user" | "assistant";
  content: string;
  source?: string;
  isStreaming?: boolean;
  confidence?: number;
  timestamp: number;
}

export interface ThreadSummary {
  thread_id: string;
  last_query: string;
  turn_count: number;
  updated_at: string;
}

// ── Provenance types ────────────────────────────────────────────────────────

export interface CitationSpan {
  start: number;
  end: number;
  text: string;
}

export interface ResolvedEntity {
  canonical_name: string;
  source_ids: string[];
  source_types: string[];
}

export interface TemporalEvent {
  source_id: string;
  timestamp: string;
  summary: string;
  source_type: string;
}

export interface InstitutionalFact {
  fact_id: string;
  statement: string;
  subject_entity_id: string;
  predicate: string;
  object_entity_id: string;
  confidence: number;
  verification_status: string;
  truth_status: string;
  valid_from?: string | null;
  valid_until?: string | null;
  evidence_artifact_id?: string | null;
  evidence_uri?: string | null;
  support_source_ids: string[];
  contradicts_fact_ids: string[];
  authority_score: number;
  source_authority: string;
  winning_fact_id?: string | null;
  superseded_by_fact_id?: string | null;
  resolution_reason: string;
  stale: boolean;
}

export interface SubQueryTrace {
  sub_query_id: string;
  sub_query_text: string;
  source_ids: string[];
  graph_node_ids: string[];
}

export interface GraphNode {
  entity_id: string;
  entity_type: string;
  labels: string[];
  properties: Record<string, unknown>;
  relationship_path: string[];
}

/** A traversed Neo4j relationship — powers the 3D edge layer and causal-lineage view. */
export interface GraphProvenanceEdge {
  source_entity_id: string;
  target_entity_id: string;
  rel_type: string;
  /** Stable relationship identifier — cross-referenced against
   *  ProvenanceData.violating_edge_ids to paint inverted causal edges red. */
  rel_id?: string;
  properties?: Record<string, unknown>;
  confidence?: number;
}

export interface ProvenanceData {
  query_id?: string;
  overall_confidence: number;
  citation_coverage?: number;
  query_coverage?: number;
  sources?: Record<string, SourceSummary>;
  graph_nodes?: GraphNode[];
  /** Directed edges traversed during reasoning — authoritative input for the 3D graph. */
  graph_edges?: GraphProvenanceEdge[];
  /** Count of causal edges that failed timestamp direction integrity checks. */
  direction_violations?: number;
  /** rel_ids of edges flagged by the temporal integrity check — the 3D nebula
   *  highlights these in red so users can spot inverted causal claims. */
  violating_edge_ids?: string[];
  citation_map?: Record<string, string[]>;
  citation_spans: CitationSpan[];
  resolved_entities: ResolvedEntity[];
  temporal_chain: TemporalEvent[];
  institutional_facts?: InstitutionalFact[];
  sub_query_traces: SubQueryTrace[];
  reasoning_steps: string[];
}
