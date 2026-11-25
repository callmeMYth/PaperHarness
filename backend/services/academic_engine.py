"""Core Academic Engine: wraps the 3,000-paper academic-polish skill corpus,
structured audit diagnostics, glossary extraction & checking, fast cached
native-corpus retrieval, reference rule loader, and CJK/EN typography cleaner.
"""
from __future__ import annotations

import json
import math
import re
import sys
from collections import Counter
from functools import lru_cache
from pathlib import Path
from typing import Any

from backend.config import get_skill_dir

# ---------- Structured Audit Engine (grounded in 3,000-paper corpus) ----------
SPLIT_RE = re.compile(r"(?<=[.!?])\s+(?=[A-Z\"])")
ABBR_RE = re.compile(r"\b(e\.g|i\.e|et al|etc|vs|Fig|Eq|Sec|Tab|resp|cf)\.$")

CHINGLISH_OPENERS = {
    "besides": ("4.0x more common in CN than native papers; informal", "Replace with `In addition,` / `Furthermore,` / `Moreover,`"),
    "in this way": ("3.5x more common in CN than native papers", "Use participial `thereby + -ing` or omit"),
    "meanwhile": ("3.0x more common in CN when non-temporal", "Use `In addition,` / `Additionally,` unless truly simultaneous"),
    "consequently": ("2.0x more common in CN papers", "Alternate with `Thus,` / `Hence,` / `As a result,`"),
    "specifically": ("2.0x more common in CN papers", "Vary with `In particular,` or state directly"),
    "therefore": ("1.9x more common in CN papers", "Alternate with `Thus,` / `Hence,` or causal clauses"),
    "to this end": ("1.5x more common in CN papers", "Alternate with `To achieve this,` / `Motivated by this,`"),
}

CHINGLISH_PHRASES = [
    (r"\bwe adopt\b|\bis adopted\b", "CN high-freq literal translation (`adopt`, z=+8.2)", "Native authors strongly prefer `we use` / `using` / `we employ`"),
    (r"\bverify the effectiveness\b|\beffectiveness of our proposed\b", "CN cliché experiment phrasing (z=+10.6)", "Rewrite as `we show that our method improves ... by X%`"),
    (r"\bthe experimental results\b|\bexperimental results show\b", "High-freq CN subject (z=+8.6)", "Vary with `Table X shows` / `Our results show` / `We find that`"),
    (r"\bsuperiority of\b", "Overstated tone (z=+6.4)", "Replace with `stronger performance` / `gains over baselines`"),
    (r"\bmore and more\b", "Informal literal translation", "Use `increasing` / `growing`"),
    (r"\bmake an improvement\b|\bdo an experiment\b", "Wordy nominalization / weak verb", "Use `improve` / `conduct an experiment` or `evaluate`"),
    (r"\bwith the rapid development of\b|\bin recent years,\s+deep learning", "Generic CN intro cliché", "Cut broad background; open directly with task & bottleneck"),
    (r"\bin order to\b", "Wordy connector", "Tighten to `to`"),
    (r"\bdue to the fact that\b", "Wordy connector", "Tighten to `because`"),
    (r"\ba large number of\b|\blots of\b|\ba lot of\b", "Wordy / informal quantifier", "Use `numerous` / `many` / `extensive`"),
    (r"\bthe reason is because\b", "Redundant grammar", "Use `the reason is that`"),
    (r"\bdiscuss about\b|\bemphasize on\b", "Preposition error", "Transitive verbs take direct objects: `discuss` / `emphasize`"),
]

AI_WORDS = [
    "delve", "delves", "delving", "pivotal", "intricate", "paramount", "underscore", "underscores",
    "showcase", "showcases", "showcasing", "tapestry", "holistic", "seamless", "seamlessly",
    "groundbreaking", "cutting-edge", "meticulous", "meticulously", "realm", "landscape",
    "harness", "harnessing", "testament", "game-changer", "revolutionize", "revolutionizing",
]

