# A.I.D.A. (ai-gateway slice) — document mastery path

**A**utomated **I**ntelligent **D**ocument & Video **A**ssistant — prepare-only document pipeline with **deep assurance** (merged **A.I.A.D.A.** / **A.C.C.E.S.S.** concepts from prior Grok planning).

Weekend focus: **complex document / PDF ADA processing** while sensors are built elsewhere. Local LiteLLM only for PHI (`tier-local-fast`). No Extend.ai / remote cloud models by default.

## What it does

1. Watch NFS (or local) drop folders under `AIDA_INGEST_ROOT` (default `/Volumes/ai-data/work/ingest`)
2. Lifecycle: `_incoming → _processing → _done | _error` (+ `_briefs`, `_prep`, `_aida_reports`)
3. **ocrmypdf** searchable PDF (host binary preferred)
4. **Docling** structure IR (MIT, local) → Markdown + JSON; enriches `txt_pix`
5. **GraniteDocling VLM** (Apache-2.0) — **always available as an option** when Docling is installed (env or per-request `use_vlm`; not forced on every file)
6. **veraPDF** PDF/UA (host CLI or Docker) + structure **heuristics**
7. **Mastery scorecard**: `ada_pre_check`, WCAG PDF techniques, Section 508 matrix, composite score
8. **axe-core** on linear HTML (WAVE stand-in)
9. **Dual briefs** + full linear HTML + SR HTML
10. **JIST** + emotional soft gate
11. **Style recommendation** (APA / AMA / CMOS / GPO / plain-care / scientific-imrad packs)
12. **4-tier knowledgebase**: `raw → processed → txt_pix → jist`
13. **Remediation** (PyMuPDF metadata/outline) + optional **OpenDataLoader Tagged PDF** candidate + re-veraPDF — HITL required
14. **AcroForm form fill** via [ai-pdf-autofiller](https://github.com/lindseystead/ai-pdf-autofiller) (MIT) — prepare-only, never submit-ready without HITL
15. **adeu DOCX redline** ([dealfluence/adeu](https://github.com/dealfluence/adeu), MIT) — brief → DOCX Track Changes; local only
16. **officecli generation** ([officecli/officecli](https://github.com/officecli/officecli)) — PPTX/DOCX/XLSX/report from prompts; **External Mode → local LiteLLM** by default (MANAGER document-output probe)
17. **VPAT-style seed** + **SQLite catalog** + HITL API

`decision_authority: prepare_only` — not clinical/legal final decisions. Not a formal VPAT/508 filing.

## Adobe-free PDF tagging doctrine

There is **no mature open-source Acrobat Auto-Tag equivalent**. In-place PDF/UA requires writing `StructTreeRoot`, `ParentTree`, MCIDs, marked content, `RoleMap`, alt text, reading order, language, artifacts, etc.

| Layer | Tool | Role | Claim allowed |
|-------|------|------|----------------|
| Validate | **veraPDF** | PDF/UA gold standard | pass/fail only |
| Layout / IR | **Docling** (MIT) | Headings, tables, reading-order IR → MD/JSON | Structure for briefs/RAG — **not** PDF tags |
| Vision (optional) | **GraniteDocling** (Apache-2.0) | Hard layouts | Same as Docling IR |
| Light PDF surgery | **PyMuPDF** | Title/lang/outline | Prepare-only |
| Tagged PDF candidate | **OpenDataLoader PDF** (Apache-2.0 free auto-tag) | Untagged → Tagged PDF | Candidate only; **PDF/UA export is enterprise (not used)**; always re-veraPDF |
| Form fields | **ai-pdf-autofiller** (MIT) | AcroForm fill from JSON | Filled values ≠ accessibility tags |
| Future StructWriter | **Apache PDFBox** + Docling IR | Write real structure tree | Design stub — multi-sprint |
| Commercial | Adobe / PDFix / axesPDF | Auto-tag / repair | **Excluded** by policy |

**Two durable paths:**

1. **Remediate-in-place** — OpenDataLoader trial → later PDFBox StructWriter fed by Docling.
2. **Regenerate** — Docling MD → accessible HTML/DOCX → LibreOffice PDF/UA export (often better for *new* docs).

Future **StructWriter** contract (not implemented this weekend):

```
inputs:  DoclingDocument | structure JSON + original PDF bytes
outputs: tagged PDF bytes + role map summary
engine:  PDFBox (Apache-2.0) via JVM bridge
validate: veraPDF
```

## Explicitly not included

| Tool / claim | Status |
|--------------|--------|
| **Adobe Acrobat / Auto-Tag / Sensei** | **Excluded** (proprietary) |
| “We match Acrobat Auto-Tag” | **Never claimed** |
| WAVE SaaS | axe-core HTML stand-in only |
| JAWS / NVDA automation | HITL + VoiceOver on linear HTML |
| Grackle / PDFix commercial default | Not wired |
| iText AGPL as default | Not default (license) |
| Full PDFBox structure engine | Roadmap / multi-sprint |
| Extend.ai / remote doc AI | Disabled by default |
| Auto tax e-file / submit | Never — HITL only |
| Video first-pass | Not in this slice |

## Run (host — preferred on M4)

```bash
cd ~/ai-gateway
python3 -m venv services/aida/.venv
source services/aida/.venv/bin/activate
pip install -r services/aida/requirements.txt
./scripts/start_aida.sh
```

Optional sidecars / extras:

```bash
./scripts/aida_setup_formfill.sh          # ai-pdf-autofiller on :8793
./scripts/aida_setup_opendataloader.sh    # brew openjdk@17 + pip opendataloader-pdf
./scripts/aida_setup_adeu.sh              # adeu + python-docx in A.I.D.A. venv
./scripts/aida_setup_officecli.sh         # npm officecli + External Mode → LiteLLM
./scripts/aida_setup_verapdf.sh
./scripts/aida_setup_docling.sh
```

`start_aida.sh` auto-prepends Homebrew **OpenJDK 17** (`JAVA_HOME`) so OpenDataLoader does not pick up system Java 8.

Smoke:

```bash
curl -sS http://127.0.0.1:8792/health | python3 -m json.tool
# Expect: docling.vlm_option.available, form_fill, opendataloader keys

./scripts/aida_drop_once.py /path/to/sample.pdf --category medical

# Force Granite on one ingest (no process restart):
curl -sS -X POST http://127.0.0.1:8792/v1/ingest \
  -H 'Content-Type: application/json' \
  -d '{"path":"/abs/sample.pdf","category":"medical","use_vlm":true,"use_llm":false}'

# Form fill (after aida_setup_formfill.sh):
curl -sS -X POST http://127.0.0.1:8792/v1/forms/inspect \
  -H 'Content-Type: application/json' \
  -d '{"pdf_path":"/abs/w9.pdf"}'
curl -sS -X POST http://127.0.0.1:8792/v1/forms/fill \
  -H 'Content-Type: application/json' \
  -d '{"pdf_path":"/abs/w9.pdf","category":"legal","user_data":{"firstname":"Jane","lastname":"Doe"},"use_semantic_inference":false}'
# → submit_ready is always false; review then HITL

# Phase 3 adeu — brief MD → DOCX redline:
curl -sS -X POST http://127.0.0.1:8792/v1/adeu/from-brief \
  -H 'Content-Type: application/json' \
  -d '{"category":"legal","stem":"advocacy","title":"Advocacy letter draft","markdown":"# Letter\n\nWe request a care plan review.\n","edits":[{"type":"modify","target_text":"care plan review","new_text":"comprehensive care plan review","comment":"Stronger ask"}]}'

# Phase 4 officecli — generate DOCX/PPTX for MANAGER orchestration probe:
curl -sS -X POST http://127.0.0.1:8792/v1/officecli/configure -H 'Content-Type: application/json' -d '{}'
curl -sS -X POST http://127.0.0.1:8792/v1/officecli/generate \
  -H 'Content-Type: application/json' \
  -d '{"kind":"docx","topic":"Respite funding one-pager","category":"legal","mode":"fast","prompt":"Write a one-page non-PHI respite funding overview with sections: purpose, eligibility checklist placeholders, next steps. No patient names."}'

curl -sS -X POST http://127.0.0.1:8792/v1/hitl \
  -H 'Content-Type: application/json' \
  -d '{"report_id":"YOUR_ID","hitl_screen_reader":"pass","notes":"VoiceOver OK"}'
```

## Compose (optional)

```bash
./scripts/docker/compose.sh --profile aida up -d --build
```

Mounts `/Volumes/ai-data/work/ingest` → `/ingest`. LiteLLM via compose network.
Note: Docker profile disables veraPDF Docker-in-Docker by default (`VERAPDF_DISABLE_DOCKER=1`); prefer host AIDA on M4.

## API

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/health` | Tools: ocrmypdf / veraPDF / axe / Docling+VLM option / form_fill / opendataloader / model |
| GET | `/v1/pending` | Files waiting in `_incoming` |
| POST | `/v1/ingest` | Process absolute path (`use_vlm` optional) |
| POST | `/v1/ingest/upload` | Multipart upload → process (`use_vlm` form field) |
| POST | `/v1/watch/tick` | Drain pending (claim lifecycle) |
| GET | `/v1/report/{id}` | Receipt JSON by report_id |
| POST | `/v1/hitl` | Record screen-reader / remediation HITL |
| GET | `/v1/catalog` | Accessibility resource catalog |
| GET | `/v1/vpat/{id}` | VPAT-style seed for a report |
| GET | `/v1/forms/health` | Autofiller sidecar probe |
| GET | `/v1/forms/recipes` | w9 / hr-onboarding / generic |
| POST | `/v1/forms/inspect` | List AcroForm field names |
| POST | `/v1/forms/fill` | Fill PDF from JSON (prepare-only) |
| GET | `/v1/adeu/health` | adeu CLI/SDK availability |
| POST | `/v1/adeu/extract` | DOCX → Markdown |
| POST | `/v1/adeu/apply` | Apply Track Changes edits JSON |
| POST | `/v1/adeu/sanitize` | Strip metadata / prep distribute |
| POST | `/v1/adeu/from-brief` | Markdown → draft DOCX → optional redline |
| GET | `/v1/officecli/health` | officecli binary + External Mode status |
| POST | `/v1/officecli/configure` | Write External Mode → LiteLLM config |
| POST | `/v1/officecli/generate` | `pptx\|docx\|xlsx\|report` generation (no publish) |
| GET | `/v1/officecli/outputs` | List `_prep/officecli` artifacts |

## Env

| Variable | Default | Meaning |
|----------|---------|---------|
| `AIDA_INGEST_ROOT` | `/Volumes/ai-data/work/ingest` | Drop root |
| `AIDA_PORT` | `8792` | Listen port |
| `AIDA_LITELLM_BASE` | `http://127.0.0.1:4000` | Chat completions |
| `AIDA_LITELLM_KEY` / `LITELLM_MASTER_KEY` | — | Auth |
| `AIDA_MODEL` | `tier-local-fast` | PHI-safe local alias |
| `AIDA_ALLOW_REMOTE` | `0` | Must stay 0 for medical PHI |
| `AIDA_CONSENT_ID` | `consent-example-full-2026-07-02` | Receipt consent |
| `AIDA_CATALOG_DB` | `{ingest}/_config/accessibility_catalog.db` | SQLite catalog |
| `AIDA_AXE_DISABLE` | `0` | Set `1` to skip npx axe |
| `AIDA_AXE_TIMEOUT` | `120` | axe CLI timeout seconds |
| `AIDA_DOCLING_DISABLE` | `0` | Set `1` to skip Docling |
| `AIDA_DOCLING_PIPELINE` | `standard` | Process default: `standard` or `vlm` |
| `AIDA_DOCLING_VLM` | `0` | Process default on for Granite when `1` |
| `AIDA_DOCLING_VLM_MODEL` | `granite_docling` | Docling VLM model key |
| `AIDA_FORMFILL_URL` | `http://127.0.0.1:8793` | ai-pdf-autofiller base |
| `AIDA_FORMFILL_DISABLE` | `0` | Set `1` to skip form fill |
| `AIDA_FORMFILL_TIMEOUT` | `60` | HTTP timeout seconds |
| `AIDA_FORMFILL_API_KEY` | empty | If sidecar auth enabled |
| `AIDA_OPENDATALOADER` | `auto` | `auto`/`1` try when installed; `0` off |
| `AIDA_OPENDATALOADER_DISABLE` | `0` | Set `1` to skip OpenDataLoader |
| `AIDA_JAVA_HOME` / `JAVA_HOME` | brew openjdk@17 if present | JDK for OpenDataLoader JVM |
| `AIDA_ADEU_DISABLE` | `0` | Set `1` to skip adeu |
| `AIDA_ADEU_AUTHOR` | `A.I.D.A.` | Track Changes author |
| `AIDA_ADEU_CMD` | auto (venv `adeu`) | Override adeu binary |
| `AIDA_OFFICECLI_DISABLE` | `0` | Set `1` to skip officecli |
| `AIDA_OFFICECLI_CMD` | auto (`~/.local/bin/officecli`) | Override binary |
| `AIDA_OFFICECLI_MODEL` | `tier-local-fast` | External Mode model id |
| `AIDA_OFFICECLI_ALLOW_HOSTED` | `0` | Hosted credits/platform (off for PHI) |
| `AIDA_OFFICECLI_TIMEOUT` | `300` | Generation timeout seconds |
| `VERAPDF_CMD` | — | Host veraPDF binary |
| `VERAPDF_DOCKER_IMAGE` | `verapdf/cli:latest` | Official veraPDF CLI |
| `VERAPDF_DOCKER_PLATFORM` | `linux/amd64` | Emulation on arm64 |
| `VERAPDF_DISABLE_DOCKER` | `0` (host) / `1` (compose) | Skip docker runner |

## Artifacts per document

| Artifact | Location |
|----------|----------|
| Receipt | `{cat}/_aida_reports/{stem}__{report_id}.json` |
| Caregiver / plain briefs | `{cat}/_briefs/*__caregiver.md`, `*__caregivee.md` |
| Screen-reader brief HTML | `{cat}/_briefs/*__sr.html` |
| Full linear HTML (axe target) | `{cat}/_briefs/*__document_linear.html` |
| VPAT seed | `{cat}/_aida_reports/{stem}.vpat_seed.{json,md}` |
| Remediation plan | `{cat}/_prep/remediation/{stem}.remediation_plan.json` |
| Remediated PDF | `{cat}/_prep/remediation/{stem}.remediated.pdf` |
| Tagged PDF candidate | `{cat}/_prep/remediation/{stem}.tagged.pdf` (OpenDataLoader) |
| Filled form | `{cat}/_prep/forms/{stem}.filled.pdf` + `.fill_report.json` |
| adeu drafts / redlines | `{cat}/_prep/adeu/{stem}.draft.docx`, `{stem}.redlined.docx` |
| officecli outputs | `{cat}/_prep/officecli/*.{docx,pptx,xlsx,html}` + `.prompt.md` + receipt JSON |
| Tiers | `_knowledgebase/{raw,processed,txt_pix,jist}/YYYY/MM/{cat}/` |

## MANAGER document-output orchestration

A.I.D.A. exposes a thin **document_output** agent for M.A.N.A.G.E.R. testing:

```
POST /v1/document-output/plan   → style_id + kind + chain (no generate)
POST /v1/document-output/run    → officecli generate → optional adeu → receipt
```

```
style pack + brief / JIST
        │
        ├─► document_output (style → kind → officecli → adeu)
        │
        ├─► form fill (AcroForm)
        │
        └─► A.I.D.A. a11y (OCR, Docling, veraPDF, linear HTML)
```

```bash
# Plan only (fast)
curl -sS -X POST http://127.0.0.1:8792/v1/document-output/plan \
  -H 'Content-Type: application/json' \
  -d '{"topic":"Advocacy letter to insurer","category":"legal","intent":"formal letter","body":"Request redetermination of home nursing hours."}'

# Full run (calls local LLM via officecli — may take minutes)
curl -sS -X POST http://127.0.0.1:8792/v1/document-output/run \
  -H 'Content-Type: application/json' \
  -d '{"topic":"Advocacy letter","category":"legal","intent":"letter","body":"Request redetermination.","edits":[{"type":"modify","target_text":"redetermination","new_text":"prompt redetermination","match_mode":"first"}]}'
```

| Capability | Tool | MANAGER note |
|------------|------|--------------|
| Plan kind + style | `document_output` plan | Heuristic style packs + intent keywords |
| New deck / memo / workbook | officecli External → LiteLLM | Medical uses local model only |
| Negotiate / redline DOCX | adeu | Pass `edits[]` on run; empty skips redline safely |
| Fill government forms | ai-pdf-autofiller | Deterministic + HITL |
| Accessibility certify path | veraPDF + Docling + HITL | Never claim PDF/UA without veraPDF |

OfficeCLI **hosted trial / publish** stay **off** (`AIDA_OFFICECLI_ALLOW_HOSTED=0`, always `--no-publish`).

Artifacts: `{cat}/_prep/document_output/*.document_output.json` + officecli/adeu paths in receipt.

## JAWS / NVDA / VoiceOver

Automated path: PDF/UA (veraPDF) + linear HTML + optional axe.
**HITL required:** open `__document_linear.html` or `__sr.html` in VoiceOver (macOS) or NVDA/JAWS (Windows); then `POST /v1/hitl` with `hitl_screen_reader: pass|fail|partial`.

## Ops notes (weekend)

- **veraPDF host (preferred):** `./scripts/aida_setup_verapdf.sh` → `brew install verapdf`. `/health` should show `verapdf.mode: host`.
- **veraPDF + NFS Docker fallback:** If host CLI missing, runner **copies PDF to local temp** before `docker run` (`docker_mount: local_temp_copy`).
- **axe-core:** `./scripts/aida_setup_axe.sh` installs Chrome for Testing + ChromeDriver into `~/.browser-driver-manager`. Auto-discovered; override with `AIDA_CHROME_PATH` / `AIDA_CHROMEDRIVER_PATH`. Set `AIDA_AXE_DISABLE=1` to skip.
- **PyMuPDF remediation:** Writes `{stem}.remediated.pdf` under `_prep/remediation/` (metadata + outline; not full PDF/UA auto-tag), then **re-runs veraPDF** (`verapdf_before` / `verapdf_after` + `delta`). RAW tier never overwritten. HITL still required.
- **OpenDataLoader:** Optional free Tagged PDF write-back. `./scripts/aida_setup_opendataloader.sh` installs **openjdk@17** (brew) + `opendataloader-pdf`. Receipt fields `opendataloader_tagging` + `verapdf_after_tagged`. Not Acrobat; not certified without veraPDF pass.
- **adeu (Phase 3):** Local DOCX Track Changes. `./scripts/aida_setup_adeu.sh`. Use `/v1/adeu/from-brief` from caregiver/legal briefs. No Adeu Cloud. HITL before send.
- **officecli (Phase 4):** `./scripts/aida_setup_officecli.sh` → External Mode + LiteLLM. Generate under `{cat}/_prep/officecli/`. Chain DOCX into adeu. Hosted/publish off.
- **Docling (MIT):** Structure IR → `{cat}/_prep/docling/{stem}.docling.md` + `.json`. Enriches `txt_pix`. Not Adobe tag write-back.
- **GraniteDocling (Apache-2.0):** Always advertised on `/health` as `docling.vlm_option`. Enable process-wide with `AIDA_DOCLING_VLM=1`, or per request `use_vlm: true`. Soft-falls back to standard on failure. First run downloads weights.
- **Form fill:** `./scripts/aida_setup_formfill.sh` → sidecar `:8793`. Semantic inference **default off**. Ingest only *detects* AcroForm candidates (`form_fill.candidate`); fill is explicit API.
- **Style packs:** `services/aida/kb/styles/*` — receipt field `style_recommendation`.
- **LiteLLM:** Dual briefs / JIST need `tier-local-fast`; pass `use_llm: false` for pure structural runs.
- **Open-source policy:** Docling MIT + GraniteDocling Apache-2.0 + OpenDataLoader Apache-2.0 + ai-pdf-autofiller MIT + veraPDF + axe; **no Adobe**.

## Relation to MANAGER (`~/grokcode`)

Gateway-local slice of `agents/aida` + accessibility vault concepts. Full J.E.S.U.S. / K.A.R.E.N. / N.A.R.C. orchestrator remains in MANAGER core. Form fill continues Non-Cloud K.A.R.E.N. AcroForm plans (deterministic + HITL). This service is ahead of MANAGER’s `accessibility_vault` stub on **real veraPDF** wiring.
