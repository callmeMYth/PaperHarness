# Changelog

All notable changes to **PaperHarness** are documented in this file.

## [2.0.0] - 2026-11-25

### Added
- **Conversational-First Native Desktop Workbench**: Mrite-inspired 4-column frameless Windows WebView2 desktop app (`launch_desktop.py`) with native Windows Open / Save-As / Folder dialogs and exact file path display + 1-click Explorer reveal.
- **True Multi-Conversation Concurrency**: Independent per-session streaming (`sessionId`-scoped messages, todos, artifacts, drafts, and per-session `AbortController` stop buttons) so multiple chats can draw diagrams, translate sections, and verify citations simultaneously.
- **Full LaTeX Workspace Support & Clean Submission Export**: Drag-and-drop an entire LaTeX project folder (`.tex` + `figures/` + `.bib`), live `\includegraphics` preview, direct write-back with `.bak` backup, and 1-click `submission.zip` export (strips `.aux/.log/.bak/compiled root PDF`).
- **Diagram Studio 2.0**: 4-phase collaborative multi-agent PPTX architecture generator (`Architect → Parallel Stage Builders → Anti-Hallucination Edge Auditor → Deterministic Grid + Obstacle-Aware Lane Router + VLM Self-Critique`), 13 built-in 2.5D deep-learning vector illustrations (`conv_stack_3d`, `conv_pyramid`, `patch_grid`, `cross_attn`, `unet_trapezoid`, `moe_router`, `diffusion_steps`, etc.), 4 top-venue layout archetypes, custom hex color pickers, 4-way in-box image controls, conversational `refine_diagram`, and 1:1 native editable `.pptx` export.
- **Multimodal DL Glossary + Multi-Provider Web Search + Anti-Translationese Pipeline**: Built-in 44-term Multimodal Deep Learning glossary, zero-key arXiv + Bing CN search (plus optional Bocha / Tavily / Serper keys), `en2zh` English-corpus isolation, similarity threshold gating + style-strength control, and two-step Faithful Draft → De-Translationese Smooth Pass with post-translation consistency check.
- **Hot-Swap External Knowledge Pack**: Priority loading from `local_data/knowledge_pack/` and maintainer CLI `manage_knowledge_pack.py` so corpus/rules/embeddings can be updated without rebuilding `.exe`.
- **Smart Data Figures, Safe Figure Patcher & Citation Verifier**: 600/1200 DPI collision-free Matplotlib figures (8 venue presets, 7 chart types), LaTeX `booktabs` + Word three-line tables, vector SVG/PDF & raster text patching with 0.0000% outside-box pixel integrity check, and Crossref citation verification.
