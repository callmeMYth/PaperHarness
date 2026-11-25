"""Incremental Corpus Expansion, Style Distillation & SFT/DPO Training Flywheel.

Designed for continuously adding new papers (arXiv IDs, PDF, LaTeX, Word, JSONL)
into modular, shareable Corpus Packs — seamlessly compatible with `corpus_builder`
(`corpus.jsonl` / `examples.jsonl` / `embeddings_i8.npz`) and hot-reloaded into
the PaperHarness Agent without restarting!
"""
from __future__ import annotations

import io
import json
import math
import re
import zipfile
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from backend.config import DATA_DIR, PROJECT_ROOT, get_skill_dir
from backend.services.doc_io import (
    import_arxiv_paper,
    import_docx_bytes,
    import_pdf_bytes,
    import_tex_bytes,
)

PACKS_DIR = DATA_DIR / "corpus_packs"
PACKS_DIR.mkdir(parents=True, exist_ok=True)
FEEDBACK_FILE = DATA_DIR / "feedback_pairs.jsonl"
PACK_STATE_FILE = DATA_DIR / "pack_state.json"

CORPUS_BUILDER_DIR = PROJECT_ROOT.parent / "corpus_builder"

# Same section canon & sentence filtering rules as corpus_builder/clean_latex.py & build_index.py
SECTION_MAP = [
    ("abstract", r"abstract"),
    ("introduction", r"introduc"),
    ("related_work", r"related|background|prior work|literature|preliminar"),
    ("conclusion", r"conclu|discussion|limitation|future work|summary|broader impact"),
    ("experiments", r"experiment|evaluat|result|ablation|analysis|empirical|benchmark|implementation detail|setup|setting"),
    ("method", r"method|approach|model|framework|architecture|proposed|our |formulation|algorithm|design|overview|network|learning|training"),
]

SPLIT_RE = re.compile(r"(?<=[.!?])\s+(?=[A-Z\[])")
ABBR_RE = re.compile(r"\b(e\.g|i\.e|et al|etc|vs|Fig|Eq|Sec|Tab|resp|cf)\.$")
WORD_RE = re.compile(r"[A-Za-z][A-Za-z\-']*|\[MATH\]|\[CITE\]|\[REF\]")
STOP_WORDS = set("the a an of to in and or for on with by is are was were be been this that these those it its as at from which".split())

TRANSITIONS = [
    "however", "moreover", "furthermore", "in addition", "additionally", "therefore", "thus", "hence",
    "consequently", "as a result", "in contrast", "meanwhile", "specifically", "in particular", "notably",
    "besides", "finally", "overall", "to this end", "in this way", "nevertheless", "on the other hand",
    "importantly", "instead", "similarly", "unlike", "while", "although", "given", "to address",
]


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


def _canon_section(heading: str) -> str:
    h = heading.lower()
    for name, pat in SECTION_MAP:
        if re.search(pat, h):
            return name
    return "other"


def _clean_text_to_corpus_style(text: str) -> str:
    """Normalize inline LaTeX math/citations/refs identically to corpus_builder/clean_latex.py."""
    t = re.sub(r"(?<!\\)%.*", "", text)
    t = re.sub(r"\\(?:cite[a-zA-Z]*|citep|citet|citealp)\*?(\[[^\]]*\])*\{[^}]*\}", "[CITE]", t)
    t = re.sub(r"\\(?:eqref|autoref|cref|Cref|ref|pageref)\{[^}]*\}", "[REF]", t)
    t = re.sub(r"\\label\{[^}]*\}|\\footnote\{[^{}]*\}", "", t)
    t = re.sub(r"\\begin\{(?:equation|align|gather)\*?\}[\s\S]*?\\end\{(?:equation|align|gather)\*?\}", " [MATH] ", t, flags=re.S)
    t = re.sub(r"\$\$.*?\$\$|\\\[.*?\\\]|\\\(.*?\\\)", " [MATH] ", t, flags=re.S)
    t = re.sub(r"(?<!\\)\$[^$\n]{1,400}?(?<!\\)\$", "[MATH]", t)
    for _ in range(2):
        t = re.sub(r"\\(?:textbf|textit|emph|underline|texttt|textsc|textrm|mathrm|text)\{([^{}]*)\}", r"\1", t)
    t = re.sub(r"\\[a-zA-Z@]+\*?(\[[^\]]*\])?(\{[^{}]*\})*", " ", t)
    t = re.sub(r"[{}~]", " ", t)
    t = re.sub(r"(\[MATH\]\s*){2,}", "[MATH] ", t)
    t = re.sub(r"(\[CITE\][\s,;]*){2,}", "[CITE] ", t)
    return re.sub(r"\s+", " ", t).strip()


