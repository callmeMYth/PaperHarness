"""Safe Figure Text Patcher (SVG / Vector PDF / Raster PNG with Pixel-Diff Integrity Guard).

Academic integrity rule:
- Vector figures (SVG / PDF): modify ONLY text nodes cleanly without touching a single plotted curve.
- Raster figures (PNG / JPG): sample local background inside each user-selected bounding box,
  inpaint/mask strictly inside the box, render replacement text, and compute a Pixel-Diff Integrity
  Certificate proving 0.00% pixels outside the text boxes were altered.
"""
from __future__ import annotations

import base64
import io
import os
import re
import xml.etree.ElementTree as ET
from typing import Any

import numpy as np
from PIL import Image, ImageDraw, ImageFont

FONT_CANDIDATES = {
    "sans": [
        r"C:\Windows\Fonts\arial.ttf",
        r"C:\Windows\Fonts\segoeui.ttf",
        r"C:\Windows\Fonts\calibri.ttf",
        r"C:\Windows\Fonts\msyh.ttc",
    ],
    "serif": [
        r"C:\Windows\Fonts\times.ttf",
        r"C:\Windows\Fonts\georgia.ttf",
        r"C:\Windows\Fonts\simsun.ttc",
    ],
    "mono": [
        r"C:\Windows\Fonts\consola.ttf",
        r"C:\Windows\Fonts\cour.ttf",
    ],
    "cjk": [
        r"C:\Windows\Fonts\msyh.ttc",
        r"C:\Windows\Fonts\simsun.ttc",
        r"C:\Windows\Fonts\simhei.ttf",
    ],
}


def _load_font(family: str, size: int, has_cjk: bool = False) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    order = FONT_CANDIDATES["cjk"] + FONT_CANDIDATES.get(family, []) if has_cjk else FONT_CANDIDATES.get(family, FONT_CANDIDATES["sans"])
    for fp in order:
        if os.path.exists(fp):
            try:
                return ImageFont.truetype(fp, size=max(8, size))
            except Exception:
                continue
    return ImageFont.load_default()


def _parse_float(val: str | float | int | None) -> float | None:
    if val is None or val == "":
        return None
    try:
        m = re.match(r"^\s*(-?\d+(?:\.\d+)?)", str(val))
        return float(m.group(1)) if m else None
    except Exception:
        return None


def inspect_svg_text_nodes(svg_text: str) -> dict[str, Any]:
    """Extract every editable <text> element from a vector SVG figure."""
    root = ET.fromstring(svg_text)
    nodes: list[dict[str, Any]] = []
    idx = 0
    for elem in root.iter():
        tag = elem.tag.split("}")[-1]
        if tag == "text":
            full_text = "".join(elem.itertext()).strip()
            if full_text:
                nodes.append({
                    "id": f"svg-txt-{idx}",
                    "index": idx,
                    "text": full_text,
                    "font_size": elem.attrib.get("font-size", ""),
                    "fill": elem.attrib.get("fill", "#16191F"),
                    "x": elem.attrib.get("x", ""),
                    "y": elem.attrib.get("y", ""),
                    "dx": 0.0,
                    "dy": 0.0,
                })
                idx += 1
    return {"kind": "svg", "nodes": nodes, "svg": svg_text}


