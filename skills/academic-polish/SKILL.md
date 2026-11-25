---
name: academic-polish
description: 深度学习/计算机领域学术论文全链路工具：中译英与英文润色、参考英文论文格式仿写、英文论文精读翻中文并完整导出（Markdown/双语/MathJax HTML）、稿件中式与AI腔自动体检、整篇术语一致性锁定、以及投稿前审稿人预审。Use when the user asks to translate a Chinese academic paper into English, polish academic English, mimic a reference English paper's formatting/LaTeX style, translate and export an English/arXiv/PDF paper into fluent Chinese without translationese, audit a draft for Chinglish/AI-isms, lock paper terminology, or run a pre-submission peer review in deep learning, ML, CV, or NLP.
---

# Academic Polish v0.2：深度学习论文写作、润色、精读翻译与预审

本 skill 基于 **3,000 篇**深度学习顶会与顶刊论文提炼（NeurIPS、ICML、CVPR、ICCV、ACL、EMNLP、AAAI、TPAMI、IJCV、TNNLS、TIP 等，2020–2026 年）：
- **2,500 篇英语母语地区作者论文**（其中 **1,400 篇为 2020–2021 年零 LLM 润色污染的高引基准**，1,100 篇为 2022–2026 年前沿论文）
- **500 篇华人地区单位作者论文**（用于实证对比定位中式高频表达偏差）

内置四大脚本（均支持零依赖或优雅降级）：
- `scripts/retrieve.py`：从约 10 万条真实例句中检索风格参照（`bge-small-en-v1.5` int8 向量检索 + 零依赖 BM25 自动回退，默认 `--group native`）
- `scripts/paper_io.py`：提取 arXiv ID / `.tex` / `.pdf` / `.md` 为分章节文件，并一键导出纯中文 `.md`、双语对照 `.md` 及带 MathJax 公式渲染的 `.html`（浏览器 `Ctrl+P` 即得排版精美的 PDF）
- `scripts/audit.py`：零依赖自动化体检，对照 3,000 篇母语基线扫描超长句、中式表达、AI 腔、Overclaim、连用被动与句首重复
- `scripts/glossary.py`：长论文全局术语表提取与译后一致性审计

---

## 支持的六种模式

| 模式 | 适用场景 | 核心输出 |
|---|---|---|
| **`zh2en`** | 中文论文段落/章节 → 学术英语 | 逐句修改对照表 + 终稿 |
| **`polish`** | 已有英文稿学术化、去中式英语、去 AI 腔 | （可选先跑 `audit.py`）逐句修改对照表 + 终稿 |
| **`mimic`** | 给参考英文论文 + 中文稿，同步翻译并仿写版式/LaTeX/行文风格 | 6 维格式蓝图 + 修改对照表 + 套用模板的终稿 |
| **`en2zh`** | 阅读英文论文（arXiv ID / PDF / LaTeX / Markdown）翻中文并**完整导出** | 锁定术语表 + 完整导出的 `_zh.md` / `_bilingual.md` / `_zh.html` / `_bilingual.html` |
| **`audit`** | 英文稿中式表达 / AI 腔 / 可读性自动化体检 | 量化指标表 + 分级诊断清单（P0/P1/P2） |
| **`review`** | 投稿前模拟 NeurIPS/CVPR/TPAMI 审稿人预审 | 5 维评分卡 + Major/Minor Concerns + 可落地改写建议 |

---

## 硬性约束（所有模式一律遵守）
1. **不改变事实**：数字、单位、数据集、模型名、公式符号、实验结论强度保持原样。
2. **不新增内容**：不编造实验、数据、论点或参考文献；审稿预审发现缺实验时只提建议，绝不伪造结果。
3. **仿写绝不抄袭**：`mimic` 模式只仿结构、排版宏与行文范式，严禁复制参考论文的原句或文献；中文稿缺失小节只放 `% TODO` 占位。
4. **保留 LaTeX 与公式**：`\cite{}`、`\ref{}`、`$...$`、`$$...$$`、`\label{}` 等命令与数学变量原样保留。
5. **术语一致**：用户自定义术语表 > 锁定的 `glossary.json` > `references/dl_terminology.md`。
6. 原文有歧义时标出 `⚠ 需作者确认` 及可选方案，不擅自猜测。

---

## 按需加载参考资料（不要一次全读）

| 模式 | 需要读取的参考文档 |
|---|---|
| `zh2en` | `references/zh2en_rules.md` + `references/dl_terminology.md` + `references/phrasebank/<section>.md` |
| `polish` | `references/polish_rules.md` + `references/chinglish_patterns.md` + `references/phrasebank/<section>.md` |
| `mimic` | `references/format_mimicry.md` + `references/zh2en_rules.md` + `references/dl_terminology.md` |
| `en2zh` | `references/en2zh_rules.md` + `references/dl_terminology.md` + `references/glossary_workflow.md` |
| `review` | `references/presubmission_review.md` + `references/chinglish_patterns.md` |
| 深度逻辑调整 | 追加读取 `references/paragraph_logic.md` |
| 终稿前必查 | `references/checklist.md` |

