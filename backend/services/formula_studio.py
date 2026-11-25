"""Interactive Formula Composer, Placement Recommender & Symbol Consistency Engine.

Gives authors BOTH:
1. AI/heuristic Recommended Placement Anchors between/inside paragraphs (Display vs Inline, with rationale).
2. Full Manual Placement Control (move equation up/down across paragraphs, switch Inline <-> Display,
   edit LaTeX, and automatically synchronize contextual equation references `Eq. (k)` and trailing punctuation).
3. Paper-wide Symbol Consistency Audit (flags conflicting styles like `x` vs `\\mathbf{x}` and generates a Notation Table).
"""
from __future__ import annotations

import re
from collections import defaultdict
from typing import Any

EQ_BLOCK_RE = re.compile(
    r"(\\begin\{(?:equation|align)\*?\}([\s\S]*?)\\end\{(?:equation|align)\*?\}|\$\$([\s\S]*?)\$\$)",
    re.S,
)
INLINE_MATH_RE = re.compile(r"(?<!\$)\$([^$\n]{1,120})\$(?!\$)")


def split_paragraphs_preserving_blocks(text: str) -> list[dict[str, Any]]:
    """Split manuscript into addressable blocks (headings, prose paragraphs, display equations)."""
    # Ensure LaTeX section commands and Markdown headings are always separated as standalone blocks
    normalized = re.sub(
        r"(\\(?:sub)*section\*?\{(?:[^{}]|\{[^{}]*\})*\})\s*\n(?!\n)",
        r"\1\n\n",
        text.strip(),
    )
    normalized = re.sub(r"^(#{1,4}\s+.+)\n(?!\n)", r"\1\n\n", normalized, flags=re.M)
    raw_blocks = [b.strip() for b in re.split(r"\n\s*\n", normalized) if b.strip()]
    blocks: list[dict[str, Any]] = []
    eq_counter = 0

    for raw in raw_blocks:
        # Check if a display equation is embedded inside a paragraph
        eq_matches = list(EQ_BLOCK_RE.finditer(raw))
        if not eq_matches:
            is_head = bool(re.match(r"^(?:\\(?:sub)*section\*?\{(?:[^{}]|\{[^{}]*\})*\}|#{1,4}\s+[^\n]+)$", raw))
            blocks.append({"id": f"blk-{len(blocks)}", "kind": "heading" if is_head else "paragraph", "text": raw})
            continue

        pos = 0
        for m in eq_matches:
            before = raw[pos : m.start()].strip()
            if before:
                blocks.append({"id": f"blk-{len(blocks)}", "kind": "paragraph", "text": before})
            eq_counter += 1
            body = (m.group(2) if m.group(2) is not None else m.group(3) or "").strip()
            lbl_m = re.search(r"\\label\{([^}]+)\}", body)
            label = lbl_m.group(1) if lbl_m else f"eq:auto_{eq_counter}"
            clean_latex = re.sub(r"\\label\{[^}]+\}", "", body).strip()
            blocks.append({
                "id": f"eq-{eq_counter}",
                "kind": "equation",
                "display": True,
                "number": eq_counter,
                "label": label,
                "latex": clean_latex,
                "raw": m.group(0),
            })
            pos = m.end()
        after = raw[pos:].strip()
        if after:
            blocks.append({"id": f"blk-{len(blocks)}", "kind": "paragraph", "text": after})

    return blocks


