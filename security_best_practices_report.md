# Security and Ponytail Audit Report

## Executive summary

The repository is synchronized with `origin/main` (fast-forwarded from `c40410d` to `64caf29`) while preserving the local site-builder work. Open PR review found duplicate PRs and one unstable PR; they should not all be merged blindly. The local site-builder implementation contains a high-impact stored XSS risk and missing CSRF protection on state-changing admin routes.

## Critical / High findings

### SEC-001 — Stored XSS in generated sites (High)

**Location:** `src/pit_panel/web/routes/site_builder.py:99-118, 142-165`

Widget text, headings, URLs, image sources, alt text, and the HTML title are interpolated into generated HTML without escaping or protocol validation. An admin can persist payloads such as `<script>` or `javascript:` URLs; every visitor to the published site can execute attacker-controlled content. `_validate_tree()` only validates widget types and shape, not output safety.

**Fix:** HTML-escape text/attributes and allow only safe URL schemes (`https`, `http`, relative paths, and optionally `mailto` where intended). Add regression tests for text, attributes, title, and dangerous URLs.

### SEC-002 — CSRF middleware is origin-based, not token-based (Medium)

**Location:** `src/pit_panel/web/app.py:107-136`

The repository already has global CSRF protection for unsafe methods: it checks `Origin`/`Referer` and skips only explicit exemptions. The site-builder routes are therefore covered today; the original finding that they had no CSRF protection was incorrect. The remaining hardening opportunity is to add route-level tests proving that site-builder mutations reject cross-origin requests and to avoid expanding the exemption list.

**Fix:** Keep the existing shared middleware; add regression coverage rather than duplicating a token system in site-builder routes.

### SEC-003 — Unsafe static publish/delete path boundary (High)

**Location:** `site_builder.py:276-280, 328-330`; `caddy.py:109-131`

The publish directory is formed from a database-controlled `subdomain`, and deletion recursively removes `published_html_path.parent`. Current creation derives a constrained subdomain, but database values and future migrations are trust boundaries. The delete path should be resolved and checked to remain under `_PUBLISH_HTML_DIR` before `rmtree`; the Caddy root should receive the same canonical safe path.

**Fix:** centralize a path-safe helper using `Path.resolve()` plus `is_relative_to()` and reject invalid persisted subdomains before filesystem/Caddy operations.

## Medium findings

### SEC-004 — Session-cache PRs are mutually overlapping and have different security semantics (Medium)

PRs #303 and #307 both modify `validate_session`; #307 reconstructs a `User` from cached serialized fields, including secrets, while #303 still performs a DB lookup on cache hits. PR #298 is independent and safe-looking but needs tests. Do not merge #303 and #307 together without choosing one design. Any cache must honor revocation and expiration quickly and avoid caching sensitive model fields unnecessarily.

### SEC-005 — Duplicate PRs #297 and #299, and overlapping #304 (Low/Process)

PRs #297 and #299 have the same one-file patch. PR #304 contains the same HTMX redirect change plus unrelated route edits. Merge one coherent patch only, after tests; close duplicates rather than merging all.

### SEC-006 — PR #306 is unstable

PR #306 has a failing/cancelled CI result on Python 3.13 and should be fixed or closed before consideration.

## Ponytail recommendations

- Keep one shared auth/CSRF helper instead of repeating route-local guards.
- Keep the site-builder widget schema small; do not add a templating engine or new dependency.
- Prefer standard-library `html.escape`, `urllib.parse`, and `Path.is_relative_to`.
- Do not merge generated `.jules/*` learning files or `pr_desc.md` unless the project explicitly wants them.

## Scope reviewed

- Current local changes after fast-forwarding `origin/main`.
- All 11 open PRs returned by GitHub on 2026-08-20.
- Detailed diffs for PRs #298, #299, #303, #304, #305, #307.

## Next action

Implement SEC-001 and the path-boundary portion of SEC-003 first; add CSRF regression coverage for SEC-002, then run the full test suite and re-check the PR set. Keep changes on a feature branch; do not commit, push, or merge PRs without explicit authorization.
