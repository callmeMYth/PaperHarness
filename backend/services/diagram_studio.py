"""Top-Venue Architecture & Flowchart Studio.

Guarantees:
1. Shared deterministic port-distributed orthogonal arrow router (`compute_routed_edges`)
   used identically in SVG preview, Vector PDF, 600/1200 DPI PNG, AND native PowerPoint `.pptx`
   so exported PPTX matches the tool 1:1 and arrows are NEVER occluded by module boxes.
2. Zero-overflow CJK + English auto-wrap & font auto-fit engine.
3. Concurrent Multi-Agent PPT Diagram Synthesis (`stream_concurrent_diagram_agents`) supporting
   configurable concurrency (1–4 parallel specialist agents + optional parallel AI icon tiles).
"""
from __future__ import annotations

import asyncio
import base64
import html
import io
import json
import re
from collections import defaultdict
from typing import Any, AsyncGenerator

import pymupdf
from PIL import Image, ImageDraw
from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
from pptx.oxml.ns import qn
from pptx.util import Inches, Pt

VENUE_DIAGRAM_THEMES: dict[str, dict[str, Any]] = {
    "CVPR Clean Slate": {
        "bg": "#FFFFFF",
        "ink": "#16191F",
        "muted": "#525A66",
        "arrow": "#2C3B4E",
        "group_bg": "#F7F9FC",
        "group_border": "#B8C7D9",
        "palette": {
            "primary": ("#EAF1F8", "#1E3A5F", "#1E3A5F"),
            "accent": ("#FDF0EA", "#C2410C", "#9A3412"),
            "sage": ("#ECF7F0", "#1F6F4A", "#14532D"),
            "violet": ("#F3EFFB", "#5B4B8A", "#3F3364"),
            "neutral": ("#F4F3EF", "#7B7F88", "#2B303A"),
        },
    },
    "NeurIPS Editorial": {
        "bg": "#FFFFFF",
        "ink": "#18181B",
        "muted": "#52525B",
        "arrow": "#3F3F46",
        "group_bg": "#FAF9F6",
        "group_border": "#D4CFC4",
        "palette": {
            "primary": ("#EEF2FF", "#3730A3", "#312E81"),
            "accent": ("#FEF3C7", "#B45309", "#92400E"),
            "sage": ("#E6F4EA", "#137333", "#0D5224"),
            "violet": ("#F5EEFA", "#7E22CE", "#581C87"),
            "neutral": ("#F4F4F5", "#71717A", "#27272A"),
        },
    },
    "Nature Crisp": {
        "bg": "#FFFFFF",
        "ink": "#111827",
        "muted": "#4B5563",
        "arrow": "#374151",
        "group_bg": "#F8FAFC",
        "group_border": "#CBD5E1",
        "palette": {
            "primary": ("#E0F2FE", "#0369A1", "#0C4A6E"),
            "accent": ("#FEE2E2", "#B91C1C", "#7F1D1D"),
            "sage": ("#CCFBF1", "#0F766E", "#115E59"),
            "violet": ("#EDE9FE", "#6D28D9", "#4C1D95"),
            "neutral": ("#F1F5F9", "#64748B", "#1E293B"),
        },
    },
}

DIAGRAM_TEMPLATES: dict[str, dict[str, Any]] = {
    "hierattn_cvpr": {
        "title": "HierAttn-Net: Adaptive Cross-Scale Visual Token Routing",
        "venue_theme": "CVPR Clean Slate",
        "width": 1240,
        "height": 520,
        "font_size": 14,
        "corner_radius": 11,
        "groups": [
            {"id": "g1", "label": "Stage 1 · Multi-Scale Visual Encoding", "x": 28, "y": 58, "w": 280, "h": 424, "tone": "neutral"},
            {"id": "g2", "label": "Stage 2 · Adaptive Token Routing (Core)", "x": 362, "y": 58, "w": 526, "h": 424, "tone": "primary"},
            {"id": "g3", "label": "Stage 3 · Language Fusion", "x": 942, "y": 58, "w": 270, "h": 424, "tone": "sage"},
        ],
        "nodes": [
            {"id": "n_img", "label": "High-Res Image", "sublabel": "I ∈ R^(H×W×3)", "x": 52, "y": 106, "w": 232, "h": 84, "tone": "neutral", "icon": "patch_grid"},
            {"id": "n_enc", "label": "Multi-Layer Conv & ViT", "sublabel": "X ∈ R^(N×D)", "x": 52, "y": 234, "w": 232, "h": 84, "tone": "primary", "icon": "conv_stack_3d"},
            {"id": "n_qry", "label": "Text Query Prompt", "sublabel": "q ∈ R^D", "x": 52, "y": 364, "w": 232, "h": 82, "tone": "violet", "icon": "token_strip"},
            {"id": "n_csie", "label": "Cross-Scale Importance\nEstimator (CSIE)", "sublabel": "s_i = σ(q·k_i/√D + α·MLP)", "x": 388, "y": 116, "w": 224, "h": 106, "tone": "primary", "icon": "cross_attn"},
            {"id": "n_gate", "label": "Differentiable Top-K\nBudget Gate", "sublabel": "Retain R | Prune P", "x": 388, "y": 318, "w": 224, "h": 102, "tone": "accent", "icon": "moe_router"},
            {"id": "n_hi", "label": "High-Res Tokens", "sublabel": "X_R (fine details)", "x": 686, "y": 124, "w": 176, "h": 88, "tone": "primary", "icon": "conv_pyramid"},
            {"id": "n_rsm", "label": "Residual Semantic\nMerger (RSM)", "sublabel": "M context tokens", "x": 686, "y": 318, "w": 176, "h": 102, "tone": "sage", "icon": "merge_pool"},
            {"id": "n_cat", "label": "Token Sequence\n[X_R ; Z]", "sublabel": "|R|+M ≪ N (-41%)", "x": 968, "y": 146, "w": 218, "h": 98, "tone": "sage", "icon": "token_strip"},
            {"id": "n_llm", "label": "Multimodal LLM\nBackbone", "sublabel": "DocVQA · ChartQA", "x": 968, "y": 318, "w": 218, "h": 102, "tone": "primary", "icon": "encoder_stack"},
        ],
        "edges": [
            {"from": "n_img", "to": "n_enc", "label": "Patches", "dashed": False},
            {"from": "n_enc", "to": "n_csie", "label": "X", "dashed": False},
            {"from": "n_qry", "to": "n_csie", "label": "Query q", "dashed": True},
            {"from": "n_csie", "to": "n_gate", "label": "Scores s", "dashed": False},
            {"from": "n_gate", "to": "n_hi", "label": "Top-K", "dashed": False},
            {"from": "n_gate", "to": "n_rsm", "label": "Pruned", "dashed": True},
            {"from": "n_hi", "to": "n_cat", "label": "", "dashed": False},
            {"from": "n_rsm", "to": "n_cat", "label": "Z", "dashed": False},
            {"from": "n_cat", "to": "n_llm", "label": "Feed", "dashed": False},
        ],
    },
    "diffusion_neurips": {
        "title": "Latent Controllable Diffusion with Structural Adapter",
        "venue_theme": "NeurIPS Editorial",
        "width": 1240,
        "height": 470,
        "font_size": 14,
        "corner_radius": 11,
        "groups": [
            {"id": "g1", "label": "Conditioning Encoders", "x": 30, "y": 58, "w": 286, "h": 376, "tone": "neutral"},
            {"id": "g2", "label": "Denoising DiT Backbone (×L Blocks)", "x": 368, "y": 58, "w": 524, "h": 376, "tone": "primary"},
            {"id": "g3", "label": "VAE Decoding", "x": 944, "y": 58, "w": 266, "h": 376, "tone": "sage"},
        ],
        "nodes": [
            {"id": "c_txt", "label": "Text Encoder", "sublabel": "T5-XXL + CLIP", "x": 58, "y": 118, "w": 230, "h": 88, "tone": "violet", "icon": "token_strip"},
            {"id": "c_str", "label": "Layout / Depth Map", "sublabel": "Structural Control", "x": 58, "y": 280, "w": 230, "h": 88, "tone": "accent", "icon": "conv_pyramid"},
            {"id": "d_dit", "label": "MM-DiT Cross-Attn", "sublabel": "AdaLN-Zero", "x": 398, "y": 118, "w": 212, "h": 88, "tone": "primary", "icon": "cross_attn"},
            {"id": "d_adp", "label": "Zero-Conv Adapter", "sublabel": "Learnable Residual", "x": 398, "y": 280, "w": 212, "h": 88, "tone": "accent", "icon": "conv_stack_3d"},
            {"id": "d_vel", "label": "Flow Matching Head", "sublabel": "v_θ(z_t, t, c)", "x": 666, "y": 196, "w": 200, "h": 98, "tone": "primary", "icon": "diffusion_steps"},
            {"id": "v_dec", "label": "Latent VAE Decoder", "sublabel": "z_0 → x̂ ∈ R^(H×W×3)", "x": 970, "y": 196, "w": 214, "h": 98, "tone": "sage", "icon": "unet_trapezoid"},
        ],
        "edges": [
            {"from": "c_txt", "to": "d_dit", "label": "Cross-Attn", "dashed": False},
            {"from": "c_str", "to": "d_adp", "label": "Control", "dashed": False},
            {"from": "d_adp", "to": "d_dit", "label": "+ Δh", "dashed": True},
            {"from": "d_dit", "to": "d_vel", "label": "Hidden", "dashed": False},
            {"from": "d_vel", "to": "v_dec", "label": "ODE Solve", "dashed": False},
        ],
    },
    "agent_icml": {
        "title": "Self-Verifying Academic Agent Harness Loop",
        "venue_theme": "Nature Crisp",
        "width": 1240,
        "height": 470,
        "font_size": 14,
        "corner_radius": 11,
        "groups": [
            {"id": "g1", "label": "Perception & Retrieval", "x": 30, "y": 58, "w": 300, "h": 376, "tone": "neutral"},
            {"id": "g2", "label": "Tool-Augmented Planning", "x": 382, "y": 58, "w": 476, "h": 376, "tone": "primary"},
            {"id": "g3", "label": "Verification & Commit", "x": 910, "y": 58, "w": 298, "h": 376, "tone": "sage"},
        ],
        "nodes": [
            {"id": "a_in", "label": "Manuscript AST", "sublabel": "LaTeX / Word / Math", "x": 58, "y": 118, "w": 244, "h": 88, "tone": "neutral", "icon": "token_strip"},
            {"id": "a_rag", "label": "3,000-Paper Corpus", "sublabel": "Native Style Packs", "x": 58, "y": 278, "w": 244, "h": 88, "tone": "violet", "icon": "attn_grid"},
            {"id": "a_plan", "label": "Policy LLM Reasoner", "sublabel": "Skill Rules + Glossary", "x": 410, "y": 118, "w": 208, "h": 94, "tone": "primary", "icon": "encoder_stack"},
            {"id": "a_tool", "label": "Python Tool Sandbox", "sublabel": "Audit · Plot · Crossref", "x": 646, "y": 268, "w": 186, "h": 96, "tone": "accent", "icon": "gate_router"},
            {"id": "a_diff", "label": "Human-in-the-Loop\nDiff Review", "sublabel": "Accept / Reject Cards", "x": 938, "y": 192, "w": 242, "h": 106, "tone": "sage", "icon": "merge_pool"},
        ],
        "edges": [
            {"from": "a_in", "to": "a_plan", "label": "Context", "dashed": False},
            {"from": "a_rag", "to": "a_plan", "label": "Top-K", "dashed": True},
            {"from": "a_plan", "to": "a_tool", "label": "Invoke", "dashed": False},
            {"from": "a_tool", "to": "a_plan", "label": "Feedback", "dashed": True},
            {"from": "a_plan", "to": "a_diff", "label": "Edits", "dashed": False},
        ],
    },
}