def analyze_formulas_and_placements(text: str) -> dict[str, Any]:
    """Extract equations, audit notation consistency, and recommend optimal insertion anchors."""
    blocks = split_paragraphs_preserving_blocks(text)
    equations = [b for b in blocks if b["kind"] == "equation"]

    # Symbol extraction & consistency audit
    symbol_variants: dict[str, set[str]] = defaultdict(set)
    all_math_spans = [e["latex"] for e in equations] + INLINE_MATH_RE.findall(text)

    for span in all_math_spans:
        for bm in re.findall(r"\\(?:mathbf|boldsymbol|mathcal|mathbb)\{([A-Za-z])\}|\\([a-zA-Z]+)", span):
            if bm[0]:
                full = re.search(rf"\\(?:mathbf|boldsymbol|mathcal|mathbb)\{{{bm[0]}\}}", span)
                if full:
                    symbol_variants[bm[0].lower()].add(full.group(0))
        for plain in re.findall(r"(?<![\\A-Za-z])([A-Za-z])(?![A-Za-z])", re.sub(r"\\[a-zA-Z]+(?:\{[^{}]*\})?", " ", span)):
            if plain not in ("i", "j", "k", "m", "n", "t", "d", "a"):
                symbol_variants[plain.lower()].add(plain)

    symbol_conflicts = []
    for base, forms in sorted(symbol_variants.items()):
        if len(forms) >= 2 and any("\\mathbf" in f for f in forms) and any(len(f) == 1 for f in forms):
            symbol_conflicts.append({
                "symbol": base,
                "variants": sorted(forms),
                "suggestion": f"Verify whether scalar `{base}` and vector/matrix `{next(f for f in forms if 'mathbf' in f)}` refer to distinct quantities; keep notation consistent.",
            })

    # Recommend optimal insertion anchors for new equations
    recommendations: list[dict[str, Any]] = []
    trigger_re = re.compile(
        r"\b(formulate|objective|loss|optimization|saliency|probability|score|similarity|attention|distance|weighted|budget-constrained|define)\b",
        re.I,
    )
    for idx, blk in enumerate(blocks):
        if blk["kind"] != "paragraph":
            continue
        next_is_eq = idx + 1 < len(blocks) and blocks[idx + 1]["kind"] == "equation"
        if next_is_eq:
            continue
        hits = trigger_re.findall(blk["text"])
        if hits:
            kw = hits[0].lower()
            suggested_latex = (
                r"\mathcal{L}_{\text{total}} = \mathcal{L}_{\text{task}} + \lambda \left(\frac{|\mathcal{R}|}{N} - \rho\right)^2"
                if kw in ("formulate", "objective", "loss", "optimization", "budget-constrained")
                else r"\mathrm{Score}(\mathbf{x}_i, \mathbf{q}) = \frac{\mathbf{x}_i^\top \mathbf{q}}{\|\mathbf{x}_i\|_2 \|\mathbf{q}\|_2}"
            )
            recommendations.append({
                "id": f"rec-{idx}",
                "after_block_index": idx,
                "recommended_mode": "display",
                "trigger": kw,
                "rationale": f"Paragraph introduces `{kw}` without an explicit formal expression — inserting a numbered display equation immediately after clarifies mathematical rigor.",
                "suggested_latex": suggested_latex,
                "suggested_label": f"eq:{kw}",
                "suggested_where": r"where $\lambda > 0$ balances task fidelity against the target token budget ratio $\rho$.",
            })

    return {
        "blocks": blocks,
        "equations": equations,
        "symbol_conflicts": symbol_conflicts,
        "recommendations": recommendations[:5],
    }


def rebuild_manuscript_from_blocks(
    blocks: list[dict[str, Any]],
    sync_refs: bool = True,
    lang: str = "en",
) -> dict[str, Any]:
    """Reassemble manuscript after user manually moves/inserts/toggles equations, syncing punctuation & numbering."""
    out_parts: list[str] = []
    eq_num = 0
    old_to_new: dict[int, int] = {}

    for i, blk in enumerate(blocks):
        kind = blk.get("kind", "paragraph")
        if kind == "equation":
            eq_num += 1
            old_n = blk.get("number")
            if isinstance(old_n, int):
                old_to_new[old_n] = eq_num
            latex = (blk.get("latex") or "").strip()
            label = blk.get("label") or f"eq:eq_{eq_num}"
            is_display = blk.get("display", True)

            # Smart trailing punctuation based on next paragraph starting with "where" / "其中"
            next_txt = blocks[i + 1].get("text", "").lstrip() if i + 1 < len(blocks) else ""
            follows_where = bool(re.match(r"^(where\b|其中)", next_txt, re.I))
            clean_body = re.sub(r"[.,，。]\s*$", "", latex)
            punct = "," if follows_where else "."

            if is_display:
                eq_str = f"\\begin{{equation}}\n{clean_body}{punct}\n\\label{{{label}}}\n\\end{{equation}}"
                out_parts.append(eq_str)
            else:
                # Attach inline formula gracefully to previous paragraph
                if out_parts:
                    out_parts[-1] = out_parts[-1].rstrip() + f" ${clean_body}$"
                else:
                    out_parts.append(f"${clean_body}$")
        else:
            out_parts.append((blk.get("text") or "").strip())

    rebuilt = "\n\n".join(p for p in out_parts if p)

    # Synchronize explicit `Eq. (k)` / `Equation (k)` / `式(k)` references if numbers shifted
    synced_refs = 0
    if sync_refs and any(k != v for k, v in old_to_new.items()):
        def _repl_ref(m: re.Match) -> str:
            nonlocal synced_refs
            old_idx = int(m.group(2))
            if old_idx in old_to_new and old_to_new[old_idx] != old_idx:
                synced_refs += 1
                return f"{m.group(1)}{old_to_new[old_idx]}{m.group(3)}"
            return m.group(0)

        rebuilt = re.sub(r"((?:Eq\.|Equation|式)\s*[（(])(\d+)([)）])", _repl_ref, rebuilt)

    return {
        "content": rebuilt,
        "equation_count": eq_num,
        "synced_references": synced_refs,
    }