OVERCLAIM = [
    (r"\bprove[sd]?\b", "Avoid `prove` without formal theorem proof", "Use `demonstrate` / `show` / `indicate`"),
    (r"\bcompletely solve[sd]?\b|\bperfectly\b|\balways\b|\bnever\b", "Absolute claim (Overclaim)", "Hedge cleanly: `effectively mitigates` / `consistently`"),
    (r"\bsignificantly\b", "Reserve `significantly` for statistical significance tests", "Use `substantially` / `notably` / `markedly` without p-values"),
    (r"\bobviously\b|\bundoubtedly\b|\bclearly\b", "Subjective assertive adverb", "Remove or support directly with quantitative evidence"),
]

DECORATIVE_ADVERBS = re.compile(
    r"\b(notably|remarkably|significantly|substantially|dramatically|considerably|importantly|crucially)\b", re.I
)
PASSIVE_RE = re.compile(
    r"\b(is|are|was|were|be|been|being)\s+[a-z]+(ed|en|built|shown|found|done|made|seen|given|taken|used|set)\b", re.I
)
CONTRACTIONS = re.compile(
    r"\b(don't|doesn't|didn't|can't|couldn't|won't|wouldn't|isn't|aren't|wasn't|weren't|it's|that's|we're|they're|haven't|hasn't)\b",
    re.I,
)


def _strip_latex_noise(text: str) -> str:
    t = re.sub(r"(?<!\\)%.*", "", text)
    t = re.sub(r"\\begin\{(?:equation|align|gather)\*?\}.*?\\end\{(?:equation|align|gather)\*?\}", " [MATH] ", t, flags=re.S)
    t = re.sub(r"\$\$.*?\$\$", " [MATH] ", t, flags=re.S)
    t = re.sub(r"\$[^$\n]+\$", "[MATH]", t)
    t = re.sub(r"\\cite[a-zA-Z]*\*?(?:\[[^\]]*\])*\{[^}]*\}", "[CITE]", t)
    t = re.sub(r"\\(?:ref|eqref|autoref|cref|Cref)\{[^}]*\}", "[REF]", t)
    t = re.sub(r"\\(?:section|subsection|subsubsection|paragraph)\*?\{[^}]*\}", "", t)
    t = re.sub(r"\\(?:textbf|textit|emph|texttt)\{([^}]*)\}", r"\1", t)
    return t


def _split_sentences(para: str) -> list[str]:
    raw, out, buf = SPLIT_RE.split(para.strip()), [], ""
    for s in raw:
        buf = f"{buf} {s}".strip() if buf else s
        if ABBR_RE.search(buf):
            continue
        if len(buf.split()) >= 3:
            out.append(buf)
        buf = ""
    if buf and len(buf.split()) >= 3:
        out.append(buf)
    return out


