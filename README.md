# PaperHarness · 学术论文写作与科研绘图桌面 Agent 工作台

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/Python-3.10%2B-3776AB.svg)](requirements.txt)
[![React + TypeScript](https://img.shields.io/badge/Frontend-React%2018%20%2B%20TypeScript-61DAFB.svg)](frontend/package.json)
[![Windows Desktop](https://img.shields.io/badge/Platform-Windows%20WebView2-0078D6.svg)](launch_desktop.py)

**PaperHarness** 是一款零登录、本地运行、以对话为核心的独立 Windows 桌面学术研究与发表工作台（内嵌 3,000 篇 NeurIPS / CVPR / ACL / TPAMI 顶会母语语料库）。支持**多对话独立并发**、**整个 LaTeX 工作区拖入与一键打包投稿包**、**多模态深度学习术语表 + 联网查词 + 防翻译腔双步翻译**、**多智能体协同绘制可 1:1 导出 `.pptx` 的顶刊流程图（含 3D 多层卷积等 13 种 2.5D 矢量示意图）**、**600/1200 DPI 智能数据绘图与三线表**、**安全改图文字（框外零改动校验）**及 **Crossref 引用防幻觉核验**。

---

## 一、快速启动（两种方式）

### 方式 A：下载免安装 Windows EXE（推荐普通用户）
前往本仓库右侧 **Releases** 页面下载 `PaperHarness_Windows_x64.zip`，解压后直接双击 `PaperHarness.exe` 即可打开独立桌面窗口（无需 Python / Node.js）。

### 方式 B：从源码运行（仅需 Python 3.10+，无需 Node.js）
1. 克隆或下载仓库到无特殊符号路径：
   ```bash
   git clone https://github.com/callmeMYth/PaperHarness.git
   cd PaperHarness
   ```
2. 双击 **`启动_PaperHarness.bat`**（自动创建 `.venv`、安装 `requirements.txt` 并启动独立桌面窗口）。
3. 点击顶部 **「配置 API」** 填入任意主流厂商或中转站 Key，点击 **「用 Key 拉取模型」** 即可开始使用（密钥仅保存在本机 `local_data/settings.json`，已被 `.gitignore` 严格排除，绝不会上传 GitHub）。

> **命令行可选启动方式**：
> - `python launch_desktop.py`：默认独立桌面窗口模式
> - `python launch_desktop.py --browser`：强制用系统默认浏览器打开
> - `python launch_desktop.py --server`：仅启动后端服务（默认 `http://127.0.0.1:8765`）

---

## 二、二次开发与修改代码指南

### 1. 修改后端 Python 代码（最简单，无需 Node.js）
- 直接编辑 `backend/` 下的 `.py` 文件，或编辑 `skills/academic-polish/` 下的提示词与规则文件。
- 双击 **`开发模式_修改代码热更新.bat`**（即使没装 Node.js 也会自动启动 `uvicorn --reload`），每次保存 Python 文件后端会自动重载，刷新窗口即刻生效。

### 2. 修改前端 React / TypeScript 界面（需 Node.js 18+）
1. 双击 **`开发模式_修改代码热更新.bat`**：自动安装 `frontend/node_modules` 并同时启动后端热重载 (`:8765`) + Vite 前端热更新 (`http://localhost:5173`)。
2. 编辑 `frontend/src/` 下的组件或样式，浏览器毫秒级实时预览。
3. 修改完毕后，双击 **`重新构建前端.bat`**（执行严格类型检查 `tsc -b` + `vite build`），生成新的 `frontend/dist/`。之后双击 `启动_PaperHarness.bat` 即可在独立桌面窗口运行你改好的新版本。

---

## 三、整体架构总览

```text
PaperHarness/
├── 启动_PaperHarness.bat              # 一键桌面启动（自动配置 .venv + 装依赖 + 启动 WebView2 窗口）
├── 开发模式_修改代码热更新.bat         # 前后端热更新开发脚本（改代码实时生效）
├── 重新构建前端.bat                   # 修改 frontend/src 后重新编译至 frontend/dist
├── launch_desktop.py                 # 桌面启动器（FastAPI 后端线程 + pywebview 窗口 / 浏览器兜底）
├── requirements.txt                  # Python 依赖清单
├── README.md                         # 本说明与二次开发文档
│
├── backend/                          # Python FastAPI 后端（核心算法、大模型网关、导出引擎）
│   ├── main.py                       # 全部 HTTP / SSE API 路由 + 托管 frontend/dist 静态页面
│   ├── config.py                     # 厂商 API 预设列表、local_data/settings.json 读写、skill 路径定位
│   └── services/
│       ├── llm_gateway.py            # 多协议大模型网关（OpenAI / Anthropic 官方 / Claude 中转 + 多模态图片消息 + 学术 Agent 流）
│       ├── omni_agent.py             # 全局「AI 对话」多模态工具编排器（发图理解 + 一句话调度全站 9 大工具）
│       ├── academic_engine.py        # 3,000 篇母语语料加权检索、术语/缩写锁定、中英文标点与多余空格清理
│       ├── doc_io.py                 # Word (.docx 原生 Track Changes 修订模式)、LaTeX (.tex)、PDF、arXiv 导入导出
│       ├── formula_studio.py         # 公式解析、符号一致性检查、推荐插入锚点与上下文 Eq. (k) 编号重排同步
│       ├── chart_table_studio.py     # 智能数据分析、8 套期刊预设、防重叠数据标签 Matplotlib 绘图 (600/1200 DPI) 与三线表
│       ├── diagram_studio.py         # 多智能体协同绘同一张 PPT 流程图（4 阶段分工 + 确定性网格 + 障碍避让分道布线 + 1:1 PPTX）
│       ├── figure_patcher.py         # 安全改图文字（SVG 无损坐标/文字修改 + PDF/PNG 框内替换与框外 0.0000% 像素校验）
│       ├── citation_verifier.py      # 正文 \cite{} 覆盖审计 + 联网 Crossref 防幻觉核验
│       └── corpus_trainer.py         # 多语料包管理、IDF 归一化检索、风格蒸馏、.zip 共享包与 SFT/DPO 微调 JSONL 导出
│
├── frontend/                         # React 18 + TypeScript + Vite 前端工作台
│   ├── package.json                  # 前端依赖与脚本
│   ├── tsconfig.json                 # 严格 TS 配置（noUnusedLocals / noUnusedParameters，杜绝冗余代码）
│   ├── vite.config.ts                # Vite 构建配置与开发期 /api 代理
│   ├── dist/                         # 已编译好的生产前端包（无 Node.js 也能直接运行）
│   └── src/
│       ├── main.tsx                  # 应用挂载入口
│       ├── App.tsx                   # 全局布局壳、左侧导航、顶部导出栏、语言/字号/主题切换与 Omni-Agent 动作分发中心
│       ├── api.ts                    # 轻量类型化 API & SSE 流式客户端
│       ├── types.ts                  # 全局 TypeScript 接口定义
│       ├── i18n.ts                   # 中/英双语词典（默认简体中文，一键切英文）
│       ├── styles/theme.css          # 浅色纸张 (paper) & 深色书房 (ink) 双主题设计系统与动画
│       └── components/
│           ├── ManuscriptStudio.tsx  # 论文工作台（导入、大纲/术语/语料检索、源码/KaTeX排版/公式编排、流式 Diff 审校）
│           ├── DataTableStudio.tsx   # 智能数据绘图（8 预设 / 7 图型 / 600–1200 DPI）与顶刊三线表（LaTeX + Word）
│           ├── DiagramStudio.tsx     # 顶刊流程图交互画布（直接拖动/缩放 + 多智能体协同绘 PPT + 1:1 导出 .pptx）
│           ├── FigurePatcherStudio.tsx # 安全改图文字（SVG 拖拽定位与 ΔX/ΔY 微调 + 位图框拖拽/缩放/方向键 1px 微调）
│           ├── CitationStudio.tsx    # 引用完整性审计与 Crossref 联网真实性核验
│           ├── CorpusStudio.tsx      # 实验室增量语料包、.zip 导入导出与 LoRA/SFT/DPO 飞轮
│           ├── OmniChatDrawer.tsx    # 全局多模态「AI 对话」抽屉（上传/拖入/Ctrl+V 贴图 + 工具卡片 + 一键导出 PPTX）
│           ├── ModelHubModal.tsx     # 厂商 API 配置中心（实时拉取 /models + Claude 中转适配 + 角色路由）
│           └── MathTex.tsx           # KaTeX 行内/独立数学公式渲染器
│
├── skills/academic-polish/           # 内置 3,000 篇顶会学术写作技能包（开箱即用，可直接编辑规则）
│   ├── SKILL.md                      # 核心学术写作与防过度声称指令规范
│   ├── references/                   # 各章节写作规则、中译英规则、润色范式
│   ├── phrasebank/                   # 高频母语学术句型库
│   └── data/                         # examples.jsonl (104,474 句) & embeddings_i8.npz 量化向量
│
└── local_data/                       # 运行后自动生成的本机数据目录（分享压缩包时请勿包含此目录！）
    ├── settings.json                 # 本机 API Key 与路由配置
    └── corpus_packs/                 # 你自行新建的增量语料包与微调反馈记录
```

---

## 四、高频二次开发速查表（“我想改 XXX，该动哪个文件？”）

| 我想修改 / 新增什么功能 | 直接编辑的文件 | 关键位置 / 说明 |
| :--- | :--- | :--- |
| **新增或修改大模型厂商 / 中转站预设** | `backend/config.py` | 修改 `_PRESET_SPECS` 元组列表（协议可选 `"openai"` / `"anthropic"` / `"anthropic_relay"`） |
| **修改论文润色、审稿、翻译的 Prompt 或纪律** | `skills/academic-polish/SKILL.md`、`references/` 及 `backend/services/llm_gateway.py` | 调整 `stream_academic_agent()` 中的 `system_prompt` 与 `directives` |
| **给「AI 对话」新增一个可调用工具** | `backend/services/omni_agent.py` + `frontend/src/App.tsx` | 1. 在 `TOOL_GUIDE` 写入工具 Schema；2. 在 `_execute_tool()` 实现工具并 yield `ui_action`；3. 在 `App.tsx` 的 `handleOmniUiAction()` 处理前端联动 |
| **修改多智能体协同画 PPT 流程图的分工与防幻觉策略** | `backend/services/diagram_studio.py` | 4 阶段分工位于 `stream_concurrent_diagram_agents()`（`architect` → 并行 `stage` → `auditor` → `composer`） |
| **调整流程图排版间距、通道宽度、颜色主题或箭头避让算法** | `backend/services/diagram_studio.py` + `frontend/src/components/DiagramStudio.tsx` | `VENUE_DIAGRAM_THEMES`（配色）、`compute_clean_grid_layout()`（阶段与通道间距）、`compute_routed_edges()` 与前端 `computeRoutedEdges()`（保持两边路由逻辑一致即可实现 1:1 导出 `.pptx`） |
| **新增科研数据绘图期刊预设、色盲友好配色或图表类型** | `backend/services/chart_table_studio.py` | 修改 `VENUE_PRESETS`、`PALETTES`、`SAMPLE_DATASETS`、`analyze_dataset()` 和 `generate_matplotlib_code()` |
| **调整 Word 修订模式或 LaTeX 导出模板** | `backend/services/doc_io.py` | 修改 `export_docx_bytes()`（OpenXML `w:ins`/`w:del`）与 `export_latex_string()` |
| **修改中/英文界面文案** | `frontend/src/i18n.ts` | 修改 `T.zh` 与 `T.en` 字典，改完运行 `重新构建前端.bat` |
| **自定义界面配色、字体大小或卡片圆角** | `frontend/src/styles/theme.css` | 修改顶部 `:root`（浅色纸张）与 `[data-theme='ink']`（深色书房）的 CSS 变量 |
| **由维护者热更新底层的语料库 / 规则 / 模型向量包（免重打 EXE）** | `manage_knowledge_pack.py` + `local_data/knowledge_pack/` | 在命令行运行 `python manage_knowledge_pack.py ingest --pdf ...` 或 `package-override`，程序启动时优先加载 `local_data/knowledge_pack/` 覆盖内置包，无需重新打包 `.exe` |
| **自定义多模态术语词表与联网搜索引擎** | 界面「术语库与联网搜索」或 `backend/services/terminology_and_search.py` | 默认内置 44 条多模态深度学习术语表 + 免 Key 学术搜索（arXiv + Bing CN），也支持自填博查 / Tavily / Serper Key，且对话 Agent 可直接调用 `web_search` 与 `lookup_term` |
| **自定义流程图构图骨架、配色与框内 2.5D 卷积/注意力示意图** | `backend/services/diagram_studio.py` + `frontend/src/components/DiagramStudio.tsx` | 支持 4 种顶会构图骨架、自定义主色/强调色、13 种 2.5D 深度学习矢量示意图（含 3D 多层卷积堆叠 / CNN 特征金字塔 / ViT 分块 / 跨注意力 / U-Net / MoE / 扩散去噪）以及嵌入工作区真图/本地图片，一键 1:1 导出 `.pptx` |
| **LaTeX 整个工作区导入与一键打包投稿包** | `backend/services/tex_workspace.py` | 直接把整个论文文件夹拖入窗口即可读取全部 `.tex`/图片/`.bib`；顶部点击「打包投稿 .zip」自动剔除 `.aux/.log/.bak` 与编译 PDF，输出干净的 Overleaf / arXiv 投稿压缩包 |

---

## 五、核心后端接口一览（`backend/main.py`）

- **配置与模型**：`GET /api/health`、`GET /api/sample`、`GET/POST /api/settings*`、`POST /api/settings/test-provider`（实时拉取 `/models`）
- **论文读写与学术 Agent**：`POST /api/manuscript/import-file`、`import-arxiv`、`export-docx`、`export-latex`、`glossary`、`corpus`、`typography`、`outline`、`POST /api/agent/stream` (SSE)
- **全局多模态 AI 对话**：`POST /api/chat/stream` (SSE，支持多轮消息 + `base64` 图片 + 工具调用与 `ui_action` 事件)
- **公式排版**：`POST /api/formula/analyze`、`POST /api/formula/rebuild`
- **智能数据绘图与三线表**：`POST /api/charts/analyze`、`POST /api/charts/render`、`POST /api/tables/generate`、`POST /api/tables/export-docx`
- **顶刊流程图与多智能体 PPT**：`POST /api/diagrams/generate-stream` (SSE 4 阶段协同流水线)、`render`、`export-pptx`、`export-pdf`、`export-png`、`ai-asset`
- **安全改图文字**：`POST /api/patcher/inspect`、`patch-svg`、`patch-raster`
- **引用核验**：`POST /api/citations/audit`
- **语料与微调飞轮**：`GET/POST/PATCH/DELETE /api/corpus/packs*`、`ingest-files`、`ingest-arxiv`、`ingest-text`、`distill`、`build-vectors`、`export-zip`、`import-zip`、`feedback`、`export-training`

---

## 六、推送更新与自动发布 Windows EXE（GitHub 工作流）

本仓库已配置好 `.gitignore`（自动屏蔽 `local_data/` 密钥、`node_modules/`、`.venv/`、`release/`）与 GitHub Actions 自动构建流水线（`.github/workflows/ci-and-release.yml`）。

### 1. 仓库地址（已绑定 `origin`）
```bash
git remote -v
# origin  https://github.com/callmeMYth/PaperHarness.git
```

### 2. 以后日常修改代码后推送更新
```bash
# 若修改了 frontend/src，请先运行「重新构建前端.bat」更新 frontend/dist
git add .
git commit -m "feat: 描述本次更新内容"
git push
```

### 3. 自动云端构建并发布新版 `PaperHarness.exe`（GitHub Releases）
只需打一个 `v` 开头的版本标签并推送，GitHub Actions 会自动在云端 Windows 机器上打包生成 `PaperHarness_Windows_x64.zip` 并发布到仓库的 **Releases** 页面：
```bash
git tag v2.0.0
git push origin v2.0.0
```
（本机也可随时执行 `python build_exe.py` 在本地生成 `release/PaperHarness/PaperHarness.exe`。）
