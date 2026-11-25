"""Multimodal Omni-Agent Orchestrator — full-app tool calling + image understanding.

Users can converse naturally, attach screenshots / figures / sketches / table photos,
and ask the agent to invoke ANY PaperHarness studio directly (draw CVPR diagrams & PPTX,
plot 600 DPI Matplotlib charts, build booktabs three-line tables, polish/review manuscripts,
optimize formulas, send images into Figure Patcher, verify citations, or ingest corpus packs).
"""
from __future__ import annotations

import base64
import io
import json
import re
from typing import Any, AsyncGenerator

from PIL import Image

from backend.services.academic_engine import clean_typography
from backend.services.chart_table_studio import (
    execute_matplotlib_code,
    generate_academic_table,
    generate_matplotlib_code,
)
from backend.services.citation_verifier import audit_citations_local, verify_bibtex_online
from backend.services.diagram_studio import (
    compute_clean_grid_layout,
    normalize_blueprint,
    render_diagram_svg,
    stream_concurrent_diagram_agents,
)
from backend.services.formula_studio import analyze_formulas_and_placements
from backend.services.terminology_and_search import lookup_term_online, web_search
from backend.services.tex_workspace import (
    load_workspace_figure_for_patcher,
    read_workspace_text_file,
    workspace_figure_to_data_url,
)
from backend.services.llm_gateway import (
    _split_data_url,
    resolve_role_provider,
    stream_academic_agent,
    stream_multimodal_messages,
)