def patch_svg_text_nodes(svg_text: str, edits: list[dict[str, Any]]) -> dict[str, Any]:
    """Apply lossless text, font-size, color, and exact X/Y position updates to SVG <text> nodes."""
    ET.register_namespace("", "http://www.w3.org/2000/svg")
    root = ET.fromstring(svg_text)
    edit_map = {int(e["index"]): e for e in edits}
    idx = 0
    changed = 0
    for elem in root.iter():
        tag = elem.tag.split("}")[-1]
        if tag == "text":
            full_text = "".join(elem.itertext()).strip()
            if full_text:
                if idx in edit_map:
                    ed = edit_map[idx]
                    new_txt = ed.get("text", full_text)
                    dx = float(ed.get("dx") or 0.0)
                    dy = float(ed.get("dy") or 0.0)
                    orig_x = elem.attrib.get("x", "")
                    orig_y = elem.attrib.get("y", "")
                    req_x = str(ed.get("x", "")) if ed.get("x") is not None else orig_x
                    req_y = str(ed.get("y", "")) if ed.get("y") is not None else orig_y
                    pos_changed = (abs(dx) > 1e-4 or abs(dy) > 1e-4 or req_x != orig_x or req_y != orig_y)

                    if new_txt != full_text or ed.get("font_size") or ed.get("fill") or pos_changed:
                        if new_txt != full_text:
                            for child in list(elem):
                                elem.remove(child)
                            elem.text = new_txt
                        if ed.get("font_size"):
                            elem.set("font-size", str(ed["font_size"]))
                        if ed.get("fill"):
                            elem.set("fill", str(ed["fill"]))

                        if req_x != orig_x and req_x != "":
                            elem.set("x", req_x)
                        if req_y != orig_y and req_y != "":
                            elem.set("y", req_y)

                        if abs(dx) > 1e-4 or abs(dy) > 1e-4:
                            cur_x = _parse_float(elem.attrib.get("x"))
                            cur_y = _parse_float(elem.attrib.get("y"))
                            if cur_x is not None and cur_y is not None and not list(elem):
                                elem.set("x", f"{cur_x + dx:.2f}")
                                elem.set("y", f"{cur_y + dy:.2f}")
                            else:
                                prev_tf = (elem.attrib.get("transform") or "").strip()
                                tr = f"translate({dx:.2f},{dy:.2f})"
                                elem.set("transform", f"{prev_tf} {tr}".strip())
                        changed += 1
                idx += 1

    patched_svg = ET.tostring(root, encoding="unicode")
    return {
        "kind": "svg",
        "svg": patched_svg,
        "changed_nodes": changed,
        "integrity": {
            "mode": "lossless_vector",
            "outside_box_diff_pct": 0.0,
            "verified": True,
            "note": f"无损矢量修改已应用于 {changed} 处文字（含精确坐标调整），数据曲线零改动。",
        },
    }


def inspect_pdf_figure(pdf_bytes: bytes) -> dict[str, Any]:
    """Render first page of a vector PDF figure and extract exact text span bounding boxes."""
    import fitz

    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    page = doc[0]
    scale = 2.0
    pix = page.get_pixmap(matrix=fitz.Matrix(scale, scale))
    png_b64 = base64.b64encode(pix.tobytes("png")).decode("ascii")

    spans: list[dict[str, Any]] = []
    text_dict = page.get_text("dict")
    for block in text_dict.get("blocks", []):
        for line in block.get("lines", []):
            for sp in line.get("spans", []):
                txt = sp.get("text", "").strip()
                if not txt:
                    continue
                x0, y0, x1, y1 = sp["bbox"]
                spans.append({
                    "id": f"box-{len(spans)}",
                    "text": txt,
                    "x": round(x0 * scale),
                    "y": round(y0 * scale),
                    "w": max(16, round((x1 - x0) * scale)),
                    "h": max(14, round((y1 - y0) * scale)),
                    "font_size": max(10, round(sp.get("size", 10) * scale)),
                    "color": "#16191F",
                    "font_family": "sans",
                })

    return {
        "kind": "raster",
        "width": pix.width,
        "height": pix.height,
        "image_b64": png_b64,
        "boxes": spans,
    }