def audit_manuscript(text: str) -> dict[str, Any]:
    """Run full deterministic 3,000-paper baseline audit, returning rich JSON for HUD + table."""
    clean = _strip_latex_noise(text)
    paras = [p.strip() for p in re.split(r"\n\s*\n", clean) if len(p.strip().split()) >= 8]
    all_sents: list[str] = []
    findings: list[dict[str, Any]] = []

    counts = {
        "chinglish": 0,
        "ai_ism": 0,
        "overclaim": 0,
        "long_sentence": 0,
        "contraction": 0,
        "style": 0,
    }

    for pi, para in enumerate(paras, 1):
        sents = _split_sentences(para)
        all_sents.extend(sents)

        advs = DECORATIVE_ADVERBS.findall(para)
        if len(advs) >= 2:
            counts["style"] += 1
            findings.append({
                "id": f"f-{len(findings)+1}",
                "severity": "P2",
                "category": "Adverb Stacking",
                "bucket": "style",
                "location": f"P{pi}",
                "matched": ", ".join(advs),
                "detail": f"{len(advs)} decorative adverbs in one paragraph ({', '.join(advs)})",
                "suggestion": "Keep <= 1 decorative adverb per paragraph; let verbs and numbers carry impact",
                "sentence": para[:160],
            })

        passive_run = 0
        openers: list[str] = []
        for si, s in enumerate(sents, 1):
            loc = f"P{pi}.S{si}"
            words = s.split()
            low = s.lower()

            if len(words) > 40:
                counts["long_sentence"] += 1
                findings.append({
                    "id": f"f-{len(findings)+1}",
                    "severity": "P1",
                    "category": "Long Sentence",
                    "bucket": "long_sentence",
                    "location": loc,
                    "matched": f"{len(words)} words",
                    "detail": f"{len(words)} words (native target 18–25 words/sent)",
                    "suggestion": "Split into 2 crisp sentences with explicit topic continuity",
                    "sentence": s,
                })

            for op, (why, fix) in CHINGLISH_OPENERS.items():
                if low.startswith(op + ",") or low.startswith(op + " "):
                    counts["chinglish"] += 1
                    findings.append({
                        "id": f"f-{len(findings)+1}",
                        "severity": "P2",
                        "category": "Chinglish Opener",
                        "bucket": "chinglish",
                        "location": loc,
                        "matched": op,
                        "detail": why,
                        "suggestion": fix,
                        "sentence": s,
                    })

            for pat, why, fix in CHINGLISH_PHRASES:
                m = re.search(pat, s, re.I)
                if m:
                    counts["chinglish"] += 1
                    findings.append({
                        "id": f"f-{len(findings)+1}",
                        "severity": "P1",
                        "category": "Chinglish / Wordy",
                        "bucket": "chinglish",
                        "location": loc,
                        "matched": m.group(0),
                        "detail": why,
                        "suggestion": fix,
                        "sentence": s,
                    })

            ai_hits = sorted(set(w for w in AI_WORDS if re.search(rf"\b{re.escape(w)}\b", low)))
            if ai_hits:
                counts["ai_ism"] += len(ai_hits)
                findings.append({
                    "id": f"f-{len(findings)+1}",
                    "severity": "P1",
                    "category": "AI-ism Buzzword",
                    "bucket": "ai_ism",
                    "location": loc,
                    "matched": ", ".join(ai_hits),
                    "detail": f"Detected LLM-overused vocabulary: {', '.join(ai_hits)}",
                    "suggestion": "Replace with plain, precise academic verbs/adjectives",
                    "sentence": s,
                })

            for pat, why, fix in OVERCLAIM:
                m = re.search(pat, s, re.I)
                if m:
                    counts["overclaim"] += 1
                    findings.append({
                        "id": f"f-{len(findings)+1}",
                        "severity": "P1",
                        "category": "Overclaim / Tone",
                        "bucket": "overclaim",
                        "location": loc,
                        "matched": m.group(0),
                        "detail": why,
                        "suggestion": fix,
                        "sentence": s,
                    })

            cm = CONTRACTIONS.search(s)
            if cm:
                counts["contraction"] += 1
                findings.append({
                    "id": f"f-{len(findings)+1}",
                    "severity": "P0",
                    "category": "Informal Contraction",
                    "bucket": "contraction",
                    "location": loc,
                    "matched": cm.group(0),
                    "detail": f"Informal contraction `{cm.group(0)}` in academic prose",
                    "suggestion": "Expand to full form (e.g., `do not`, `it is`)",
                    "sentence": s,
                })

            if PASSIVE_RE.search(s) and not re.search(r"\bwe\s+[a-z]+", low):
                passive_run += 1
                if passive_run == 3:
                    counts["style"] += 1
                    findings.append({
                        "id": f"f-{len(findings)+1}",
                        "severity": "P2",
                        "category": "Passive Streak",
                        "bucket": "style",
                        "location": loc,
                        "matched": "3+ passive sentences",
                        "detail": "3 consecutive passive-voice sentences",
                        "suggestion": "Interleave active voice (`We ...` / `Table X shows ...`)",
                        "sentence": s,
                    })
            else:
                passive_run = 0

            first_word = re.sub(r"[^a-z]", "", words[0].lower()) if words else ""
            openers.append(first_word)
            if len(openers) >= 3 and openers[-1] == openers[-2] == openers[-3] and first_word:
                counts["style"] += 1
                findings.append({
                    "id": f"f-{len(findings)+1}",
                    "severity": "P2",
                    "category": "Repeated Opener",
                    "bucket": "style",
                    "location": loc,
                    "matched": first_word,
                    "detail": f"3 consecutive sentences opening with `{first_word}`",
                    "suggestion": "Vary openings (`While ...`, prepositional phrases, or participles)",
                    "sentence": s,
                })

    n_sents = max(1, len(all_sents))
    avg_len = round(sum(len(s.split()) for s in all_sents) / n_sents, 1) if all_sents else 0.0
    while_cnt = sum(1 for s in all_sents if s.lower().startswith("while "))

    # Compute a clean 0-100 Native Fluency Score grounded in findings density
    penalty = (
        counts["contraction"] * 10
        + counts["ai_ism"] * 7
        + counts["chinglish"] * 5
        + counts["overclaim"] * 6
        + counts["long_sentence"] * 4
        + counts["style"] * 3
    )
    if all_sents and (avg_len > 29 or avg_len < 13):
        penalty += 6
    score = max(15, min(100, int(round(100 - penalty * (8 / max(6, len(all_sents)))))))

    order = {"P0": 0, "P1": 1, "P2": 2}
    findings.sort(key=lambda x: order[x["severity"]])

    return {
        "score": score,
        "summary": {
            "paragraphs": len(paras),
            "sentences": len(all_sents),
            "words": len(clean.split()),
            "avg_sentence_len": avg_len,
            "target_sentence_len": "18–25",
            "while_contrast_count": while_cnt,
            "total_issues": len(findings),
            "counts": counts,
        },
        "findings": findings,
    }


