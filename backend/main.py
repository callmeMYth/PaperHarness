"""PaperHarness FastAPI Server — unified local harness backend + SPA host.

Zero login required. Runs cleanly on 127.0.0.1:8765 for both Web & Windows Desktop App shells.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from backend.config import (
    BUNDLE_DIR,
    PROJECT_ROOT,
    get_skill_dir,
    load_settings,
    mask_key,
    save_settings,
)
from backend.services.academic_engine import (
    clean_typography,
    extract_glossary,
    invalidate_custom_pack_cache,
    retrieve_native_examples,
)
from backend.services.corpus_trainer import (
    build_pack_int8_vectors,
    create_corpus_pack,
    delete_corpus_pack,
    distill_pack_style_profile,
    export_pack_zip_bytes,
    export_training_dataset_jsonl,
    import_pack_zip_bytes,
    ingest_arxiv_batch,
    ingest_paper_into_pack,
    ingest_uploaded_file_into_pack,
    list_corpus_packs,
    record_edit_feedback,
    update_pack_settings,
)
from backend.services.chart_table_studio import (
    PALETTES,
    SAMPLE_DATASETS,
    VENUE_PRESETS,
    analyze_dataset,
    execute_matplotlib_code,
    export_word_threeline_table_bytes,
    generate_academic_table,
    generate_matplotlib_code,
)
from backend.services.citation_verifier import audit_citations_local, verify_bibtex_online
from backend.services.diagram_studio import (
    DIAGRAM_TEMPLATES,
    VENUE_DIAGRAM_THEMES,
    export_diagram_pdf_bytes,
    export_diagram_png_bytes,
    export_diagram_pptx_bytes,
    render_diagram_svg,
    stream_concurrent_diagram_agents,
)
from backend.services.doc_io import (
    SAMPLE_PAPER,
    export_docx_bytes,
    export_latex_string,
    import_arxiv_paper,
    import_docx_bytes,
    import_pdf_bytes,
    import_tex_bytes,
    parse_outline,
)
from backend.services.figure_patcher import (
    inspect_pdf_figure,
    inspect_svg_text_nodes,
    patch_raster_figure,
    patch_svg_text_nodes,
)
from backend.services.formula_studio import (
    analyze_formulas_and_placements,
    rebuild_manuscript_from_blocks,
)
from backend.services.llm_gateway import (
    fetch_provider_models,
    generate_ai_image_b64,
    stream_academic_agent,
)
from backend.services.omni_agent import stream_omni_chat
from backend.services.terminology_and_search import (
    delete_glossary_term,
    load_glossary,
    lookup_term_online,
    upsert_glossary_term,
    web_search,
)
from backend.services.tex_workspace import (
    export_submission_zip_bytes,
    import_workspace_uploaded_files,
    import_workspace_zip_bytes,
    load_workspace_figure_for_patcher,
    read_workspace_asset_preview,
    read_workspace_text_file,
    save_workspace_text_file,
    scan_latex_workspace,
    workspace_figure_to_data_url,
)

app = FastAPI(title="PaperHarness API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------- Health & Bootstrap ----------
@app.get("/api/health")
def health() -> dict[str, Any]:
    skill_dir = get_skill_dir()
    exports_dir = PROJECT_ROOT / "local_data" / "exports"
    exports_dir.mkdir(parents=True, exist_ok=True)
    return {
        "ok": True,
        "version": "0.1.0",
        "skill_mounted": skill_dir is not None,
        "skill_path": str(skill_dir) if skill_dir else None,
        "app_dir": str(PROJECT_ROOT),
        "exports_dir": str(exports_dir),
    }


class RevealPathReq(BaseModel):
    path: str


@app.post("/api/system/reveal")
def api_system_reveal(req: RevealPathReq) -> dict[str, Any]:
    import os, subprocess

    p = Path(req.path) if req.path else (PROJECT_ROOT / "local_data" / "exports")
    if os.name == "nt":
        if p.is_file():
            subprocess.Popen(["explorer", "/select,", str(p)])
        elif p.exists():
            subprocess.Popen(["explorer", str(p)])
        else:
            fallback = PROJECT_ROOT / "local_data" / "exports"
            fallback.mkdir(parents=True, exist_ok=True)
            subprocess.Popen(["explorer", str(fallback)])
        return {"ok": True, "path": str(p)}
    return {"ok": False, "path": str(p)}


class SaveExportReq(BaseModel):
    filename: str
    data_b64: str


@app.post("/api/system/save-export")
def api_system_save_export(req: SaveExportReq) -> dict[str, Any]:
    import base64

    exports_dir = PROJECT_ROOT / "local_data" / "exports"
    exports_dir.mkdir(parents=True, exist_ok=True)
    safe_name = re.sub(r'[<>:"/\\|?*]+', "_", Path(req.filename).name) or "export.bin"
    target = exports_dir / safe_name
    target.write_bytes(base64.b64decode(req.data_b64))
    return {"ok": True, "path": str(target), "filename": safe_name}


@app.get("/api/sample")
def get_sample_workspace() -> dict[str, Any]:
    return {
        "paper": {**SAMPLE_PAPER, "outline": parse_outline(SAMPLE_PAPER["content"], "latex")},
        "datasets": SAMPLE_DATASETS,
        "diagram_templates": DIAGRAM_TEMPLATES,
        "diagram_themes": list(VENUE_DIAGRAM_THEMES.keys()),
        "diagram_theme_defs": VENUE_DIAGRAM_THEMES,
        "chart_palettes": PALETTES,
        "venue_presets": VENUE_PRESETS,
    }


# ---------- Settings & Multi-Provider API Hub ----------
@app.get("/api/settings")
def get_settings() -> dict[str, Any]:
    cfg = load_settings()
    safe_providers = []
    for p in cfg["providers"]:
        safe_providers.append({
            **p,
            "has_key": bool(p.get("api_key")),
            "api_key_masked": mask_key(p.get("api_key", "")),
            "api_key": "",  # never leak raw key in list response unless edited
        })
    return {
        "providers": safe_providers,
        "routing": cfg["routing"],
        "search": {
            "provider": cfg.get("search", {}).get("provider", "builtin_free"),
            "has_key": bool(cfg.get("search", {}).get("api_key")),
            "api_key_masked": mask_key(cfg.get("search", {}).get("api_key", "")),
        },
        "preferences": cfg["preferences"],
    }


class ProviderUpdateReq(BaseModel):
    id: str
    name: str | None = None
    region: str | None = None
    protocol: str | None = None
    base_url: str | None = None
    api_key: str | None = None
    models: list[str] | None = None
    default_model: str | None = None


@app.post("/api/settings/provider")
def upsert_provider(req: ProviderUpdateReq) -> dict[str, Any]:
    cfg = load_settings()
    providers = cfg["providers"]
    existing = next((p for p in providers if p["id"] == req.id), None)
    if existing:
        for field in ("name", "region", "protocol", "models", "default_model"):
            val = getattr(req, field)
            if val is not None:
                existing[field] = val
        if req.base_url is not None:
            existing["base_url"] = req.base_url.rstrip("/")
        if req.api_key:
            existing["api_key"] = req.api_key.strip()
    else:
        providers.append({
            "id": req.id,
            "name": req.name or req.id,
            "region": req.region or "custom",
            "protocol": req.protocol or "openai",
            "base_url": (req.base_url or "").rstrip("/"),
            "api_key": (req.api_key or "").strip(),
            "models": req.models or [],
            "default_model": req.default_model or "",
        })
    save_settings(cfg)
    return {"ok": True}


@app.delete("/api/settings/provider/{provider_id}")
def delete_provider(provider_id: str) -> dict[str, Any]:
    cfg = load_settings()
    cfg["providers"] = [p for p in cfg["providers"] if p["id"] != provider_id]
    save_settings(cfg)
    return {"ok": True}


class RoutingUpdateReq(BaseModel):
    routing: dict[str, Any] | None = None
    search: dict[str, Any] | None = None
    preferences: dict[str, Any] | None = None


@app.post("/api/settings/routing")
def update_routing(req: RoutingUpdateReq) -> dict[str, Any]:
    cfg = load_settings()
    if req.routing is not None:
        cfg["routing"].update(req.routing)
    if req.search is not None:
        cur_s = cfg.setdefault("search", {"provider": "builtin_free", "api_key": ""})
        if "provider" in req.search:
            cur_s["provider"] = req.search["provider"]
        if req.search.get("api_key"):
            cur_s["api_key"] = str(req.search["api_key"]).strip()
    if req.preferences is not None:
        cfg["preferences"].update(req.preferences)
    save_settings(cfg)
    return {"ok": True, "routing": cfg["routing"], "preferences": cfg["preferences"]}


class TestProviderReq(BaseModel):
    provider_id: str | None = None
    base_url: str | None = None
    api_key: str | None = None
    protocol: str | None = None


@app.post("/api/settings/test-provider")
async def test_provider(req: TestProviderReq) -> dict[str, Any]:
    cfg = load_settings()
    p = next((x for x in cfg["providers"] if x["id"] == req.provider_id), None) if req.provider_id else None
    base_url = (req.base_url if req.base_url is not None else (p.get("base_url", "") if p else "")).strip()
    api_key = (req.api_key or (p.get("api_key", "") if p else "")).strip()
    protocol = req.protocol or (p.get("protocol", "openai") if p else "openai")
    if not base_url:
        raise HTTPException(400, "请先填写 Base URL")
    res = await fetch_provider_models(base_url, api_key, protocol)
    if res["ok"] and p and res["models"]:
        p["base_url"] = base_url.rstrip("/")
        if req.api_key:
            p["api_key"] = api_key
        p["protocol"] = protocol
        p["models"] = res["models"]
        if not p.get("default_model") or p["default_model"] not in res["models"]:
            p["default_model"] = res["models"][0]
        save_settings(cfg)
    return res


# ---------- Manuscript Studio: Import, Export, Glossary, Corpus, Typography ----------
class TextReq(BaseModel):
    text: str


@app.post("/api/manuscript/glossary")
def api_glossary(req: TextReq) -> dict[str, Any]:
    return extract_glossary(req.text)


class CorpusReq(BaseModel):
    query: str
    section: str | None = None
    group: str = "native"
    k: int = 6


@app.post("/api/manuscript/corpus")
def api_corpus(req: CorpusReq) -> dict[str, Any]:
    return retrieve_native_examples(req.query, section=req.section, group=req.group, k=req.k)


class TypoReq(BaseModel):
    text: str
    mode: str = "auto"
    cjk_latin_space: bool = False


@app.post("/api/manuscript/typography")
def api_typography(req: TypoReq) -> dict[str, Any]:
    return clean_typography(req.text, mode=req.mode, cjk_latin_space=req.cjk_latin_space)


@app.post("/api/manuscript/outline")
def api_outline(req: TextReq) -> dict[str, Any]:
    return {"outline": parse_outline(req.text)}


@app.post("/api/manuscript/import-file")
async def api_import_file(file: UploadFile = File(...)) -> dict[str, Any]:
    data = await file.read()
    name = file.filename or "manuscript.txt"
    ext = Path(name).suffix.lower()
    try:
        if ext == ".docx":
            return import_docx_bytes(name, data)
        if ext == ".tex":
            return import_tex_bytes(name, data)
        if ext == ".pdf":
            return import_pdf_bytes(name, data)
        txt = data.decode("utf-8-sig", errors="replace")
        return {
            "title": Path(name).stem,
            "source_type": "markdown",
            "filename": name,
            "content": txt,
            "outline": parse_outline(txt, "markdown"),
        }
    except Exception as e:
        raise HTTPException(400, f"Failed to import {name}: {e}")


class ArxivReq(BaseModel):
    arxiv_id: str


@app.post("/api/manuscript/import-arxiv")
def api_import_arxiv(req: ArxivReq) -> dict[str, Any]:
    try:
        return import_arxiv_paper(req.arxiv_id)
    except Exception as e:
        raise HTTPException(400, str(e))


# ---------- Full LaTeX Project Workspace (Folder / Overleaf .zip + Figures + BibTeX) ----------
class OpenWorkspaceFolderReq(BaseModel):
    folder_path: str
    expand_inputs: bool = False


@app.post("/api/workspace/open-folder")
def api_workspace_open_folder(req: OpenWorkspaceFolderReq) -> dict[str, Any]:
    try:
        return scan_latex_workspace(Path(req.folder_path), expand_inputs=req.expand_inputs)
    except Exception as e:
        raise HTTPException(400, str(e))


@app.post("/api/workspace/import-zip")
async def api_workspace_import_zip(file: UploadFile = File(...)) -> dict[str, Any]:
    data = await file.read()
    try:
        return import_workspace_zip_bytes(file.filename or "latex_project.zip", data)
    except Exception as e:
        raise HTTPException(400, f"导入 LaTeX 压缩包失败：{e}")


@app.post("/api/workspace/import-files")
async def api_workspace_import_files(
    files: list[UploadFile] = File(...),
    rel_paths: list[str] = Form(...),
    project_name: str = Form("latex_project"),
) -> dict[str, Any]:
    items: list[tuple[str, bytes]] = []
    for f, rp in zip(files, rel_paths):
        items.append((rp, await f.read()))
    try:
        return import_workspace_uploaded_files(project_name, items)
    except Exception as e:
        raise HTTPException(400, f"导入 LaTeX 文件夹失败：{e}")


@app.get("/api/workspace/read-file")
def api_workspace_read_file(rel: str, expand_inputs: bool = False) -> dict[str, Any]:
    try:
        return read_workspace_text_file(rel, expand_inputs=expand_inputs)
    except Exception as e:
        raise HTTPException(400, str(e))


class SaveWorkspaceFileReq(BaseModel):
    rel: str
    content: str
    preamble: str = ""


@app.post("/api/workspace/save-file")
def api_workspace_save_file(req: SaveWorkspaceFileReq) -> dict[str, Any]:
    try:
        return save_workspace_text_file(req.rel, req.content, preamble=req.preamble)
    except Exception as e:
        raise HTTPException(400, str(e))


@app.get("/api/workspace/asset")
def api_workspace_asset(ref: str) -> Response:
    try:
        raw, mime = read_workspace_asset_preview(ref)
        return Response(content=raw, media_type=mime)
    except Exception as e:
        raise HTTPException(404, str(e))


class WorkspaceFigureReq(BaseModel):
    rel: str


@app.post("/api/workspace/figure-patcher")
def api_workspace_figure_patcher(req: WorkspaceFigureReq) -> dict[str, Any]:
    try:
        return load_workspace_figure_for_patcher(req.rel)
    except Exception as e:
        raise HTTPException(400, str(e))


@app.post("/api/workspace/figure-data-url")
def api_workspace_figure_data_url(req: WorkspaceFigureReq) -> dict[str, Any]:
    try:
        return workspace_figure_to_data_url(req.rel)
    except Exception as e:
        raise HTTPException(400, str(e))


@app.post("/api/workspace/export-submission-zip")
def api_workspace_export_submission_zip() -> Response:
    try:
        raw, fname, count = export_submission_zip_bytes()
        return Response(
            content=raw,
            media_type="application/zip",
            headers={
                "Content-Disposition": f'attachment; filename="{fname}"',
                "X-File-Count": str(count),
            },
        )
    except Exception as e:
        raise HTTPException(400, str(e))


# ---------- Multimodal Glossary & Multi-Provider Web Search ----------
@app.get("/api/glossary")
def api_get_glossary() -> dict[str, Any]:
    return {"terms": load_glossary()}


class GlossaryUpsertReq(BaseModel):
    en: str
    zh: str
    keep_en: bool = False
    note: str = ""


@app.post("/api/glossary")
def api_upsert_glossary(req: GlossaryUpsertReq) -> dict[str, Any]:
    return {"ok": True, "terms": upsert_glossary_term(req.en, req.zh, req.keep_en, req.note)}


class GlossaryDeleteReq(BaseModel):
    en: str


@app.post("/api/glossary/delete")
def api_delete_glossary(req: GlossaryDeleteReq) -> dict[str, Any]:
    return {"ok": True, "terms": delete_glossary_term(req.en)}


class WebSearchReq(BaseModel):
    query: str
    max_results: int = 5


@app.post("/api/search/web")
async def api_search_web(req: WebSearchReq) -> dict[str, Any]:
    return await web_search(req.query, max_results=req.max_results)


class TermLookupReq(BaseModel):
    term: str
    domain: str = "多模态深度学习"


@app.post("/api/search/term")
async def api_search_term(req: TermLookupReq) -> dict[str, Any]:
    return await lookup_term_online(req.term, domain=req.domain)


class ExportDocxReq(BaseModel):
    title: str
    revised_text: str
    original_text: str | None = None
    track_changes: bool = True
    author: str = "PaperHarness Co-Author"


@app.post("/api/manuscript/export-docx")
def api_export_docx(req: ExportDocxReq) -> Response:
    raw = export_docx_bytes(
        title=req.title,
        revised_text=req.revised_text,
        original_text=req.original_text,
        track_changes=req.track_changes,
        author=req.author,
    )
    fname = re.sub(r"[^A-Za-z0-9_-]+", "_", req.title)[:42] or "manuscript"
    suffix = "_tracked" if req.track_changes else "_clean"
    return Response(
        content=raw,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": f'attachment; filename="{fname}{suffix}.docx"'},
    )


class ExportLatexReq(BaseModel):
    title: str
    content: str
    preamble: str = ""


@app.post("/api/manuscript/export-latex")
def api_export_latex(req: ExportLatexReq) -> Response:
    tex = export_latex_string(req.title, req.content, req.preamble)
    fname = re.sub(r"[^A-Za-z0-9_-]+", "_", req.title)[:42] or "manuscript"
    return Response(
        content=tex.encode("utf-8"),
        media_type="application/x-tex",
        headers={"Content-Disposition": f'attachment; filename="{fname}.tex"'},
    )


# ---------- Streaming Academic Agent Harness (SSE) ----------
class AgentRunReq(BaseModel):
    mode: str = "polish"
    text: str
    instruction: str = ""
    section: str = "introduction"
    venue: str = "CVPR / ICCV"
    provider_id: str | None = None
    model: str | None = None


@app.post("/api/agent/stream")
async def api_agent_stream(req: AgentRunReq) -> StreamingResponse:
    async def event_gen():
        async for evt in stream_academic_agent(
            mode=req.mode,
            text=req.text,
            instruction=req.instruction,
            section=req.section,
            venue=req.venue,
            provider_id=req.provider_id,
            model=req.model,
        ):
            yield f"data: {json.dumps(evt, ensure_ascii=False)}\n\n"

    return StreamingResponse(event_gen(), media_type="text/event-stream")


# ---------- Global Multimodal Omni-Agent Chat & Full-App Tool Orchestrator ----------
class OmniChatReq(BaseModel):
    messages: list[dict[str, Any]]
    context: dict[str, Any] = {}
    enable_thinking: bool = False


@app.post("/api/chat/stream")
async def api_chat_stream(req: OmniChatReq) -> StreamingResponse:
    async def event_gen():
        async for evt in stream_omni_chat(
            messages=req.messages, context=req.context, enable_thinking=req.enable_thinking
        ):
            yield f"data: {json.dumps(evt, ensure_ascii=False)}\n\n"

    return StreamingResponse(event_gen(), media_type="text/event-stream")


# ---------- Formula Placement & Consistency Studio ----------
@app.post("/api/formula/analyze")
def api_formula_analyze(req: TextReq) -> dict[str, Any]:
    return analyze_formulas_and_placements(req.text)


class FormulaRebuildReq(BaseModel):
    blocks: list[dict[str, Any]]
    sync_refs: bool = True


@app.post("/api/formula/rebuild")
def api_formula_rebuild(req: FormulaRebuildReq) -> dict[str, Any]:
    return rebuild_manuscript_from_blocks(req.blocks, sync_refs=req.sync_refs)


# ---------- Data-to-Figure & Publication Table Studio ----------
class DatasetAnalyzeReq(BaseModel):
    csv_text: str


@app.post("/api/charts/analyze")
def api_chart_analyze(req: DatasetAnalyzeReq) -> dict[str, Any]:
    try:
        return analyze_dataset(req.csv_text)
    except Exception as e:
        raise HTTPException(400, str(e))


class ChartRenderReq(BaseModel):
    csv_text: str
    chart_type: str = "grouped_bar"
    title: str = ""
    xlabel: str = ""
    ylabel: str = ""
    venue: str = "CVPR / ICCV"
    width_in: float = 7.6
    height_in: float = 4.4
    font_family: str = "DejaVu Serif"
    font_size: float = 11.0
    line_width: float = 2.0
    palette_name: str = "oxford_academic"
    legend_pos: str = "top"
    show_grid: bool = True
    show_values: bool = True
    spacing_mode: str = "airy"
    dpi: int = 600
    custom_code: str | None = None


@app.post("/api/charts/render")
def api_chart_render(req: ChartRenderReq) -> dict[str, Any]:
    try:
        code = req.custom_code if (req.custom_code and req.custom_code.strip()) else generate_matplotlib_code(
            csv_text=req.csv_text,
            chart_type=req.chart_type,
            title=req.title,
            xlabel=req.xlabel,
            ylabel=req.ylabel,
            venue=req.venue,
            width_in=req.width_in,
            height_in=req.height_in,
            font_family=req.font_family,
            font_size=req.font_size,
            line_width=req.line_width,
            palette_name=req.palette_name,
            legend_pos=req.legend_pos,
            show_grid=req.show_grid,
            show_values=req.show_values,
            spacing_mode=req.spacing_mode,
        )
        out = execute_matplotlib_code(code, dpi=req.dpi)
        return {"ok": True, "code": code, **out}
    except Exception as e:
        raise HTTPException(400, f"Chart execution error: {e}")


class TableGenReq(BaseModel):
    csv_text: str
    caption: str = "Quantitative comparison across benchmarks. Best results are in bold and second-best are underlined."
    label: str = "tab:main_results"
    lower_is_better: list[str] = []
    decimals: int | None = None
    highlight_best: bool = True


@app.post("/api/tables/generate")
def api_table_generate(req: TableGenReq) -> dict[str, Any]:
    try:
        return generate_academic_table(
            csv_text=req.csv_text,
            caption=req.caption,
            label=req.label,
            lower_is_better=req.lower_is_better,
            decimals=req.decimals,
            highlight_best=req.highlight_best,
        )
    except Exception as e:
        raise HTTPException(400, str(e))


@app.post("/api/tables/export-docx")
def api_table_export_docx(req: TableGenReq) -> Response:
    raw = export_word_threeline_table_bytes(
        csv_text=req.csv_text,
        caption=req.caption,
        lower_is_better=req.lower_is_better,
        decimals=req.decimals,
    )
    return Response(
        content=raw,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": 'attachment; filename="academic_table.docx"'},
    )


# ---------- Top-Venue Diagram Studio (SVG + Native Editable PPTX + AI Tiles) ----------
class DiagramRenderReq(BaseModel):
    blueprint: dict[str, Any]
    dpi: int = 600


@app.post("/api/diagrams/render")
def api_diagram_render(req: DiagramRenderReq) -> dict[str, Any]:
    return {"svg": render_diagram_svg(req.blueprint)}


@app.post("/api/diagrams/export-pptx")
def api_diagram_export_pptx(req: DiagramRenderReq) -> Response:
    return Response(
        content=export_diagram_pptx_bytes(req.blueprint),
        media_type="application/vnd.openxmlformats-officedocument.presentationml.presentation",
        headers={"Content-Disposition": 'attachment; filename="paper_architecture.pptx"'},
    )


@app.post("/api/diagrams/export-pdf")
def api_diagram_export_pdf(req: DiagramRenderReq) -> Response:
    return Response(
        content=export_diagram_pdf_bytes(req.blueprint),
        media_type="application/pdf",
        headers={"Content-Disposition": 'attachment; filename="paper_architecture.pdf"'},
    )


@app.post("/api/diagrams/export-png")
def api_diagram_export_png(req: DiagramRenderReq) -> Response:
    return Response(
        content=export_diagram_png_bytes(req.blueprint, dpi=req.dpi),
        media_type="image/png",
        headers={"Content-Disposition": f'attachment; filename="paper_architecture_{req.dpi}dpi.png"'},
    )


class DiagramFromTextReq(BaseModel):
    method_text: str
    venue_theme: str = "CVPR Clean Slate"
    concurrency: int = 3
    generate_ai_icons: bool = False
    layout_mode: str = "auto"
    custom_colors: dict[str, str] | None = None


@app.post("/api/diagrams/generate-stream")
async def api_diagram_generate_stream(req: DiagramFromTextReq) -> StreamingResponse:
    async def event_gen():
        async for evt in stream_concurrent_diagram_agents(
            method_text=req.method_text,
            venue_theme=req.venue_theme,
            concurrency=req.concurrency,
            generate_ai_icons=req.generate_ai_icons,
            layout_mode=req.layout_mode,
            custom_colors=req.custom_colors,
        ):
            yield f"data: {json.dumps(evt, ensure_ascii=False)}\n\n"

    return StreamingResponse(event_gen(), media_type="text/event-stream")


class DiagramAssetReq(BaseModel):
    prompt: str


@app.post("/api/diagrams/ai-asset")
async def api_diagram_ai_asset(req: DiagramAssetReq) -> dict[str, Any]:
    styled_prompt = (
        f"Minimalist clean scientific illustration icon for a top CVPR/Nature research diagram, "
        f"white background, flat vector geometric style, no text, crisp lines: {req.prompt}"
    )
    return await generate_ai_image_b64(styled_prompt)


# ---------- Safe Figure Text Patcher ----------
@app.post("/api/patcher/inspect")
async def api_patcher_inspect(file: UploadFile = File(...)) -> dict[str, Any]:
    data = await file.read()
    name = file.filename or "figure.png"
    ext = Path(name).suffix.lower()
    if ext == ".svg":
        return inspect_svg_text_nodes(data.decode("utf-8", errors="replace"))
    if ext == ".pdf":
        return inspect_pdf_figure(data)
    # Raster PNG/JPG
    from PIL import Image
    import io, base64

    img = Image.open(io.BytesIO(data)).convert("RGB")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return {
        "kind": "raster",
        "width": img.size[0],
        "height": img.size[1],
        "image_b64": base64.b64encode(buf.getvalue()).decode("ascii"),
        "boxes": [],
    }


class PatchSvgReq(BaseModel):
    svg: str
    edits: list[dict[str, Any]]


@app.post("/api/patcher/patch-svg")
def api_patcher_svg(req: PatchSvgReq) -> dict[str, Any]:
    return patch_svg_text_nodes(req.svg, req.edits)


class PatchRasterReq(BaseModel):
    image_b64: str
    boxes: list[dict[str, Any]]


@app.post("/api/patcher/patch-raster")
def api_patcher_raster(req: PatchRasterReq) -> dict[str, Any]:
    return patch_raster_figure(req.image_b64, req.boxes)


# ---------- Citation Verifier ----------
class CitationReq(BaseModel):
    manuscript: str
    bibtex: str
    verify_online: bool = False


@app.post("/api/citations/audit")
async def api_citations(req: CitationReq) -> dict[str, Any]:
    if req.verify_online:
        return await verify_bibtex_online(req.manuscript, req.bibtex)
    return audit_citations_local(req.manuscript, req.bibtex)


# ---------- Corpus Expansion, Style Distillation & SFT/DPO Training Flywheel ----------
@app.get("/api/corpus/packs")
def api_list_packs() -> dict[str, Any]:
    return list_corpus_packs()


class CreatePackReq(BaseModel):
    name: str
    domain: str = "Custom Lab Domain"
    venue: str = "CVPR / NeurIPS"
    language: str = "en"
    weight: float = 1.4


@app.post("/api/corpus/packs")
def api_create_pack(req: CreatePackReq) -> dict[str, Any]:
    return create_corpus_pack(req.name, req.domain, req.venue, req.language, req.weight)


class UpdatePackReq(BaseModel):
    enabled: bool | None = None
    weight: float | None = None


@app.patch("/api/corpus/packs/{pack_id}")
def api_update_pack(pack_id: str, req: UpdatePackReq) -> dict[str, Any]:
    try:
        res = update_pack_settings(pack_id, enabled=req.enabled, weight=req.weight)
        invalidate_custom_pack_cache(pack_id)
        return res
    except Exception as e:
        raise HTTPException(400, str(e))


@app.delete("/api/corpus/packs/{pack_id}")
def api_delete_pack(pack_id: str) -> dict[str, Any]:
    try:
        res = delete_corpus_pack(pack_id)
        invalidate_custom_pack_cache(pack_id)
        return res
    except Exception as e:
        raise HTTPException(400, str(e))


@app.post("/api/corpus/packs/{pack_id}/ingest-files")
async def api_ingest_files(
    pack_id: str,
    files: list[UploadFile] = File(...),
    venue: str = Form("Custom"),
    year: int = Form(2026),
    group: str = Form("native"),
) -> dict[str, Any]:
    items = []
    total_sents = 0
    for f in files:
        data = await f.read()
        try:
            res = ingest_uploaded_file_into_pack(pack_id, f.filename or "paper.txt", data, venue=venue, year=year, group=group)
            total_sents += res.get("sentences_added", 0)
            items.append({"filename": f.filename, "ok": True, "sentences": res.get("sentences_added", 0)})
        except Exception as e:
            items.append({"filename": f.filename, "ok": False, "error": str(e)})
    invalidate_custom_pack_cache(pack_id)
    return {"ok": True, "total_sentences_added": total_sents, "items": items}


class IngestArxivBatchReq(BaseModel):
    arxiv_ids: list[str]
    venue: str = "arXiv"
    year: int = 2026
    group: str = "native"


@app.post("/api/corpus/packs/{pack_id}/ingest-arxiv")
def api_ingest_arxiv_batch(pack_id: str, req: IngestArxivBatchReq) -> dict[str, Any]:
    res = ingest_arxiv_batch(pack_id, req.arxiv_ids, venue=req.venue, year=req.year, group=req.group)
    invalidate_custom_pack_cache(pack_id)
    return res


class IngestTextReq(BaseModel):
    title: str
    content: str
    venue: str = "Lab Paper"
    year: int = 2026
    group: str = "lab_gold"


@app.post("/api/corpus/packs/{pack_id}/ingest-text")
def api_ingest_text(pack_id: str, req: IngestTextReq) -> dict[str, Any]:
    res = ingest_paper_into_pack(
        pack_id=pack_id,
        title=req.title,
        content=req.content,
        source_id=re.sub(r"[^a-zA-Z0-9_-]+", "_", req.title)[:32] or "paper",
        venue=req.venue,
        year=req.year,
        group=req.group,
    )
    invalidate_custom_pack_cache(pack_id)
    return res


@app.post("/api/corpus/packs/{pack_id}/distill")
def api_distill_pack(pack_id: str) -> dict[str, Any]:
    profile = distill_pack_style_profile(pack_id)
    return {"ok": True, "style_profile": profile}


@app.post("/api/corpus/packs/{pack_id}/build-vectors")
def api_build_vectors(pack_id: str) -> dict[str, Any]:
    try:
        return build_pack_int8_vectors(pack_id)
    except Exception as e:
        raise HTTPException(400, str(e))


@app.post("/api/corpus/packs/{pack_id}/export-zip")
def api_export_pack_zip(pack_id: str) -> Response:
    raw = export_pack_zip_bytes(pack_id)
    return Response(
        content=raw,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{pack_id}.zip"'},
    )


@app.post("/api/corpus/packs/import-zip")
async def api_import_pack_zip(file: UploadFile = File(...)) -> dict[str, Any]:
    data = await file.read()
    try:
        manifest = import_pack_zip_bytes(data)
        invalidate_custom_pack_cache()
        return {"ok": True, "manifest": manifest}
    except Exception as e:
        raise HTTPException(400, str(e))


class FeedbackReq(BaseModel):
    original: str
    revised: str
    tag: str = "Style"
    reason: str = ""
    decision: str = "accepted"
    venue: str = "CVPR / ICCV"
    mode: str = "polish"


@app.post("/api/corpus/feedback")
def api_record_feedback(req: FeedbackReq) -> dict[str, Any]:
    return record_edit_feedback(
        original=req.original,
        revised=req.revised,
        tag=req.tag,
        reason=req.reason,
        decision=req.decision,
        venue=req.venue,
        mode=req.mode,
    )


class ExportTrainingReq(BaseModel):
    format: str = "sft_openai"
    pack_ids: list[str] | None = None
    max_corpus_samples: int = 300


@app.post("/api/corpus/export-training")
def api_export_training(req: ExportTrainingReq) -> Response:
    jsonl_str, count = export_training_dataset_jsonl(
        fmt=req.format,
        include_pack_ids=req.pack_ids,
        max_corpus_samples=req.max_corpus_samples,
    )
    return Response(
        content=jsonl_str.encode("utf-8"),
        media_type="application/x-ndjson",
        headers={
            "Content-Disposition": f'attachment; filename="paperharness_{req.format}_{count}rows.jsonl"',
            "X-Row-Count": str(count),
        },
    )


# ---------- Static Frontend Hosting (Supports Source & Frozen PyInstaller `.exe`) ----------
DIST_DIR = BUNDLE_DIR / "frontend" / "dist"
if not DIST_DIR.exists():
    DIST_DIR = PROJECT_ROOT / "frontend" / "dist"
if (DIST_DIR / "assets").exists():
    app.mount("/assets", StaticFiles(directory=str(DIST_DIR / "assets")), name="assets")


@app.get("/{full_path:path}")
def serve_spa(full_path: str):
    if full_path.startswith("api/"):
        raise HTTPException(404, "API route not found")
    target = DIST_DIR / full_path
    if full_path and target.exists() and target.is_file():
        return FileResponse(str(target))
    index_file = DIST_DIR / "index.html"
    if index_file.exists():
        return FileResponse(str(index_file))
    return {"message": "PaperHarness API running. Build frontend (`npm run build`) or visit Vite dev server."}
