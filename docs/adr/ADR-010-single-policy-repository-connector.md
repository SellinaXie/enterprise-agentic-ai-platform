# ADR-010: One read-only policy repository connector

Status: Accepted

Demonstrate enterprise integration with one configured HTTPS pull adapter. Admins trigger bounded
syncs; the adapter cannot write upstream and delegates all content processing to the existing
ingestion and optional graph services. This constrains credentials, SSRF surface, formats, and
failure modes while preserving useful provenance.

Do not add Google Drive, SharePoint, or a generic connector framework in V8D. MCP is deferred
because one static read operation does not justify another server/protocol boundary.