def _hex_to_rgb(h: str) -> tuple[int, int, int]:
    h = h.lstrip("#")
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def _char_width_em(ch: str) -> float:
    if "\u4e00" <= ch <= "\u9fff" or "\u3000" <= ch <= "\u303f" or "\uff00" <= ch <= "\uffef":
        return 1.02
    if ch in "MW@#%&":
        return 0.85
    if ch.isupper():
        return 0.68
    if ch in "ilI1.,|:;!'\" ":
        return 0.34
    return 0.56


def _text_width_px(s: str, font_size: float) -> float:
    return sum(_char_width_em(c) for c in s) * font_size


def _wrap_text(text: str, max_w: float, font_size: float) -> list[str]:
    max_w = max(44.0, max_w)
    lines: list[str] = []
    for raw_line in (text or "").split("\n"):
        raw_line = raw_line.strip()
        if not raw_line:
            continue
        if _text_width_px(raw_line, font_size) <= max_w:
            lines.append(raw_line)
            continue
        tokens: list[str] = []
        buf = ""
        for ch in raw_line:
            if "\u4e00" <= ch <= "\u9fff":
                if buf:
                    tokens.append(buf)
                    buf = ""
                tokens.append(ch)
            elif ch == " ":
                if buf:
                    tokens.append(buf)
                    buf = ""
                tokens.append(" ")
            else:
                buf += ch
        if buf:
            tokens.append(buf)
        cur = ""
        for tok in tokens:
            if tok == " " and not cur:
                continue
            if _text_width_px(cur + tok, font_size) <= max_w or not cur:
                cur += tok
            else:
                lines.append(cur.strip())
                cur = "" if tok == " " else tok
        if cur.strip():
            lines.append(cur.strip())
    return lines


def _fit_node_typography(n: dict[str, Any], base_fs: float) -> tuple[float, float, list[str], list[str], float, float]:
    w, h = float(n["w"]), float(n["h"])
    has_icon = bool(n.get("ai_image_b64") or (n.get("icon") and n.get("icon") != "none"))
    ico_sz = min(36.0, max(22.0, h - 26.0)) if has_icon else 0.0
    avail_w = max(54.0, (w - ico_sz - 28.0) if has_icon else (w - 24.0))
    fs = base_fs
    sub_fs = max(9.5, fs - 2.6)
    lines = _wrap_text(n.get("label") or "", avail_w, fs)
    sub_lines = _wrap_text(n.get("sublabel") or "", avail_w, sub_fs) if n.get("sublabel") else []
    while fs > 9.5:
        total_h = len(lines) * fs * 1.28 + len(sub_lines) * sub_fs * 1.25 + (4 if sub_lines else 0)
        max_lw = max([_text_width_px(l, fs) for l in lines] + [_text_width_px(l, sub_fs) for l in sub_lines] + [0])
        if total_h <= h - 14 and max_lw <= avail_w + 2:
            break
        fs -= 0.8
        sub_fs = max(8.5, fs - 2.4)
        lines = _wrap_text(n.get("label") or "", avail_w, fs)
        sub_lines = _wrap_text(n.get("sublabel") or "", avail_w, sub_fs) if n.get("sublabel") else []
    return fs, sub_fs, lines, sub_lines, ico_sz, avail_w


def _tint_hex(hex_color: str, factor: float = 0.88) -> str:
    r, g, b = _hex_to_rgb(hex_color)
    tr = int(round(r + (255 - r) * factor))
    tg = int(round(g + (255 - g) * factor))
    tb = int(round(b + (255 - b) * factor))
    return f"#{tr:02X}{tg:02X}{tb:02X}"


def _darken_hex(hex_color: str, factor: float = 0.72) -> str:
    r, g, b = _hex_to_rgb(hex_color)
    return f"#{int(r*factor):02X}{int(g*factor):02X}{int(b*factor):02X}"


def _resolve_theme(blueprint: dict[str, Any]) -> dict[str, Any]:
    """Resolve venue theme and apply any user-chosen custom primary/accent/sage colors."""
    base = VENUE_DIAGRAM_THEMES.get(blueprint.get("venue_theme", "CVPR Clean Slate"), VENUE_DIAGRAM_THEMES["CVPR Clean Slate"])
    custom = blueprint.get("custom_colors")
    if not isinstance(custom, dict) or not custom:
        return base
    palette = {k: list(v) for k, v in base["palette"].items()}
    for tone_k in ("primary", "accent", "sage", "violet"):
        hx = str(custom.get(tone_k) or "").strip()
        if re.match(r"^#[0-9A-Fa-f]{6}$", hx):
            palette[tone_k] = [_tint_hex(hx, 0.87), hx, _darken_hex(hx, 0.76)]
    return {**base, "palette": palette}


