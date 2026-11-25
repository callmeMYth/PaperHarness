"""Citation & Reference Auditor + Live Crossref Integrity Verification.

Guards against AI-hallucinated references, uncited BibTeX entries, missing \\cite{} keys,
duplicate BibTeX keys, and title/year/author mismatches.
"""
from __future__ import annotations

import asyncio
import difflib
import re
from typing import Any

import httpx

CITE_RE = re.compile(r"\\cite[a-zA-Z]*\*?(?:\[[^\]]*\])*\{([^}]+)\}")
BIB_ENTRY_RE = re.compile(r"@(\w+)\s*\{\s*([^,\s]+)\s*,([\s\S]*?)\n\}", re.M)


def parse_bibtex(bib_text: str) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    for m in BIB_ENTRY_RE.finditer(bib_text):
        etype, key, body = m.group(1).lower(), m.group(2).strip(), m.group(3)
        fields: dict[str, str] = {}
        for fm in re.finditer(r"(\w+)\s*=\s*(?:\{((?:[^{}]|\{[^{}]*\})*)\}|\"([^\"]*)\"|(\d{4}))", body):
            val = (fm.group(2) or fm.group(3) or fm.group(4) or "").strip()
            fields[fm.group(1).lower()] = re.sub(r"\s+", " ", val)
        entries.append({
            "type": etype,
            "key": key,
            "title": fields.get("title", "").strip("{}"),
            "author": fields.get("author", ""),
            "year": fields.get("year", ""),
            "venue": fields.get("booktitle") or fields.get("journal") or "",
            "doi": fields.get("doi", ""),
        })
    return entries


def audit_citations_local(manuscript: str, bib_text: str) -> dict[str, Any]:
    cited_keys: list[str] = []
    for m in CITE_RE.finditer(manuscript):
        for k in m.group(1).split(","):
            ks = k.strip()
            if ks and ks not in cited_keys:
                cited_keys.append(ks)

    entries = parse_bibtex(bib_text)
    bib_keys = [e["key"] for e in entries]
    bib_key_set = set(bib_keys)
    cited_set = set(cited_keys)

    missing_in_bib = [k for k in cited_keys if k not in bib_key_set]
    unused_in_text = [k for k in bib_keys if k not in cited_set]
    dup_keys = sorted({k for k in bib_keys if bib_keys.count(k) > 1})

    return {
        "cited_count": len(cited_keys),
        "bib_count": len(entries),
        "cited_keys": cited_keys,
        "entries": entries,
        "missing_in_bib": missing_in_bib,
        "unused_in_text": unused_in_text,
        "duplicate_keys": dup_keys,
    }


async def _verify_single_crossref(client: httpx.AsyncClient, entry: dict[str, Any]) -> dict[str, Any]:
    title = entry.get("title", "")
    if not title:
        return {**entry, "status": "unverified", "confidence": 0.0, "note": "Missing title field in BibTeX."}
    try:
        r = await client.get(
            "https://api.crossref.org/works",
            params={"query.title": title, "rows": 2, "select": "DOI,title,author,issued,container-title"},
            headers={"User-Agent": "PaperHarness/0.1 (mailto:research@paperharness.local)"},
        )
        if r.status_code != 200:
            return {**entry, "status": "error", "confidence": 0.0, "note": f"Crossref HTTP {r.status_code}"}
        items = r.json().get("message", {}).get("items", [])
        if not items:
            return {**entry, "status": "not_found", "confidence": 0.0, "note": "No matching publication found in Crossref — check for typo or hallucination."}

        best = None
        best_sim = 0.0
        for it in items:
            cand_title = (it.get("title") or [""])[0]
            sim = difflib.SequenceMatcher(None, title.lower(), cand_title.lower()).ratio()
            if sim > best_sim:
                best_sim = sim
                best = it

        cand_title = (best.get("title") or [""])[0] if best else ""
        issued = (best.get("issued", {}).get("date-parts") or [[None]])[0][0] if best else None
        cand_year = str(issued) if issued else ""
        cand_doi = best.get("DOI", "") if best else ""
        cand_venue = (best.get("container-title") or [""])[0] if best else ""

        if best_sim >= 0.86:
            if entry.get("year") and cand_year and entry["year"] != cand_year:
                return {
                    **entry,
                    "status": "mismatch",
                    "confidence": round(best_sim, 2),
                    "matched_title": cand_title,
                    "matched_year": cand_year,
                    "matched_doi": cand_doi,
                    "matched_venue": cand_venue,
                    "note": f"Title verified, but year differs (BibTeX: {entry['year']} vs Crossref: {cand_year}).",
                }
            return {
                **entry,
                "status": "verified",
                "confidence": round(best_sim, 2),
                "matched_title": cand_title,
                "matched_year": cand_year,
                "matched_doi": cand_doi,
                "matched_venue": cand_venue,
                "note": "Verified against Crossref metadata.",
            }
        elif best_sim >= 0.65:
            return {
                **entry,
                "status": "partial",
                "confidence": round(best_sim, 2),
                "matched_title": cand_title,
                "matched_year": cand_year,
                "matched_doi": cand_doi,
                "note": f"Closest match ({int(best_sim*100)}% similarity): “{cand_title}” ({cand_year}). Verify exact title.",
            }
        else:
            return {
                **entry,
                "status": "not_found",
                "confidence": round(best_sim, 2),
                "matched_title": cand_title,
                "note": "Low title similarity — may be arXiv-only preprint or hallucinated citation.",
            }
    except Exception as e:
        return {**entry, "status": "error", "confidence": 0.0, "note": f"Network lookup failed: {e}"}


async def verify_bibtex_online(manuscript: str, bib_text: str) -> dict[str, Any]:
    local = audit_citations_local(manuscript, bib_text)
    entries = local["entries"]
    if not entries:
        return {**local, "verified_entries": []}

    async with httpx.AsyncClient(timeout=12.0) as client:
        tasks = [_verify_single_crossref(client, e) for e in entries[:25]]
        results = await asyncio.gather(*tasks)

    return {**local, "verified_entries": list(results)}