# ---------- Glossary Engine (wraps skill glossary.py logic) ----------
def extract_glossary(text: str) -> dict[str, Any]:
    skill_dir = get_skill_dir()
    dl_terms: list[dict[str, str]] = []
    if skill_dir and (skill_dir / "scripts").exists():
        scripts_path = str(skill_dir / "scripts")
        if scripts_path not in sys.path:
            sys.path.insert(0, scripts_path)
        try:
            import glossary as gl_mod  # type: ignore

            dl_terms = gl_mod.load_dl_terms()
        except Exception:
            dl_terms = []

    acr_re = re.compile(r"\b([A-Za-z][a-zA-Z0-9\-]*(?:\s+[A-Za-z][a-zA-Z0-9\-]*){1,5})\s*\(([A-Z][A-Z0-9\-]{1,10}s?)\)")
    stop_lead = {"the", "a", "an", "of", "in", "on", "for", "with", "to", "and", "or", "by", "as", "from", "our", "its", "this", "that", "called", "named", "known", "using", "via"}

    def trim_exp(phrase: str, acr: str) -> str:
        words = phrase.split()
        while len(words) > 2 and words[0].lower() in stop_lead:
            words.pop(0)
        first = acr[0].lower()
        for i, w in enumerate(words):
            if w[0].lower() == first and len(words) - i >= 2:
                return " ".join(words[i:])
        return " ".join(words)

    acronyms: dict[str, str] = {}
    for full, acr in acr_re.findall(text):
        base = acr[:-1] if acr.endswith("s") and len(acr) > 3 else acr
        if len(base) >= 2 and base not in {"FIG", "TAB", "EQ", "SEC", "PDF", "URL", "HTTP", "HTTPS"}:
            acronyms.setdefault(base, trim_exp(full.strip(), base))

    low = text.lower()
    seen_en: set[str] = set()
    matched_terms = []
    for t in dl_terms:
        key = t["en"].lower()
        if key in seen_en:
            continue
        en_cnt = len(re.findall(r"\b" + re.escape(key) + r"s?\b", low))
        zh_cnt = text.count(t["zh"])
        if en_cnt > 0 or zh_cnt > 0:
            seen_en.add(key)
            matched_terms.append({
                "en": t["en"],
                "zh": t["zh"],
                "count": en_cnt + zh_cnt,
                "locked": True,
            })
    matched_terms.sort(key=lambda x: -x["count"])

    proper = Counter(re.findall(r"\b(?:[A-Z][a-z]+[A-Z][A-Za-z0-9\-]*|[A-Z]{2,}[0-9]+(?:[A-Za-z]+)?)\b", text))
    keep_as_is = [k for k, v in proper.most_common(25) if v >= 1]

    # Quick consistency warnings
    issues = []
    for acr, full in acronyms.items():
        if re.search(rf"\b{re.escape(acr)}\b", text) and f"({acr})" not in text:
            issues.append({"type": "Acronym", "term": acr, "detail": f"Used without `({acr})` definition"})
    en_drift = [
        ("component_noun", ["module", "block", "unit"]),
        ("method_ref", ["our method", "our approach", "our framework", "the proposed method", "the proposed approach"]),
    ]
    for concept, variants in en_drift:
        hits = [(v, len(re.findall(rf"\b{re.escape(v)}\b", low))) for v in variants]
        hits = [(v, c) for v, c in hits if c > 0]
        if len(hits) >= 3:
            issues.append({
                "type": "Terminology Drift",
                "term": concept,
                "detail": ", ".join(f"`{v}` ({c}x)" for v, c in hits),
            })

    return {
        "acronyms": [{"acr": k, "full": v, "zh": ""} for k, v in sorted(acronyms.items())],
        "terms": matched_terms[:40],
        "keep_as_is": keep_as_is,
        "issues": issues,
    }


