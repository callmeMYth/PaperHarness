"""Full LaTeX Project Workspace Manager (Folder & Overleaf .zip Support).

Mounts an entire LaTeX project directory (`main.tex`, `sections/*.tex`, `*.bib`,
`figures/*.pdf|svg|png|jpg`, `*.csv`), serves figure previews (including live PDF->PNG
rasterization), loads figures directly into Safe Figure Patcher or Multimodal Chat,
and saves modified `.tex` / `.bib` / figures cleanly back to disk.
"""
from __future__ import annotations

import base64
import io
import mimetypes
import re
import zipfile
from pathlib import Path
from typing import Any

import pymupdf
from PIL import Image

from backend.config import DATA_DIR
from backend.services.doc_io import parse_outline
from backend.services.figure_patcher import inspect_pdf_figure, inspect_svg_text_nodes

WORKSPACES_DIR = DATA_DIR / "workspaces"
WORKSPACES_DIR.mkdir(parents=True, exist_ok=True)

_ACTIVE_ROOT: Path | None = None
_SKIP_DIRS = {".git", "__pycache__", "__MACOSX", "node_modules", ".idea", ".vscode"}
_IMG_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".svg", ".pdf"}


def get_active_workspace_root() -> Path | None:
    return _ACTIVE_ROOT if (_ACTIVE_ROOT and _ACTIVE_ROOT.exists()) else None


def _safe_resolve(rel: str, root: Path | None = None) -> Path:
    base = (root or get_active_workspace_root())
    if not base:
        raise ValueError("尚未打开任何 LaTeX 工作区目录")
    base_res = base.resolve()
    target = (base_res / rel.lstrip("/\\")).resolve()
    if base_res != target and base_res not in target.parents:
        raise ValueError("路径越界：仅允许访问当前工作区内的文件")
    return target


def _extract_tex_title(tex_text: str, fallback: str) -> str:
    m = re.search(r"\\title(?:\[[^\]]*\])?\{([\s\S]*?)\}", tex_text)
    if m:
        t = re.sub(r"\\[a-zA-Z]+\*?\{([^}]*)\}", r"\1", m.group(1))
        t = re.sub(r"\\\\|\s+", " ", t).strip()
        if t:
            return t[:140]
    return fallback


def _split_tex_preamble(tex_text: str) -> tuple[str, str]:
    m_b = re.search(r"\\begin\{document\}", tex_text)
    m_e = re.search(r"\\end\{document\}", tex_text)
    if m_b:
        pre = tex_text[: m_b.end()]
        body = tex_text[m_b.end() : m_e.start() if m_e else len(tex_text)].strip()
        return pre, body
    return "", tex_text


def _extract_graphics_paths(tex_text: str) -> list[str]:
    m = re.search(r"\\graphicspath\{([\s\S]*?)\}", tex_text)
    if not m:
        return []
    return [g.strip().strip("/\\") for g in re.findall(r"\{([^}]+)\}", m.group(1)) if g.strip()]


def _expand_tex_inputs(root: Path, tex_path: Path, depth: int = 0) -> str:
    """Resolve \\input{...} / \\include{...} cleanly (preserving clear file boundary comments)."""
    if depth > 4 or not tex_path.exists():
        return ""
    text = tex_path.read_text(encoding="utf-8-sig", errors="replace")

    def repl(m: re.Match) -> str:
        ref = m.group(1).strip()
        cands = [tex_path.parent / ref, root / ref]
        if not ref.endswith(".tex"):
            cands.extend([tex_path.parent / f"{ref}.tex", root / f"{ref}.tex"])
        for c in cands:
            if c.exists() and c.is_file():
                rel_c = c.resolve().relative_to(root.resolve()).as_posix()
                inner = _expand_tex_inputs(root, c, depth + 1)
                return f"\n% === \\input{{{rel_c}}} ===\n{inner}\n"
        return m.group(0)

    return re.sub(r"(?<!%)\\(?:input|include)\{([^}]+)\}", repl, text)


