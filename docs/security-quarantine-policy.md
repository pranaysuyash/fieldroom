# Security and quarantine policy (local upload path)

Date: 2026-10-14
Scope: the local browser/server upload and session lifecycle. This is the
FFL-SEC-010 remainder: quarantine policy, operator-visible rejection audit,
and storage lifecycle enforcement. It is not a production-boundary document —
authentication, rate limiting, and multi-tenant isolation remain open
(register: Security/privacy/operational gates).

## Rejection and quarantine layers (in upload order)

Every layer fails closed: a rejection creates no session, and the session
directory is removed before the error reaches the operator. Every rejection is
recorded in the shared audit ledger before the operator sees it.

1. **Type and size gates (413/415).** `.pdf` extension, `%PDF` magic prefix,
   and `PDF_FIELD_LAB_MAX_UPLOAD_BYTES`. No quarantine; bytes are never
   persisted for these.
2. **Structural scan (422).** `qpdf --check` when the binary is present. When
   absent, `security.qpdf` reports `not-configured` in the session payload —
   an absent check is visible, never silently skipped.
3. **Local malware scan (422, kind `malware-rejected`).** `clamscan`/
   `clamdscan` when present; same `not-configured` visibility rule. A scanner
   pass is a local scan receipt, not a malware-absence guarantee.
4. **Encrypted uploads (422, kind `upload-encrypted`).** Password-protected
   PDFs are rejected explicitly. PyMuPDF can silently open encrypted files
   with blank content, so the explicit check prevents a false-success
   session built on invisible pages.
5. **Active-content quarantine (422, kind `upload-quarantined`).** Presence
   (detection only — nothing is executed or extracted) of any of:
   - document-level JavaScript (`/Names /JavaScript`)
   - open actions (`/OpenAction`)
   - embedded files (`/Names /EmbeddedFiles`)
   - XFA (`/AcroForm /XFA`)
   The detail message names the categories found. XFA is quarantined
   deliberately even though AcroForm coexistence is a known open question
   (FFL-NAT-003): until a coexistence fixture proves safe handling, fail-closed
   is the honest default. Relaxing it is a registered owner decision.
6. **Analysis gates (413/422).** Zero-page documents, page-count limit, and
   any analysis failure (kind `analysis-failed`, detail truncated to 300
   characters).

## Audit ledger

All rejections, expiries, and vanished-storage events append one JSON line to
`<session root>/rejections.jsonl`:

```
{"recorded_at": "<ISO-8601 UTC>", "kind": "...", "status": <int>,
 "detail": "...", "filename": "..." | null, "session_id": "..." | null}
```

Kinds: `upload-rejected`, `upload-quarantined`, `upload-encrypted`,
`malware-rejected`, `structural-scan-failed`, `analysis-failed`,
`session-expired`, `session-storage-vanished`.

The ledger lives outside per-session directories on purpose: the rejection
paths delete the session directory, and the record must survive that. Write
failures are swallowed so the ledger can never mask the operator-facing
error. The ledger is local-only and inherits the session root's lifetime
(temp directory); it contains filenames and rejection reasons, never source
bytes or extracted values (sensitive-logging rule).

## Session storage lifecycle

- Sessions live in the OS temp directory under `pdf-field-lab-sessions`, one
  UUID-named directory per session (`source.pdf`, `analysis.json`,
  `editable.pdf`, page renders, manifest, review candidates/receipts, export
  receipts).
- TTL sweep (`PDF_FIELD_LAB_SESSION_TTL_SECONDS`) runs at process start, on
  every `/health` call, and on every session creation. Sweeps only remove
  UUID-shaped directories the app owns. Each expiry is audited.
- A session whose directory disappears (OS temp cleaner) fails with an
  explicit `404 session storage expired` and is audited, instead of raising
  unhandled filesystem errors.
- **Durability boundary:** sessions are ephemeral by design for the local
  lab; a process restart loses them. Moving to durable storage (permissioned,
  encrypted, deletion-correct) is a registered owner decision before any
  release-facing work.

## Explicit non-goals

- No claim that quarantine equals a malware verdict; it is an active-content
  policy gate with a visible scanner status.
- No production boundary: authentication, rate limiting, concurrency limits,
  and monitoring are out of scope here and stay on the register.
- No source bytes, extracted personal values, photos, or signatures in the
  ledger or any log (sensitive-logging rule).