# ---------- Cached 3,000-Paper Corpus Retrieval (BM25 in-memory fast index) ----------
TOK_RE = re.compile(r"[a-z][a-z\-]+")
STOP_WORDS = set(
    "the a an of to in and or for on with by is are was were be been this that these those we our it its as at from which can".split()
)


def _build_bm25_index_from_jsonl(jsonl_path: Path, pack_id: str, pack_name: str) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    postings: dict[str, list[tuple[int, int]]] = {}
    doc_lens: list[int] = []
    if not jsonl_path.exists():
        return {"rows": [], "postings": {}, "idf": {}, "doc_lens": [], "avg_len": 1.0, "pack_id": pack_id, "pack_name": pack_name}

    with jsonl_path.open(encoding="utf-8") as fh:
        for line in fh:
            if not line.strip():
                continue
            try:
                r = json.loads(line)
            except Exception:
                continue
            idx = len(rows)
            r.setdefault("pack_id", pack_id)
            r.setdefault("pack_name", pack_name)
            rows.append(r)
            toks = [t for t in TOK_RE.findall(r.get("text", "").lower()) if t not in STOP_WORDS]
            doc_lens.append(len(toks))
            tf = Counter(toks)
            for term, cnt in tf.items():
                postings.setdefault(term, []).append((idx, cnt))

    N = max(1, len(rows))
    avg_len = sum(doc_lens) / N
    idf = {t: math.log(1 + (N - len(plist) + 0.5) / (len(plist) + 0.5)) for t, plist in postings.items()}
    return {
        "rows": rows,
        "postings": postings,
        "idf": idf,
        "doc_lens": doc_lens,
        "avg_len": avg_len,
        "pack_id": pack_id,
        "pack_name": pack_name,
    }


@lru_cache(maxsize=1)
def _load_base_corpus_index() -> dict[str, Any]:
    skill_dir = get_skill_dir()
    if not skill_dir:
        return _build_bm25_index_from_jsonl(Path("__none__"), "base-dl-3000", "Base 3k Corpus")
    return _build_bm25_index_from_jsonl(skill_dir / "data" / "examples.jsonl", "base-dl-3000", "Base 3k Corpus")


_CUSTOM_PACK_CACHE: dict[str, tuple[float, dict[str, Any]]] = {}


