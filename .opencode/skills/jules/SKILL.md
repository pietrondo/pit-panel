---
name: jules
description: Delegate work to Jules, Google's cloud coding agent, and triage the resulting sessions. Use when the user says jules, delegate to jules, check jules sessions, or asks about PRs opened by jules/bolt/palette/sentinel agents.
---

# Jules (cloud agent delegation)

Jules is Google's autonomous coding agent. It runs each task in a cloud VM, pushes a
branch, and opens a PR against the repo.

## The one thing to get right

**A vague prompt is the main failure mode, not the tooling.** On this repo, brief
Jules with "find a security vulnerability" and it will explore everything, list
candidates, then stop and ask *which one should I fix?*. Nobody answers. The session
parks in `AWAITING_USER_FEEDBACK` forever and `jules remote pull` reports
**"No diff found in the remote VM"** — which looks like "nothing to merge" when the
session is actually blocked on a one-line reply.

Rules for a prompt that completes unattended:
- name the file and the function
- name the exact fix (regex, literal, behaviour)
- name the tests
- one task per session

Good: `re.fullmatch() the subdomain param in src/pit_panel/web/routes/subdomains.py:add_subdomain. Match ^[a-zA-Z0-9](?:[a-zA-Z0-9-]*[a-zA-Z0-9])?$ (single label, no dots). Add 3 tests, run ruff and pytest, open a PR.`

## CLI

```bash
jules remote new --repo . --session "<prompt>"   # delegate
jules remote list --session                      # list sessions
jules remote pull --session <id>                 # retrieve diff
```

The CLI has **no** command to read a session transcript or reply to one. Use the API.

On Windows, launching several `jules remote new` in parallel crashes the CLI (gzip
collision in `%TEMP%\jules_tmp`). Run them sequentially, or clear the cache:
`Remove-Item -Recurse -Force "$env:TEMP\jules_tmp" -ErrorAction SilentlyContinue`

## REST API

Key at `~/.Jules/api_key`. Header `X-Goog-Api-Key`. Alpha API, so field names can move.

```powershell
$k = (Get-Content "$env:USERPROFILE\.Jules\api_key" -Raw).Trim()
curl.exe -s -H "X-Goog-Api-Key: $k" "https://jules.googleapis.com/v1alpha/sessions?pageSize=100"
```

| Call | Purpose |
|---|---|
| `GET /v1alpha/sources` | list connected repos |
| `GET /v1alpha/sessions?pageSize=100` | list sessions |
| `GET /v1alpha/sessions/{id}/activities` | read what the agent is asking |
| `POST /v1alpha/sessions/{id}:sendMessage` | reply, body `{"prompt":"..."}` |
| `POST /v1alpha/sessions/{id}:approvePlan` | approve plan (only if `requirePlanApproval`) |

The JSON is **snake_case**: `agent_messaged.agent_message`, `progress_updated`,
`create_time`, `git_patch.unidiff_patch`. The official doc samples are camelCase and
will mislead you.

Read the last `agent_messaged` activity before replying. Jules states findings, then
asks; a blind reply just earns another round of questions.

## Triaging the backlog

1. List sessions, filter `state -eq "AWAITING_USER_FEEDBACK"`.
2. Read each one's last question.
3. Pull only those that genuinely have a diff.

Gotcha: in a pull loop a **blank** last line means the session **has** a diff.
`Select-Object -Last 1` swallows multi-line output and makes non-empty look empty.

## Before merging anything Jules produced

- **Scratch scripts.** Jules leaves helper scripts in the repo root: `fix_*.py`,
  `fix_mocks*.py`, `test_empty_states*.sh`, `backend_*_check.py`. 16 one-liner
  `test_empty_states*.sh` files had already landed on `main`. Patterns are gitignored —
  keep them there. Filter these out of any diff.
- **Already-landed duplicates.** Many sessions are stale: the real change arrived via
  an earlier PR and only the scratch files remain. Check before merging.
- **Nothing to merge is not the same as nothing to do.** A session parked on a question
  produces an empty diff.

## PR lifecycle

1. Receive — `jules remote pull --session <id>`
2. Review — read the diff, run `ruff check src/ tests/` and pytest locally
3. Push — `git push -u origin <branch>` (PR opens automatically)
4. CI — ruff + mypy + pytest on ubuntu, Python 3.11/3.12/3.13
5. Merge — `gh pr merge <n> --squash --delete-branch`
6. Cleanup — drop merged branches and stashes

Check that Actions is actually enabled before trusting any CI result:
`gh api repos/pietrondo/pit-panel/actions/permissions` must return `enabled: true`.

## Personas in use

Bolt (performance), Sentinel (security), Palette (micro-UX/accessibility), plus
sessions for tests and HTMX alignment. They append learnings to `.jules/{bolt,sentinel,palette}.md`.