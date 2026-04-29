# Security Notes

AIM is designed for private, internal knowledge. Treat any deployment as
security-sensitive.

## Before Publishing This Repo

- Do not commit `.env`, `.env.local`, API keys, Slack tokens, Neo4j passwords, or
  tunnel URLs.
- Rotate any token that has appeared in local logs or screenshots.
- Keep `APP_ENV=production`, `DEBUG=false`, explicit `CORS_ORIGINS`, and
  non-empty `API_KEYS` for any public deployment.
- Use `WEB_CONCURRENCY=1` per process. Scale with multiple single-worker
  instances behind a load balancer.

## Current Security Posture

Implemented:

- Slack webhook HMAC verification.
- API-key auth with constant-time comparisons.
- Tenant-key hashing for conversation ownership.
- Data classification and access-control helper layers.
- Optional field-level encryption for selected graph properties.
- Redis-backed rate limiting with in-memory fallback.
- Exact incident abstention when graph evidence is missing.

Not complete:

- No full prompt-injection red-team corpus yet.
- No ingest-time PII redaction pass yet.
- Jira/Confluence integrations are not production-hardened.
- No external penetration test or formal audit.

## Reporting

This is currently a portfolio/research project. 