def scan_latex_workspace(root_dir: Path, expand_inputs: bool = False) -> dict[str, Any]:
    global _ACTIVE_ROOT
    root = root_dir.resolve()
    if not root.exists() or not root.is_dir():
        raise ValueError(f"目录不存在：{root}")

    # Auto-unwrap single nested folder (e.g. `paper/paper/main.tex` from Overleaf/WeChat unpack)
    top_visible = [p for p in root.iterdir() if p.name not in _SKIP_DIRS]
    if len(top_visible) == 1 and top_visible[0].is_dir():
        root = top_visible[0].resolve()

    _ACTIVE_ROOT = root

    tex_files: list[dict[str, Any]] = []
    bib_files: list[dict[str, Any]] = []
    figures: list[dict[str, Any]] = []
    data_files: list[dict[str, Any]] = []

    for p in sorted(root.rglob("*")):
        if not p.is_file():
            continue
        if any(part in _SKIP_DIRS for part in p.relative_to(root).parts):
            continue
        rel = p.relative_to(root).as_posix()
        ext = p.suffix.lower()
        size_kb = round(p.stat().st_size / 1024.0, 1)
        if ext == ".tex":
            raw_head = p.read_text(encoding="utf-8-sig", errors="replace")[:4000]
            is_entry = bool(re.search(r"\\documentclass|\\begin\{document\}", raw_head))
            tex_files.append({"rel": rel, "name": p.name, "size_kb": size_kb, "is_entry": is_entry})
        elif ext == ".bib":
            bib_files.append({"rel": rel, "name": p.name, "size_kb": size_kb})
        elif ext in _IMG_EXTS:
            # Exclude compiled full-paper PDFs sitting beside a same-stem .tex (e.g. main.pdf, main_review.pdf)
            if ext == ".pdf" and (p.parent / f"{p.stem}.tex").exists():
                continue
            figures.append({"rel": rel, "name": p.name, "ext": ext.lstrip("."), "size_kb": size_kb})
        elif ext in (".csv", ".tsv"):
            data_files.append({"rel": rel, "name": p.name, "size_kb": size_kb})

    # Pick main .tex entry intelligently
    entries = [f for f in tex_files if f["is_entry"]]
    main_tex = None
    for pref in ("main.tex", "paper.tex", "manuscript.tex"):
        main_tex = next((f for f in entries if f["name"].lower() == pref), None)
        if main_tex:
            break
    if not main_tex:
        main_tex = sorted(entries, key=lambda x: (x["rel"].count("/"), len(x["rel"])))[0] if entries else (tex_files[0] if tex_files else None)

    title = root.name
    preamble = ""
    content = ""
    graphics_paths: list[str] = []
    if main_tex:
        main_path = root / main_tex["rel"]
        full_raw = _expand_tex_inputs(root, main_path) if expand_inputs else main_path.read_text(encoding="utf-8-sig", errors="replace")
        title = _extract_tex_title(full_raw, root.name)
        preamble, content = _split_tex_preamble(full_raw)
        graphics_paths = _extract_graphics_paths(full_raw)

    # Concatenate .bib files so Citation Lab works automatically on the full LaTeX workspace
    bibtex_parts = []
    for bf in bib_files[:4]:
        try:
            bibtex_parts.append((root / bf["rel"]).read_text(encoding="utf-8-sig", errors="replace").strip())
        except Exception:
            pass
    merged_bib = "\n\n".join(p for p in bibtex_parts if p)

    return {
        "ok": True,
        "root_dir": str(root),
        "project_name": root.name,
        "title": title,
        "main_tex": main_tex["rel"] if main_tex else "",
        "active_file": main_tex["rel"] if main_tex else "",
        "preamble": preamble,
        "content": content,
        "outline": parse_outline(content, "latex"),
        "bibtex": merged_bib,
        "graphics_paths": graphics_paths,
        "tex_files": tex_files,
        "bib_files": bib_files,
        "figures": figures,
        "data_files": data_files,
    }


def import_workspace_zip_bytes(filename: str, raw_bytes: bytes) -> dict[str, Any]:
    """Extract an Overleaf/LaTeX .zip into local_data/workspaces/<stem> and mount it."""
    stem = re.sub(r"[^A-Za-z0-9_\u4e00-\u9fff-]+", "_", Path(filename).stem).strip("_") or "latex_project"
    dest = WORKSPACES_DIR / stem
    if dest.exists():
        import shutil
        shutil.rmtree(dest, ignore_errors=True)
    dest.mkdir(parents=True, exist_ok=True)

    with zipfile.ZipFile(io.BytesIO(raw_bytes)) as zf:
        for info in zf.infolist():
            if info.is_dir():
                continue
            parts = [p for p in Path(info.filename).parts if p not in ("", ".", "..")]
            if not parts or any(p in _SKIP_DIRS for p in parts):
                continue
            out = dest.joinpath(*parts)
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_bytes(zf.read(info))

    # Unwrap single top-level directory (standard Overleaf / GitHub zip convention)
    top_entries = [p for p in dest.iterdir() if p.name not in _SKIP_DIRS]
    mount_root = top_entries[0] if (len(top_entries) == 1 and top_entries[0].is_dir()) else dest
    return scan_latex_workspace(mount_root, expand_inputs=False)