---

## 核心工作流

### A. 中译英 / 英文润色 / 格式仿写（`zh2en` / `polish` / `mimic`）
1. **识别任务**：确定模式、所属章节（`abstract`/`introduction`/`related_work`/`method`/`experiments`/`conclusion`）和力度（默认中度；需调整段落逻辑时用深度）。
2. **先体检（`polish` 推荐）与锁定术语（长文推荐）**：
   ```bash
   python "<skill_dir>/scripts/audit.py" "<draft_file>"
   python "<skill_dir>/scripts/glossary.py" extract "<input_file>" --out glossary.json --md glossary.md
   ```
3. **提取格式蓝图（仅 `mimic`）**：通读参考英文论文，按 `references/format_mimicry.md` 提取 6 维格式蓝图与章节映射。
4. **初稿重建**：中文稿按英文句法重建（拆流水句、补主语、已知→新信息、长定语后置、显化逻辑）；深度模式按 `paragraph_logic.md` 调整段落逻辑。
5. **检索母语真实例句并修订（推荐）**：
   ```bash
   python "<skill_dir>/scripts/retrieve.py" "<英文初稿句子>" --section <section> --group native --k 6
   ```
   - 仅用英文检索；参照例句的句式、动词选择与衔接方式修订，不得照搬内容；无 Python 时跳过并注明。
6. **自检与术语核对**：核对 `references/checklist.md`（长文可跑 `glossary.py check --lang en`）。
7. **固定输出格式**：
   - `mimic` 先给 **格式蓝图**；
   - **修改对照表**（逐句：`| # | 原文 | 修改后 | 修改理由 |`，理由必须带标签：【语法】【用词】【句式】【逻辑】【衔接】【简洁】【语气】【术语】【格式】，写清具体原因）；
   - **段落逻辑调整说明**（做了段落级调整时输出）；
   - **终稿**（完整可粘贴/可编译文本，无批注标记）。

### B. 英文论文精读翻中文 + 完整导出（`en2zh`）
1. **提取与切片**：当用户输入 arXiv ID（如 `2103.14030`）、`.tex`、`.pdf` 或 `.md` 时，运行：
   ```bash
   python "<skill_dir>/scripts/paper_io.py" extract "<source>" --out-dir "<work_dir>"
   ```
   （短段粘贴则直接翻译，无需切片。）
2. **提取并锁定全局术语表**：
   ```bash
   python "<skill_dir>/scripts/glossary.py" extract "<work_dir>/paper.json" --out "<work_dir>/glossary.json" --md "<work_dir>/glossary.md"
   ```
3. **逐章去翻译腔翻译**：严格遵循 `references/en2zh_rules.md` 与锁定的 `glossary.json`，逐节读取 `<work_dir>/sections/00_*.md`，将译文以相同文件名写入 `<work_dir>/translated/00_*.md`（保持段落数量与小节标题一一对应，所有 `$...$` / `$$...$$` 公式与编号完整保留）。
4. **全篇术语一致性检查与一键导出**：
   ```bash
   python "<skill_dir>/scripts/paper_io.py" export "<work_dir>" --name "<paper_slug>" --zh-title "<中文标题>"
   python "<skill_dir>/scripts/glossary.py" check "<work_dir>/export/<paper_slug>_zh.md" --glossary "<work_dir>/glossary.json" --lang zh
   ```
   若检出术语漂移，统一修正后重新执行 `export`，最终把 `export/` 下的 4 个文件（纯中文 MD、双语 MD、纯中文 HTML、双语 HTML）链接交还用户。

### C. 自动化体检（`audit`）与投稿前预审（`review`）
- `audit`：直接运行 `scripts/audit.py` 输出量化体检报告；可询问用户是否立即按报告执行 `polish`。
- `review`：先运行 `scripts/audit.py` 获取语言诊断，再按 `references/presubmission_review.md` 从 5 个维度输出完整审稿人预审报告（评分卡 + Major Concerns + Minor/Overclaim 清单 + P0/P1/P2 行动项）。

## 风格目标（英文产出）
- 读起来像**英语母语研究者在顶会发表的论文**：清晰、精确、克制；
- 主动语态为主（*We propose / We use / We show that*），客观流程用被动；
- 避免中式高频套话（`In this way / Besides / Meanwhile / we adopt / verify the effectiveness`）与 AI 腔词（`delve / pivotal / intricate / showcase / underscore`）；
- 平均句长 18–25 词，长短句交替，多用 `While A, B` 合并对比句。