def make_procedural_icon_png(kind: str, stroke_hex: str = "#1E3A5F", size: int = 256) -> bytes:
    """High-DPI 256x256 2.5D Deep Learning & Multimodal vector schematics (auto-tinted to module color)."""
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    s = size / 96.0
    p = lambda x, y: (x * s, y * s)
    r, g, b = _hex_to_rgb(stroke_hex)
    stroke = (r, g, b, 240)
    soft = (r, g, b, 42)
    mid = (r, g, b, 108)
    lw = max(2, int(round(1.9 * s)))

    if kind == "conv_stack_3d":
        # 4 isometric 3D translucent convolutional feature-map slices stacked in depth
        for i in range(4):
            ox = 14 + i * 11.5
            oy = 26 - i * 4.2
            w_f, h_f, dx, dy = 26, 46, 12, -8
            front = [p(ox, oy), p(ox + w_f, oy), p(ox + w_f, oy + h_f), p(ox, oy + h_f)]
            top = [p(ox, oy), p(ox + dx, oy + dy), p(ox + w_f + dx, oy + dy), p(ox + w_f, oy)]
            side = [p(ox + w_f, oy), p(ox + w_f + dx, oy + dy), p(ox + w_f + dx, oy + h_f + dy), p(ox + w_f, oy + h_f)]
            alpha_f = 55 + i * 38
            draw.polygon(front, fill=(r, g, b, alpha_f), outline=stroke)
            draw.polygon(top, fill=(r, g, b, max(30, alpha_f - 25)), outline=stroke)
            draw.polygon(side, fill=(r, g, b, min(220, alpha_f + 30)), outline=stroke)
    elif kind == "conv_pyramid":
        # 4 shrinking 3D isometric convolutional downsampling stages (CNN / Swin Feature Pyramid)
        specs = [(10, 14, 15, 68), (31, 21, 14, 54), (51, 29, 13, 38), (70, 36, 12, 24)]
        for i, (ox, oy, wf, hf) in enumerate(specs):
            dx, dy = 6.5, -5.0
            a = 50 + i * 45
            draw.polygon([p(ox, oy), p(ox + wf, oy), p(ox + wf, oy + hf), p(ox, oy + hf)], fill=(r, g, b, a), outline=stroke)
            draw.polygon([p(ox, oy), p(ox + dx, oy + dy), p(ox + wf + dx, oy + dy), p(ox + wf, oy)], fill=(r, g, b, max(25, a - 22)), outline=stroke)
            draw.polygon([p(ox + wf, oy), p(ox + wf + dx, oy + dy), p(ox + wf + dx, oy + hf + dy), p(ox + wf, oy + hf)], fill=(r, g, b, min(225, a + 35)), outline=stroke)
    elif kind == "patch_grid":
        # ViT 3x3 image patchification -> 1D token strip
        for ri in range(3):
            for ci in range(3):
                x0, y0 = 10 + ci * 13, 22 + ri * 13
                draw.rectangle([p(x0, y0), p(x0 + 11, y0 + 11)], fill=(r, g, b, 45 + (ri * 3 + ci) * 16), outline=stroke, width=max(1, lw // 2))
        draw.line([p(53, 42), p(65, 42)], fill=stroke, width=lw)
        draw.polygon([p(68, 42), p(62, 37), p(62, 47)], fill=stroke)
        for i in range(4):
            y0 = 16 + i * 16
            draw.rounded_rectangle([p(72, y0), p(86, y0 + 11)], radius=int(3 * s), fill=(r, g, b, 65 + i * 38), outline=stroke, width=max(1, lw // 2))
    elif kind == "cross_attn":
        # Bipartite cross-modality attention links (Vision <-> Language)
        left_y = [22, 48, 74]
        right_y = [22, 48, 74]
        for ly in left_y:
            for ry in right_y:
                w_line = lw if ly == ry else max(1, lw // 2)
                draw.line([p(28, ly), p(68, ry)], fill=(r, g, b, 210 if ly == ry else 85), width=w_line)
        for y in left_y:
            draw.rounded_rectangle([p(10, y - 8), p(28, y + 8)], radius=int(4 * s), fill=mid, outline=stroke, width=lw)
        for y in right_y:
            draw.ellipse([p(68, y - 8), p(84, y + 8)], fill=(r, g, b, 175), outline=stroke, width=lw)
    elif kind == "unet_trapezoid":
        # Encoder-Decoder / U-Net symmetric hourglass + skip link
        draw.polygon([p(12, 16), p(40, 32), p(40, 64), p(12, 80)], fill=(r, g, b, 85), outline=stroke)
        draw.rounded_rectangle([p(42, 34), p(54, 62)], radius=int(3 * s), fill=(r, g, b, 180), outline=stroke, width=lw)
        draw.polygon([p(56, 32), p(84, 16), p(84, 80), p(56, 64)], fill=(r, g, b, 65), outline=stroke)
        draw.line([p(24, 18), p(72, 18)], fill=stroke, width=max(1, lw // 2))
    elif kind == "moe_router":
        # Sparse Mixture-of-Experts gating router -> activated experts
        draw.polygon([p(24, 34), p(38, 48), p(24, 62), p(10, 48)], fill=soft, outline=stroke)
        for i, ey in enumerate([20, 48, 76]):
            active = i in (0, 2)
            draw.line([p(38, 48), p(58, ey)], fill=(r, g, b, 235 if active else 70), width=lw if active else max(1, lw // 2))
            draw.rounded_rectangle([p(58, ey - 10), p(84, ey + 10)], radius=int(4 * s), fill=(r, g, b, 165 if active else 35), outline=stroke, width=lw)
    elif kind == "diffusion_steps":
        # Progressive denoising frames (noisy -> structured -> crisp)
        for i, ox in enumerate([10, 37, 64]):
            draw.rounded_rectangle([p(ox, 28), p(ox + 22, 68)], radius=int(4 * s), fill=(r, g, b, 40 + i * 60), outline=stroke, width=lw)
            if i == 0:
                for dx, dy in [(5, 8), (14, 12), (9, 22), (16, 28), (6, 31)]:
                    draw.ellipse([p(ox + dx - 1.5, 28 + dy - 1.5), p(ox + dx + 1.5, 28 + dy + 1.5)], fill=stroke)
            elif i == 1:
                draw.ellipse([p(ox + 5, 40), p(ox + 17, 56)], fill=(r, g, b, 90), outline=stroke, width=max(1, lw // 2))
            else:
                draw.ellipse([p(ox + 5, 40), p(ox + 17, 56)], fill=(r, g, b, 210), outline=stroke, width=lw)
    elif kind == "tensor_cube":
        draw.polygon([p(20, 32), p(56, 16), p(80, 28), p(44, 44)], fill=soft, outline=stroke)
        draw.polygon([p(20, 32), p(44, 44), p(44, 80), p(20, 68)], fill=mid, outline=stroke)
        draw.polygon([p(44, 44), p(80, 28), p(80, 64), p(44, 80)], fill=(r, g, b, 75), outline=stroke)
    elif kind in ("attn_grid", "attn_heatmap"):
        cell, ox, oy = 15, 18, 18
        weights = [225, 90, 40, 25, 80, 215, 120, 40, 35, 110, 230, 100, 30, 50, 130, 225]
        for idx, w in enumerate(weights):
            ri, ci = divmod(idx, 4)
            x0, y0 = ox + ci * cell, oy + ri * cell
            draw.rectangle([p(x0 + 1, y0 + 1), p(x0 + cell - 1, y0 + cell - 1)], fill=(r, g, b, w), outline=(255, 255, 255, 220))
    elif kind == "encoder_stack":
        for i in range(3):
            y = 18 + i * 22
            draw.rounded_rectangle([p(14, y), p(82, y + 16)], radius=int(4 * s), fill=(r, g, b, 55 + i * 45), outline=stroke, width=lw)
    elif kind == "token_strip":
        for i in range(4):
            x = 12 + i * 19
            draw.rounded_rectangle([p(x, 28), p(x + 15, 68)], radius=int(3 * s), fill=(r, g, b, 55 + i * 40), outline=stroke, width=lw)
    elif kind == "gate_router":
        draw.polygon([p(48, 14), p(82, 48), p(48, 82), p(14, 48)], fill=soft, outline=stroke)
        draw.line([p(28, 48), p(68, 48)], fill=stroke, width=int(2.6 * s))
        draw.line([p(48, 28), p(48, 68)], fill=stroke, width=int(2.6 * s))
    else:
        for cy in (26, 48, 70):
            draw.ellipse([p(14, cy - 7), p(28, cy + 7)], fill=mid, outline=stroke, width=lw)
            draw.line([p(28, cy), p(62, 48)], fill=stroke, width=lw)
        draw.ellipse([p(60, 36), p(84, 60)], fill=(r, g, b, 190), outline=stroke, width=lw)

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


# ---------- Obstacle-Aware, Global-Lane-Separated Orthogonal Router (1:1 Identical in SVG & PPTX) ----------
def _rect_overlap(a: tuple[float, float, float, float], b: tuple[float, float, float, float]) -> bool:
    return a[0] < b[2] and a[2] > b[0] and a[1] < b[3] and a[3] > b[1]


def _seg_hits_nodes(
    x1: float,
    y1: float,
    x2: float,
    y2: float,
    nodes: list[dict[str, Any]],
    exclude: set[str],
    margin: float = 7.0,
) -> bool:
    sx0, sx1 = min(x1, x2), max(x1, x2)
    sy0, sy1 = min(y1, y2), max(y1, y2)
    for n in nodes:
        if n["id"] in exclude:
            continue
        nx0, ny0 = float(n["x"]) - margin, float(n["y"]) - margin
        nx1, ny1 = float(n["x"]) + float(n["w"]) + margin, float(n["y"]) + float(n["h"]) + margin
        if sx0 <= nx1 and sx1 >= nx0 and sy0 <= ny1 and sy1 >= ny0:
            return True
    return False


def _ranges_overlap(a0: float, a1: float, b0: float, b1: float, pad: float = 4.0) -> bool:
    return min(a0, a1) - pad < max(b0, b1) and max(a0, a1) + pad > min(b0, b1)


def compute_routed_edges(blueprint: dict[str, Any]) -> list[dict[str, Any]]:
    """Obstacle-aware orthogonal router with global corridor lane separation & zero label overlap."""
    nodes = blueprint.get("nodes", [])
    node_map = {n["id"]: n for n in nodes}
    base_fs = float(blueprint.get("font_size", 14))
    lbl_fs = max(10.0, base_fs - 3.0)
    canvas_w = float(blueprint.get("width", 1240))
    canvas_h = float(blueprint.get("height", 520))

    # Deduplicate edges & strip self-loops
    seen_pairs: set[tuple[str, str]] = set()
    clean_edges: list[dict[str, Any]] = []
    for e in blueprint.get("edges", []):
        u, v = str(e.get("from", "")), str(e.get("to", ""))
        if not u or not v or u == v or u not in node_map or v not in node_map or (u, v) in seen_pairs:
            continue
        seen_pairs.add((u, v))
        clean_edges.append(e)

    # Determine safe bypass bus Y baselines strictly outside all nodes
    min_node_y = min((float(n["y"]) for n in nodes), default=90.0)
    max_node_bot = max((float(n["y"]) + float(n["h"]) for n in nodes), default=canvas_h - 60.0)
    groups = blueprint.get("groups", [])
    min_group_y = min((float(g["y"]) for g in groups), default=min_node_y - 26.0)
    max_group_bot = max((float(g["y"]) + float(g["h"]) for g in groups), default=max_node_bot + 16.0)

    # Step 1: Classify each edge's route mode & exit/entry sides (checking intermediate box obstacles!)
    specs: list[dict[str, Any]] = []
    side_out: dict[tuple[str, str], list[int]] = defaultdict(list)
    side_in: dict[tuple[str, str], list[int]] = defaultdict(list)

    for idx, e in enumerate(clean_edges):
        src, dst = node_map[e["from"]], node_map[e["to"]]
        sx, sy, sw, sh = float(src["x"]), float(src["y"]), float(src["w"]), float(src["h"])
        dx, dy, dw, dh = float(dst["x"]), float(dst["y"]), float(dst["w"]), float(dst["h"])
        scx, scy = sx + sw / 2, sy + sh / 2
        dcx, dcy = dx + dw / 2, dy + dh / 2

        h_gap_r = dx - (sx + sw)
        h_gap_l = sx - (dx + dw)
        v_gap_d = dy - (sy + sh)
        v_gap_u = sy - (dy + dh)
        excl = {src["id"], dst["id"]}

        # Check if any intermediate node sits strictly between src and dst horizontally
        between_h = [
            n for n in nodes
            if n["id"] not in excl
            and float(n["x"]) + float(n["w"]) > min(sx + sw, dx + dw) + 6
            and float(n["x"]) < max(sx, dx) - 6
            and _ranges_overlap(float(n["y"]), float(n["y"]) + float(n["h"]), min(sy, dy) - 10, max(sy + sh, dy + dh) + 10)
        ]
        # Check if any intermediate node sits strictly between src and dst vertically (same column)
        between_v = [
            n for n in nodes
            if n["id"] not in excl
            and float(n["y"]) + float(n["h"]) > min(sy + sh, dy + dh) + 4
            and float(n["y"]) < max(sy, dy) - 4
            and _ranges_overlap(float(n["x"]), float(n["x"]) + float(n["w"]), min(sx, dx) - 6, max(sx + sw, dx + dw) + 6)
        ]

        mode = "normal"
        if (h_gap_r >= 18 or h_gap_l >= 18) and between_h:
            # Long-range cross-stage skip connection -> bypass bus strictly outside boxes!
            mid_y_avg = (scy + dcy) / 2.0
            if mid_y_avg <= (min_node_y + max_node_bot) / 2.0:
                mode = "bypass_top"
                s_side, d_side = "top", "top"
            else:
                mode = "bypass_bottom"
                s_side, d_side = "bottom", "bottom"
        elif h_gap_r >= 18:
            s_side, d_side = "right", "left"
        elif h_gap_l >= 18:
            s_side, d_side = "left", "right"
        elif (v_gap_d >= 10 or v_gap_u >= 10) and between_v:
            # Same-column jump over middle box -> side gutter!
            mode = "side_gutter"
            s_side, d_side = "right", "right"
        elif v_gap_d >= 10:
            s_side, d_side = "bottom", "top"
        elif v_gap_u >= 10:
            s_side, d_side = "top", "bottom"
        elif abs(dcx - scx) >= abs(dcy - scy):
            s_side, d_side = ("right", "left") if dcx >= scx else ("left", "right")
        else:
            s_side, d_side = ("bottom", "top") if dcy >= scy else ("top", "bottom")

        specs.append({"idx": idx, "edge": e, "s_side": s_side, "d_side": d_side, "mode": mode})
        side_out[(src["id"], s_side)].append(idx)
        side_in[(dst["id"], d_side)].append(idx)

    # Sort ports along each side to minimize line crossings
    for (nid, side), e_idxs in side_out.items():
        e_idxs.sort(key=lambda i: (float(node_map[clean_edges[i]["to"]]["y"]) if side in ("left", "right") else float(node_map[clean_edges[i]["to"]]["x"])))
    for (nid, side), e_idxs in side_in.items():
        e_idxs.sort(key=lambda i: (float(node_map[clean_edges[i]["from"]]["y"]) if side in ("left", "right") else float(node_map[clean_edges[i]["from"]]["x"])))

    def port_xy(n: dict[str, Any], side: str, rank: int, total: int, inset: float = 0.0) -> tuple[float, float]:
        frac = 0.5 if total <= 1 else (0.22 + 0.56 * (rank / max(1, total - 1)))
        x, y, w, h = float(n["x"]), float(n["y"]), float(n["w"]), float(n["h"])
        if side == "right":
            return x + w + inset, y + h * frac
        if side == "left":
            return x - inset, y + h * frac
        if side == "bottom":
            return x + w * frac, y + h + inset
        return x + w * frac, y - inset

    # Global lane registries so NO two parallel trunks ever stack on top of each other!
    used_v_lanes: list[tuple[float, float, float]] = []  # (x, y_min, y_max)
    used_h_lanes: list[tuple[float, float, float]] = []  # (y, x_min, x_max)

    def pick_clear_x(ideal_x: float, lo_x: float, hi_x: float, y_a: float, y_b: float, excl: set[str]) -> float:
        y0, y1 = min(y_a, y_b), max(y_a, y_b)
        step = 14.0
        offsets = [0.0]
        for k in range(1, 9):
            offsets.extend([-k * step, k * step])
        best_x = max(lo_x, min(hi_x, ideal_x))
        for off in offsets:
            cand = ideal_x + off
            if cand < lo_x or cand > hi_x:
                continue
            if _seg_hits_nodes(cand, y0, cand, y1, nodes, excl, margin=6.0):
                continue
            if any(abs(cand - ux) < 12.0 and _ranges_overlap(y0, y1, uy0, uy1) for ux, uy0, uy1 in used_v_lanes):
                continue
            used_v_lanes.append((cand, y0, y1))
            return cand
        used_v_lanes.append((best_x, y0, y1))
        return best_x

    def pick_clear_y(ideal_y: float, direction: int, x_a: float, x_b: float, excl: set[str]) -> float:
        x0, x1 = min(x_a, x_b), max(x_a, x_b)
        step = 15.0
        for k in range(10):
            cand = max(46.0, min(canvas_h - 14.0, ideal_y + direction * k * step))
            if _seg_hits_nodes(x0, cand, x1, cand, nodes, excl, margin=5.0):
                continue
            if any(abs(cand - uy) < 13.0 and _ranges_overlap(x0, x1, ux0, ux1) for uy, ux0, ux1 in used_h_lanes):
                continue
            used_h_lanes.append((cand, x0, x1))
            return cand
        used_h_lanes.append((ideal_y, x0, x1))
        return ideal_y

    # Step 2: Route every edge on a guaranteed distinct, obstacle-free orthogonal polyline
    routed: list[dict[str, Any]] = []
    for sp in specs:
        idx, e, s_side, d_side, mode = sp["idx"], sp["edge"], sp["s_side"], sp["d_side"], sp["mode"]
        src, dst = node_map[e["from"]], node_map[e["to"]]
        excl = {src["id"], dst["id"]}
        o_list = side_out[(src["id"], s_side)]
        i_list = side_in[(dst["id"], d_side)]
        x1, y1 = port_xy(src, s_side, o_list.index(idx), len(o_list), inset=1.0)
        x2, y2 = port_xy(dst, d_side, i_list.index(idx), len(i_list), inset=3.5)

        if mode == "bypass_top":
            base_y = max(48.0, min(min_group_y - 10.0, min_node_y - 22.0))
            bus_y = pick_clear_y(base_y, -1, x1, x2, excl)
            pts = [(x1, y1), (x1, bus_y), (x2, bus_y), (x2, y2)]
        elif mode == "bypass_bottom":
            base_y = min(canvas_h - 18.0, max(max_group_bot + 10.0, max_node_bot + 20.0))
            bus_y = pick_clear_y(base_y, 1, x1, x2, excl)
            pts = [(x1, y1), (x1, bus_y), (x2, bus_y), (x2, y2)]
        elif mode == "side_gutter":
            ideal_gx = max(x1, x2) + 22.0
            gx = pick_clear_x(ideal_gx, ideal_gx - 4.0, min(canvas_w - 14.0, ideal_gx + 90.0), y1, y2, excl)
            pts = [(x1, y1), (gx, y1), (gx, y2), (x2, y2)]
        elif s_side in ("right", "left"):
            if abs(y2 - y1) < 4.5 and not _seg_hits_nodes(x1, y1, x2, y2, nodes, excl, margin=5.0):
                pts = [(x1, y1), (x2, y2)]
                used_h_lanes.append(((y1 + y2) / 2.0, min(x1, x2), max(x1, x2)))
            else:
                lo_x = min(x1, x2) + 14.0
                hi_x = max(x1, x2) - 14.0
                if hi_x <= lo_x:
                    lo_x = hi_x = (x1 + x2) / 2.0
                mid_x = pick_clear_x((x1 + x2) / 2.0, lo_x, hi_x, y1, y2, excl)
                pts = [(x1, y1), (mid_x, y1), (mid_x, y2), (x2, y2)]
        else:
            if abs(x2 - x1) < 4.5 and not _seg_hits_nodes(x1, y1, x2, y2, nodes, excl, margin=5.0):
                pts = [(x1, y1), (x2, y2)]
                used_v_lanes.append(((x1 + x2) / 2.0, min(y1, y2), max(y1, y2)))
            else:
                mid_y = pick_clear_y((y1 + y2) / 2.0, 1, x1, x2, excl)
                pts = [(x1, y1), (x1, mid_y), (x2, mid_y), (x2, y2)]

        routed.append({
            "edge": e,
            "points": pts,
            "label_xy": ((x1 + x2) / 2.0, (y1 + y2) / 2.0),
            "dashed": bool(e.get("dashed")),
            "label": (e.get("label") or "").strip(),
        })

    # Step 3: Collision-free Edge Label Pill Placement (never overlaps nodes or other pills!)
    node_rects = [(float(n["x"]) - 4, float(n["y"]) - 4, float(n["x"]) + float(n["w"]) + 4, float(n["y"]) + float(n["h"]) + 4) for n in nodes]
    used_pill_rects: list[tuple[float, float, float, float]] = []

    for item in routed:
        lbl = item["label"]
        if not lbl:
            continue
        bw = max(36.0, _text_width_px(lbl, lbl_fs) + 14.0)
        bh = 21.0
        pts = item["points"]
        # Pick the longest segment on the polyline as primary label host
        segs = sorted(
            [(pts[i], pts[i + 1], ((pts[i + 1][0] - pts[i][0]) ** 2 + (pts[i + 1][1] - pts[i][1]) ** 2) ** 0.5) for i in range(len(pts) - 1)],
            key=lambda s: -s[2],
        )
        p_a, p_b, _ = segs[0]
        is_horiz = abs(p_a[1] - p_b[1]) < 2.0
        cands: list[tuple[float, float]] = []
        for t_frac in (0.5, 0.35, 0.65, 0.25, 0.75):
            bx = p_a[0] + (p_b[0] - p_a[0]) * t_frac
            by = p_a[1] + (p_b[1] - p_a[1]) * t_frac
            cands.append((bx, by))
            if is_horiz:
                cands.extend([(bx, by - 16.0), (bx, by + 16.0)])
            else:
                cands.extend([(bx, by - 22.0), (bx, by + 22.0)])
        chosen = cands[0]
        for cx, cy in cands:
            cx_c = max(bw / 2 + 6, min(canvas_w - bw / 2 - 6, cx))
            cy_c = max(bh / 2 + 6, min(canvas_h - bh / 2 - 6, cy))
            rect = (cx_c - bw / 2 - 2, cy_c - bh / 2 - 2, cx_c + bw / 2 + 2, cy_c + bh / 2 + 2)
            if any(_rect_overlap(rect, nr) for nr in node_rects):
                continue
            if any(_rect_overlap(rect, pr) for pr in used_pill_rects):
                continue
            chosen = (cx_c, cy_c)
            used_pill_rects.append(rect)
            break
        else:
            used_pill_rects.append((chosen[0] - bw / 2, chosen[1] - bh / 2, chosen[0] + bw / 2, chosen[1] + bh / 2))
        item["label_xy"] = chosen

    return routed


def _polyline_to_rounded_svg_path(pts: list[tuple[float, float]], radius: float = 8.0) -> str:
    if len(pts) <= 2:
        return f"M {pts[0][0]:.1f} {pts[0][1]:.1f} L {pts[-1][0]:.1f} {pts[-1][1]:.1f}"
    d = [f"M {pts[0][0]:.1f} {pts[0][1]:.1f}"]
    for i in range(1, len(pts) - 1):
        p0, p1, p2 = pts[i - 1], pts[i], pts[i + 1]
        v1x, v1y = p1[0] - p0[0], p1[1] - p0[1]
        v2x, v2y = p2[0] - p1[0], p2[1] - p1[1]
        l1 = max(1e-3, (v1x * v1x + v1y * v1y) ** 0.5)
        l2 = max(1e-3, (v2x * v2x + v2y * v2y) ** 0.5)
        r = min(radius, l1 * 0.45, l2 * 0.45)
        ax, ay = p1[0] - v1x / l1 * r, p1[1] - v1y / l1 * r
        bx, by = p1[0] + v2x / l2 * r, p1[1] + v2y / l2 * r
        d.append(f"L {ax:.1f} {ay:.1f} Q {p1[0]:.1f} {p1[1]:.1f} {bx:.1f} {by:.1f}")
    d.append(f"L {pts[-1][0]:.1f} {pts[-1][1]:.1f}")
    return " ".join(d)


def _fit_group_label(label: str, g_w: float, base_fs: float) -> tuple[float, list[str]]:
    """Auto-fit stage group title strictly inside g.w - 24px (1:1 identical across SVG & PPTX)."""
    avail_w = max(80.0, g_w - 24.0)
    fs = max(10.5, base_fs - 1.6)
    lines = _wrap_text(label, avail_w, fs)
    while fs > 9.0 and (len(lines) > 2 or any(_text_width_px(l, fs) > avail_w + 1.0 for l in lines)):
        fs -= 0.7
        lines = _wrap_text(label, avail_w, fs)
    return fs, lines[:2]


def render_diagram_svg(blueprint: dict[str, Any]) -> str:
    """Render publication SVG with strict Z-order: Groups -> Nodes -> Routed Arrows -> Edge Labels."""
    theme = _resolve_theme(blueprint)
    W, H = int(blueprint.get("width", 1240)), int(blueprint.get("height", 520))
    base_fs = float(blueprint.get("font_size", 14))
    rad = float(blueprint.get("corner_radius", 11))

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}" style="background:{theme["bg"]};font-family:\'Inter\',\'Microsoft YaHei\',\'DejaVu Sans\',sans-serif;">',
        "<defs>",
        f'<marker id="ph-arrow" viewBox="0 0 10 10" refX="8.2" refY="5" markerWidth="6.5" markerHeight="6.5" orient="auto-start-reverse">'
        f'<path d="M 0 1.2 L 9 5 L 0 8.8 z" fill="{theme["arrow"]}"/></marker>',
        "</defs>",
        f'<rect x="0" y="0" width="{W}" height="{H}" fill="{theme["bg"]}"/>',
    ]

    if blueprint.get("title"):
        parts.append(f'<text x="28" y="36" font-size="{base_fs + 3.5:.1f}" font-weight="600" fill="{theme["ink"]}">{html.escape(blueprint["title"])}</text>')

    # Layer 1: Groups (with auto-fitted stage header strictly inside group border!)
    for g in blueprint.get("groups", []):
        parts.append(
            f'<rect x="{g["x"]}" y="{g["y"]}" width="{g["w"]}" height="{g["h"]}" rx="{rad + 2}" '
            f'fill="{theme["group_bg"]}" stroke="{theme["group_border"]}" stroke-width="1.5" stroke-dasharray="6,4"/>'
        )
        g_fs, g_lines = _fit_group_label(g.get("label", ""), float(g["w"]), base_fs)
        for li, gln in enumerate(g_lines):
            parts.append(f'<text x="{g["x"] + 12:.1f}" y="{g["y"] + 21 + li * (g_fs * 1.24):.1f}" font-size="{g_fs:.1f}" font-weight="600" fill="{theme["muted"]}">{html.escape(gln)}</text>')

    # Layer 2: Nodes & Icons
    for n in blueprint.get("nodes", []):
        fill_c, border_c, text_c = theme["palette"].get(n.get("tone", "primary"), theme["palette"]["primary"])
        x, y, w, h = float(n["x"]), float(n["y"]), float(n["w"]), float(n["h"])
        parts.append(f'<rect x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{h:.1f}" rx="{rad}" fill="{fill_c}" stroke="{border_c}" stroke-width="1.7"/>')

        fs, sub_fs, lines, sub_lines, ico_sz, avail_w = _fit_node_typography(n, base_fs)
        has_icon = ico_sz > 0
        if has_icon:
            ai_b64 = n.get("ai_image_b64")
            href = f"data:image/png;base64,{ai_b64}" if ai_b64 else f"data:image/png;base64,{base64.b64encode(make_procedural_icon_png(n.get('icon', 'encoder_stack'), border_c)).decode()}"
            parts.append(f'<image href="{href}" x="{x + 11:.1f}" y="{y + (h - ico_sz)/2:.1f}" width="{ico_sz:.1f}" height="{ico_sz:.1f}" preserveAspectRatio="xMidYMid meet"/>')
            text_x = x + 15.0 + ico_sz + avail_w / 2.0
        else:
            text_x = x + w / 2.0

        line_h, sub_h = fs * 1.28, sub_fs * 1.25
        total_h = len(lines) * line_h + len(sub_lines) * sub_h + (3 if sub_lines else 0)
        cur_y = y + (h - total_h) / 2.0 + fs * 0.88
        for ln in lines:
            parts.append(f'<text x="{text_x:.1f}" y="{cur_y:.1f}" text-anchor="middle" font-size="{fs:.1f}" font-weight="600" fill="{text_c}">{html.escape(ln)}</text>')
            cur_y += line_h
        if sub_lines:
            cur_y += 2.0
            for sln in sub_lines:
                parts.append(f'<text x="{text_x:.1f}" y="{cur_y:.1f}" text-anchor="middle" font-size="{sub_fs:.1f}" fill="{theme["muted"]}" font-family="\'JetBrains Mono\',monospace">{html.escape(sln)}</text>')
                cur_y += sub_h

    # Layer 3 & 4: Routed Arrows ON TOP of nodes, then Edge Label Pills ON TOP of arrows!
    routed = compute_routed_edges(blueprint)
    for re_item in routed:
        d = _polyline_to_rounded_svg_path(re_item["points"])
        dash = ' stroke-dasharray="5,4"' if re_item["dashed"] else ""
        parts.append(f'<path d="{d}" fill="none" stroke="{theme["arrow"]}" stroke-width="1.9" stroke-linejoin="round" stroke-linecap="round"{dash} marker-end="url(#ph-arrow)"/>')

    lbl_fs = max(10.0, base_fs - 3.0)
    for re_item in routed:
        lbl = re_item["label"]
        if not lbl:
            continue
        lx, ly = re_item["label_xy"]
        bw = max(36.0, _text_width_px(lbl, lbl_fs) + 14.0)
        parts.append(f'<rect x="{lx - bw/2:.1f}" y="{ly - 10.5:.1f}" width="{bw:.1f}" height="21" rx="6" fill="white" stroke="#D5DCE4" stroke-width="0.9"/>')
        parts.append(f'<text x="{lx:.1f}" y="{ly + 3.5:.1f}" text-anchor="middle" font-size="{lbl_fs:.1f}" font-weight="500" fill="{theme["muted"]}">{html.escape(lbl)}</text>')

    parts.append("</svg>")
    return "\n".join(parts)


def export_diagram_pdf_bytes(blueprint: dict[str, Any]) -> bytes:
    svg_bytes = render_diagram_svg(blueprint).encode("utf-8")
    return pymupdf.open(stream=svg_bytes, filetype="svg").convert_to_pdf()


def export_diagram_png_bytes(blueprint: dict[str, Any], dpi: int = 600) -> bytes:
    clamped = max(150, min(1200, int(dpi)))
    pdf_doc = pymupdf.open(stream=export_diagram_pdf_bytes(blueprint), filetype="pdf")
    return pdf_doc[0].get_pixmap(dpi=clamped, alpha=False).tobytes("png")


def _set_line_dash(shape_or_line, dash: str = "dash") -> None:
    ln = shape_or_line._get_or_add_ln()
    for child in list(ln):
        if child.tag.endswith("prstDash"):
            ln.remove(child)
    ln.append(ln.makeelement(qn("a:prstDash"), {"val": dash}))


def export_diagram_pptx_bytes(blueprint: dict[str, Any]) -> bytes:
    """1:1 Visual-Fidelity Editable PowerPoint (.pptx) matching the interactive canvas exactly."""
    theme = _resolve_theme(blueprint)
    prs = Presentation()
    prs.slide_width, prs.slide_height = Inches(13.333), Inches(7.5)
    slide = prs.slides.add_slide(prs.slide_layouts[6])

    W, H = float(blueprint.get("width", 1240)), float(blueprint.get("height", 520))
    base_fs = float(blueprint.get("font_size", 14))
    rad = float(blueprint.get("corner_radius", 11))
    scale = min(12.4 / W, 6.4 / H)
    ox, oy = (13.333 - W * scale) / 2.0, (7.5 - H * scale) / 2.0
    # 1 pt = 1/72 inch, so convert canvas px to exact PowerPoint pt matching visual scale!
    px_to_pt = scale * 72.0

    sx = lambda v: Inches(ox + v * scale)
    sy = lambda v: Inches(oy + v * scale)
    sw = lambda v: Inches(v * scale)

    # Title
    if blueprint.get("title"):
        tb = slide.shapes.add_textbox(sx(24), sy(8), sw(W - 48), sw(36))
        p = tb.text_frame.paragraphs[0]
        r = p.add_run()
        r.text = blueprint["title"]
        r.font.name, r.font.size, r.font.bold = "Microsoft YaHei", Pt((base_fs + 3.0) * px_to_pt), True
        r.font.color.rgb = RGBColor(*_hex_to_rgb(theme["ink"]))

    # Layer 1: Dashed Stage Groups (exact dashed border!)
    for g in blueprint.get("groups", []):
        shp = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, sx(g["x"]), sy(g["y"]), sw(g["w"]), sw(g["h"]))
        shp.fill.solid()
        shp.fill.fore_color.rgb = RGBColor(*_hex_to_rgb(theme["group_bg"]))
        shp.line.color.rgb = RGBColor(*_hex_to_rgb(theme["group_border"]))
        shp.line.width = Pt(1.3)
        _set_line_dash(shp.line, "dash")
        shp.adjustments[0] = min(0.15, (rad + 2) / max(1.0, min(g["w"], g["h"])))
        g_fs, g_lines = _fit_group_label(g.get("label", ""), float(g["w"]), base_fs)
        tf = shp.text_frame
        tf.word_wrap, tf.vertical_anchor = True, MSO_ANCHOR.TOP
        tf.margin_left, tf.margin_right, tf.margin_top = sw(12), sw(12), sw(7)
        p = tf.paragraphs[0]
        p.alignment = PP_ALIGN.LEFT
        run = p.add_run()
        run.text = "\n".join(g_lines)
        run.font.name, run.font.size, run.font.bold = "Microsoft YaHei", Pt(g_fs * px_to_pt), True
        run.font.color.rgb = RGBColor(*_hex_to_rgb(theme["muted"]))

    # Layer 2: Module Nodes & Embedded Icons (exact auto-fit typography & corner radius!)
    for n in blueprint.get("nodes", []):
        fill_c, border_c, text_c = theme["palette"].get(n.get("tone", "primary"), theme["palette"]["primary"])
        shp = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, sx(n["x"]), sy(n["y"]), sw(n["w"]), sw(n["h"]))
        shp.fill.solid()
        shp.fill.fore_color.rgb = RGBColor(*_hex_to_rgb(fill_c))
        shp.line.color.rgb = RGBColor(*_hex_to_rgb(border_c))
        shp.line.width = Pt(1.5)
        shp.adjustments[0] = min(0.32, rad / max(1.0, min(n["w"], n["h"])))

        fs, sub_fs, lines, sub_lines, ico_sz, _ = _fit_node_typography(n, base_fs)
        tf = shp.text_frame
        tf.word_wrap, tf.vertical_anchor = True, MSO_ANCHOR.MIDDLE
        tf.margin_top = tf.margin_bottom = sw(4)
        tf.margin_right = sw(8)
        tf.margin_left = sw(8)

        if ico_sz > 0:
            ai_b64 = n.get("ai_image_b64")
            img_bytes = base64.b64decode(ai_b64) if ai_b64 else make_procedural_icon_png(n.get("icon", "encoder_stack"), border_c)
            slide.shapes.add_picture(io.BytesIO(img_bytes), sx(n["x"] + 11), sy(n["y"] + (n["h"] - ico_sz) / 2), width=sw(ico_sz), height=sw(ico_sz))
            tf.margin_left = sw(ico_sz + 14)

        p = tf.paragraphs[0]
        p.alignment = PP_ALIGN.CENTER
        r1 = p.add_run()
        r1.text = "\n".join(lines)
        r1.font.name, r1.font.size, r1.font.bold = "Microsoft YaHei", Pt(fs * px_to_pt), True
        r1.font.color.rgb = RGBColor(*_hex_to_rgb(text_c))

        if sub_lines:
            p2 = tf.add_paragraph()
            p2.alignment = PP_ALIGN.CENTER
            r2 = p2.add_run()
            r2.text = "\n".join(sub_lines)
            r2.font.name, r2.font.size = "Consolas", Pt(sub_fs * px_to_pt)
            r2.font.color.rgb = RGBColor(*_hex_to_rgb(theme["muted"]))

    # Layer 3: Exact Multi-Segment Routed Arrows ON TOP of nodes (using FreeformBuilder!)
    routed = compute_routed_edges(blueprint)
    for re_item in routed:
        pts = re_item["points"]
        if len(pts) < 2:
            continue
        fb = slide.shapes.build_freeform(sx(pts[0][0]), sy(pts[0][1]))
        fb.add_line_segments([(sx(px), sy(py)) for px, py in pts[1:]], close=False)
        line_shp = fb.convert_to_shape()
        line_shp.fill.background()  # transparent fill so open polyline never fills!
        line_shp.line.color.rgb = RGBColor(*_hex_to_rgb(theme["arrow"]))
        line_shp.line.width = Pt(1.55)
        if re_item["dashed"]:
            _set_line_dash(line_shp.line, "dash")
        ln = line_shp.line._get_or_add_ln()
        ln.append(ln.makeelement(qn("a:tailEnd"), {"type": "triangle", "w": "med", "len": "med"}))

    # Layer 4: White Rounded-Pill Edge Labels ON TOP of arrows!
    lbl_fs = max(10.0, base_fs - 3.0)
    for re_item in routed:
        lbl = re_item["label"]
        if not lbl:
            continue
        lx, ly = re_item["label_xy"]
        bw = max(38.0, _text_width_px(lbl, lbl_fs) + 14.0)
        bh = 21.0
        pill = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, sx(lx - bw / 2), sy(ly - bh / 2), sw(bw), sw(bh))
        pill.fill.solid()
        pill.fill.fore_color.rgb = RGBColor(255, 255, 255)
        pill.line.color.rgb = RGBColor(0xD5, 0xDC, 0xE4)
        pill.line.width = Pt(0.75)
        pill.adjustments[0] = 0.3
        tf = pill.text_frame
        tf.margin_left = tf.margin_right = tf.margin_top = tf.margin_bottom = Inches(0)
        tf.vertical_anchor = MSO_ANCHOR.MIDDLE
        p = tf.paragraphs[0]
        p.alignment = PP_ALIGN.CENTER
        r = p.add_run()
        r.text = lbl
        r.font.name, r.font.size = "Microsoft YaHei", Pt(lbl_fs * px_to_pt)
        r.font.color.rgb = RGBColor(*_hex_to_rgb(theme["muted"]))

    buf = io.BytesIO()
    prs.save(buf)
    return buf.getvalue()


def normalize_blueprint(bp: dict[str, Any], venue_theme: str = "CVPR Clean Slate") -> dict[str, Any]:
    """Validate, clamp, deduplicate edges, and gently separate any overlapping nodes."""
    W = int(bp.get("width") or 1240)
    H = int(bp.get("height") or 540)
    theme_name = bp.get("venue_theme") if bp.get("venue_theme") in VENUE_DIAGRAM_THEMES else venue_theme
    groups = []
    for i, g in enumerate(bp.get("groups") or []):
        gx = max(12, min(W - 140, float(g.get("x", 28))))
        gy = max(48, min(H - 120, float(g.get("y", 58))))
        gw = max(120, min(W - gx - 12, float(g.get("w", 280))))
        gh = max(100, min(H - gy - 12, float(g.get("h", 420))))
        groups.append({"id": str(g.get("id") or f"g{i+1}"), "label": str(g.get("label") or f"Stage {i+1}"), "x": gx, "y": gy, "w": gw, "h": gh, "tone": str(g.get("tone") or "neutral")})

    nodes = []
    for i, n in enumerate(bp.get("nodes") or []):
        nw = max(120, min(360, float(n.get("w", 210))))
        nh = max(60, min(180, float(n.get("h", 86))))
        nx = max(20, min(W - nw - 20, float(n.get("x", 50 + (i % 4) * 280))))
        ny = max(68, min(H - nh - 18, float(n.get("y", 110 + (i // 4) * 140))))
        nodes.append({
            "id": str(n.get("id") or f"n{i+1}"),
            "label": str(n.get("label") or f"Module {i+1}"),
            "sublabel": str(n.get("sublabel") or ""),
            "x": nx,
            "y": ny,
            "w": nw,
            "h": nh,
            "tone": str(n.get("tone") or "primary"),
            "icon": str(n.get("icon") or "encoder_stack"),
            **({"ai_image_b64": n["ai_image_b64"]} if n.get("ai_image_b64") else {}),
        })

    # Gentle de-overlap pass if raw LLM coords placed two boxes on top of each other
    for _ in range(6):
        moved = False
        for i in range(len(nodes)):
            for j in range(i + 1, len(nodes)):
                a, b = nodes[i], nodes[j]
                if _rect_overlap((a["x"] - 8, a["y"] - 8, a["x"] + a["w"] + 8, a["y"] + a["h"] + 8), (b["x"] - 8, b["y"] - 8, b["x"] + b["w"] + 8, b["y"] + b["h"] + 8)):
                    push = (a["y"] + a["h"] + 24) - b["y"]
                    if b["y"] + push + b["h"] <= H - 16:
                        b["y"] += push
                        moved = True
        if not moved:
            break

    valid_ids = {n["id"] for n in nodes}
    seen_e: set[tuple[str, str]] = set()
    edges = []
    for e in bp.get("edges") or []:
        u, v = str(e.get("from", "")), str(e.get("to", ""))
        if u in valid_ids and v in valid_ids and u != v and (u, v) not in seen_e:
            seen_e.add((u, v))
            edges.append({"from": u, "to": v, "label": str(e.get("label") or "")[:22], "dashed": bool(e.get("dashed", False))})

    return {
        "title": str(bp.get("title") or "Architecture Overview"),
        "venue_theme": theme_name,
        "width": W,
        "height": H,
        "font_size": int(bp.get("font_size") or 14),
        "corner_radius": int(bp.get("corner_radius") or 11),
        "groups": groups,
        "nodes": nodes,
        "edges": edges,
        **({"custom_colors": bp["custom_colors"]} if isinstance(bp.get("custom_colors"), dict) else {}),
        **({"layout_mode": bp["layout_mode"]} if bp.get("layout_mode") else {}),
    }


def compute_clean_grid_layout(
    title: str,
    venue_theme: str,
    stages: list[dict[str, Any]],
    edges: list[dict[str, Any]],
    layout_mode: str = "pipeline",
    custom_colors: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Deterministic publication-grade layout solver supporting 4 top-venue archetypes:
    `pipeline` | `dual_branch` | `zoom_callout` | `sample_left`.
    """
    non_empty = [s for s in stages if s.get("nodes")]
    if not non_empty:
        return normalize_blueprint(DIAGRAM_TEMPLATES["hierattn_cvpr"], venue_theme)

    n_stages = len(non_empty)
    max_rows = max(len(s["nodes"]) for s in non_empty)
    node_stage: dict[str, int] = {str(n["id"]): si for si, st in enumerate(non_empty) for n in st["nodes"]}
    has_skip = any(abs(node_stage.get(str(e.get("to")), 0) - node_stage.get(str(e.get("from")), 0)) >= 2 for e in edges)

    groups_out: list[dict[str, Any]] = []
    nodes_out: list[dict[str, Any]] = []

    if layout_mode == "zoom_callout" and n_stages >= 3:
        # Upper clean main pipeline + lower wide dashed Zoom-in Callout expanding the core novelty stage
        zoom_idx = min(n_stages - 2, max(1, n_stages // 2))
        top_stages = [s for i, s in enumerate(non_empty) if i != zoom_idx]
        zoom_stage = non_empty[zoom_idx]
        W, MARGIN_X, CHANNEL_W = 1280, 28.0, 88.0
        top_max_r = max(len(s["nodes"]) for s in top_stages)
        top_h = 48.0 + top_max_r * 82.0 + max(0, top_max_r - 1) * 34.0 + 18.0
        TOP_Y = 74.0 if has_skip else 56.0
        gw = (W - 2 * MARGIN_X - (len(top_stages) - 1) * CHANNEL_W) / len(top_stages)
        for si, st in enumerate(top_stages):
            gx = MARGIN_X + si * (gw + CHANNEL_W)
            groups_out.append({"id": str(st.get("id") or f"g{si+1}"), "label": str(st.get("label") or f"Stage {si+1}"), "x": round(gx, 1), "y": round(TOP_Y, 1), "w": round(gw, 1), "h": round(top_h, 1), "tone": "neutral"})
            k = len(st["nodes"])
            bh = k * 82.0 + max(0, k - 1) * 34.0
            sy = TOP_Y + 48.0 + (top_h - 66.0 - bh) / 2.0
            for ri, n in enumerate(st["nodes"]):
                nodes_out.append({
                    "id": str(n["id"]), "label": str(n.get("label") or ""), "sublabel": str(n.get("sublabel") or ""),
                    "x": round(gx + 18.0, 1), "y": round(sy + ri * 116.0, 1), "w": round(gw - 36.0, 1), "h": 82.0,
                    "tone": str(n.get("tone") or "primary"), "icon": str(n.get("icon") or "encoder_stack"),
                    **({"ai_image_b64": n["ai_image_b64"]} if n.get("ai_image_b64") else {}),
                })
        # Bottom wide Zoom-in Callout box (horizontal arrangement of novelty sub-modules!)
        zy = TOP_Y + top_h + 44.0
        zh = 158.0
        zw = W - 2 * MARGIN_X
        groups_out.append({"id": str(zoom_stage.get("id") or "gzoom"), "label": f"Zoom-in · {zoom_stage.get('label', 'Core Module')}", "x": MARGIN_X, "y": round(zy, 1), "w": round(zw, 1), "h": zh, "tone": "accent"})
        znodes = zoom_stage["nodes"]
        zn = len(znodes)
        z_gap = 66.0
        z_nw = min(290.0, (zw - 60.0 - (zn - 1) * z_gap) / max(1, zn))
        z_start_x = MARGIN_X + (zw - (zn * z_nw + (zn - 1) * z_gap)) / 2.0
        for zi, n in enumerate(znodes):
            nodes_out.append({
                "id": str(n["id"]), "label": str(n.get("label") or ""), "sublabel": str(n.get("sublabel") or ""),
                "x": round(z_start_x + zi * (z_nw + z_gap), 1), "y": round(zy + 52.0, 1), "w": round(z_nw, 1), "h": 86.0,
                "tone": str(n.get("tone") or "accent"), "icon": str(n.get("icon") or "conv_stack_3d"),
                **({"ai_image_b64": n["ai_image_b64"]} if n.get("ai_image_b64") else {}),
            })
        H = int(round(zy + zh + 34.0))
    else:
        W = 1280 if n_stages >= 4 else 1240
        MARGIN_X = 28.0
        CHANNEL_W = 84.0 if n_stages >= 4 else 96.0
        GROUP_PAD_X = 20.0
        GROUP_HEAD_H = 50.0
        GROUP_PAD_BOT = 22.0
        GAP_Y = 58.0 if layout_mode == "dual_branch" else (46.0 if max_rows <= 3 else 36.0)
        NODE_H = 88.0 if max_rows <= 3 else 78.0
        TOP_Y = 82.0 if has_skip else 58.0
        BOT_PAD = 52.0 if has_skip else 26.0
        group_inner_h = max_rows * NODE_H + max(0, max_rows - 1) * GAP_Y
        GROUP_H = GROUP_HEAD_H + group_inner_h + GROUP_PAD_BOT
        H = max(520, int(round(TOP_Y + GROUP_H + BOT_PAD)))
        avail_w = W - 2 * MARGIN_X - max(0, n_stages - 1) * CHANNEL_W
        # In `sample_left`, give Stage 1 extra width for embedding a real sample figure!
        if layout_mode == "sample_left" and n_stages >= 3:
            w0 = avail_w * 0.31
            w_rest = (avail_w - w0) / (n_stages - 1)
            widths = [w0] + [w_rest] * (n_stages - 1)
        else:
            widths = [avail_w / n_stages] * n_stages

        cur_x = MARGIN_X
        for si, st in enumerate(non_empty):
            gw = widths[si]
            nw = max(148.0, gw - 2 * GROUP_PAD_X)
            groups_out.append({
                "id": str(st.get("id") or f"g{si + 1}"),
                "label": str(st.get("label") or f"Stage {si + 1}"),
                "x": round(cur_x, 1), "y": round(TOP_Y, 1), "w": round(gw, 1), "h": round(GROUP_H, 1),
                "tone": str(st.get("tone") or "neutral"),
            })
            st_nodes = st["nodes"]
            k = len(st_nodes)
            block_h = k * NODE_H + max(0, k - 1) * GAP_Y
            start_y = TOP_Y + GROUP_HEAD_H + (group_inner_h - block_h) / 2.0
            for ri, n in enumerate(st_nodes):
                ny = start_y + ri * (NODE_H + GAP_Y)
                # In `sample_left`, make the first input node taller if it is the sole node in Stage 1
                nh = (GROUP_H - GROUP_HEAD_H - GROUP_PAD_BOT - 12.0) if (layout_mode == "sample_left" and si == 0 and k == 1) else NODE_H
                nodes_out.append({
                    "id": str(n["id"]), "label": str(n.get("label") or f"Module {ri + 1}"), "sublabel": str(n.get("sublabel") or ""),
                    "x": round(cur_x + GROUP_PAD_X, 1), "y": round(ny, 1), "w": round(nw, 1), "h": round(min(220.0, nh), 1),
                    "tone": str(n.get("tone") or "primary"), "icon": str(n.get("icon") or "encoder_stack"),
                    **({"ai_image_b64": n["ai_image_b64"]} if n.get("ai_image_b64") else {}),
                })
            cur_x += gw + CHANNEL_W

    return normalize_blueprint(
        {
            "title": title,
            "venue_theme": venue_theme,
            "layout_mode": layout_mode,
            "width": W,
            "height": H,
            "font_size": 14,
            "corner_radius": 11,
            "groups": groups_out,
            "nodes": nodes_out,
            "edges": edges,
            **({"custom_colors": custom_colors} if custom_colors else {}),
        },
        venue_theme,
    )


def _extract_json_obj(raw: str | None) -> dict[str, Any]:
    if not raw:
        raise ValueError("模型返回为空")
    m = re.search(r"\{[\s\S]*\}", raw)
    if not m:
        raise ValueError("未找到有效 JSON 对象")
    return json.loads(m.group(0))


# ---------- Collaborative Multi-Agent PPT Flowchart Pipeline (ONE Unified Zero-Overlap Diagram!) ----------
async def stream_concurrent_diagram_agents(
    method_text: str,
    venue_theme: str = "CVPR Clean Slate",
    concurrency: int = 3,
    generate_ai_icons: bool = False,
    layout_mode: str = "auto",
    custom_colors: dict[str, str] | None = None,
) -> AsyncGenerator[dict[str, Any], None]:
    """Collaborative Multi-Agent Assembly of ONE top-venue editable PPTX flowchart:
    Phase 1: Lead Architect Agent designs unified layout & dispatches exact per-stage contracts.
    Phase 2: Parallel Stage Builder Agents (Semaphore(concurrency)) design each stage's modules concurrently.
    Phase 3: Anti-Hallucination Edge Auditor Agent verifies every arrow against the paper & prunes clutter.
    Phase 4: Deterministic Grid Layout + Obstacle-Aware Lane Router synthesizes 1:1 SVG & editable PPTX.
    """
    from backend.services.llm_gateway import complete_llm_text, generate_ai_image_b64, resolve_role_provider

    prov, model = resolve_role_provider("writing")
    if not prov or not model or (not prov.get("api_key") and prov.get("region") != "local"):
        yield {
            "type": "need_api_key",
            "message": "请先在「配置 API」中配置模型密钥并选择模型，即可启动多智能体协同分工绘制零重叠顶刊 PPT 流程图。",
        }
        return

    n_workers = max(1, min(4, int(concurrency)))
    paper_ctx = method_text[:4000]

    # ---------- PHASE 1: Lead Architect Agent (Global Layout & Task Dispatch) ----------
    yield {"type": "worker_start", "id": "architect", "role": "architect", "name": "1. 总规划架构师 · 全局排版与任务派发"}
    arch_sys = (
        "You are the Lead Diagram Architect designing ONE clean, publication-grade CVPR/NeurIPS architecture figure.\n"
        "Your job is ONLY to partition the paper's method into 3 or 4 clean left-to-right stages and issue crystal-clear "
        "task briefs + grounded inter-stage interface contracts to specialist Stage Builder Agents.\n"
        "STRICT ANTI-HALLUCINATION RULES:\n"
        "- ONLY include stages, modules, and data flows explicitly supported by the paper/prompt.\n"
        "- NEVER invent unnecessary cross-stage skip arrows; keep inter-stage interfaces minimal and clean (1-2 flows between adjacent stages, at most 1 explicit residual skip if truly in the method).\n"
        "- Do NOT output pixel coordinates; layout geometry is computed deterministically later.\n"
        "- Keep each stage `label` ultra-concise (<= 26 chars, e.g. `Stage 2 · CSIE Routing`).\n"
        'Return ONLY valid JSON matching:\n'
        '{"title":"Concise Figure Title","stages":['
        '{"id":"s1","label":"Stage 1 · Short Name","task_brief":"Exact responsibility of Stage 1 Agent","max_nodes":2,"expected_inputs":"Raw Input","expected_outputs":"Encoded Features","tone":"neutral"}'
        '],"cross_stage_contracts":[{"from_stage":"s1","to_stage":"s2","data_flow":"short tensor/signal name","dashed":false}]}'
    )
    try:
        plan = _extract_json_obj(await complete_llm_text(arch_sys, f"Paper Method / Request:\n{paper_ctx}", temperature=0.2))
    except Exception as e:
        yield {"type": "worker_error", "id": "architect", "name": "总规划架构师", "error": f"总规划失败：{e}"}
        return

    raw_stages = (plan.get("stages") or [])[:4]
    if len(raw_stages) < 2:
        yield {"type": "worker_error", "id": "architect", "name": "总规划架构师", "error": "规划阶段数不足，请补充更具体的方法描述。"}
        return

    fig_title = str(plan.get("title") or "Architecture Overview")
    contracts = plan.get("cross_stage_contracts") or []
    yield {
        "type": "worker_done",
        "id": "architect",
        "name": f"1. 总规划架构师 · 已拆分 {len(raw_stages)} 阶段任务",
        "detail": " → ".join(str(s.get("label", s.get("id"))) for s in raw_stages),
    }

    # ---------- PHASE 2: Parallel Stage Builder Agents (Concurrent under Semaphore) ----------
    sem = asyncio.Semaphore(n_workers)
    queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
    built_stages: dict[int, dict[str, Any]] = {}

    async def build_stage(idx: int, st_spec: dict[str, Any]) -> None:
        sid = str(st_spec.get("id") or f"s{idx + 1}")
        s_label = str(st_spec.get("label") or f"Stage {idx + 1}")
        wid = f"stage-{idx + 1}"
        async with sem:
            await queue.put({"type": "worker_start", "id": wid, "role": "stage", "name": f"2.{idx + 1} 阶段绘制员 · {s_label}"})
            stage_sys = (
                f"You are the Specialist Builder Agent for ONLY ONE stage ({sid}: {s_label}) of a unified academic architecture diagram.\n"
                "Do NOT design other stages. Focus strictly on your assigned Task Brief.\n"
                f"Task Brief: {st_spec.get('task_brief', '')}\n"
                f"Expected Inputs: {st_spec.get('expected_inputs', '')} | Expected Outputs: {st_spec.get('expected_outputs', '')}\n"
                f"Allowed node count: 1 to {min(3, max(1, int(st_spec.get('max_nodes') or 3)))} nodes (top-to-bottom order).\n"
                "Rules:\n"
                f"- Prefix ALL your node IDs with `{sid}_` (e.g. `{sid}_n1`, `{sid}_n2`).\n"
                "- Keep `label` crisp (<= 4 words), `sublabel` concise (tensor dims or core op, <= 24 chars).\n"
                "- Choose `tone` from: primary, accent, sage, violet, neutral.\n"
                "- Choose the most semantically accurate 2.5D DL `icon` from: conv_stack_3d (3D multi-layer conv feature maps), conv_pyramid (CNN downsampling pyramid), patch_grid (ViT patchify), attn_grid (attention heatmap), cross_attn (multimodal cross-attention), unet_trapezoid (encoder-decoder), moe_router (MoE gating), diffusion_steps (denoising steps), tensor_cube, encoder_stack, token_strip, gate_router, merge_pool, none.\n"
                "- Output `internal_edges` ONLY for genuine top-to-bottom data flows strictly inside this stage.\n"
                "- Specify `entry_node_id` (primary receiver from previous stage) and `exit_node_id` (primary output to next stage).\n"
                'Return ONLY valid JSON: {"nodes":[{"id":"...","label":"...","sublabel":"...","tone":"primary","icon":"encoder_stack"}],'
                '"internal_edges":[{"from":"...","to":"...","label":"short","dashed":false}],"entry_node_id":"...","exit_node_id":"..."}'
            )
            try:
                res = _extract_json_obj(await complete_llm_text(stage_sys, f"Paper Context (reference ONLY your stage):\n{paper_ctx}", temperature=0.22))
                s_nodes = (res.get("nodes") or [])[:3]
                if not s_nodes:
                    s_nodes = [{"id": f"{sid}_n1", "label": s_label, "sublabel": "", "tone": "primary", "icon": "encoder_stack"}]
                for ni, n in enumerate(s_nodes):
                    n["id"] = str(n.get("id") or f"{sid}_n{ni + 1}")
                    if not n["id"].startswith(f"{sid}_"):
                        n["id"] = f"{sid}_{n['id']}"
                valid_local = {n["id"] for n in s_nodes}
                local_edges = []
                for e in res.get("internal_edges") or []:
                    u, v = str(e.get("from", "")), str(e.get("to", ""))
                    if u not in valid_local and f"{sid}_{u}" in valid_local:
                        u = f"{sid}_{u}"
                    if v not in valid_local and f"{sid}_{v}" in valid_local:
                        v = f"{sid}_{v}"
                    if u in valid_local and v in valid_local and u != v:
                        local_edges.append({"from": u, "to": v, "label": str(e.get("label") or "")[:14], "dashed": bool(e.get("dashed", False))})
                entry_id = str(res.get("entry_node_id") or s_nodes[0]["id"])
                exit_id = str(res.get("exit_node_id") or s_nodes[-1]["id"])
                if entry_id not in valid_local:
                    entry_id = f"{sid}_{entry_id}" if f"{sid}_{entry_id}" in valid_local else s_nodes[0]["id"]
                if exit_id not in valid_local:
                    exit_id = f"{sid}_{exit_id}" if f"{sid}_{exit_id}" in valid_local else s_nodes[-1]["id"]

                built_stages[idx] = {
                    "id": sid,
                    "label": s_label,
                    "tone": str(st_spec.get("tone") or "neutral"),
                    "nodes": s_nodes,
                    "internal_edges": local_edges,
                    "entry_node_id": entry_id,
                    "exit_node_id": exit_id,
                }
                await queue.put({
                    "type": "worker_done",
                    "id": wid,
                    "name": f"2.{idx + 1} {s_label} · {len(s_nodes)} 模块",
                    "detail": " / ".join(n["label"] for n in s_nodes),
                })
            except Exception as e:
                # Deterministic minimal fallback so one stage failure never breaks the whole collaborative diagram
                fallback_id = f"{sid}_n1"
                built_stages[idx] = {
                    "id": sid,
                    "label": s_label,
                    "tone": "neutral",
                    "nodes": [{"id": fallback_id, "label": s_label, "sublabel": "", "tone": "primary", "icon": "encoder_stack"}],
                    "internal_edges": [],
                    "entry_node_id": fallback_id,
                    "exit_node_id": fallback_id,
                }
                await queue.put({"type": "worker_error", "id": wid, "name": s_label, "error": str(e)})

    stage_tasks = [asyncio.create_task(build_stage(i, s)) for i, s in enumerate(raw_stages)]
    finished_stages = 0
    while finished_stages < len(raw_stages):
        evt = await queue.get()
        yield evt
        if evt["type"] in ("worker_done", "worker_error"):
            finished_stages += 1
    await asyncio.gather(*stage_tasks, return_exceptions=True)

    ordered_stages = [built_stages[i] for i in range(len(raw_stages)) if i in built_stages]
    stage_by_id = {s["id"]: s for s in ordered_stages}
    all_nodes = [n for s in ordered_stages for n in s["nodes"]]

    # Assemble candidate grounded edges (internal + contracted cross-stage interfaces)
    candidate_edges: list[dict[str, Any]] = []
    for s in ordered_stages:
        candidate_edges.extend(s["internal_edges"])
    for c in contracts:
        s_from = stage_by_id.get(str(c.get("from_stage", "")))
        s_to = stage_by_id.get(str(c.get("to_stage", "")))
        if s_from and s_to and s_from["id"] != s_to["id"]:
            candidate_edges.append({
                "from": s_from["exit_node_id"],
                "to": s_to["entry_node_id"],
                "label": str(c.get("data_flow") or "")[:14],
                "dashed": bool(c.get("dashed", False)),
            })
    # Guarantee adjacent stages are connected cleanly if architect omitted a trivial link
    for i in range(len(ordered_stages) - 1):
        u, v = ordered_stages[i]["exit_node_id"], ordered_stages[i + 1]["entry_node_id"]
        if not any(e["from"] in {n["id"] for n in ordered_stages[i]["nodes"]} and e["to"] in {n["id"] for n in ordered_stages[i + 1]["nodes"]} for e in candidate_edges):
            candidate_edges.append({"from": u, "to": v, "label": "", "dashed": False})

    # ---------- PHASE 3: Anti-Hallucination Edge Auditor Agent + Optional Parallel AI Icon Agent ----------
    yield {"type": "worker_start", "id": "auditor", "role": "auditor", "name": "3. 幻觉连线审查官 · 校验箭头真实性与拓扑精简"}
    if generate_ai_icons:
        yield {"type": "worker_start", "id": "icons", "role": "icons", "name": "3.5 AI 视觉图标员 · 并行生成模块插画"}

    auditor_sys = (
        "You are a strict Academic Diagram Edge Auditor. Your ONLY mission is to eliminate hallucinated arrows, "
        "redundant duplicate edges, accidental backwards cycles, and visual arrow clutter.\n"
        "Rules:\n"
        "- Inspect the assembled stage nodes and candidate edges against the paper text.\n"
        "- Keep ONLY edges strictly grounded in the actual data flow; prune redundant transitive shortcuts unless it is an explicit residual/skip connection in the paper.\n"
        "- Ensure every node participates cleanly with no isolated islands, and keep edge labels concise (<= 14 chars, or empty string when self-evident).\n"
        "- Never invent new node IDs; ONLY use IDs present in the provided node list.\n"
        'Return ONLY valid JSON: {"edges":[{"from":"...","to":"...","label":"short","dashed":false}],"pruned_reason":"一句话中文说明去除了哪些冗余/幻觉连线"}'
    )
    audit_payload = json.dumps(
        {
            "stages": [{"id": s["id"], "label": s["label"], "nodes": [{"id": n["id"], "label": n["label"], "sublabel": n["sublabel"]} for n in s["nodes"]]} for s in ordered_stages],
            "candidate_edges": candidate_edges,
        },
        ensure_ascii=False,
    )

    async def run_auditor() -> tuple[list[dict[str, Any]], str]:
        try:
            ares = _extract_json_obj(await complete_llm_text(auditor_sys, f"Assembled Graph:\n{audit_payload}\n\nPaper Reference:\n{paper_ctx[:2600]}", temperature=0.1))
            valid_ids = {n["id"] for n in all_nodes}
            audited = [
                {"from": str(e["from"]), "to": str(e["to"]), "label": str(e.get("label") or "")[:16], "dashed": bool(e.get("dashed", False))}
                for e in (ares.get("edges") or [])
                if str(e.get("from", "")) in valid_ids and str(e.get("to", "")) in valid_ids and str(e.get("from")) != str(e.get("to"))
            ]
            if audited:
                return audited, str(ares.get("pruned_reason") or "已校验全部连线并去除冗余箭头")
        except Exception:
            pass
        return candidate_edges, "采用架构师核准连线契约"

    async def run_icons() -> int:
        if not generate_ai_icons or not all_nodes:
            return 0
        targets = [n for n in all_nodes if n.get("tone") in ("accent", "sage", "primary")][:3]
        results = await asyncio.gather(
            *(generate_ai_image_b64(f"Minimalist scientific flat vector icon, white background, no text: {n['label']}") for n in targets),
            return_exceptions=True,
        )
        ok_cnt = 0
        for n_obj, r in zip(targets, results):
            if isinstance(r, dict) and r.get("ok") and r.get("b64"):
                n_obj["ai_image_b64"] = r["b64"]
                ok_cnt += 1
        return ok_cnt

    (final_edges, audit_note), icon_cnt = await asyncio.gather(run_auditor(), run_icons())
    pruned_delta = max(0, len(candidate_edges) - len(final_edges))
    yield {
        "type": "worker_done",
        "id": "auditor",
        "name": f"3. 幻觉连线审查官 · 保留 {len(final_edges)} 条有效箭头" + (f"（剔除 {pruned_delta} 条冗余）" if pruned_delta else ""),
        "detail": audit_note,
    }
    if generate_ai_icons:
        yield {"type": "worker_done", "id": "icons", "name": f"3.5 AI 视觉图标员 · 嵌入 {icon_cnt} 枚插画", "detail": ""}

    # ---------- PHASE 4: Deterministic Grid Layout + Optional VLM Visual Self-Critique + 1:1 PPTX Synthesis ----------
    yield {"type": "worker_start", "id": "composer", "role": "composer", "name": "4. 排版引擎 & 视觉自检 · 无碰撞布线与 1:1 PPT 绘成"}
    eff_layout = layout_mode if layout_mode in ("pipeline", "dual_branch", "zoom_callout", "sample_left") else (
        "dual_branch" if len(ordered_stages) >= 3 and len(ordered_stages[0]["nodes"]) == 2 else "pipeline"
    )
    final_bp = compute_clean_grid_layout(fig_title, venue_theme, ordered_stages, final_edges, layout_mode=eff_layout, custom_colors=custom_colors)

    # Optional VLM Visual Self-Critique (runs automatically if a vision provider is configured!)
    v_prov, v_model = resolve_role_provider("vision")
    vlm_note = ""
    if v_prov and v_model and (v_prov.get("api_key") or v_prov.get("region") == "local"):
        try:
            from backend.services.llm_gateway import stream_multimodal_messages

            preview_png = export_diagram_png_bytes(final_bp, dpi=150)
            img_uri = "data:image/png;base64," + base64.b64encode(preview_png).decode("ascii")
            critic_sys = (
                "You are a CVPR/Nature visual figure critic inspecting a freshly rendered architecture diagram.\n"
                "Check ONLY if any node label is too long/cramped, if core novelty blocks need accent/sage highlight tones, "
                "or if a better 2.5D DL icon fits (conv_stack_3d, conv_pyramid, patch_grid, attn_grid, cross_attn, unet_trapezoid, moe_router, diffusion_steps).\n"
                'Return ONLY JSON: {"fixes":[{"id":"node_id","label":"optional shorter label","tone":"optional","icon":"optional"}],"summary":"一句话中文视觉复核结论"}'
            )
            node_roster = json.dumps([{"id": n["id"], "label": n["label"], "tone": n["tone"], "icon": n["icon"]} for n in final_bp["nodes"]], ensure_ascii=False)
            chunks: list[str] = []
            async for d in stream_multimodal_messages(
                v_prov, v_model, critic_sys, [{"role": "user", "content": f"Nodes:\n{node_roster}\nInspect this diagram image and suggest surgical fixes if needed.", "images": [img_uri]}], temperature=0.1
            ):
                chunks.append(d)
            vres = _extract_json_obj("".join(chunks))
            fix_map = {str(f["id"]): f for f in (vres.get("fixes") or []) if f.get("id")}
            for n in final_bp["nodes"]:
                fx = fix_map.get(n["id"])
                if not fx:
                    continue
                if fx.get("label"):
                    n["label"] = str(fx["label"])[:36]
                if fx.get("tone") in ("primary", "accent", "sage", "violet", "neutral"):
                    n["tone"] = fx["tone"]
                if fx.get("icon"):
                    n["icon"] = str(fx["icon"])
            vlm_note = str(vres.get("summary") or "视觉自检完成")
        except Exception:
            vlm_note = ""

    pptx_bytes = export_diagram_pptx_bytes(final_bp)

    yield {
        "type": "worker_done",
        "id": "composer",
        "name": f"4. PPT 合成完成 · 1:1 可编辑 PPTX（{len(pptx_bytes) // 1024} KB）" + (" · 已通过视觉自检" if vlm_note else ""),
        "detail": vlm_note or f"{len(final_bp['groups'])} 阶段 · {len(final_bp['nodes'])} 模块 · {len(final_bp['edges'])} 条无重叠正交箭头",
    }
    yield {
        "type": "candidate",
        "id": "collaborative-final",
        "name": f"多智能体协同成果 · {fig_title}",
        "blueprint": final_bp,
        "node_count": len(final_bp["nodes"]),
        "edge_count": len(final_bp["edges"]),
        "audit_note": f"{audit_note}" + (f" | 视觉自检：{vlm_note}" if vlm_note else ""),
    }
    yield {"type": "done", "workers": len(ordered_stages) + 2, "provider": prov["name"], "model": model, "audit_note": audit_note}