def import_workspace_uploaded_files(project_name: str, items: list[tuple[str, bytes]]) -> dict[str, Any]:
    """Persist files dropped from a folder (browser webkitGetAsEntry fallback) and mount as workspace."""
    import shutil

    stem = re.sub(r"[^A-Za-z0-9_\u4e00-\u9fff-]+", "_", project_name).strip("_") or "latex_project"
    dest = WORKSPACES_DIR / stem
    if dest.exists():
        shutil.rmtree(dest, ignore_errors=True)
    dest.mkdir(parents=True, exist_ok=True)

    skip_exts = {".aux", ".bbl", ".blg", ".brf", ".log", ".out", ".fls", ".fdb_latexmk", ".synctex"}
    for rel, raw in items:
        parts = [p for p in Path(rel).parts if p not in ("", ".", "..")]
        if not parts or any(p in _SKIP_DIRS for p in parts):
            continue
        if Path(parts[-1]).suffix.lower() in skip_exts:
            continue
        out = dest.joinpath(*parts)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(raw)
    return scan_latex_workspace(dest, expand_inputs=False)


def resolve_workspace_figure(ref: str) -> Path | None:
    """Resolve a relative figure path or LaTeX \\includegraphics reference (even without extension)."""
    root = get_active_workspace_root()
    if not root:
        return None
    cleaned = ref.strip().strip('"').strip("'").lstrip("./")
    if not cleaned:
        return None

    # Direct match or extension-completed match in root & common figure folders
    search_prefixes = ["", "figures", "figs", "fig", "images", "img", "assets"]
    cands: list[Path] = []
    for pref in search_prefixes:
        base = (root / pref / cleaned) if pref else (root / cleaned)
        cands.append(base)
        if not base.suffix:
            for ext in (".png", ".jpg", ".jpeg", ".svg", ".pdf", ".webp"):
                cands.append(base.with_suffix(ext))

    root_res = root.resolve()
    for c in cands:
        try:
            cr = c.resolve()
            if (root_res == cr or root_res in cr.parents) and cr.exists() and cr.is_file():
                return cr
        except Exception:
            continue

    # Basename fallback search inside workspace
    stem = Path(cleaned).stem.lower()
    for p in root.rglob("*"):
        if p.is_file() and p.suffix.lower() in _IMG_EXTS and p.stem.lower() == stem:
            return p
    return None


def read_workspace_asset_preview(ref: str) -> tuple[bytes, str]:
    """Return image bytes + media_type for live preview (auto-rasterizes .pdf figures to PNG)."""
    p = resolve_workspace_figure(ref)
    if not p:
        raise FileNotFoundError(f"工作区中未找到图片：{ref}")
    ext = p.suffix.lower()
    if ext == ".pdf":
        doc = pymupdf.open(str(p))
        pix = doc[0].get_pixmap(matrix=pymupdf.Matrix(2.0, 2.0), alpha=False)
        return pix.tobytes("png"), "image/png"
    if ext == ".svg":
        return p.read_bytes(), "image/svg+xml"
    mime = mimetypes.guess_type(str(p))[0] or "image/png"
    return p.read_bytes(), mime


def read_workspace_text_file(rel: str, expand_inputs: bool = False) -> dict[str, Any]:
    p = _safe_resolve(rel)
    if not p.exists() or not p.is_file():
        raise FileNotFoundError(f"文件不存在：{rel}")
    root = get_active_workspace_root()
    assert root is not None
    raw = _expand_tex_inputs(root, p) if (expand_inputs and p.suffix.lower() == ".tex") else p.read_text(encoding="utf-8-sig", errors="replace")
    if p.suffix.lower() == ".tex":
        pre, body = _split_tex_preamble(raw)
        return {"ok": True, "rel": rel, "full_path": str(p), "preamble": pre, "content": body if pre else raw, "raw": raw, "outline": parse_outline(raw, "latex")}
    return {"ok": True, "rel": rel, "full_path": str(p), "preamble": "", "content": raw, "raw": raw}


