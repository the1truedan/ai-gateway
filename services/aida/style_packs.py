#!/usr/bin/env python3
"""Style pack loader + genre → style_id recommendation (Layer B/D).

Packs live under services/aida/kb/styles/<id>/STYLE.yaml (+ optional NOTES.md).
No full commercial manuals — public summaries and section checklists only.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

PACKS_ROOT = Path(__file__).resolve().parent / "kb" / "styles"

# Fallback built-ins if YAML missing
_BUILTIN: dict[str, dict[str, Any]] = {
    "scientific-imrad-icmje": {
        "style_id": "scientific-imrad-icmje",
        "name": "Scientific IMRaD + ICMJE manuscript",
        "domains": ["original_research", "caregiver_ai", "acl_track", "medical_methods"],
        "structure": "imrad",
        "cite_processor": "csl:american-medical-association",
        "front_matter": [
            "title",
            "authors",
            "affiliations",
            "abstract_structured",
            "keywords",
        ],
        "body": ["introduction", "methods", "results", "discussion", "conclusions"],
        "back_matter": [
            "references",
            "tables",
            "figures",
            "funding",
            "conflicts",
            "data_availability",
            "author_contributions",
        ],
        "layout": {"margins_in": 1.0, "body_pt": 12, "line_spacing": 2.0},
        "accessibility_export": True,
        "decision_authority": "prepare_only",
    },
    "apa-7": {
        "style_id": "apa-7",
        "name": "APA 7th",
        "domains": ["social_science", "hci", "psychology"],
        "cite_processor": "csl:apa",
        "accessibility_export": True,
        "decision_authority": "prepare_only",
    },
    "ama": {
        "style_id": "ama",
        "name": "AMA / biomedical cites",
        "domains": ["clinical", "biomedical"],
        "cite_processor": "csl:american-medical-association",
        "accessibility_export": True,
        "decision_authority": "prepare_only",
    },
    "cmos-notes-bib": {
        "style_id": "cmos-notes-bib",
        "name": "Chicago notes-bibliography",
        "domains": ["history", "long_form", "publishing"],
        "cite_processor": "csl:chicago-notes-bibliography",
        "accessibility_export": True,
        "decision_authority": "prepare_only",
    },
    "gpo": {
        "style_id": "gpo",
        "name": "GPO / federal correspondence tone",
        "domains": ["government_letter", "official"],
        "cite_processor": None,
        "accessibility_export": True,
        "decision_authority": "prepare_only",
    },
    "plain-care": {
        "style_id": "plain-care",
        "name": "Plain-language caregiving (JIST companion)",
        "domains": ["medical", "caregiver", "caregivee"],
        "cite_processor": None,
        "accessibility_export": True,
        "decision_authority": "prepare_only",
    },
}


def packs_root() -> Path:
    return PACKS_ROOT


def list_pack_ids() -> list[str]:
    ids = set(_BUILTIN.keys())
    if PACKS_ROOT.is_dir():
        for p in PACKS_ROOT.iterdir():
            if p.is_dir() and (p / "STYLE.yaml").is_file():
                ids.add(p.name)
    return sorted(ids)


def load_pack(style_id: str) -> dict[str, Any]:
    path = PACKS_ROOT / style_id / "STYLE.yaml"
    if path.is_file():
        try:
            import yaml  # type: ignore

            data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
            if isinstance(data, dict):
                data.setdefault("style_id", style_id)
                return data
        except Exception:  # noqa: BLE001
            # minimal YAML-less parse: key: value lines
            data = {"style_id": style_id}
            for line in path.read_text(encoding="utf-8").splitlines():
                if ":" in line and not line.strip().startswith("#"):
                    k, v = line.split(":", 1)
                    data[k.strip()] = v.strip().strip("\"'")
            return data
    return dict(_BUILTIN.get(style_id) or {"style_id": style_id, "name": style_id})


def recommend_style(
    text: str,
    *,
    doc_kind: str | None = None,
    category: str | None = None,
) -> dict[str, Any]:
    """Heuristic genre → style_id (prepare-only recommendation)."""
    t = (text or "")[:8000].lower()
    kind = (doc_kind or "").lower()
    cat = (category or "").lower()
    scores: dict[str, float] = {sid: 0.0 for sid in list_pack_ids()}

    def bump(sid: str, n: float) -> None:
        if sid in scores:
            scores[sid] += n
        else:
            scores[sid] = n

    # Scientific / ACL / methods paper
    if re.search(
        r"\b(abstract|introduction|methods?|results?|discussion|hypothesis|"
        r"references|doi:|arxiv|peer.?review|imrad|conclusion)\b",
        t,
    ):
        bump("scientific-imrad-icmje", 4.0)
        bump("ama", 1.5)
        bump("apa-7", 1.0)
    if re.search(r"\b(clinical trial|randomized|cohort|p\s*<|confidence interval)\b", t):
        bump("scientific-imrad-icmje", 2.0)
        bump("ama", 2.0)

    # Legal
    if re.search(r"\b(plaintiff|defendant|u\.s\.c\.|case no\.|bluebook|whereas)\b", t):
        bump("cmos-notes-bib", 2.0)
    if re.search(r"\b(power of attorney|guardianship|summons)\b", t) or kind == "legal":
        bump("cmos-notes-bib", 2.5)

    # Government
    if re.search(r"\b(federal register|cfr|gpo|department of|honorable)\b", t):
        bump("gpo", 3.0)

    # Caregiving / medical ingest defaults
    if cat in ("medical", "pharmacy_rx", "hospice", "insurance") or kind in (
        "lab_results",
        "clinical_results",
        "medicare",
        "hospice_form",
        "medication_list",
    ):
        # Prefer plain-care for clinical *ingest* over scientific manuscript
        bump("plain-care", 5.5)
        bump("ama", 1.0)
        # dampen false IMRaD hits on short clinical extracts
        if scores.get("scientific-imrad-icmje", 0) and len(t) < 2000:
            scores["scientific-imrad-icmje"] = max(0.0, scores["scientific-imrad-icmje"] - 3.0)

    if not any(scores.values()):
        bump("plain-care", 1.0)

    best = max(scores.items(), key=lambda x: x[1])
    pack = load_pack(best[0])
    return {
        "style_id": best[0],
        "confidence": round(min(1.0, best[1] / 6.0), 2),
        "rationale": f"Heuristic scores lead with {best[0]} ({best[1]:.1f})",
        "pack_summary": {
            "name": pack.get("name"),
            "cite_processor": pack.get("cite_processor"),
            "structure": pack.get("structure"),
        },
        "alternatives": [
            {"style_id": sid, "score": sc}
            for sid, sc in sorted(scores.items(), key=lambda x: -x[1])[1:4]
            if sc > 0
        ],
        "decision_authority": "prepare_only",
    }