def invalidate_custom_pack_cache(pack_id: str | None = None) -> None:
    if pack_id:
        _CUSTOM_PACK_CACHE.pop(pack_id, None)
    else:
        _CUSTOM_PACK_CACHE.clear()


def _load_custom_pack_index(pack_dir: Path, pack_id: str, pack_name: str) -> dict[str, Any]:
    ex_path = pack_dir / "examples.jsonl"
    if not ex_path.exists():
        return _build_bm25_index_from_jsonl(ex_path, pack_id, pack_name)
    mtime = ex_path.stat().st_mtime
    cached = _CUSTOM_PACK_CACHE.get(pack_id)
    if cached and cached[0] == mtime:
        return cached[1]
    built = _build_bm25_index_from_jsonl(ex_path, pack_id, pack_name)
    _CUSTOM_PACK_CACHE[pack_id] = (mtime, built)
    return built


def _score_bm25_index(
    idx_data: dict[str, Any],
    qt: Counter,
    section: str | None,
    group: str,
    weight: float,
    limit: int,
) -> list[tuple[float, dict[str, Any]]]:
    rows = idx_data["rows"]
    if not rows:
        return []
    postings = idx_data["postings"]
    idf = idx_data["idf"]
    doc_lens = idx_data["doc_lens"]
    avg_len = idx_data["avg_len"]
    # Normalize by log(2 + N) so small custom lab packs compete fairly against the 104k-sentence base pack!
    scale_norm = 1.0 / max(1.0, math.log(2.0 + len(rows)))
    k1, b = 1.5, 0.75
    scores: dict[int, float] = {}
    for term, q_cnt in qt.items():
        plist = postings.get(term)
        if not plist:
            continue
        term_idf = idf[term] * scale_norm * (1 + math.log(1 + q_cnt))
        for doc_id, tf in plist:
            r = rows[doc_id]
            if group != "all" and r.get("group") not in (group, "lab_gold"):
                continue
            if section and section != "any" and r.get("section") != section:
                continue
            dl = doc_lens[doc_id]
            s = term_idf * tf * (k1 + 1) / (tf + k1 * (1 - b + b * dl / avg_len))
            scores[doc_id] = scores.get(doc_id, 0.0) + s * weight

    top_ids = sorted(scores.keys(), key=lambda i: -scores[i])[: limit * 2]
    return [(scores[i], rows[i]) for i in top_ids]


def retrieve_native_examples(
    query: str,
    section: str | None = None,
    group: str = "native",
    k: int = 6,
) -> dict[str, Any]:
    """Sub-100ms multi-pack weighted BM25 search across base 3,000-paper pack + all enabled custom packs."""
    from backend.config import DATA_DIR

    qt = Counter(t for t in TOK_RE.findall(query.lower()) if t not in STOP_WORDS)
    if not qt:
        return {"corpus_size": 0, "active_packs": 0, "results": []}

    # Check base pack enabled/weight state
    state_file = DATA_DIR / "pack_state.json"
    base_enabled, base_weight = True, 1.0
    if state_file.exists():
        try:
            st = json.loads(state_file.read_text(encoding="utf-8"))
            base_enabled = st.get("base_enabled", True)
            base_weight = float(st.get("base_weight", 1.0))
        except Exception:
            pass

    total_corpus_size = 0
    active_packs = 0
    candidates: list[tuple[float, dict[str, Any]]] = []

    if base_enabled:
        base_idx = _load_base_corpus_index()
        total_corpus_size += len(base_idx["rows"])
        if base_idx["rows"]:
            active_packs += 1
            candidates.extend(_score_bm25_index(base_idx, qt, section, group, base_weight, k))

    packs_dir = DATA_DIR / "corpus_packs"
    if packs_dir.exists():
        for pdir in sorted(packs_dir.iterdir()):
            mpath = pdir / "manifest.json"
            if not pdir.is_dir() or not mpath.exists():
                continue
            try:
                m = json.loads(mpath.read_text(encoding="utf-8"))
                if not m.get("enabled", True):
                    continue
                p_idx = _load_custom_pack_index(pdir, m["id"], m["name"])
                total_corpus_size += len(p_idx["rows"])
                if p_idx["rows"]:
                    active_packs += 1
                    candidates.extend(
                        _score_bm25_index(p_idx, qt, section, group, float(m.get("weight", 1.4)), k)
                    )
            except Exception:
                continue

    candidates.sort(key=lambda pair: -pair[0])
    results = []
    seen: set[str] = set()
    for sc, r in candidates:
        txt = r.get("text", "")
        if txt in seen:
            continue
        seen.add(txt)
        results.append({
            "text": txt,
            "prev": (r.get("prev") or "")[:200],
            "section": r.get("section", "other"),
            "venue": r.get("venue", ""),
            "year": r.get("year", ""),
            "group": r.get("group", "native"),
            "pack_name": r.get("pack_name", "Base 3k Corpus"),
            "score": round(sc, 3),
        })
        if len(results) >= k:
            break

    return {"corpus_size": total_corpus_size, "active_packs": active_packs, "results": results}


