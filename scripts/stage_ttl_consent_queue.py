#!/usr/bin/env python3
"""Stage xAI ttl export assets into Obsidian consent-gated ingest queue.

Copies zzz_ingest-tagged blobs + PDFs from ~/Downloads/ttl into:
  zzz_ingest/incoming/consent-gated-ttl-2026-07-03/
Writes catalog manifest + Obsidian sidecars (consent_required until review).
"""

from __future__ import annotations

import hashlib
import json
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

VAULT = Path("$HOME/Documents/Obsidian/grokmsgs/grokmsgs")
DROP = VAULT / "zzz_ingest" / "incoming" / "consent-gated-ttl-2026-07-03"
CATALOG = VAULT / "zzz_ingest" / "catalog"
ASSETS = (
    Path.home()
    / "Downloads/ttl/30d/export_data/<export-id>/prod-mc-asset-server"
)
CATALOG_JSON = Path(__file__).resolve().parent.parent / "import-data/staging/ttl_asset_catalog.json"

CONSENT_ID = "consent-example-full-2026-07-02"
PATIENT_PSEUDO_ID = "example-caregiver"
BATCH_ID = "consent-gated-ttl-2026-07-03"

STEM_NOISE = re.compile(r"[^\w\s.-]+")
PDF_TITLE = re.compile(rb"/Title\s*\(([^)]+)\)")


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def detect_kind(raw: bytes) -> tuple[str, str]:
    if raw[:4] == b"%PDF":
        return "pdf", ".pdf"
    if raw[:2] == b"PK":
        return "docx", ".docx"
    if raw.lstrip()[:1] in (b"{", b"["):
        return "json", ".json"
    text = raw[:4000].decode("utf-8", errors="replace")
    if text.lstrip().startswith("#") or "## " in text[:800]:
        return "markdown", ".md"
    if "<html" in text[:500].lower() or "<!doctype" in text[:500].lower():
        return "html", ".html"
    if "delivered-to:" in text[:200].lower():
        return "email", ".eml"
    return "text", ".txt"


def safe_stem(title: str, asset_id: str, ext: str) -> str:
    stem = STEM_NOISE.sub(" ", (title or "untitled").lower())
    stem = re.sub(r"\s+", "-", stem).strip("-")[:72] or "untitled"
    return f"{stem}--{asset_id[:8]}{ext}"


def pdf_title(raw: bytes) -> str:
    m = PDF_TITLE.search(raw[:8000])
    if not m:
        return ""
    try:
        return m.group(1).decode("latin-1", errors="replace").strip()
    except Exception:
        return ""


def phi_hint(text: str) -> dict[str, Any]:
    lower = text.lower()
    keys = (
        "ssn", "social security", "patient", "diagnosis", "hipaa",
        "medical", "doctor", "ssdi", "ptsd", "wera", "caregiv",
        "example person", "gmail", "consent",
    )
    hits = [k for k in keys if k in lower]
    return {"has_phi_hint": bool(hits), "hints": hits}


def sidecar_body(
    *,
    rel_path: str,
    asset_id: str,
    title: str,
    kind: str,
    size: int,
    digest: str,
    tags: list[str],
    source_path: str,
) -> str:
    hint = phi_hint(title)
    return f"""---
ingest_status: consent_gated_pending
consent_required: true
consent_id: {CONSENT_ID}
patient_pseudo_id: {PATIENT_PSEUDO_ID}
batch_id: {BATCH_ID}
source: xai_ttl_export
asset_id: {asset_id}
file_kind: {kind}
sha256: {digest}
phi_review: required
phi_hint: {json.dumps(hint)}
tags: {json.dumps(tags)}
staged_at: {datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")}
vault_rel: {rel_path}
ttl_source: {source_path}
---

# {title or asset_id}

**Consent-gated staging** — do not promote to modules until `scan_ingest_dan.py --execute` after consent review.

| Field | Value |
|-------|-------|
| Asset ID | `{asset_id}` |
| Kind | {kind} |
| Size | {size:,} bytes |
| Tags | {", ".join(tags) or "—"} |

Run review:
```bash
cd {VAULT / "zzz_ingest/scripts"}
python scan_ingest_dan.py --drop consent-gated-ttl-2026-07-03
python scan_ingest_dan.py --drop consent-gated-ttl-2026-07-03 --execute
```
"""