TOOL_GUIDE = """You are PaperHarness Omni-Agent — an all-in-one academic research & publishing assistant with direct control over the entire desktop workbench.
You can see images the user sends (paper figures, hand-drawn sketches, experimental table screenshots, architecture diagrams) AND invoke any workbench tool.

When the user asks you to create, draw, plot, tabulate, polish, translate, review, clean punctuation, optimize formulas, edit text inside an image, verify citations, or add papers to the corpus:
1. Write a concise, helpful response in the user's language (default Simplified Chinese).
2. Emit ONE OR MORE fenced tool blocks in the exact format below (the app intercepts and executes them live, rendering visual results and updating the corresponding studio automatically):

```tool_call
{"tool": "<tool_name>", "args": { ... }}
```

Available tools and exact schemas:
1. `draw_diagram` — Create ONE clean, zero-overlap, anti-hallucination top-venue architecture flowchart (1:1 exportable to native editable PowerPoint .pptx).
   - Preferred Collaborative Multi-Agent PPT Mode (recommended whenever drawing from the active paper or complex architecture — runs Lead Architect -> Parallel Stage Builders -> Anti-Hallucination Edge Auditor -> Deterministic Grid Layout + VLM Self-Critique -> 1:1 PPTX):
     `{"tool":"draw_diagram","args":{"collaborative":true,"venue_theme":"CVPR Clean Slate","layout_mode":"auto|pipeline|dual_branch|zoom_callout|sample_left","custom_colors":{"primary":"#1E3A5F","accent":"#C2410C"},"method_text":"<description or omit to use active manuscript>","concurrency":3,"generate_ai_icons":false}}`
   - Fast Deterministic Stage-Grid Mode (when drawing a custom flowchart or redrawing an uploaded reference sketch — pass logical stages + grounded edges, NEVER guess pixel x/y):
     `{"tool":"draw_diagram","args":{"title":"Concise Title","venue_theme":"CVPR Clean Slate","layout_mode":"pipeline|dual_branch|zoom_callout|sample_left","custom_colors":{"primary":"#1E3A5F","accent":"#C2410C"},"stages":[{"id":"s1","label":"Stage 1 · Input","nodes":[{"id":"s1_n1","label":"Short Name","sublabel":"R^(N×D)","tone":"primary|accent|sage|violet|neutral","icon":"conv_stack_3d|conv_pyramid|patch_grid|attn_grid|cross_attn|unet_trapezoid|moe_router|diffusion_steps|tensor_cube|encoder_stack|token_strip|gate_router|merge_pool|none"}]}],"edges":[{"from":"s1_n1","to":"s2_n1","label":"short","dashed":false}]}}`
     Venue theme options: "CVPR Clean Slate", "NeurIPS Editorial", "Nature Scientific", "IEEE Classic", "Minimal Monochrome".

1b. `refine_diagram` — Surgically tweak the active diagram's style, custom hex colors, node labels/icons (e.g. changing an encoder to `conv_stack_3d` or `conv_pyramid`), or embed a workspace figure into a node!
   `{"tool":"refine_diagram","args":{"venue_theme":"Nature Scientific","custom_colors":{"primary":"#0F4C5C","accent":"#D97706"},"node_updates":[{"match":"Encoder","label":"optional new label","tone":"primary","icon":"conv_stack_3d","workspace_figure":"optional figures/img.png"}]}}`

2. `draw_chart` — Plot a 600 DPI publication Matplotlib figure from CSV data (you can transcribe data from an uploaded table/chart image into CSV!).
   `{"tool":"draw_chart","args":{"csv_text":"Method,Metric1,Metric2\\n...","chart_type":"grouped_bar|line_curve|scatter_pareto|heatmap|horizontal_bar|error_bar|dual_axis","title":"...","ylabel":"Score (%)","venue":"CVPR / ICCV|NeurIPS / ICML|Nature / Science|IEEE / TPAMI|ACL / EMNLP|ICLR Modern|中文核心 / 学位论文|黑白灰度打印 (Grayscale)","spacing_mode":"airy","dpi":600}}`

3. `build_table` — Build a publication LaTeX `booktabs` + Word three-line table (auto-bolds best & underlines second-best).
   `{"tool":"build_table","args":{"csv_text":"Method,Acc,GFLOPs\\n...","caption":"...","label":"tab:results","lower_is_better":["GFLOPs"],"decimals":1}}`

4. `edit_manuscript` — Polish, translate, peer-review, mimic venue style, clean Chinese/English punctuation, or propose Accept/Reject diffs on the active manuscript.
   - Run academic harness mode: `{"tool":"edit_manuscript","args":{"action":"polish|zh2en|en2zh|mimic|review","instruction":"..."}}`
   - Clean CJK/English punctuation & extra spaces: `{"tool":"edit_manuscript","args":{"action":"clean_typography"}}`
   - Direct diff cards: `{"tool":"edit_manuscript","args":{"action":"propose_edits","edits":[{"original":"exact text","revised":"improved text","tag":"表达","reason":"中文理由"}]}}`

5. `optimize_formulas` — Analyze equations, detect symbol inconsistency, and open Interactive Formula Placement Studio.
   `{"tool":"optimize_formulas","args":{}}`

6. `patch_figure_text` — Load an attached chat image OR a figure from the mounted LaTeX workspace (e.g. `figures/overview.pdf`) into Safe Figure Text Patcher to edit & reposition text with 0.0000% outside-box pixel modification guarantee.
   `{"tool":"patch_figure_text","args":{"workspace_figure":"<optional relative figure path in LaTeX workspace>","image_index":0,"boxes":[{"text":"New Label","x":120,"y":40,"w":180,"h":36,"font_size":16,"color":"#16191F"}]}}` (omit `boxes` if user will draw boxes manually or when loading PDF/SVG vector figures).

7. `verify_citations` — Audit `\\cite{}` coverage and verify BibTeX entries online via Crossref to prevent hallucinated references.
   `{"tool":"verify_citations","args":{"verify_online":true,"bibtex":"<optional new bibtex or omit to use workspace bibtex>"}}`

8. `web_search` — Search the live internet & arXiv for latest papers, methods, or technical facts (uses configured search engine or built-in free search).
   `{"tool":"web_search","args":{"query":"Flow Matching multimodal VLM 2025"}}`

9. `lookup_term` — Search online for authoritative Chinese academic translations of an unfamiliar English term/phrase (especially multimodal DL terms) and suggest 2-3 grounded candidates.
   `{"tool":"lookup_term","args":{"term":"token pruning","domain":"多模态深度学习"}}`

10. `switch_studio` — Navigate the workbench to any studio: `"manuscript"|"charts"|"diagrams"|"patcher"|"citations"`.

Strict rules:
- If the user asks a pure question (e.g. explaining an uploaded paper figure or answering a writing question), answer directly without invoking unnecessary tools.
- NEVER fabricate experimental numbers or citation DOIs. When reading numbers from an uploaded image, transcribe faithfully.
- Keep tool_call JSON strictly valid with double quotes and no trailing commas.
"""