# ---------- Skill Reference Loader ----------
MODE_REFS: dict[str, list[str]] = {
    "zh2en": ["zh2en_rules.md", "dl_terminology.md"],
    "polish": ["polish_rules.md", "chinglish_patterns.md"],
    "mimic": ["format_mimicry.md", "zh2en_rules.md"],
    "en2zh": ["en2zh_rules.md", "glossary_workflow.md"],
    "review": ["presubmission_review.md", "chinglish_patterns.md"],
    "audit": ["chinglish_patterns.md", "polish_rules.md"],
}


def load_skill_context(mode: str, section: str = "introduction") -> str:
    """Load targeted reference rules & section phrasebank from academic-polish-plugin."""
    skill_dir = get_skill_dir()
    if not skill_dir:
        return ""
    refs_dir = skill_dir / "references"
    chunks: list[str] = []
    for fname in MODE_REFS.get(mode, ["polish_rules.md"]):
        p = refs_dir / fname
        if p.exists():
            txt = p.read_text(encoding="utf-8")
            # Keep context crisp and token-efficient
            chunks.append(f"### Reference: {fname}\n{txt[:3600]}")

    pb = refs_dir / "phrasebank" / f"{section}.md"
    if pb.exists():
        chunks.append(f"### Phrasebank ({section})\n{pb.read_text(encoding='utf-8')[:2200]}")

    return "\n\n".join(chunks)


# ---------- Deterministic CJK & Academic Typography Cleaner ----------
PROTECT_RE = re.compile(
    r"(```[\s\S]*?```|`[^`\n]+`|\$\$[\s\S]*?\$\$|\$[^$\n]+\$|\\begin\{(?:equation|align|gather|table|tabular)\*?\}[\s\S]*?\\end\{(?:equation|align|gather|table|tabular)\*?\}|\\[a-zA-Z]+\*?(?:\[[^\]]*\])?(?:\{[^{}]*\})+)"
)


