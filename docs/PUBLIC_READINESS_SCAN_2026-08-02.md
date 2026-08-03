# Public readiness scan — ai-gateway

**Date:** 2026-08-02 (UTC)  
**Tree scanned:** `66f2ffb` + readiness commit (tracked files only)  
**Scope:** PHI, secrets, LAN IPs, home paths, usernames, lab hostnames  
**Goal:** stage private repo for public switch (visibility flip is a separate explicit step)

## Remotes (post pull/push)

| Remote | Branch | Tip role |
|--------|--------|----------|
| **GitHub** `the1truedan/ai-gateway` | `main` (private) | Sanitized public package history (orphan root `abeca24`…) |
| **Forgejo** | `main` | Same sanitized tip (force-updated from lab history) |
| **Forgejo** | `lab-main` | Pre-sanitize full lab tree tip `43c3dca` (preserved) |
| **Local** | `lab-main` | Same as Forgejo `lab-main` |

GitHub’s three-commit public line was **not** a fast-forward of lab history (orphan root). Local `main` was reset to that tip; lab history kept on `lab-main`.

## Method

- `git ls-files` only (what clones would ship).
- Patterns: IPv4 / RFC1918, `/Users/`, `/home/`, `/Volumes/` inventory, emails, key material, PHI/HIPAA tokens, lab nicknames, tracked credential filenames.
- Local untracked `.env` inspected for **presence of secrets** (values not published).

## Results summary

| Check | Result | Notes |
|-------|--------|--------|
| Tracked `.env` / private keys | **PASS** | No `.env`, `.pem`, or credential files tracked |
| Real API keys / tokens in git | **PASS** | Only placeholders / `os.environ/…` / empty examples |
| RFC1918 / LAN IPs | **PASS** | None in tracked files |
| `/Users/dtm` or home absolute paths | **PASS** | None |
| Email addresses | **PASS** | Only `you@example.com` style placeholders |
| PHI / HIPAA | **PASS (semantic)** | Matches are **routing / policy keywords** (orchestrator refuses PHI, QQQ gates) — no patient records or caregiver PII |
| Lab nicknames (M4RV/MRGPU/Tower) | **PASS after scrub** | Ops prose uses role labels (`NAS_HOST`, Mac workstation, GPU worker) — no lab computer nicknames in public tree |
| Public identity | **INTENTIONAL** | GitHub user `the1truedan`, Linktree/Ko-fi, LICENSE copyright — expected for public OSS |
| Generic volume defaults | **ACCEPTABLE** | `/Volumes/ai-data`, `/Volumes/models/…` as **Mac NFS convention defaults**, overridable by env |
| Host roles | **PASS** | `nas-host` / `gpu-host` / `mac-client` vocabulary only |

## Residual risks (accept before public)

1. **Local untracked secrets** on the workstation (`.env`, `.env.bak-*`) — must stay gitignored; never `git add -f`. Local hostnames/IPs in runtime containers and untracked lab files are fine and **not** published.
2. **`/Volumes/…` defaults** — generic but lab-flavored; operators should override via env (already supported).
3. **Org cross-links** to private sibling repos (`mok-tua`, `grok-tua-tok-tua`, …) — links are fine; those repos may still be private.
4. **History on GitHub `main`** is the **sanitized orphan root** only (good). Full lab history remains on Forgejo/local `lab-main` (keep private).

## Hardening applied this pass

- Expanded `.gitignore` for `.env.*`, `*.bak*`, `node_modules/`, `artifacts/`, merged litellm configs, venvs, logs.
- Scrubbed remaining `M4RV`/`MRGPU` mentions in bees ops docs.
- This scan report committed under `docs/`.

## Public switch checklist (manual)

- [x] Sanitized tip on GitHub private `main`
- [x] Same tip on Forgejo `main` (+ `lab-main` preserved)
- [x] Automated scan clean of IPs / home paths / real keys / PHI data
- [x] `.gitignore` hardened for local secrets
- [x] Human skim of `README.md`, `.env.example`, `litellm_config*.yaml`, `docs/ops/bees/*`
- [x] Confirm sibling private repos are OK to link (or switch links to public mirrors)
- [x] `gh repo edit the1truedan/ai-gateway --visibility public` (2026-08-03)
- [x] Scrub residual “Tower” lab nickname from bees ops docs + Grafana tag (2026-08-03 follow-up)
- [ ] Optional: GitHub Topics + first Release tag `v0.1.0-public`

## Re-check 2026-08-03 (README / assets retouch + host scrub)

| Check | Result |
|-------|--------|
| README hero media | Mermaid routing + vendored Headroom savings + hippo SVG (no empty admin/JSON heroes) |
| `docs/assets/upstream/*` | Apache-2.0 Headroom PNG + hippo SVG + attribution README |
| `config/hosts/mac.env` | NAS addr is hostname placeholder (`nas-host.local`), not RFC1918 |
| `litellm_config.mac-worker.yaml` | Worker aliases only; keys via `os.environ/…` |
| Local `.env` / `.env.bak-*` | Still **gitignored** (never force-add) |
| Personal narrative in README/STORY | **Intentional** public story (care pivot / ACL) — no addresses, phones, or clinical records |
| Lab hostnames / LAN IPs on GitHub | **PASS** — no `192.168.*`; no M4RV/MRGPU; “Tower” prose → NAS host role language |
| Local lab names/IPs | **OK on workstation only** — runtime orchestrator routes, Docker env, untracked `.env` |

## Verdict

**Staged for public switch: CONDITIONAL GO.**  
No PHI payloads, LAN IPs, home paths, or real secrets found in **tracked** tree. Residual items are intentional identity, generic volume defaults, and ops role language. Flip visibility only after the manual checklist above.