def _extract_tool_calls(full_text: str) -> list[dict[str, Any]]:
    calls: list[dict[str, Any]] = []
    for m in re.finditer(r"```(?:tool_call|json)\s*([\s\S]*?)```", full_text):
        raw = m.group(1).strip()
        try:
            obj = json.loads(raw)
        except Exception:
            continue
        if isinstance(obj, dict) and isinstance(obj.get("tool"), str):
            calls.append({"tool": obj["tool"].strip(), "args": obj.get("args") if isinstance(obj.get("args"), dict) else {}})
        elif isinstance(obj, list):
            for it in obj:
                if isinstance(it, dict) and isinstance(it.get("tool"), str):
                    calls.append({"tool": it["tool"].strip(), "args": it.get("args") if isinstance(it.get("args"), dict) else {}})
    return calls


def _collect_conversation_images(messages: list[dict[str, Any]]) -> list[str]:
    imgs: list[str] = []
    for m in messages:
        for im in m.get("images") or []:
            if isinstance(im, str) and im.strip():
                imgs.append(im)
    return imgs


async def _execute_tool(
    tool: str,
    args: dict[str, Any],
    context: dict[str, Any],
    all_images: list[str],
) -> AsyncGenerator[dict[str, Any], None]:
    manuscript = str(context.get("manuscript") or "")
    title = str(context.get("title") or "PaperHarness")
    venue = str(context.get("venue") or "CVPR / ICCV")
    bibtex = str(context.get("bibtex") or "")

    if tool == "draw_diagram":
        theme = str(args.get("venue_theme") or "CVPR Clean Slate")
        lmode = str(args.get("layout_mode") or "auto")
        ccols = args.get("custom_colors") if isinstance(args.get("custom_colors"), dict) else None
        # Fast deterministic stage-grid mode (zero pixel guessing!)
        if isinstance(args.get("stages"), list) and args["stages"] and not args.get("collaborative"):
            yield {"type": "tool_start", "tool": "draw_diagram", "label": "正在运行确定性网格排版与无碰撞通道布线..."}
            bp = compute_clean_grid_layout(
                title=str(args.get("title") or "Architecture Overview"),
                venue_theme=theme,
                stages=args["stages"],
                edges=list(args.get("edges") or []),
                layout_mode=lmode if lmode != "auto" else "pipeline",
                custom_colors=ccols,
            )
            svg = render_diagram_svg(bp)
            yield {"type": "ui_action", "action": "load_diagram", "studio": "diagrams", "blueprint": bp}
            yield {
                "type": "tool_result",
                "tool": "draw_diagram",
                "summary": f"已排版绘成《{bp['title']}》（{len(bp['groups'])} 阶段 · {len(bp['nodes'])} 模块 · {len(bp['edges'])} 条无重叠箭头 · 支持 1:1 导出 .pptx）",
                "preview_svg": svg,
                "blueprint": bp,
                "target_studio": "diagrams",
            }
            return

        bp_raw = args.get("blueprint")
        if isinstance(bp_raw, dict) and bp_raw.get("nodes") and not args.get("collaborative"):
            yield {"type": "tool_start", "tool": "draw_diagram", "label": "正在执行去重叠布线并同步至可编辑画布..."}
            if ccols:
                bp_raw["custom_colors"] = ccols
            bp = normalize_blueprint(bp_raw, theme)
            svg = render_diagram_svg(bp)
            yield {"type": "ui_action", "action": "load_diagram", "studio": "diagrams", "blueprint": bp}
            yield {
                "type": "tool_result",
                "tool": "draw_diagram",
                "summary": f"已绘制《{bp['title']}》（{len(bp['nodes'])} 个模块 · {len(bp['edges'])} 条无重叠箭头 · 支持 1:1 导出 .pptx）",
                "preview_svg": svg,
                "blueprint": bp,
                "target_studio": "diagrams",
            }
            return

        # Collaborative Multi-Agent Assembly of ONE Publication-Grade PPTX Flowchart
        method_txt = str(args.get("method_text") or manuscript or title)
        conc = max(1, min(4, int(args.get("concurrency") or 3)))
        gen_icons = bool(args.get("generate_ai_icons", False))
        yield {"type": "tool_start", "tool": "draw_diagram", "label": f"正在启动多智能体协同绘顶刊 PPT 图（总规划 → {conc}路并发 → 幻觉审查 → 视觉自检）..."}
        final_cand = None
        audit_note = ""
        async for ev in stream_concurrent_diagram_agents(
            method_txt, venue_theme=theme, concurrency=conc, generate_ai_icons=gen_icons, layout_mode=lmode, custom_colors=ccols
        ):
            if ev.get("type") == "worker_done":
                yield {"type": "tool_start", "tool": "draw_diagram", "label": f"✓ {ev.get('name', '')}"}
            elif ev.get("type") == "candidate":
                final_cand = ev
                audit_note = str(ev.get("audit_note") or "")
        if final_cand:
            best = final_cand["blueprint"]
            svg = render_diagram_svg(best)
            yield {"type": "ui_action", "action": "load_diagram", "studio": "diagrams", "blueprint": best}
            yield {
                "type": "tool_result",
                "tool": "draw_diagram",
                "summary": f"多智能体已协同完成《{best['title']}》（{len(best['groups'])} 阶段 · {len(best['nodes'])} 模块 · {len(best['edges'])} 条经核验无重叠箭头）"
                + (f" · {audit_note}" if audit_note else ""),
                "preview_svg": svg,
                "blueprint": best,
                "target_studio": "diagrams",
            }
        else:
            yield {"type": "tool_result", "tool": "draw_diagram", "summary": "多智能体协同绘图未完成，请重试或补充方法描述。"}
        return

    if tool == "refine_diagram":
        yield {"type": "tool_start", "tool": "refine_diagram", "label": "正在按你的要求微调当前流程图风格、配色与框内图示..."}
        node_updates = list(args.get("node_updates") or [])
        for upd in node_updates:
            wf = str(upd.get("workspace_figure") or "").strip()
            if wf:
                try:
                    du = workspace_figure_to_data_url(wf)
                    upd["ai_image_b64"] = du["data_url"].split(",", 1)[-1]
                except Exception:
                    pass
        yield {
            "type": "ui_action",
            "action": "refine_diagram",
            "studio": "diagrams",
            "venue_theme": args.get("venue_theme"),
            "custom_colors": args.get("custom_colors"),
            "node_updates": node_updates,
        }
        yield {
            "type": "tool_result",
            "tool": "refine_diagram",
            "summary": "已实时更新右侧流程图的风格、配色与框内图示（导出 .pptx 自动保持 1:1 一致）。",
            "target_studio": "diagrams",
        }
        return

    if tool == "web_search":
        q = str(args.get("query") or "").strip()
        yield {"type": "tool_start", "tool": "web_search", "label": f"正在联网检索：{q}..."}
        sres = await web_search(q, max_results=int(args.get("max_results") or 5))
        lines = [f"- {r['title']} ({r['source']})\n  {r['snippet']}" for r in sres.get("results") or []]
        yield {
            "type": "tool_result",
            "tool": "web_search",
            "summary": f"通过 {sres.get('provider')} 检索到 {len(lines)} 条结果：\n" + ("\n".join(lines[:4]) if lines else "暂无直接结果"),
        }
        return

    if tool == "lookup_term":
        term = str(args.get("term") or "").strip()
        domain = str(args.get("domain") or "多模态深度学习")
        yield {"type": "tool_start", "tool": "lookup_term", "label": f"正在联网查证术语「{term}」的地道中文译法..."}
        tres = await lookup_term_online(term, domain=domain)
        cands = tres.get("candidates") or []
        cand_lines = [f"• {c.get('zh', '')}（{c.get('scene', '')}）" for c in cands]
        summary = f"术语「{term}」查证结果（来源：{tres.get('search_provider')}）：\n" + ("\n".join(cand_lines) if cand_lines else tres.get("note", ""))
        if tres.get("note") and cand_lines:
            summary += f"\n建议：{tres['note']}"
        yield {"type": "tool_result", "tool": "lookup_term", "summary": summary}
        return

    if tool == "draw_chart":
        csv_text = str(args.get("csv_text") or "").strip()
        if not csv_text:
            yield {"type": "tool_result", "tool": "draw_chart", "summary": "缺少 CSV 实验数据，无法绘制图表。"}
            return
        chart_type = str(args.get("chart_type") or "grouped_bar")
        chart_title = str(args.get("title") or "Experimental Comparison")
        ylabel = str(args.get("ylabel") or "Score")
        chart_venue = str(args.get("venue") or venue)
        spacing = str(args.get("spacing_mode") or "airy")
        dpi = int(args.get("dpi") or 600)
        yield {"type": "tool_start", "tool": "draw_chart", "label": f"正在以 {dpi} DPI 渲染防重叠出版级图表 ({chart_type})..."}
        code = generate_matplotlib_code(
            csv_text=csv_text,
            chart_type=chart_type,
            title=chart_title,
            ylabel=ylabel,
            venue=chart_venue,
            spacing_mode=spacing,
        )
        out = execute_matplotlib_code(code, dpi=min(600, dpi))
        yield {
            "type": "ui_action",
            "action": "load_chart",
            "studio": "charts",
            "sub_mode": "figure",
            "csv_text": csv_text,
            "chart_type": chart_type,
            "title": chart_title,
            "ylabel": ylabel,
            "venue": chart_venue,
        }
        yield {
            "type": "tool_result",
            "tool": "draw_chart",
            "summary": f"已渲染 {chart_type} 出版级图表（{chart_venue} · 自动避让数据标签），并已同步至「数据绘图与三线表」。",
            "preview_png_b64": out["png_b64"],
            "target_studio": "charts",
        }
        return

    if tool == "build_table":
        csv_text = str(args.get("csv_text") or "").strip()
        if not csv_text:
            yield {"type": "tool_result", "tool": "build_table", "summary": "缺少 CSV 数据，无法生成三线表。"}
            return
        caption = str(args.get("caption") or "Quantitative comparison across benchmarks. Best results are in bold and second-best are underlined.")
        label = str(args.get("label") or "tab:results")
        lower_cols = list(args.get("lower_is_better") or [])
        decimals = args.get("decimals")
        yield {"type": "tool_start", "tool": "build_table", "label": "正在生成 LaTeX booktabs 与 Word 三线表..."}
        tbl = generate_academic_table(csv_text, caption=caption, label=label, lower_is_better=lower_cols, decimals=decimals)
        yield {
            "type": "ui_action",
            "action": "load_table",
            "studio": "charts",
            "sub_mode": "table",
            "csv_text": csv_text,
            "caption": caption,
            "label": label,
            "lower_is_better": lower_cols,
        }
        yield {
            "type": "tool_result",
            "tool": "build_table",
            "summary": f"已生成 {len(tbl['rows'])} 行出版级三线表（自动加粗最优、下划线次优），已同步至表格工作台。",
            "code_snippet": tbl["latex"],
            "target_studio": "charts",
        }
        return

    if tool == "edit_manuscript":
        action = str(args.get("action") or "polish")
        if action == "clean_typography":
            yield {"type": "tool_start", "tool": "edit_manuscript", "label": "正在执行中英文标点与多余空格清理..."}
            res = clean_typography(manuscript)
            yield {
                "type": "ui_action",
                "action": "update_manuscript",
                "studio": "manuscript",
                "content": res["cleaned"],
            }
            yield {
                "type": "tool_result",
                "tool": "edit_manuscript",
                "summary": f"已完成标点与空格规范化清理（修复 {res['changes']} 处），并更新论文编辑器。",
                "target_studio": "manuscript",
            }
            return

        if action == "propose_edits" and isinstance(args.get("edits"), list) and args["edits"]:
            cards = [
                {
                    "id": f"omni-edit-{i}",
                    "original": str(it.get("original", "")).strip(),
                    "revised": str(it.get("revised", "")).strip(),
                    "tag": str(it.get("tag", "表达")),
                    "reason": str(it.get("reason", "")),
                    "status": "pending",
                }
                for i, it in enumerate(args["edits"], 1)
                if it.get("original") and it.get("revised")
            ]
            yield {"type": "ui_action", "action": "push_edits", "studio": "manuscript", "edits": cards}
            yield {
                "type": "tool_result",
                "tool": "edit_manuscript",
                "summary": f"已向论文工作台推送 {len(cards)} 张可逐句「接受 / 拒绝」的修改卡片。",
                "target_studio": "manuscript",
            }
            return

        if action in ("polish", "zh2en", "en2zh", "mimic", "review"):
            target_text = str(args.get("text") or manuscript)
            if not target_text.strip():
                yield {"type": "tool_result", "tool": "edit_manuscript", "summary": "当前论文编辑器为空，请先导入或粘贴论文内容。"}
                return
            yield {"type": "tool_start", "tool": "edit_manuscript", "label": f"正在调用学术引擎执行 {action} 并检索 3,000 篇母语语料..."}
            edits_collected: list[dict[str, Any]] = []
            text_chunks: list[str] = []
            async for ev in stream_academic_agent(mode=action, text=target_text, instruction=str(args.get("instruction") or ""), venue=venue):
                if ev.get("type") == "token":
                    text_chunks.append(ev.get("text", ""))
                elif ev.get("type") == "edits":
                    edits_collected = ev.get("edits", [])
            if edits_collected:
                yield {"type": "ui_action", "action": "push_edits", "studio": "manuscript", "edits": edits_collected, "stream_text": "".join(text_chunks)}
                yield {
                    "type": "tool_result",
                    "tool": "edit_manuscript",
                    "summary": f"学术引擎 ({action}) 已生成 {len(edits_collected)} 条可逐句审核的修改建议，已推送至论文工作台。",
                    "target_studio": "manuscript",
                }
            else:
                yield {"type": "ui_action", "action": "push_edits", "studio": "manuscript", "edits": [], "stream_text": "".join(text_chunks)}
                yield {
                    "type": "tool_result",
                    "tool": "edit_manuscript",
                    "summary": f"学术引擎 ({action}) 分析完成，详细报告已同步至论文工作台右侧面板。",
                    "target_studio": "manuscript",
                }
            return

    if tool == "optimize_formulas":
        yield {"type": "tool_start", "tool": "optimize_formulas", "label": "正在解析公式编号、符号一致性与最佳插入锚点..."}
        res = analyze_formulas_and_placements(manuscript)
        eq_count = sum(1 for b in res.get("blocks", []) if b.get("kind") == "equation")
        rec_count = len(res.get("recommendations", []))
        conf_count = len(res.get("symbol_conflicts", []))
        yield {"type": "ui_action", "action": "open_formula_studio", "studio": "manuscript", "center_view": "formula"}
        yield {
            "type": "tool_result",
            "tool": "optimize_formulas",
            "summary": f"已解析 {eq_count} 个独立公式、{rec_count} 处推荐锚点、{conf_count} 项符号一致性提示，并切换到公式排版视图。",
            "target_studio": "manuscript",
        }
        return

    if tool == "patch_figure_text":
        ws_fig = str(args.get("workspace_figure") or "").strip()
        if ws_fig:
            yield {"type": "tool_start", "tool": "patch_figure_text", "label": f"正在从 LaTeX 工作区载入图片 {ws_fig} 至「安全改图文字」..."}
            insp = load_workspace_figure_for_patcher(ws_fig)
            if insp.get("kind") == "svg":
                yield {"type": "ui_action", "action": "load_patcher_svg", "studio": "patcher", "svg": insp["svg"], "full_path": insp.get("full_path", ws_fig)}
                yield {"type": "tool_result", "tool": "patch_figure_text", "summary": f"已载入工作区矢量 SVG：{ws_fig}（{len(insp.get('nodes', []))} 个可拖动文字节点）", "target_studio": "patcher"}
            else:
                yield {
                    "type": "ui_action",
                    "action": "load_patcher_raster",
                    "studio": "patcher",
                    "image_b64": insp["image_b64"],
                    "width": insp["width"],
                    "height": insp["height"],
                    "boxes": insp.get("boxes") or [],
                }
                yield {"type": "tool_result", "tool": "patch_figure_text", "summary": f"已载入工作区图片 {ws_fig}（自动识别 {len(insp.get('boxes') or [])} 个文字框，可直接拖动定位）", "target_studio": "patcher"}
            return

        if not all_images:
            yield {"type": "tool_result", "tool": "patch_figure_text", "summary": "当前对话未附带图片，请先上传/粘贴图片，或打开 LaTeX 工作区后指定其中图片路径。"}
            return
        idx = int(args.get("image_index", -1))
        img_uri = all_images[idx] if -len(all_images) <= idx < len(all_images) else all_images[-1]
        yield {"type": "tool_start", "tool": "patch_figure_text", "label": "正在将图片载入「安全改图文字」并初始化可拖动定位框..."}
        _, b64_raw = _split_data_url(img_uri)
        pil_img = Image.open(io.BytesIO(base64.b64decode(b64_raw))).convert("RGB")
        W, H = pil_img.size
        buf = io.BytesIO()
        pil_img.save(buf, format="PNG")
        png_b64 = base64.b64encode(buf.getvalue()).decode("ascii")
        norm = bool(args.get("normalized", False))
        boxes_out = []
        for i, b in enumerate(args.get("boxes") or []):
            bx = float(b.get("x", 40))
            by = float(b.get("y", 40))
            bw = float(b.get("w", 160))
            bh = float(b.get("h", 34))
            if norm or (0 <= bx <= 1000 and 0 <= by <= 1000 and bw <= 1000 and bh <= 1000 and (W > 1050 or H > 1050)):
                if norm:
                    bx, by, bw, bh = bx * W / 1000.0, by * H / 1000.0, bw * W / 1000.0, bh * H / 1000.0
            boxes_out.append({
                "id": f"agent-box-{i}",
                "text": str(b.get("text") or "新标签"),
                "x": max(0, min(W - 20, round(bx))),
                "y": max(0, min(H - 16, round(by))),
                "w": max(24, min(W, round(bw))),
                "h": max(18, min(H, round(bh))),
                "font_size": int(b.get("font_size") or max(14, round(bh * 0.7))),
                "color": str(b.get("color") or "#16191F"),
                "font_family": str(b.get("font_family") or "sans"),
                "align": str(b.get("align") or "center"),
            })
        yield {
            "type": "ui_action",
            "action": "load_patcher_raster",
            "studio": "patcher",
            "image_b64": png_b64,
            "width": W,
            "height": H,
            "boxes": boxes_out,
        }
        yield {
            "type": "tool_result",
            "tool": "patch_figure_text",
            "summary": f"已将图片 ({W}×{H}) 载入「安全改图文字」（预设 {len(boxes_out)} 个可拖动定位框），可直接拖动微调并一键校验导出。",
            "target_studio": "patcher",
        }
        return

    if tool == "verify_citations":
        bib = str(args.get("bibtex") or bibtex)
        online = bool(args.get("verify_online", True))
        yield {"type": "tool_start", "tool": "verify_citations", "label": "正在核验正文 \\cite{} 覆盖率与 Crossref 真实性..."}
        res = await verify_bibtex_online(manuscript, bib) if online else audit_citations_local(manuscript, bib)
        entries = res.get("entries") or []
        verified = sum(1 for e in entries if e.get("status") == "verified")
        missing = len(res.get("missing_in_bib") or [])
        yield {"type": "ui_action", "action": "load_citations", "studio": "citations", "bibtex": bib}
        yield {
            "type": "tool_result",
            "tool": "verify_citations",
            "summary": f"引用核验完成：共 {len(entries)} 条文献（核验通过 {verified} 条 · 缺失 BibTeX 键 {missing} 个），已同步至引用核验室。",
            "target_studio": "citations",
        }
        return

    if tool == "switch_studio":
        st = str(args.get("studio") or "manuscript")
        if st in ("manuscript", "charts", "diagrams", "patcher", "citations"):
            yield {"type": "ui_action", "action": "switch_studio", "studio": st}
            yield {"type": "tool_result", "tool": "switch_studio", "summary": f"已切换工作区至 {st}", "target_studio": st}


