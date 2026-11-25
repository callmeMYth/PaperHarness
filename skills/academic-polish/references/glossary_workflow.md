# 整篇论文全局术语锁定流程（Glossary Lock）

> 痛点：长论文分批翻译（无论是中译英还是英译中）时，极易出现前后译名漂移（例如前半篇叫 `backbone → 主干网络`，后半篇变成 `骨干网`；或英文稿混用 `module / block / unit`、`our method / the proposed approach / our network`）。

## 三步工作流

### 1. 翻译前：自动提取与锁定
对整篇输入稿（`.md` / `.tex` / `paper_io.py` 导出的 `paper.json`）运行：
```bash
python "<skill_dir>/scripts/glossary.py" extract "<input_file>" --out glossary.json --md glossary.md
```
脚本会自动提取：
- 文中定义的所有缩写对（如 `Large Language Model (LLM)`、`Multi-Head Self-Attention (MHSA)`）
- 命中 `references/dl_terminology.md` 的深度学习领域术语及其推荐中英对照
- 高频专有模型名/数据集名（自动标记为“保留原英文不翻译”）

在开始逐章翻译前，将 `glossary.md` 展示给用户（或按用户补充的自定义术语更新 `glossary.json`），**一旦锁定，后续所有章节严格遵守**。

### 2. 翻译中：按章节严格引用
- 每次处理一个章节时，强制核对 `glossary.json` 中的映射；
- 首次出现术语时按方向规范展开（英译中：`中文（English, ACR）`；中译英：`Full English Name (ACR)`），后续统一使用约定形式。

### 3. 翻译后：自动一致性审计
全篇翻译或润色完成后运行：
```bash
python "<skill_dir>/scripts/glossary.py" check "<translated_file>" --glossary glossary.json --lang zh|en
```
脚本会检查并报告：
- 同一英文术语是否出现了多个中文变体（或同一概念混用近义词）
- 锁定的专有模型名是否被误译
- 缩写首次出现是否遗漏了全称展开

发现不一致处直接在终稿中统一修复后再导出。