def save_workspace_text_file(rel: str, content: str, preamble: str = "") -> dict[str, Any]:
    p = _safe_resolve(rel)
    p.parent.mkdir(parents=True, exist_ok=True)
    # Create a one-time backup before first overwrite so user's original LaTeX is always safe
    bak = p.with_suffix(p.suffix + ".bak")
    if p.exists() and not bak.exists():
        bak.write_bytes(p.read_bytes())
    final_text = f"{preamble}\n\n{content}\n\\end{{document}}\n" if (preamble.strip() and "\\begin{document}" in preamble and "\\end{document}" not in content) else content
    p.write_text(final_text, encoding="utf-8")
    return {"ok": True, "rel": rel, "full_path": str(p)}


def load_workspace_figure_for_patcher(rel: str) -> dict[str, Any]:
    p = resolve_workspace_figure(rel)
    if not p:
        raise FileNotFoundError(f"工作区中未找到图片：{rel}")
    ext = p.suffix.lower()
    raw = p.read_bytes()
    if ext == ".svg":
        return {**inspect_svg_text_nodes(raw.decode("utf-8", errors="replace")), "rel": rel, "full_path": str(p)}
    if ext == ".pdf":
        return {**inspect_pdf_figure(raw), "rel": rel, "full_path": str(p)}
    img = Image.open(io.BytesIO(raw)).convert("RGB")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return {
        "kind": "raster",
        "width": img.size[0],
        "height": img.size[1],
        "image_b64": base64.b64encode(buf.getvalue()).decode("ascii"),
        "boxes": [],
        "rel": rel,
        "full_path": str(p),
    }


def workspace_figure_to_data_url(rel: str) -> dict[str, Any]:
    """Convert any workspace figure (.png/.jpg/.svg/.pdf) into a PNG data URL ready for Multimodal Chat."""
    p = resolve_workspace_figure(rel)
    if not p:
        raise FileNotFoundError(f"工作区中未找到图片：{rel}")
    ext = p.suffix.lower()
    if ext == ".pdf":
        doc = pymupdf.open(str(p))
        png = doc[0].get_pixmap(matrix=pymupdf.Matrix(2.0, 2.0), alpha=False).tobytes("png")
    elif ext == ".svg":
        pdf_bytes = pymupdf.open(stream=p.read_bytes(), filetype="svg").convert_to_pdf()
        png = pymupdf.open(stream=pdf_bytes, filetype="pdf")[0].get_pixmap(dpi=220, alpha=False).tobytes("png")
    else:
        img = Image.open(io.BytesIO(p.read_bytes())).convert("RGB")
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        png = buf.getvalue()
    return {
        "ok": True,
        "rel": rel,
        "full_path": str(p),
        "data_url": "data:image/png;base64," + base64.b64encode(png).decode("ascii"),
    }


def export_submission_zip_bytes() -> tuple[bytes, str, int]:
    """Package clean journal/Overleaf submission.zip excluding build artifacts (.aux/.log/.bak/compiled PDF)."""
    root = get_active_workspace_root()
    if not root:
        raise ValueError("尚未打开任何 LaTeX 论文工作区")
    skip_exts = {".aux", ".bbl", ".blg", ".brf", ".log", ".out", ".fls", ".fdb_latexmk", ".synctex", ".bak", ".toc", ".lof", ".lot", ".nav", ".snm"}
    buf = io.BytesIO()
    count = 0
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
        for p in sorted(root.rglob("*")):
            if not p.is_file():
                continue
            rel_parts = p.relative_to(root).parts
            if any(part in _SKIP_DIRS for part in rel_parts):
                continue
            ext = p.suffix.lower()
            if ext in skip_exts or p.name.endswith(".synctex.gz") or p.name.endswith(".bak"):
                continue
            # Exclude compiled full-paper PDFs beside same-stem .tex
            if ext == ".pdf" and (p.parent / f"{p.stem}.tex").exists():
                continue
            zf.write(p, f"{root.name}/{p.relative_to(root).as_posix()}")
            count += 1
    fname = re.sub(r"[^A-Za-z0-9_\u4e00-\u9fff-]+", "_", root.name)[:36] or "latex_paper"
    return buf.getvalue(), f"{fname}_submission.zip", count