def _split_sentences(text: str) -> list[str]:
    raw, out, buf = SPLIT_RE.split(text), [], ""
    for s in raw:
        buf = f"{buf} {s}".strip() if buf else s
        if ABBR_RE.search(buf):
            continue
        out.append(buf)
        buf = ""
    if buf:
        out.append(buf)
    return out


def _is_good_sentence(s: str) -> bool:
    w = s.split()
    if not (8 <= len(w) <= 65):
        return False
    if s.rstrip().endswith((":", ",", ";")) or s.count("[MATH]") > 3 or s.count("[REF]") > 3:
        return False
    cjk = len(re.findall(r"[\u4e00-\u9fff]", s))
    if cjk >= 12:
        return True  # Allow clean Chinese academic sentences for Chinese packs
    return sum(c.isalpha() for c in s) / max(1, len(s)) > 0.68


def _load_base_pack_state() -> dict[str, Any]:
    if PACK_STATE_FILE.exists():
        try:
            return json.loads(PACK_STATE_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {"base_enabled": True, "base_weight": 1.0}


def _save_base_pack_state(st: dict[str, Any]) -> None:
    PACK_STATE_FILE.write_text(json.dumps(st, ensure_ascii=False, indent=2), encoding="utf-8")


# ---------- Pack Discovery & CRUD ----------
def list_corpus_packs() -> dict[str, Any]:
    """List the mounted base 3,000-paper pack plus all custom incremental lab packs."""
    packs: list[dict[str, Any]] = []
    base_state = _load_base_pack_state()
    skill_dir = get_skill_dir()

    if skill_dir and (skill_dir / "data" / "examples.jsonl").exists():
        ex_path = skill_dir / "data" / "examples.jsonl"
        emb_path = skill_dir / "data" / "embeddings_i8.npz"
        # Fast cached size metadata
        sz_mb = round(ex_path.stat().st_size / (1024 * 1024), 1)
        emb_mb = round(emb_path.stat().st_size / (1024 * 1024), 1) if emb_path.exists() else 0.0
        packs.append({
            "id": "base-dl-3000",
            "name": "Base Top-Venue DL Corpus (3,000 Papers)",
            "domain": "Deep Learning · CV · NLP · ML",
            "venue": "NeurIPS / ICML / CVPR / ICCV / ACL / TPAMI",
            "language": "en",
            "readonly": True,
            "enabled": base_state.get("base_enabled", True),
            "weight": float(base_state.get("base_weight", 1.0)),
            "paper_count": 3000,
            "sentence_count": 104474,
            "has_vectors": emb_path.exists(),
            "size_mb": round(sz_mb + emb_mb, 1),
            "updated_at": "Built-in Baseline",
            "papers": [],
            "style_profile": None,
        })

    for pdir in sorted(PACKS_DIR.iterdir()):
        manifest_path = pdir / "manifest.json"
        if not pdir.is_dir() or not manifest_path.exists():
            continue
        try:
            m = json.loads(manifest_path.read_text(encoding="utf-8"))
            prof_path = pdir / "style_profile.json"
            m["style_profile"] = json.loads(prof_path.read_text(encoding="utf-8")) if prof_path.exists() else None
            total_bytes = sum(f.stat().st_size for f in pdir.glob("*") if f.is_file())
            m["size_mb"] = round(total_bytes / (1024 * 1024), 2)
            m["readonly"] = False
            packs.append(m)
        except Exception:
            continue

    cb_corpus = CORPUS_BUILDER_DIR / "data" / "corpus.jsonl"
    feedback_count = 0
    if FEEDBACK_FILE.exists():
        feedback_count = sum(1 for ln in FEEDBACK_FILE.open(encoding="utf-8") if ln.strip())

    return {
        "packs": packs,
        "corpus_builder_detected": cb_corpus.exists(),
        "corpus_builder_path": str(cb_corpus) if cb_corpus.exists() else None,
        "corpus_builder_mb": round(cb_corpus.stat().st_size / (1024 * 1024), 1) if cb_corpus.exists() else 0.0,
        "feedback_count": feedback_count,
    }


def create_corpus_pack(
    name: str,
    domain: str = "Custom Lab Domain",
    venue: str = "CVPR / NeurIPS",
    language: str = "en",
    weight: float = 1.4,
) -> dict[str, Any]:
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-") or "pack"
    pack_id = f"{slug[:28]}-{datetime.now(timezone.utc).strftime('%H%M%S')}"
    pdir = PACKS_DIR / pack_id
    pdir.mkdir(parents=True, exist_ok=True)
    manifest = {
        "id": pack_id,
        "name": name.strip(),
        "domain": domain.strip(),
        "venue": venue.strip(),
        "language": language,
        "enabled": True,
        "weight": float(weight),
        "paper_count": 0,
        "sentence_count": 0,
        "has_vectors": False,
        "updated_at": _now_iso(),
        "papers": [],
    }
    (pdir / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    (pdir / "examples.jsonl").write_text("", encoding="utf-8")
    (pdir / "paragraphs.jsonl").write_text("", encoding="utf-8")
    return manifest


def update_pack_settings(pack_id: str, enabled: bool | None = None, weight: float | None = None) -> dict[str, Any]:
    if pack_id == "base-dl-3000":
        st = _load_base_pack_state()
        if enabled is not None:
            st["base_enabled"] = enabled
        if weight is not None:
            st["base_weight"] = max(0.1, min(5.0, float(weight)))
        _save_base_pack_state(st)
        return {"ok": True, **st}

    mpath = PACKS_DIR / pack_id / "manifest.json"
    if not mpath.exists():
        raise FileNotFoundError(f"Pack `{pack_id}` not found.")
    m = json.loads(mpath.read_text(encoding="utf-8"))
    if enabled is not None:
        m["enabled"] = enabled
    if weight is not None:
        m["weight"] = max(0.1, min(5.0, float(weight)))
    mpath.write_text(json.dumps(m, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"ok": True, "manifest": m}


def delete_corpus_pack(pack_id: str) -> dict[str, Any]:
    if pack_id == "base-dl-3000":
        raise ValueError("Base 3,000-paper pack cannot be deleted (you can toggle it off).")
    pdir = PACKS_DIR / pack_id
    if pdir.exists():
        for f in pdir.glob("*"):
            if f.is_file():
                f.unlink()
        pdir.rmdir()
    return {"ok": True}


# ---------- Incremental Paper Ingestion (PDF / TeX / DOCX / MD / JSONL / arXiv) ----------
def _content_to_section_paragraphs(content: str) -> list[tuple[str, str, str]]:
    """Parse raw imported paper content into (section, heading, cleaned_paragraph) tuples."""
    cur_head = "Body"
    cur_sec = "other"
    out: list[tuple[str, str, str]] = []
    normalized = re.sub(r"(\\(?:sub)*section\*?\{(?:[^{}]|\{[^{}]*\})*\})\s*\n(?!\n)", r"\1\n\n", content.strip())
    normalized = re.sub(r"^(#{1,4}\s+.+)\n(?!\n)", r"\1\n\n", normalized, flags=re.M)

    for blk in re.split(r"\n\s*\n", normalized):
        b = blk.strip()
        if not b:
            continue
        m_tex = re.match(r"^\\(?:sub)*section\*?\{((?:[^{}]|\{[^{}]*\})*)\}$", b)
        m_md = re.match(r"^#{1,4}\s+(.+)$", b)
        if m_tex or m_md:
            cur_head = (m_tex.group(1) if m_tex else m_md.group(1)).strip()
            if re.search(r"appendix|supplementary|reference|bibliography|acknowledg", cur_head, re.I):
                break
            cur_sec = _canon_section(cur_head)
            continue
        cleaned = _clean_text_to_corpus_style(b)
        if len(cleaned.split()) >= 12 or len(re.findall(r"[\u4e00-\u9fff]", cleaned)) >= 25:
            out.append((cur_sec, cur_head[:80], cleaned))
    return out


def ingest_paper_into_pack(
    pack_id: str,
    title: str,
    content: str,
    source_id: str,
    venue: str = "Custom",
    year: int = 2026,
    group: str = "native",
    max_per_paper: int = 45,
) -> dict[str, Any]:
    """Incrementally clean, segment, deduplicate, append to pack JSONL, and update style profile."""
    pdir = PACKS_DIR / pack_id
    mpath = pdir / "manifest.json"
    if not mpath.exists():
        raise FileNotFoundError(f"Corpus pack `{pack_id}` not found.")

    manifest = json.loads(mpath.read_text(encoding="utf-8"))
    sec_paras = _content_to_section_paragraphs(content)

    # Deduplicate against existing sentences in pack
    ex_path = pdir / "examples.jsonl"
    para_path = pdir / "paragraphs.jsonl"
    seen_sents: set[str] = set()
    if ex_path.exists():
        for ln in ex_path.open(encoding="utf-8"):
            try:
                seen_sents.add(json.loads(ln).get("text", ""))
            except Exception:
                continue

    new_paras: list[dict[str, Any]] = []
    new_rows: list[dict[str, Any]] = []
    for sec, head, ptxt in sec_paras:
        new_paras.append({
            "arxiv": source_id,
            "group": group,
            "venue": venue,
            "year": year,
            "section": sec,
            "heading": head,
            "text": ptxt,
        })
        sents = _split_sentences(ptxt)
        for i, s in enumerate(sents):
            if len(new_rows) >= max_per_paper:
                break
            if not _is_good_sentence(s) or s in seen_sents:
                continue
            seen_sents.add(s)
            new_rows.append({
                "text": s,
                "prev": sents[i - 1] if i > 0 else "",
                "section": sec,
                "group": group,
                "venue": venue,
                "year": year,
                "arxiv": source_id,
                "pack_id": pack_id,
            })

    with para_path.open("a", encoding="utf-8") as pfh:
        for pr in new_paras:
            pfh.write(json.dumps(pr, ensure_ascii=False) + "\n")
    with ex_path.open("a", encoding="utf-8") as efh:
        for r in new_rows:
            efh.write(json.dumps(r, ensure_ascii=False) + "\n")

    manifest["paper_count"] = int(manifest.get("paper_count", 0)) + 1
    manifest["sentence_count"] = int(manifest.get("sentence_count", 0)) + len(new_rows)
    manifest["updated_at"] = _now_iso()
    manifest.setdefault("papers", []).append({
        "id": source_id,
        "title": title[:120],
        "venue": venue,
        "year": year,
        "group": group,
        "paragraphs": len(new_paras),
        "sentences": len(new_rows),
        "added_at": _now_iso(),
    })
    mpath.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    # Automatically refresh empirical style profile for this pack
    profile = distill_pack_style_profile(pack_id)
    return {
        "ok": True,
        "paper_title": title,
        "paragraphs_added": len(new_paras),
        "sentences_added": len(new_rows),
        "manifest": manifest,
        "style_profile": profile,
    }


def ingest_uploaded_file_into_pack(
    pack_id: str,
    filename: str,
    data: bytes,
    venue: str = "Custom",
    year: int = 2026,
    group: str = "native",
) -> dict[str, Any]:
    ext = Path(filename).suffix.lower()
    if ext == ".jsonl":
        # Direct batch JSONL ingestion (compatible with corpus_builder/data/corpus.jsonl or examples.jsonl!)
        pdir = PACKS_DIR / pack_id
        mpath = pdir / "manifest.json"
        if not mpath.exists():
            raise FileNotFoundError(f"Pack `{pack_id}` not found.")
        manifest = json.loads(mpath.read_text(encoding="utf-8"))
        ex_path = pdir / "examples.jsonl"
        para_path = pdir / "paragraphs.jsonl"
        added_sents = 0
        paper_ids: set[str] = set()
        with ex_path.open("a", encoding="utf-8") as efh, para_path.open("a", encoding="utf-8") as pfh:
            for line in data.decode("utf-8-sig", errors="replace").splitlines():
                if not line.strip():
                    continue
                obj = json.loads(line)
                txt = obj.get("text", "").strip()
                if not txt:
                    continue
                pid = str(obj.get("arxiv") or obj.get("paper_id") or filename)
                paper_ids.add(pid)
                pfh.write(json.dumps({
                    "arxiv": pid,
                    "group": obj.get("group", group),
                    "venue": obj.get("venue", venue),
                    "year": obj.get("year", year),
                    "section": obj.get("section", "other"),
                    "heading": obj.get("heading", ""),
                    "text": txt,
                }, ensure_ascii=False) + "\n")
                if "prev" in obj:
                    efh.write(json.dumps({**obj, "pack_id": pack_id}, ensure_ascii=False) + "\n")
                    added_sents += 1
                else:
                    sents = _split_sentences(txt)
                    for i, s in enumerate(sents[:25]):
                        if _is_good_sentence(s):
                            efh.write(json.dumps({
                                "text": s,
                                "prev": sents[i - 1] if i > 0 else "",
                                "section": obj.get("section", "other"),
                                "group": obj.get("group", group),
                                "venue": obj.get("venue", venue),
                                "year": obj.get("year", year),
                                "arxiv": pid,
                                "pack_id": pack_id,
                            }, ensure_ascii=False) + "\n")
                            added_sents += 1
        manifest["paper_count"] = int(manifest.get("paper_count", 0)) + max(1, len(paper_ids))
        manifest["sentence_count"] = int(manifest.get("sentence_count", 0)) + added_sents
        manifest["updated_at"] = _now_iso()
        manifest.setdefault("papers", []).append({
            "id": filename,
            "title": f"JSONL Batch: {filename} ({len(paper_ids)} papers)",
            "venue": venue,
            "year": year,
            "group": group,
            "sentences": added_sents,
            "added_at": _now_iso(),
        })
        mpath.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
        profile = distill_pack_style_profile(pack_id)
        return {"ok": True, "paper_title": filename, "sentences_added": added_sents, "manifest": manifest, "style_profile": profile}

    if ext == ".docx":
        doc = import_docx_bytes(filename, data)
    elif ext == ".tex":
        doc = import_tex_bytes(filename, data)
    elif ext == ".pdf":
        doc = import_pdf_bytes(filename, data)
    else:
        txt = data.decode("utf-8-sig", errors="replace")
        doc = {"title": Path(filename).stem, "content": txt}

    return ingest_paper_into_pack(
        pack_id=pack_id,
        title=doc["title"],
        content=doc["content"],
        source_id=Path(filename).stem,
        venue=venue,
        year=year,
        group=group,
    )


def ingest_arxiv_batch(
    pack_id: str,
    arxiv_ids: list[str],
    venue: str = "arXiv",
    year: int = 2026,
    group: str = "native",
) -> dict[str, Any]:
    """Fetch and incrementally train a corpus pack from a list of arXiv IDs."""
    results = []
    total_added = 0
    for raw_id in arxiv_ids:
        aid = raw_id.strip()
        if not aid:
            continue
        try:
            doc = import_arxiv_paper(aid)
            res = ingest_paper_into_pack(
                pack_id=pack_id,
                title=doc["title"],
                content=doc["content"],
                source_id=aid,
                venue=venue,
                year=year,
                group=group,
            )
            total_added += res["sentences_added"]
            results.append({"id": aid, "ok": True, "title": doc["title"], "sentences": res["sentences_added"]})
        except Exception as e:
            results.append({"id": aid, "ok": False, "error": str(e)})
    return {"ok": True, "total_sentences_added": total_added, "items": results}


# ---------- Style Profile Distillation (Ported from corpus_builder/analyze_corpus.py) ----------
def distill_pack_style_profile(pack_id: str) -> dict[str, Any]:
    """Compute empirical style baselines (avg sentence len, top we-verbs, openers, transitions, log-odds)."""
    pdir = PACKS_DIR / pack_id
    ex_path = pdir / "examples.jsonl"
    if not ex_path.exists():
        return {}

    rows = [json.loads(ln) for ln in ex_path.open(encoding="utf-8") if ln.strip()]
    if not rows:
        return {}

    sec_counts: Counter = Counter()
    sent_lens: list[int] = []
    we_verbs: Counter = Counter()
    openers: Counter = Counter()
    transitions: Counter = Counter()
    group_toks: dict[str, Counter] = {"cn": Counter(), "native": Counter()}

    for r in rows:
        sec_counts[r.get("section", "other")] += 1
        txt = r.get("text", "")
        words = txt.split()
        sent_lens.append(len(words))
        toks = [w.lower() for w in WORD_RE.findall(txt)]
        if len(toks) >= 3:
            openers[" ".join(toks[:3])] += 1
        for i, w in enumerate(toks[:-1]):
            if w == "we" and not toks[i + 1].startswith("["):
                we_verbs[toks[i + 1]] += 1
        low = txt.lower()
        for tr in TRANSITIONS:
            if low.startswith(tr + " ") or low.startswith(tr + ","):
                transitions[tr] += 1
        grp = "cn" if r.get("group") == "cn" else "native"
        for w in toks:
            if w not in STOP_WORDS and not w.startswith("[") and len(w) >= 3:
                group_toks[grp][w] += 1

    avg_len = round(sum(sent_lens) / max(1, len(sent_lens)), 1)

    # Optional Monroe log-odds if both native & cn papers exist in this pack
    cn_overused = []
    if sum(group_toks["cn"].values()) >= 200 and sum(group_toks["native"].values()) >= 200:
        prior = group_toks["cn"] + group_toks["native"]
        a0 = sum(prior.values())
        n_cn, n_na = sum(group_toks["cn"].values()), sum(group_toks["native"].values())
        scored = []
        for k, a in prior.items():
            if a < 6:
                continue
            y1, y2 = group_toks["cn"][k], group_toks["native"][k]
            l1 = math.log((y1 + a) / (n_cn + a0 - y1 - a))
            l2 = math.log((y2 + a) / (n_na + a0 - y2 - a))
            z = (l1 - l2) / math.sqrt(1 / (y1 + a) + 1 / (y2 + a))
            scored.append((round(z, 2), k, y1, y2))
        scored.sort(reverse=True)
        cn_overused = [{"phrase": k, "z": z, "cn": y1, "native": y2} for z, k, y1, y2 in scored[:15]]

    profile = {
        "sentence_count": len(rows),
        "avg_sentence_len": avg_len,
        "section_distribution": dict(sec_counts),
        "top_we_verbs": [{"verb": k, "count": v} for k, v in we_verbs.most_common(12)],
        "top_openers": [{"opener": k, "count": v} for k, v in openers.most_common(10)],
        "top_transitions": [{"transition": k, "count": v} for k, v in transitions.most_common(10)],
        "cn_overused_logodds": cn_overused,
        "distilled_at": _now_iso(),
    }
    (pdir / "style_profile.json").write_text(json.dumps(profile, ensure_ascii=False, indent=2), encoding="utf-8")
    return profile


def build_pack_int8_vectors(pack_id: str) -> dict[str, Any]:
    """Build compact int8 BGE vector embeddings for a pack (matches corpus_builder/build_index.py)."""
    pdir = PACKS_DIR / pack_id
    ex_path = pdir / "examples.jsonl"
    mpath = pdir / "manifest.json"
    if not ex_path.exists():
        raise FileNotFoundError(f"Pack `{pack_id}` not found.")
    rows = [json.loads(ln) for ln in ex_path.open(encoding="utf-8") if ln.strip()]
    if not rows:
        raise ValueError("Pack has 0 sentences — ingest papers first.")
    try:
        import numpy as np
        from sentence_transformers import SentenceTransformer
    except ImportError:
        return {
            "ok": False,
            "backend": "bm25_ready",
            "message": "Optional `sentence-transformers` is not installed (BM25 retrieval is already active and instant). Install `pip install sentence-transformers` to enable int8 dense vector indexing.",
        }

    model = SentenceTransformer("BAAI/bge-small-en-v1.5", device="cpu")
    emb = model.encode([r["text"] for r in rows], batch_size=128, normalize_embeddings=True)
    emb = emb.astype(np.float32)
    scale = np.float32(max(1e-8, float(np.max(np.abs(emb)))) / 127.0)
    emb_i8 = np.clip(np.rint(emb / scale), -127, 127).astype(np.int8)
    np.savez(pdir / "embeddings_i8.npz", emb=emb_i8, scale=scale)

    m = json.loads(mpath.read_text(encoding="utf-8"))
    m["has_vectors"] = True
    m["updated_at"] = _now_iso()
    mpath.write_text(json.dumps(m, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"ok": True, "backend": "bge_int8", "sentences_indexed": len(rows)}


# ---------- Pack Sharing (.zip Export / Import for Lab Mates) ----------
def export_pack_zip_bytes(pack_id: str) -> bytes:
    """Package a trained custom Corpus Pack as a portable .zip for teammates (no raw copyrighted PDFs)."""
    pdir = PACKS_DIR / pack_id
    if not pdir.exists():
        raise FileNotFoundError(f"Pack `{pack_id}` not found.")
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for fname in ("manifest.json", "examples.jsonl", "style_profile.json", "embeddings_i8.npz"):
            fp = pdir / fname
            if fp.exists():
                zf.write(fp, arcname=fname)
    return buf.getvalue()


def import_pack_zip_bytes(data: bytes) -> dict[str, Any]:
    """Import a colleague's shared Corpus Pack .zip directly into PaperHarness."""
    with zipfile.ZipFile(io.BytesIO(data), "r") as zf:
        if "manifest.json" not in zf.namelist():
            raise ValueError("Invalid pack archive: missing manifest.json")
        manifest = json.loads(zf.read("manifest.json").decode("utf-8"))
        pid = re.sub(r"[^a-zA-Z0-9_-]+", "-", str(manifest.get("id") or "imported-pack"))
        pdir = PACKS_DIR / pid
        pdir.mkdir(parents=True, exist_ok=True)
        for fname in ("manifest.json", "examples.jsonl", "style_profile.json", "embeddings_i8.npz"):
            if fname in zf.namelist():
                (pdir / fname).write_bytes(zf.read(fname))
        return manifest


# ---------- Human Feedback Flywheel & SFT / DPO Fine-Tuning Export ----------
def record_edit_feedback(
    original: str,
    revised: str,
    tag: str,
    reason: str,
    decision: str,
    venue: str = "CVPR / ICCV",
    mode: str = "polish",
) -> dict[str, Any]:
    """Log every Accept / Reject decision to build a lab-specific preference dataset."""
    row = {
        "timestamp": _now_iso(),
        "decision": decision,
        "mode": mode,
        "venue": venue,
        "tag": tag,
        "reason": reason,
        "original": original,
        "revised": revised,
    }
    with FEEDBACK_FILE.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, ensure_ascii=False) + "\n")
    return {"ok": True}


def export_training_dataset_jsonl(
    fmt: str = "sft_openai",
    include_pack_ids: list[str] | None = None,
    max_corpus_samples: int = 300,
) -> tuple[str, int]:
    """Export fine-tuning dataset (SFT ChatML / ShareGPT / DPO) for LLaMA-Factory, Unsloth, or OpenAI."""
    lines: list[str] = []

    # 1. Include real human-verified Accept/Reject feedback pairs first (highest signal!)
    fb_rows: list[dict[str, Any]] = []
    if FEEDBACK_FILE.exists():
        for ln in FEEDBACK_FILE.open(encoding="utf-8"):
            if ln.strip():
                try:
                    fb_rows.append(json.loads(ln))
                except Exception:
                    continue

    if fmt == "dpo_preference":
        for r in fb_rows:
            prompt = f"Polish this academic sentence for {r.get('venue', 'CVPR')} style without changing facts or math:\n{r['original']}"
            if r.get("decision") == "accepted":
                lines.append(json.dumps({
                    "prompt": prompt,
                    "chosen": r["revised"],
                    "rejected": r["original"],
                    "meta": {"tag": r.get("tag"), "venue": r.get("venue")},
                }, ensure_ascii=False))
            elif r.get("decision") == "rejected":
                lines.append(json.dumps({
                    "prompt": prompt,
                    "chosen": r["original"],
                    "rejected": r["revised"],
                    "meta": {"tag": r.get("tag"), "venue": r.get("venue")},
                }, ensure_ascii=False))
        return "\n".join(lines), len(lines)

    # SFT format (OpenAI ChatML or LLaMA-Factory ShareGPT)
    for r in fb_rows:
        if r.get("decision") != "accepted":
            continue
        sys_p = f"You are an expert academic editor specializing in {r.get('venue', 'top-venue')} papers."
        usr_p = f"Polish the following academic sentence ({r.get('tag', 'Style')}):\n{r['original']}"
        if fmt == "sharegpt_llamafactory":
            lines.append(json.dumps({
                "conversations": [
                    {"from": "system", "value": sys_p},
                    {"from": "human", "value": usr_p},
                    {"from": "gpt", "value": r["revised"]},
                ]
            }, ensure_ascii=False))
        else:
            lines.append(json.dumps({
                "messages": [
                    {"role": "system", "content": sys_p},
                    {"role": "user", "content": usr_p},
                    {"role": "assistant", "content": r["revised"]},
                ]
            }, ensure_ascii=False))

    # 2. Add contextual continuation / style-alignment pairs from custom packs
    target_packs = include_pack_ids or [p.name for p in PACKS_DIR.iterdir() if p.is_dir()]
    budget = max_corpus_samples
    for pid in target_packs:
        if budget <= 0:
            break
        ex_path = PACKS_DIR / pid / "examples.jsonl"
        if not ex_path.exists():
            continue
        for ln in ex_path.open(encoding="utf-8"):
            if budget <= 0:
                break
            if not ln.strip():
                continue
            r = json.loads(ln)
            if not r.get("prev"):
                continue
            sys_p = f"Continue academic prose in native {r.get('venue', 'top-venue')} {r.get('section', 'method')} style."
            usr_p = f"Previous sentence:\n{r['prev']}\n\nWrite the next concise academic sentence:"
            if fmt == "sharegpt_llamafactory":
                lines.append(json.dumps({
                    "conversations": [
                        {"from": "system", "value": sys_p},
                        {"from": "human", "value": usr_p},
                        {"from": "gpt", "value": r["text"]},
                    ]
                }, ensure_ascii=False))
            else:
                lines.append(json.dumps({
                    "messages": [
                        {"role": "system", "content": sys_p},
                        {"role": "user", "content": usr_p},
                        {"role": "assistant", "content": r["text"]},
                    ]
                }, ensure_ascii=False))
            budget -= 1

    return "\n".join(lines), len(lines)


def get_active_custom_style_guidance() -> str:
    """Build a crisp prompt block summarizing enabled custom packs' distilled styles for the Agent."""
    info = list_corpus_packs()
    blocks: list[str] = []
    for p in info["packs"]:
        if p.get("readonly") or not p.get("enabled"):
            continue
        prof = p.get("style_profile")
        if not prof or prof.get("sentence_count", 0) == 0:
            continue
        verbs = ", ".join(v["verb"] for v in prof.get("top_we_verbs", [])[:8])
        openers = ", ".join(f'"{o["opener"]}"' for o in prof.get("top_openers", [])[:5])
        blocks.append(
            f"- Custom Pack `{p['name']}` ({p['domain']}, weight {p['weight']}x, {p['paper_count']} papers): "
            f"target avg sentence length {prof['avg_sentence_len']} words; "
            f"preferred `we` verbs: {verbs or 'N/A'}; common openers: {openers or 'N/A'}."
        )
    return "\n".join(blocks)
