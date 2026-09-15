# Policy repository connector

V8D includes exactly one enterprise connector: an opt-in, read-only HTTPS adapter for a policy
repository. An authenticated `admin` explicitly calls
`POST /api/v1/connectors/policy-repository/sync`; there is no background polling and no upstream
write capability.

The configured endpoint is `POLICY_REPOSITORY_BASE_URL` plus
`POLICY_REPOSITORY_DOCUMENTS_PATH`. It must return:

```json
{
  "documents": [
    {
      "external_id": "POL-001",
      "title": "Data Handling Policy",
      "content": "Approved policy text...",
      "source_uri": "https://policies.example.com/POL-001",
      "updated_at": "2026-09-01T12:00:00Z",
      "metadata": {"classification": "internal"}
    }
  ]
}
```

Responses, document count, content, metadata, timeouts, and redirects are bounded. Production
requires HTTPS. The bearer token is injected as a secret, never persisted, returned, or logged.
Fetched text is labeled untrusted evidence, deduplicated, normalized, chunked, embedded, and
stored through the existing V3 pipeline. Optional `enrich_graph=true` reuses V6 GraphRAG
enrichment; individual graph failures degrade explicitly without deleting successfully ingested
documents. Provenance records connector type, repository host, external ID/URI, and upstream
timestamp.

MCP is intentionally deferred. This integration exposes one static read operation with a
configured origin and permission; a separate MCP server would expand deployment and trust surface
without improving the present permission model. Revisit MCP only if several tools/resources,
cross-client discovery, or standardized delegated authorization become real requirements.