def stage_file(
    src: Path,
    dest_dir: Path,
    *,
    title: str,
    tags: list[str],
    vault_prefix: str,
) -> dict[str, Any]:
    raw = src.read_bytes()
    kind, ext = detect_kind(raw)
    if kind == "pdf" and not title:
        title = pdf_title(raw) or title
    name = safe_stem(title, src.parent.name, ext)
    dest = dest_dir / name
    if dest.exists():
        name = safe_stem(f"{title}-{src.parent.name[:4]}", src.parent.name, ext)
        dest = dest_dir / name
    dest.write_bytes(raw)
    rel = f"{vault_prefix}/{name}"
    sidecar = dest.with_suffix(dest.suffix + ".md")
    digest = sha256_bytes(raw)
    sidecar.write_text(
        sidecar_body(
            rel_path=rel,
            asset_id=src.parent.name,
            title=title,
            kind=kind,
            size=len(raw),
            digest=digest,
            tags=tags,
            source_path=str(src),
        ),
        encoding="utf-8",
    )
    return {
        "asset_id": src.parent.name,
        "vault_rel": rel,
        "sidecar_rel": rel + ".md",
        "title": title,
        "kind": kind,
        "size_bytes": len(raw),
        "sha256": digest,
        "tags": tags,
        "phi_hint": phi_hint(title),
        "status": "consent_gated_pending",
    }


def main() -> int:
    catalog = json.loads(CATALOG_JSON.read_text(encoding="utf-8"))
    zzz_rows = [r for r in catalog["tagged_assets"] if "zzz_ingest" in r["tags"]]

    zzz_dir = DROP / "zzz_ingest"
    pdf_dir = DROP / "pdfs"
    zzz_dir.mkdir(parents=True, exist_ok=True)
    pdf_dir.mkdir(parents=True, exist_ok=True)

    staged: list[dict[str, Any]] = []

    for row in zzz_rows:
        src = Path(row["path"])
        if not src.is_file():
            continue
        entry = stage_file(
            src,
            zzz_dir,
            title=row.get("title_guess", ""),
            tags=row.get("tags", []),
            vault_prefix=f"zzz_ingest/incoming/{BATCH_ID}/zzz_ingest",
        )
        staged.append(entry)

    pdf_ids: set[str] = set()
    for src in sorted(ASSETS.rglob("content")):
        raw = src.read_bytes()[:8]
        if raw[:4] != b"%PDF":
            continue
        if src.parent.name in pdf_ids:
            continue
        pdf_ids.add(src.parent.name)
        full = src.read_bytes()
        title = pdf_title(full) or f"pdf-{src.parent.name[:8]}"
        text = full[:12000].decode("utf-8", errors="replace").lower()
        tags = []
        if "example person" in text:
            tags.append("example_person")
        if any(k in text for k in ("ssdi", "wera", "caregiv", "patient", "medical", "doctor", "hipaa")):
            tags.append("care_legal")
        if "manager" in text or "m.a.n.a.g.e.r" in text:
            tags.append("manager")
        entry = stage_file(
            src,
            pdf_dir,
            title=title,
            tags=tags,
            vault_prefix=f"zzz_ingest/incoming/{BATCH_ID}/pdfs",
        )
        staged.append(entry)

    manifest = {
        "batch_id": BATCH_ID,
        "staged_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "consent_id": CONSENT_ID,
        "patient_pseudo_id": PATIENT_PSEUDO_ID,
        "status": "consent_gated_pending",
        "source_ttl": str(ASSETS.parent),
        "drop_path": str(DROP.relative_to(VAULT)),
        "counts": {
            "zzz_ingest": len(zzz_rows),
            "pdfs": len(pdf_ids),
            "total": len(staged),
        },
        "items": staged,
        "next_steps": [
            f"Review sidecars under {DROP.relative_to(VAULT)}",
            "python scan_ingest_dan.py --drop consent-gated-ttl-2026-07-03",
            "python scan_ingest_dan.py --drop consent-gated-ttl-2026-07-03 --execute",
        ],
    }

    manifest_path = CATALOG / f"consent_gated_queue_{BATCH_ID}.json"
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")

    readme = DROP / "README.md"
    readme.write_text(
        f"""---
ingest_status: consent_gated_pending
consent_required: true
consent_id: {CONSENT_ID}
batch_id: {BATCH_ID}
---

# Consent-gated TTL staging ({BATCH_ID})

Staged from xAI full export `~/Downloads/ttl` — **not ingested** until D.A.N. review.

| Subfolder | Count | Contents |
|-----------|-------|----------|
| `zzz_ingest/` | {len(zzz_rows)} | Manager docs, TODO/CHANGELOG, incoming manifests |
| `pdfs/` | {len(pdf_ids)} | Personal/care/legal PDF attachments |

Manifest: `zzz_ingest/catalog/consent_gated_queue_{BATCH_ID}.json`
""",
        encoding="utf-8",
    )

    print(f"Staged {len(staged)} items → {DROP}")
    print(f"  zzz_ingest: {len(zzz_rows)} | pdfs: {len(pdf_ids)}")
    print(f"Manifest: {manifest_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())