async def stream_omni_chat(
    messages: list[dict[str, Any]],
    context: dict[str, Any] | None = None,
) -> AsyncGenerator[dict[str, Any], None]:
    """Stream multimodal chat + live interception & execution of full-workbench tool calls."""
    ctx = context or {}
    all_images = _collect_conversation_images(messages)
    has_images = bool(all_images)

    # Prefer dedicated vision role when images are attached and configured; fallback seamlessly to writing model
    prov, model = (resolve_role_provider("vision") if has_images else (None, ""))
    if not prov or not model or (not prov.get("api_key") and prov.get("region") != "local"):
        prov, model = resolve_role_provider("writing")

    if not prov or not model or (not prov.get("api_key") and prov.get("region") != "local"):
        yield {
            "type": "need_api_key",
            "message": "请先在「配置 API」中配置模型密钥并选择模型，即可开启支持发送图片与调用全站工具的智能体对话。",
        }
        return

    manuscript_snippet = str(ctx.get("manuscript") or "")[:2400]
    ws_info = ctx.get("latex_workspace") if isinstance(ctx.get("latex_workspace"), dict) else None
    ws_summary = ""
    if ws_info and ws_info.get("root_dir"):
        tex_list = ", ".join(ws_info.get("tex_files") or [])[:400]
        fig_list = ", ".join(ws_info.get("figures") or [])[:500]
        ws_summary = (
            f"Mounted LaTeX Workspace Root: {ws_info['root_dir']}\n"
            f"Active File: {ws_info.get('active_file', '')}\n"
            f"Workspace TeX Files: {tex_list or '(none)'}\n"
            f"Workspace Figures (can be loaded via patch_figure_text workspace_figure): {fig_list or '(none)'}\n"
        )
    # If draw_diagram requested a specific workspace .tex file, allow helper access transparently
    _ = read_workspace_text_file
    system_prompt = (
        TOOL_GUIDE
        + f"\n\n--- Active Workspace Context ---\n"
        + f"Current Studio: {ctx.get('studio', 'manuscript')}\n"
        + f"Paper Title: {ctx.get('title', 'Untitled')}\n"
        + f"Target Venue: {ctx.get('venue', 'CVPR / ICCV')}\n"
        + f"Attached Images in Conversation: {len(all_images)}\n"
        + ws_summary
        + (f"Active Manuscript Excerpt:\n\"\"\"\n{manuscript_snippet}\n\"\"\"\n" if manuscript_snippet.strip() else "Active Manuscript: (empty)\n")
    )

    # Trim conversation history to last 12 turns to keep latency snappy
    recent_msgs = messages[-12:]
    full_chunks: list[str] = []
    # Stream visible text while withholding ```tool_call ... ``` fences from raw chat output
    buf = ""
    in_tool_fence = False

    try:
        async for delta in stream_multimodal_messages(prov, model, system_prompt, recent_msgs, temperature=0.3):
            full_chunks.append(delta)
            buf += delta
            while buf:
                if not in_tool_fence:
                    idx = buf.find("```tool_call")
                    if idx != -1:
                        if idx > 0:
                            yield {"type": "token", "text": buf[:idx]}
                        buf = buf[idx + len("```tool_call") :]
                        in_tool_fence = True
                    else:
                        # Keep trailing up to 12 chars in case ```tool_call spans chunks
                        safe = max(0, len(buf) - 12)
                        if safe > 0:
                            yield {"type": "token", "text": buf[:safe]}
                            buf = buf[safe:]
                        break
                else:
                    end_idx = buf.find("```")
                    if end_idx != -1:
                        buf = buf[end_idx + 3 :]
                        in_tool_fence = False
                    else:
                        break
        if buf and not in_tool_fence:
            yield {"type": "token", "text": buf}
    except Exception as e:
        yield {"type": "error", "message": f"{prov['name']} ({model}) 调用失败：{e}"}
        return

    full_text = "".join(full_chunks)
    tool_calls = _extract_tool_calls(full_text)
    for call in tool_calls[:4]:
        try:
            async for evt in _execute_tool(call["tool"], call["args"], ctx, all_images):
                yield evt
        except Exception as e:
            yield {"type": "tool_result", "tool": call["tool"], "summary": f"工具执行失败：{e}", "error": True}

    yield {"type": "done", "provider": prov["name"], "model": model, "tools_executed": len(tool_calls)}
