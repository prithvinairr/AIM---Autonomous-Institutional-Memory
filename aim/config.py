from __future__ import annotations

from functools import lru_cache

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # ── App ───────────────────────────────────────────────────────────────────
    app_name: str = "AIM – Autonomous Institutional Memory"
    app_version: str = "0.2.0"
    app_env: str = "development"
    debug: bool = False
    log_level: str = "INFO"

    # ── Auth & Rate limiting ──────────────────────────────────────────────────
    # Comma-separated list of valid API keys. Empty = open (dev mode).
    api_keys: list[str] = Field(default_factory=list)
    rate_limit_per_minute: int = Field(default=60, ge=1, le=10_000)

    # ── Multi-tenancy ────────────────────────────────────────────────────────
    # When True, all graph queries are scoped to the caller's tenant_id
    # (derived from API key hash). Entities must carry a tenant_id property.
    multi_tenant: bool = False

    # ── Field-level encryption ───────────────────────────────────────────────
    # Fernet key (base64-encoded 32 bytes). Generate with:
    #   python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
    # When empty, encryption is disabled (dev mode).
    encryption_key: str = ""
    # Rotation support: newest key first. When non-empty this overrides
    # ``encryption_key``. Encryption always uses ``encryption_keys[0]``;
    # decryption tries each key in order so ciphertext written under a
    # retiring key still reads during the rotation window.
    encryption_keys: list[str] = Field(default_factory=list)
    # Comma-separated list of entity property names to encrypt before Neo4j write.
    # Example: "email,ssn,api_token"
    encrypted_fields: list[str] = Field(default_factory=list)

    # ── Cross-system entity resolution ────────────────────────────────────────
    # Rapidfuzz ``token_set_ratio`` threshold (0-100) for merging entities
    # across source types when their titles are not exactly equal.  Two titles
    # scoring ≥ this threshold collapse into a single ``ResolvedEntity`` with
    # all source_ids and source_types merged.  90 is a conservative default —
    # "Platform team" ↔ "platform-team" merges; "Platform" ↔ "Platform API"
    # does not.
    entity_merge_fuzzy_threshold: float = Field(default=90.0, ge=0.0, le=100.0)

    # ── CORS ──────────────────────────────────────────────────────────────────
    # Explicit list of allowed origins for the frontend. In debug mode, ["*"]
    # is used if this is empty. In production, this must be set explicitly.
    # Example: "https://app.yourcompany.com,http://localhost:3000"
    cors_origins: list[str] = Field(default_factory=list)

    # ── Neo4j ─────────────────────────────────────────────────────────────────
    neo4j_uri: str = "bolt://localhost:7687"
    neo4j_user: str = "neo4j"
    neo4j_password: str = ""
    neo4j_database: str = "neo4j"

    # ── Vector DB ────────────────────────────────────────────────────────────
    # "qdrant" (default — local-first, private-mesh compatible), "pinecone"
    # (cloud, requires API key), or "local" (alias for qdrant).
    # Default flipped from "pinecone" to "qdrant" post-δ.3 so the sovereignty
    # story is structural: fresh deployments use a local vector store and do
    # NOT leak embeddings to Pinecone unless an operator explicitly opts in.
    # Qdrant URL defaults to ``http://localhost:6333`` in the factory when
    # ``vector_db_url`` is empty — works out of the box with a local Qdrant
    # container (``docker run -p 6333:6333 qdrant/qdrant``).
    vector_db_provider: str = "qdrant"
    vector_db_url: str = ""  # for qdrant/local providers
    pinecone_api_key: str = ""
    pinecone_index_name: str = "aim-knowledge"
    pinecone_environment: str = "us-east-1"
    pinecone_namespace: str = "default"
    embedding_dimension: int = 1536

    # ── LLM Provider ─────────────────────────────────────────────────────────
    # "local" (default — any OpenAI-compatible server, e.g. Ollama / vLLM /
    #     llama.cpp — answers never leave your infra), "anthropic", "openai".
    # Default flipped from "anthropic" to "local" in Phase δ.2 (panel audit
    # 2026-04-18) so the sovereignty story is structural, not guarded:
    # *the default deployment cannot leak answers to an external provider*
    # unless an operator explicitly flips this knob. External API keys
    # become opt-in, not required.
    llm_provider: str = "local"
    # Base URL for OpenAI-compatible endpoints. Ollama's local default
    # matches the embedding sovereignty default so a fresh deployment
    # with Ollama running locally works out of the box.
    llm_base_url: str = "http://localhost:11434/v1"
    anthropic_api_key: str = ""
    llm_model: str = "claude-opus-4-6"
    llm_temperature: float = Field(default=0.1, ge=0.0, le=2.0)
    llm_max_tokens: int = Field(default=4096, ge=100, le=32_768)

    # ── Embeddings ────────────────────────────────────────────────────────────
    # "local" (default — any OpenAI-compatible embedding server e.g. Ollama)
    # or "openai" (requires OPENAI_API_KEY — data leaves your infra).
    # Default flipped to "local" to make the sovereignty story structural
    # rather than guarded: embeddings cannot leak to OpenAI unless an
    # operator explicitly opts in.
    embedding_provider: str = "local"
    # Base URL for local embedding server. Defaults to the Ollama standard
    # port — works out of the box for the common dev setup. Operators on
    # vLLM, llama.cpp, LM Studio, etc. override this env var.
    embedding_base_url: str = "http://localhost:11434/v1"
    openai_api_key: str = ""
    embedding_model: str = "text-embedding-3-small"
    embedding_cache_size: int = Field(default=2000, ge=100)

    # ── Entity Extraction ────────────────────────────────────────────────────
    # When True, MCP-fetched text is auto-extracted into the graph during queries.
    auto_extract_from_mcp: bool = False
    # Minimum LLM confidence to accept an extracted entity/relationship.
    extraction_confidence_threshold: float = Field(default=0.7, ge=0.0, le=1.0)
    # Restrict extraction to these entity types (empty = all known types).
    extraction_entity_types: list[str] = Field(default_factory=list)
    # δ.1: When True, the ingest worker augments every extracted batch with
    # derived MENTIONS edges via ``derive_mentions`` — the same pass the
    # seed worker runs. Closes the audit gap where live-ingested docs
    # landed as leaf nodes with no cross-references.
    live_ingestion_augment_mentions: bool = True
    # δ.2: When True (default), the ingest worker additionally reads a
    # bounded snapshot of the pre-existing corpus from Neo4j and runs
    # ``derive_mentions`` over union(snapshot, batch). Emitted edges must
    # touch at least one newly-extracted entity — edges between two
    # pre-existing entities are already someone else's responsibility.
    # Makes a Slack message that references an already-ingested Jira ticket
    # get a real MENTIONS edge instead of a leaf-node miss.
    # Flip to False when the corpus outgrows
    # ``ingestion_cross_corpus_snapshot_limit`` and you need a periodic
    # sweep rather than per-event reads.
    live_ingestion_cross_corpus_mentions: bool = True
    ingestion_cross_corpus_snapshot_limit: int = Field(default=10_000, ge=100, le=100_000)
    # Webhook shared secrets for signature verification.
    webhook_slack_signing_secret: str = ""
    webhook_jira_secret: str = ""
    webhook_confluence_secret: str = ""

    # ── MCP ───────────────────────────────────────────────────────────────────
    # "live" = call external APIs (Slack, Jira); "indexed" = read from local store
    mcp_mode: str = "live"
    # Transport used to reach MCP servers.
    #   "stdio"   = spawn MCP server subprocess, speak JSON-RPC 2.0 over stdio
    #               (the reference MCP spec transport — default).
    #   "jsonrpc" = JSON-RPC 2.0 over HTTP.
    #   "native"  = legacy REST endpoints (for backends that predate MCP).
    mcp_transport: str = "stdio"

    # ── MCP Ingest ───────────────────────────────────────────────────────────
    # Polling interval for MCP streaming ingest worker (seconds).
    mcp_ingest_interval_seconds: int = Field(default=300, ge=30, le=3600)
    # Enable the MCP ingest worker on startup.
    mcp_ingest_enabled: bool = False

    # ── Slack MCP ─────────────────────────────────────────────────────────────
    slack_bot_token: str = ""
    slack_app_token: str = ""
    slack_default_channels: list[str] = Field(default=["general"])

    # ── Jira MCP ──────────────────────────────────────────────────────────────
    jira_base_url: str = ""
    jira_email: str = ""
    jira_api_token: str = ""
    jira_default_projects: list[str] = Field(default=["ENG"])

    # ── Redis ─────────────────────────────────────────────────────────────────
    redis_url: str = "redis://localhost:6379"

    # ── Conversations ─────────────────────────────────────────────────────────
    # Number of past turns injected into the decomposer + synthesizer context.
    # Each turn = 1 user message + 1 assistant message.
    conversation_max_turns: int = Field(default=10, ge=1, le=50)
    # How long conversation threads are retained in Redis.
    conversation_ttl_seconds: int = Field(default=604800, ge=3600, le=7_776_000)  # 7d, max 90d

    # ── Observability ─────────────────────────────────────────────────────────
    otlp_endpoint: str = ""  # e.g. "http://jaeger:4317"

    # ── Timeouts (seconds) ────────────────────────────────────────────────────
    route_timeout_seconds: float = Field(default=60.0, ge=5.0, le=600.0)
    node_timeout_seconds: float = Field(default=20.0, ge=2.0, le=300.0)
    neo4j_query_timeout_seconds: float = Field(default=10.0, ge=1.0, le=120.0)
    mcp_provider_timeout_seconds: float = Field(default=15.0, ge=2.0, le=300.0)
    mcp_handler_timeout_seconds: float = Field(default=25.0, ge=5.0, le=600.0)

    # ── Circuit breakers ──────────────────────────────────────────────────────
    circuit_breaker_threshold: int = Field(default=5, ge=1)
    circuit_breaker_reset_seconds: float = Field(default=60.0, ge=10.0, le=3600.0)

    # ── RAG Tuning ────────────────────────────────────────────────────────────
    max_sub_queries: int = Field(default=5, ge=1, le=10)
    top_k_vectors: int = Field(default=10, ge=1, le=50)
    graph_search_depth: int = Field(default=2, ge=1, le=5)
    graph_hub_degree_limit: int = Field(default=25, ge=5, le=100)
    similarity_threshold: float = Field(default=0.75, ge=0.0, le=1.0)
    # Use hybrid (fulltext + vector) entity search against Neo4j. Activates
    # the entity_embedding_idx. When False, fulltext-only search is used.
    graph_use_hybrid_search: bool = True
    # Automatically find paths between top-ranked entities, not just those
    # the decomposer extracted as entity_pairs. Surfaces causal chains.
    graph_proactive_paths: bool = True
    # Multi-hop teacher expansion: after normal graph search, run a bounded
    # unfiltered 2-hop BFS from the top seed and use those nodes as candidate
    # evidence. This separates recall expansion from synthesis and lifted the
    # A.2 multi-hop NDCG above graph_only in local eval.
    graph_teacher_bfs_enabled: bool = True
    graph_teacher_bfs_limit: int = Field(default=20, ge=1, le=100)

    # ── Phase 10: query-conditioned path scoring ─────────────────────────────
    # Edge score = α·query_affinity + β·feedback_weight + γ·inverse_degree.
    # Defaults (0, 1, 0) are behaviour-equivalent to the pre-Phase-10 mean
    # of feedback-adjusted rel_type weights — flag-off the module is a no-op.
    # Must sum to 1.0 (validated at construction by PathScoringWeights).
    graph_edge_query_weight: float = Field(default=0.0, ge=0.0, le=1.0)
    graph_edge_feedback_weight: float = Field(default=1.0, ge=0.0, le=1.0)
    graph_edge_degree_weight: float = Field(default=0.0, ge=0.0, le=1.0)
    # "mean" (robust) or "product" (penalises weak links). Pre-Phase-10
    # behaviour is "mean", so that stays the default.
    graph_path_aggregation: str = "mean"

    # ── Reasoning loop ────────────────────────────────────────────────────────
    # Maximum evaluation reloops (1 = original + 1 retry; 4 = up to 5 passes).
    max_reasoning_loops: int = Field(default=3, ge=1, le=5)
    # Minimum evaluation score to accept without re-searching.
    reloop_threshold: float = Field(default=0.50, ge=0.0, le=1.0)

    # Maximum concurrent LLM calls per process — prevents API quota exhaustion.
    max_concurrent_llm_calls: int = Field(default=10, ge=1, le=100)

    # ── Synthesis mode ────────────────────────────────────────────────────────
    # "graph_aware" (default, Phase β — typed subgraph block with stable
    #    n-IDs + edges-by-id + edge-path citations).
    # "flat" (legacy escape hatch — bullets + path-chains). Kept for operators
    #    who need byte-compat output formatting; flipped δ.2 after the flag
    #    had baked in production for a full rev.
    synthesis_mode: str = "graph_aware"

    # ── Retrieval fusion ──────────────────────────────────────────────────────
    # "graph_reranks_vector" (default, Phase γ.1/δ.3 — after both retrievals
    #    complete, vector snippets whose metadata.entity_id matches a
    #    graph-retrieved entity get an additive score boost, and the snippet
    #    list is re-sorted by fused_score). Behaviourally equivalent when the
    #    two retrievers disagree entirely; rises where they agree. Default
    #    flipped in δ.3 so graph-structural evidence reshapes the vector
    #    ranking in the default runtime — not just when opted in.
    # "parallel" (legacy escape hatch — graph and vector run as independent
    #    siblings; their outputs are concatenated in the synthesizer context).
    #    Kept for operators who want byte-compat scoring or who've benchmarked
    #    parallel higher on their corpus.
    retrieval_fusion_mode: str = "graph_reranks_vector"
    # Additive boost applied to a vector snippet when the graph corroborates
    # it. 0.15 keeps the boost meaningful without steamrolling raw similarity;
    # tune per-corpus by running eval with different values.
    retrieval_fusion_boost: float = Field(default=0.15, ge=0.0, le=1.0)

    # ── Branch-and-select reasoning ───────────────────────────────────────────
    # Number of independent retrieval branches to fan out per sub-query
    # before selecting the best-scoring answer (tree-of-thought pattern).
    # ``1`` is zero-cost — the legacy linear pipeline.
    # ``2`` (default, flipped post-δ.3) fans out hybrid + graph_only so
    # the tree-of-thought feature actually fires for every query instead
    # of being a dark-by-default flag. Doubles retrieval cost but the
    # evaluator's heuristic scoring means no extra LLM calls unless
    # ``evaluator_mode`` is flipped to ``llm``/``hybrid``/``llm_tiebreaker``.
    # ``3`` adds vector_only as a third branch — use when branch diversity
    # is more valuable than cost. Scoring / selection primitives live in
    # aim/agents/branch_selector.py; fan-out wiring is gated by this knob.
    reasoning_branch_count: int = Field(default=2, ge=1, le=3)

    # ── Evaluator mode ────────────────────────────────────────────────────────
    # "heuristic" (default, zero LLM cost), "llm" (LLM-based), "hybrid" (both),
    # or "llm_tiebreaker" (δ.3 Move 3 — heuristic scores branches; LLM only
    # fires when the top-two heuristic spread is below
    # ``evaluator_llm_tiebreaker_threshold``, so the LLM cost is near-zero
    # when one branch clearly wins but available to break genuine ties).
    evaluator_mode: str = "heuristic"
    # In hybrid mode: below this, always reloop without LLM; above, always pass.
    evaluator_llm_threshold_low: float = Field(default=0.35, ge=0.0, le=1.0)
    evaluator_llm_threshold_high: float = Field(default=0.65, ge=0.0, le=1.0)
    # Branch-selection tiebreaker threshold (llm_tiebreaker mode only).
    # When max(heuristic_scores) - runner_up < this value, an LLM judge
    # is asked to pick between the top candidates. Default 0.1 — in a
    # 3-branch fan-out, a 0.1 spread is the "too close to call" zone.
    evaluator_llm_tiebreaker_threshold: float = Field(default=0.1, ge=0.0, le=1.0)

    # ── Re-ranking ────────────────────────────────────────────────────────────
    # "cross_encoder" (learned), "llm" (LLM-based), or "none" (title-based only)
    reranker_provider: str = "cross_encoder"
    reranker_model: str = "cross-encoder/ms-marco-MiniLM-L-6-v2"
    reranker_top_k: int = Field(default=15, ge=5, le=50)

    # ── Cache ─────────────────────────────────────────────────────────────────
    response_cache_ttl_seconds: int = Field(default=3600, ge=60, le=86_400)
    response_cache_max_size: int = Field(default=500, ge=10, le=10_000)
    # How long user feedback is retained in Redis.
    feedback_ttl_seconds: int = Field(default=7_776_000, ge=3600, le=31_536_000)  # max 1yr

    # ── Data sovereignty ─────────────────────────────────────────────────────
    # "off" = no enforcement; "audit" = log only; "strict" = block violations
    # Default is "strict" — classified data is blocked from external LLMs,
    # with automatic reroute to the configured local provider when
    # ``sovereignty_fallback_to_local=True`` and ``llm_base_url`` is set.
    # Override to "audit" for log-only or "off" during early development.
    sovereignty_mode: str = "strict"
    # Classification levels allowed to be sent to external LLM providers.
    # Only relevant in "audit" or "strict" mode.
    sovereignty_allowed_classifications: list[str] = Field(
        default_factory=lambda: ["PUBLIC", "INTERNAL"]
    )
    # Provider names considered external (traffic leaves your network).
    external_llm_providers: list[str] = Field(
        default_factory=lambda: ["anthropic", "openai"]
    )

    # ── Classification-aware routing ─────────────────────────────────────────
    # When sovereignty_mode is "strict" and data is classified above the
    # allowed level, route to a local LLM instead of blocking entirely.
    # Requires llm_provider=local + llm_base_url configured.
    sovereignty_fallback_to_local: bool = True
    # Encrypt cached responses at rest in Redis using the Fernet key.
    # Prevents PII/sensitive data from being readable if Redis is compromised.
    cache_encryption_enabled: bool = True

    # ── Data classification ───────────────────────────────────────────────────
    # Fields that are RESTRICTED (never sent to LLM — PII, secrets, credentials).
    restricted_fields: list[str] = Field(
        default_factory=lambda: ["ssn", "api_token", "password", "secret", "private_key"]
    )
    # Fields that are CONFIDENTIAL (sent only if llm_max_data_classification allows).
    confidential_fields: list[str] = Field(
        default_factory=lambda: ["email", "phone", "salary", "address"]
    )
    # Maximum data classification level allowed in LLM context window.
    # "public", "internal", "confidential", "restricted"
    llm_max_data_classification: str = "internal"

    # Semantic classifier runs as a second pass after regex. Off by default:
    # turning it on pulls in a non-trivial ML dependency (Presidio / DeBERTa).
    # When off, ``classify_text`` is regex-only and behaviourally identical to
    # the pre-Phase-11 pipeline.
    semantic_classifier_enabled: bool = False

    # ── Audit logging ─────────────────────────────────────────────────────────
    audit_log_enabled: bool = True
    audit_log_ttl_seconds: int = Field(default=2_592_000, ge=3600, le=31_536_000)  # 30d

    # ── Request limits ────────────────────────────────────────────────────────
    max_request_body_bytes: int = Field(default=2_097_152, ge=1024, le=52_428_800)  # max 50 MiB

    # ── Pricing (USD per token, approximate list prices) ──────────────────────
    # Override these when Anthropic or OpenAI change pricing.
    llm_input_cost_per_mtok: float = Field(default=15.0, ge=0.0)   # $/1M input
    llm_output_cost_per_mtok: float = Field(default=75.0, ge=0.0)  # $/1M output
    embedding_cost_per_mtok: float = Field(default=0.02, ge=0.0)   # $/1M tokens

    # ── Validators ────────────────────────────────────────────────────────────

    @field_validator("llm_provider")
    @classmethod
    def _validate_llm_provider(cls, v: str) -> str:
        valid = {"anthropic", "openai", "local"}
        if v not in valid:
            raise ValueError(f"llm_provider must be one of {valid}")
        return v

    @field_validator("embedding_provider")
    @classmethod
    def _validate_embedding_provider(cls, v: str) -> str:
        valid = {"openai", "local"}
        if v not in valid:
            raise ValueError(f"embedding_provider must be one of {valid}")
        return v

    @field_validator("vector_db_provider")
    @classmethod
    def _validate_vector_db_provider(cls, v: str) -> str:
        valid = {"pinecone", "qdrant", "local"}
        if v not in valid:
            raise ValueError(f"vector_db_provider must be one of {valid}")
        return v

    @field_validator("mcp_mode")
    @classmethod
    def _validate_mcp_mode(cls, v: str) -> str:
        valid = {"live", "indexed"}
        if v not in valid:
            raise ValueError(f"mcp_mode must be one of {valid}")
        return v

    @field_validator("mcp_transport")
    @classmethod
    def _validate_mcp_transport(cls, v: str) -> str:
        # Phase 13: ``native`` was soft-deprecated in the prior pass and is
        # now rejected at validation time. It bypassed the MCP JSON-RPC
        # handshake and dispatched through provider-native REST calls —
        # safe in isolation but off-spec. Operators who still have it
        # pinned must migrate to ``stdio`` (default) or ``jsonrpc``
        # (reserved for the future HTTP client).
        valid = {"jsonrpc", "stdio"}
        if v not in valid:
            raise ValueError(f"mcp_transport must be one of {valid}")
        return v

    @field_validator("sovereignty_mode")
    @classmethod
    def _validate_sovereignty_mode(cls, v: str) -> str:
        valid = {"off", "audit", "strict"}
        if v not in valid:
            raise ValueError(f"sovereignty_mode must be one of {valid}")
        return v

    @field_validator("reranker_provider")
    @classmethod
    def _validate_reranker_provider(cls, v: str) -> str:
        valid = {"cross_encoder", "llm", "none"}
        if v not in valid:
            raise ValueError(f"reranker_provider must be one of {valid}")
        return v

    @field_validator("synthesis_mode")
    @classmethod
    def _validate_synthesis_mode(cls, v: str) -> str:
        valid = {"flat", "graph_aware"}
        if v not in valid:
            raise ValueError(f"synthesis_mode must be one of {valid}")
        return v

    @field_validator("evaluator_mode")
    @classmethod
    def _validate_evaluator_mode(cls, v: str) -> str:
        # δ.3 Move 3: "llm_tiebreaker" added — heuristic-first branch
        # selection with LLM judge only when top-two are within
        # ``evaluator_llm_tiebreaker_threshold``.
        valid = {"heuristic", "llm", "hybrid", "llm_tiebreaker"}
        if v not in valid:
            raise ValueError(f"evaluator_mode must be one of {valid}")
        return v

    @field_validator("retrieval_fusion_mode")
    @classmethod
    def _validate_retrieval_fusion_mode(cls, v: str) -> str:
        valid = {"parallel", "graph_reranks_vector"}
        if v not in valid:
            raise ValueError(f"retrieval_fusion_mode must be one of {valid}")
        return v

    @field_validator("llm_max_data_classification")
    @classmethod
    def _validate_data_classification(cls, v: str) -> str:
        valid = {"public", "internal", "confidential", "restricted"}
        if v not in valid:
            raise ValueError(f"llm_max_data_classification must be one of {valid}")
        return v

    @field_validator("log_level")
    @classmethod
    def _validate_log_level(cls, v: str) -> str:
        valid = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
        upper = v.upper()
        if upper not in valid:
            raise ValueError(f"log_level must be one of {valid}")
        return upper

    @field_validator("app_env")
    @classmethod
    def _validate_app_env(cls, v: str) -> str:
        valid = {"development", "staging", "production"}
        if v not in valid:
            raise ValueError(f"app_env must be one of {valid}")
        return v

    @model_validator(mode="after")
    def _apply_local_provider_smart_defaults(self) -> "Settings":
        """Snap model names to Ollama-friendly values when the operator hasn't
        overridden them and the provider is ``local``.

        Rationale: the sovereign-default deployment path
        (``LLM_PROVIDER=local``, ``EMBEDDING_PROVIDER=local``) points at
        Ollama by default, but the ``llm_model`` / ``embedding_model``
        / ``embedding_dimension`` defaults are tuned for the external
        providers (Anthropic / OpenAI). On a fresh Ollama install those
        names are not pullable — the first request 404s.

        This validator rewrites the defaults in place *only* when the
        fields still match the external sentinel values, so explicit
        overrides are never clobbered. Models chosen:

        * ``llama3.2`` — general-purpose 3B chat model, one
          ``ollama pull llama3.2`` away.
        * ``nomic-embed-text`` — 768-dim embedding model, the standard
          Ollama embedder; dimension is flipped to match.

        Operators on a bigger rig override via ``LLM_MODEL=llama3.3:70b``
        or similar and both knobs are respected.
        """
        if self.llm_provider == "local" and self.llm_model == "claude-opus-4-6":
            self.llm_model = "llama3.2"
        if (
            self.embedding_provider == "local"
            and self.embedding_model == "text-embedding-3-small"
        ):
            self.embedding_model = "nomic-embed-text"
            if self.embedding_dimension == 1536:
                self.embedding_dimension = 768
        return self

    @model_validator(mode="after")
    def _check_embedding_base_url(self) -> "Settings":
        # Fail at config-load time rather than at first query. The same
        # check previously lived inside ``get_embedding_provider`` where
        # it would only fire once a request reached the vector retriever.
        if self.embedding_provider == "local" and not self.embedding_base_url:
            raise ValueError(
                "embedding_provider='local' requires EMBEDDING_BASE_URL "
                "(e.g. http://localhost:11434/v1 for Ollama). This is the "
                "sovereign default — set openai explicitly if you want "
                "embeddings to leave your infra."
            )
        return self

    @model_validator(mode="after")
    def _check_required_credentials(self) -> "Settings":
        missing: list[str] = []
        # LLM credentials: only required for external providers
        if self.llm_provider == "anthropic" and not self.anthropic_api_key:
            missing.append("ANTHROPIC_API_KEY")
        if self.llm_provider == "openai" and not self.openai_api_key:
            missing.append("OPENAI_API_KEY")
        if not self.neo4j_password:
            missing.append("NEO4J_PASSWORD")
        # Vector DB credentials: only required for cloud providers
        if self.vector_db_provider == "pinecone" and not self.pinecone_api_key:
            missing.append("PINECONE_API_KEY")
        # Embedding credentials: only required for cloud embedding provider
        if self.embedding_provider == "openai" and not self.openai_api_key and "OPENAI_API_KEY" not in missing:
            missing.append("OPENAI_API_KEY")
        if missing:
            msg = (
                f"AIM: missing credentials — {', '.join(missing)}. "
                "Affected features will be disabled."
            )
            if self.app_env == "production":
                raise ValueError(
                    f"{msg} In production, all credentials must be configured."
                )
            import warnings
            warnings.warn(msg, RuntimeWarning, stacklevel=2)
        return self

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"

    @property
    def effective_cors_origins(self) -> list[str]:
        """Resolve CORS origins: explicit list → debug wildcard → locked down."""
        if self.cors_origins:
            return self.cors_origins
        if self.debug:
            return ["*"]
        return []


@lru_cache
def get_settings() -> Settings:
    return Settings()