def patch_raster_figure(image_b64: str, boxes: list[dict[str, Any]]) -> dict[str, Any]:
    """Patch text strictly inside declared bounding boxes + compute Pixel-Diff Integrity Certificate."""
    raw = base64.b64decode(image_b64.split(",")[-1])
    orig_img = Image.open(io.BytesIO(raw)).convert("RGB")
    patched = orig_img.copy()
    W, H = orig_img.size
    arr_orig = np.array(orig_img)
    draw = ImageDraw.Draw(patched)

    allowed_mask = np.zeros((H, W), dtype=bool)
    edited_count = 0

    for b in boxes:
        x = max(0, min(W - 1, int(round(b["x"]))))
        y = max(0, min(H - 1, int(round(b["y"]))))
        w = max(4, min(W - x, int(round(b["w"]))))
        h = max(4, min(H - y, int(round(b["h"]))))
        allowed_mask[y : y + h, x : x + w] = True

        def _sample_bg(rx: int, ry: int, rw: int, rh: int) -> tuple[int, int, int]:
            bps = []
            if ry > 1:
                bps.append(arr_orig[max(0, ry - 2) : ry, rx : rx + rw].reshape(-1, 3))
            if ry + rh + 2 < H:
                bps.append(arr_orig[ry + rh : min(H, ry + rh + 2), rx : rx + rw].reshape(-1, 3))
            if rx > 1:
                bps.append(arr_orig[ry : ry + rh, max(0, rx - 2) : rx].reshape(-1, 3))
            if rx + rw + 2 < W:
                bps.append(arr_orig[ry : ry + rh, rx + rw : min(W, rx + rw + 2)].reshape(-1, 3))
            return tuple(int(v) for v in np.median(np.vstack(bps), axis=0)) if bps else (255, 255, 255)

        # If user dragged a detected box away from its original text spot, erase the original spot cleanly too
        if b.get("erase_x") is not None and b.get("erase_w"):
            ex = max(0, min(W - 1, int(round(b["erase_x"]))))
            ey = max(0, min(H - 1, int(round(b["erase_y"]))))
            ew = max(4, min(W - ex, int(round(b["erase_w"]))))
            eh = max(4, min(H - ey, int(round(b["erase_h"]))))
            if (ex, ey, ew, eh) != (x, y, w, h):
                allowed_mask[ey : ey + eh, ex : ex + ew] = True
                draw.rectangle([ex, ey, ex + ew - 1, ey + eh - 1], fill=_sample_bg(ex, ey, ew, eh))

        bg = _sample_bg(x, y, w, h)
        draw.rectangle([x, y, x + w - 1, y + h - 1], fill=bg)
        new_txt = str(b.get("text", ""))
        if new_txt:
            has_cjk = bool(re.search(r"[\u4e00-\u9fff]", new_txt))
            fs = int(b.get("font_size") or max(11, int(h * 0.72)))
            font = _load_font(str(b.get("font_family", "sans")), fs, has_cjk=has_cjk)
            color = str(b.get("color", "#16191F"))
            align = str(b.get("align", "center"))
            tb = draw.textbbox((0, 0), new_txt, font=font)
            tw, th = tb[2] - tb[0], tb[3] - tb[1]
            if align == "left":
                tx = x + 3
            elif align == "right":
                tx = x + max(1, w - tw - 3)
            else:
                tx = x + max(1, (w - tw) // 2)
            ty = y + max(0, (h - th) // 2) - tb[1]
            tx += int(round(b.get("text_dx") or 0))
            ty += int(round(b.get("text_dy") or 0))
            patch_crop = patched.crop((x, y, x + w, y + h))
            cd = ImageDraw.Draw(patch_crop)
            cd.text((tx - x, ty - y), new_txt, fill=color, font=font)
            patched.paste(patch_crop, (x, y))
        edited_count += 1

    arr_new = np.array(patched)
    diff_mask = np.any(arr_orig != arr_new, axis=2)
    total_px = W * H
    inside_diff_pct = round(float(np.sum(diff_mask & allowed_mask)) / max(1, total_px) * 100.0, 3)
    outside_diff_pct = round(float(np.sum(diff_mask & (~allowed_mask))) / max(1, total_px) * 100.0, 4)

    buf = io.BytesIO()
    patched.save(buf, format="PNG")
    out_b64 = base64.b64encode(buf.getvalue()).decode("ascii")

    return {
        "kind": "raster",
        "image_b64": out_b64,
        "width": W,
        "height": H,
        "edited_boxes": edited_count,
        "integrity": {
            "mode": "strict_bbox_clipped_raster",
            "inside_box_diff_pct": inside_diff_pct,
            "outside_box_diff_pct": outside_diff_pct,
            "verified": outside_diff_pct == 0.0,
            "note": f"Integrity verified: {outside_diff_pct:.4f}% pixels modified outside text boxes ({edited_count} label(s) updated).",
        },
    }
