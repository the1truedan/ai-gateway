#!/usr/bin/env python3
"""Accessibility resource catalog (SQLite) — A.C.C.E.S.S. vault table."""

from __future__ import annotations

import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def default_db_path(ingest_root: Path | None = None) -> Path:
    env = os.environ.get("AIDA_CATALOG_DB", "").strip()
    if env:
        return Path(env).expanduser()
    if ingest_root:
        return Path(ingest_root) / "_config" / "accessibility_catalog.db"
    return Path(
        os.environ.get("AIDA_INGEST_ROOT", "/Volumes/ai-data/work/ingest")
    ) / "_config" / "accessibility_catalog.db"


def _conn(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(str(db_path))
    c.row_factory = sqlite3.Row
    return c


def init_db(db_path: Path | None = None) -> Path:
    path = db_path or default_db_path()
    conn = _conn(path)
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS accessibility_resources (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            resource_title TEXT,
            source_url_or_path TEXT UNIQUE,
            type TEXT,
            category TEXT,
            wcag_score REAL,
            composite_score REAL,
            pdf_ua_pass INTEGER,
            issues_found TEXT,
            remediation_status TEXT DEFAULT 'pending',
            hitl_screen_reader TEXT DEFAULT 'pending',
            report_id TEXT,
            linked_caregiving_context TEXT,
            last_tested TEXT,
            ingested_at TEXT DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS hitl_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            report_id TEXT,
            field TEXT,
            value TEXT,
            notes TEXT,
            actor TEXT,
            at TEXT
        );
        """
    )
    conn.commit()
    conn.close()
    return path


def upsert_resource(
    *,
    title: str,
    source: str,
    rtype: str = "pdf",
    category: str | None = None,
    wcag_score: float | None = None,
    composite_score: float | None = None,
    pdf_ua_pass: bool | None = None,
    issues: list[str] | None = None,
    remediation_status: str = "pending",
    hitl_screen_reader: str = "pending",
    report_id: str | None = None,
    context: str | None = None,
    db_path: Path | None = None,
) -> dict[str, Any]:
    path = init_db(db_path)
    conn = _conn(path)
    now = datetime.now(timezone.utc).isoformat()
    pdf_ua_int = None if pdf_ua_pass is None else (1 if pdf_ua_pass else 0)
    conn.execute(
        """
        INSERT INTO accessibility_resources (
            resource_title, source_url_or_path, type, category,
            wcag_score, composite_score, pdf_ua_pass, issues_found,
            remediation_status, hitl_screen_reader, report_id,
            linked_caregiving_context, last_tested
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(source_url_or_path) DO UPDATE SET
            resource_title=excluded.resource_title,
            type=excluded.type,
            category=excluded.category,
            wcag_score=excluded.wcag_score,
            composite_score=excluded.composite_score,
            pdf_ua_pass=excluded.pdf_ua_pass,
            issues_found=excluded.issues_found,
            remediation_status=excluded.remediation_status,
            hitl_screen_reader=excluded.hitl_screen_reader,
            report_id=excluded.report_id,
            linked_caregiving_context=excluded.linked_caregiving_context,
            last_tested=excluded.last_tested
        """,
        (
            title,
            source,
            rtype,
            category,
            wcag_score,
            composite_score,
            pdf_ua_int,
            "; ".join(issues or [])[:2000],
            remediation_status,
            hitl_screen_reader,
            report_id,
            context,
            now,
        ),
    )
    conn.commit()
    conn.close()
    return {"status": "ok", "db": str(path), "source": source, "last_tested": now}


def list_resources(limit: int = 50, db_path: Path | None = None) -> list[dict[str, Any]]:
    path = init_db(db_path)
    conn = _conn(path)
    rows = conn.execute(
        """
        SELECT resource_title, source_url_or_path, type, category, wcag_score,
               composite_score, pdf_ua_pass, remediation_status, hitl_screen_reader,
               report_id, last_tested
        FROM accessibility_resources
        ORDER BY last_tested DESC
        LIMIT ?
        """,
        (limit,),
    ).fetchall()
    conn.close()
    out = []
    for r in rows:
        d = dict(r)
        if d.get("pdf_ua_pass") is not None:
            d["pdf_ua_pass"] = bool(d["pdf_ua_pass"])
        out.append(d)
    return out


def log_hitl(
    report_id: str,
    *,
    field: str,
    value: str,
    notes: str = "",
    actor: str = "admin",
    db_path: Path | None = None,
) -> dict[str, Any]:
    path = init_db(db_path)
    conn = _conn(path)
    now = datetime.now(timezone.utc).isoformat()
    conn.execute(
        "INSERT INTO hitl_log (report_id, field, value, notes, actor, at) VALUES (?,?,?,?,?,?)",
        (report_id, field, value, notes, actor, now),
    )
    if field == "hitl_screen_reader":
        conn.execute(
            """
            UPDATE accessibility_resources
            SET hitl_screen_reader = ?, last_tested = ?
            WHERE report_id = ?
            """,
            (value, now, report_id),
        )
    if field == "remediation_status":
        conn.execute(
            """
            UPDATE accessibility_resources
            SET remediation_status = ?, last_tested = ?
            WHERE report_id = ?
            """,
            (value, now, report_id),
        )
    conn.commit()
    conn.close()
    return {"status": "ok", "report_id": report_id, "field": field, "value": value, "at": now}