def clean_typography(
    text: str,
    mode: str = "auto",
    cjk_latin_space: bool = False,
) -> dict[str, Any]:
    """Normalize punctuation and spacing while strictly preserving LaTeX, math, citations, and code.

    - Chinese context: converts stray half-width `, . ; : ? ! ( )` adjacent to CJK characters into
      full-width Chinese punctuation, strips redundant spaces between Chinese characters, and
      enforces configurable CJK-Latin spacing (`cjk_latin_space`).
    - English context: strips double spaces, fixes space before punctuation, normalizes smart quotes
      and non-breaking spaces, keeps `\\cite{}` / `~\\ref{}` spacing clean.
    """
    tokens: list[str] = []

    def _mask(m: re.Match) -> str:
        idx = len(tokens)
        tokens.append(m.group(0))
        return f"\uE000TOK{idx}\uE001"

    masked = PROTECT_RE.sub(_mask, text)
    changes: list[str] = []

    cjk_chars = len(re.findall(r"[\u4e00-\u9fff]", masked))
    latin_chars = len(re.findall(r"[A-Za-z]", masked))
    is_zh = mode == "zh" or (mode == "auto" and cjk_chars > max(10, latin_chars * 0.25))

    out = masked
    if is_zh:
        # 1. Remove redundant spaces between Chinese characters
        new_out, n1 = re.subn(r"([\u4e00-\u9fff])[ \t]+([\u4e00-\u9fff])", r"\1\2", out)
        if n1:
            changes.append(f"Removed {n1} redundant space(s) between Chinese characters")
        out = new_out

        # 2. Convert half-width punctuation immediately after/between CJK into full-width
        # Parentheses wrapping Chinese content first so trailing period after `）` converts cleanly
        out, n3 = re.subn(r"\(([^()\n]*[\u4e00-\u9fff][^()\n]*)\)", r"（\1）", out)
        punct_map = {",": "，", ";": "；", ":": "：", "?": "？", "!": "！"}
        for hw, fw in punct_map.items():
            out, c = re.subn(rf"([\u4e00-\u9fff）】》”])[ \t]*{re.escape(hw)}", rf"\1{fw}", out)
            n3 += c
        # Period after CJK or Chinese closing bracket (avoid decimal numbers or file extensions)
        out, c_dot = re.subn(r"([\u4e00-\u9fff）】》”])[ \t]*\.(?!\d)", r"\1。", out)
        n3 += c_dot
        if n3:
            changes.append(f"Normalized {n3} half-width punctuation mark(s) to Chinese full-width")

        # 3. Remove spaces before/after Chinese full-width punctuation
        new_out, n2 = re.subn(r"[ \t]*([，。；：？！、（）【】《》“”])[ \t]*", r"\1", out)
        if n2:
            changes.append(f"Trimmed spaces around {n2} Chinese punctuation marks")
        out = new_out

        # 4. CJK-Latin/Digit spacing policy
        if cjk_latin_space:
            out, s1 = re.subn(r"([\u4e00-\u9fff])([A-Za-z0-9])", r"\1 \2", out)
            out, s2 = re.subn(r"([A-Za-z0-9])([\u4e00-\u9fff])", r"\1 \2", out)
            if s1 + s2:
                changes.append(f"Inserted {s1 + s2} CJK–Latin readability space(s)")
        else:
            out, s1 = re.subn(r"([\u4e00-\u9fff])[ \t]+([A-Za-z0-9])", r"\1\2", out)
            out, s2 = re.subn(r"([A-Za-z0-9])[ \t]+([\u4e00-\u9fff])", r"\1\2", out)
            if s1 + s2:
                changes.append(f"Stripped {s1 + s2} space(s) between Chinese and Latin/numbers (journal compact mode)")
    else:
        # English academic typography
        out, n_multi = re.subn(r" {2,}", " ", out)
        if n_multi:
            changes.append(f"Collapsed {n_multi} duplicate space(s)")
        out, n_sp = re.subn(r" +([,.;:!?])", r"\1", out)
        if n_sp:
            changes.append(f"Removed {n_sp} stray space(s) before punctuation")
        out, n_fw = re.subn(r"[，。；：（）]", lambda m: {"，": ", ", "。": ". ", "；": "; ", "：": ": ", "（": " (", "）": ") "}[m.group(0)], out)
        if n_fw:
            changes.append(f"Converted {n_fw} stray full-width punctuation mark(s) to English ASCII")
        out = re.sub(r" {2,}", " ", out)

    # Restore protected math/LaTeX/code blocks untouched
    for idx, tok in enumerate(tokens):
        out = out.replace(f"\uE000TOK{idx}\uE001", tok)

    # Clean trailing whitespace per line
    out = "\n".join(line.rstrip() for line in out.splitlines())

    return {
        "detected_lang": "zh" if is_zh else "en",
        "original": text,
        "cleaned": out,
        "changed": out != text,
        "changes": changes or ["Typography is already clean — no changes needed."],
    }
