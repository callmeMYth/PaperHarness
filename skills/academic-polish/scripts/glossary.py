#!/usr/bin/env python
"""Global glossary extractor and consistency checker for long-paper translation (en2zh / zh2en).

Usage:
  python glossary.py extract <input_file> --out glossary.json [--md glossary.md]
  python glossary.py check <translated_file> --glossary glossary.json [--lang zh|en]
"""
import argparse, json, re, sys
from collections import Counter
from pathlib import Path

TERM_FILE = Path(__file__).resolve().parents[1] / "references" / "dl_terminology.md"
# Captures both Title Case and lowercase technical terms followed by (ACR), e.g. "shifted window multi-head self-attention (SW-MSA)"
ACRONYM_RE = re.compile(r"\b([A-Za-z][a-zA-Z0-9\-]*(?:\s+[A-Za-z][a-zA-Z0-9\-]*){1,5})\s*\(([A-Z][A-Z0-9\-]{1,10}s?)\)")
STOP_LEAD = {"the", "a", "an", "of", "in", "on", "for", "with", "to", "and", "or", "by", "as", "from", "our", "its", "this", "that", "called", "named", "known", "using", "via"}
KEEP_UNTRANSLATED = {"token", "prompt", "transformer", "dropout", "softmax", "resnet", "lora"}

# Common Chinese synonym-drift groups to guard against when checking zh translations
ZH_DRIFT_GROUPS = [
    ("backbone", ["主干网络", "骨干网络", "骨干网", "主干网"]),
    ("ablation study", ["消融实验", "消融研究", "去除实验"]),
    ("batch size", ["批大小", "批次大小", "批量大小"]),
    ("receptive field", ["感受野", "接收野"]),
    ("attention", ["注意力", "注意机制"]),
    ("fine-tuning", ["微调", "精调"]),
    ("pre-training", ["预训练", "预先训练"]),
    ("baseline", ["基线", "基准模型"]),
    ("loss function", ["损失函数", "代价函数"]),
    ("hyperparameter", ["超参数", "超参"]),
    ("feature map", ["特征图", "特性图"]),
    ("ground truth", ["真实标签", "真值", "标注真值"]),
]

EN_DRIFT_GROUPS = [
    ("component_noun", ["module", "block", "unit"]),
    ("method_ref", ["our method", "our approach", "our framework", "the proposed method", "the proposed approach"]),
]


def trim_expansion(phrase, acr):
    """Trim leading filler words so expansion aligns cleanly with the acronym's initials."""
    words = phrase.split()
    while len(words) > 2 and words[0].lower() in STOP_LEAD:
        words.pop(0)
    # Try aligning with the first letter of the acronym
    first = acr[0].lower()
    for i, w in enumerate(words):
        if w[0].lower() == first and len(words) - i >= 2:
            return " ".join(words[i:])
    return " ".join(words)


def load_dl_terms():
    """Parse references/dl_terminology.md cleanly, avoiding partial slash fragments."""
    terms = []
    if not TERM_FILE.exists():
        return terms
    for line in TERM_FILE.read_text(encoding="utf-8").splitlines():
        if not line.startswith("|") or line.startswith("|---") or "中文" in line:
            continue
        cols = [c.strip() for c in line.strip("|").split("|")]
        if len(cols) < 2:
            continue
        zh_raw = cols[0].replace("★", "").strip()
        en_raw = cols[1].strip()
        if not zh_raw or not en_raw:
            continue
        # Only split multi-item rows when both sides have equal slash-separated items without shared tail
        zh_parts = [p.strip() for p in zh_raw.split("/")]
        en_parts = [re.sub(r"\s*\([^)]*\)", "", p).strip() for p in en_raw.split("/")]
        if len(zh_parts) == len(en_parts) and len(en_parts) > 1:
            # Handle shared English tail like "training / validation / test set"
            tail_words = en_parts[-1].split()
            if len(tail_words) >= 2 and all(len(p.split()) == 1 for p in en_parts[:-1]):
                tail = " ".join(tail_words[1:])
                en_parts = [f"{p} {tail}" for p in en_parts[:-1]] + [en_parts[-1]]
            # Handle shared Chinese tail like "语义 / 实例 / 全景分割"
            if len(zh_parts[-1]) >= 3 and all(len(z) <= 2 for z in zh_parts[:-1]):
                zh_tail = zh_parts[-1][-2:]
                zh_parts = [f"{z}{zh_tail}" for z in zh_parts[:-1]] + [zh_parts[-1]]
            pairs = list(zip(zh_parts, en_parts))
        else:
            pairs = [(zh_parts[0], en_parts[0])]
        for z, e in pairs:
            if len(e) < 3 or e.lower() in KEEP_UNTRANSLATED:
                continue
            terms.append({"zh": z, "en": e, "en_full": en_raw})
    return terms


def read_input(path: Path):
    if path.suffix.lower() == ".json":
        data = json.loads(path.read_text(encoding="utf-8-sig"))
        parts = [data.get("title", "")]
        for s in data.get("sections", []):
            parts.append(s.get("heading", ""))
            parts.extend(s.get("paragraphs", []))
        return "\n\n".join(parts)
    return path.read_text(encoding="utf-8-sig")


def cmd_extract(args):
    text = read_input(Path(args.input))
    low = text.lower()

    # 1. Acronyms defined in text: Full Name (ACR)
    acronyms = {}
    for full, acr in ACRONYM_RE.findall(text):
        base_acr = acr[:-1] if acr.endswith("s") and len(acr) > 3 else acr
        if len(base_acr) >= 2 and base_acr not in {"FIG", "TAB", "EQ", "SEC", "PDF", "URL", "HTTP", "HTTPS"}:
            acronyms.setdefault(base_acr, trim_expansion(full.strip(), base_acr))

    # 2. Domain terms matched from dl_terminology.md
    seen_en, matched_terms = set(), []
    for t in load_dl_terms():
        key = t["en"].lower()
        if key in seen_en:
            continue
        en_pat = r"\b" + re.escape(key) + r"s?\b"
        en_cnt = len(re.findall(en_pat, low))
        zh_cnt = text.count(t["zh"])
        if en_cnt > 0 or zh_cnt > 0:
            seen_en.add(key)
            matched_terms.append({
                "en": t["en"], "zh": t["zh"], "en_full": t["en_full"],
                "count": en_cnt + zh_cnt, "locked": True
            })
    matched_terms.sort(key=lambda x: -x["count"])

    # 3. Frequent CamelCase / AllCaps model & dataset names (keep untranslated)
    proper = Counter(re.findall(r"\b(?:[A-Z][a-z]+[A-Z][A-Za-z0-9\-]*|[A-Z]{2,}[0-9]+(?:[A-Za-z]+)?)\b", text))
    keep_as_is = [k for k, v in proper.most_common(30) if v >= 2]

    glossary = {
        "source": str(args.input),
        "acronyms": [{"acr": k, "full": v, "zh": ""} for k, v in sorted(acronyms.items())],
        "terms": matched_terms[:60],
        "keep_as_is": keep_as_is,
    }
    Path(args.out).write_text(json.dumps(glossary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Saved glossary JSON to {args.out}: {len(acronyms)} acronyms, {len(matched_terms[:60])} DL terms, {len(keep_as_is)} proper names.")

    if args.md:
        md = ["# 论文锁定术语表（Glossary Lock）\n",
              "## 1. 缩写定义（首次出现须写全称）",
              "| 缩写 | 英文全称 | 锁定中文译名 |", "|---|---|---|"]
        for a in glossary["acronyms"]:
            md.append(f"| `{a['acr']}` | {a['full']} | {a['zh'] or '（待确认/保留英文）'} |")
        md += ["\n## 2. 命中深度学习标准术语", "| English | 锁定中文 | 原文频次 |", "|---|---|---|"]
        for t in glossary["terms"]:
            md.append(f"| {t['en']} | {t['zh']} | {t['count']} |")
        md += ["\n## 3. 模型/数据集专有名词（保留原英文不翻译）\n", ", ".join(f"`{k}`" for k in keep_as_is) or "（无）"]
        Path(args.md).write_text("\n".join(md) + "\n", encoding="utf-8")
        print(f"Saved glossary Markdown to {args.md}")


def cmd_check(args):
    text = read_input(Path(args.input))
    g = json.loads(Path(args.glossary).read_text(encoding="utf-8-sig"))
    issues = []

    if args.lang == "zh":
        for concept, variants in ZH_DRIFT_GROUPS:
            # Count longest variants first and mask matches so "主干网" never double-counts inside "主干网络"
            masked, hits = text, []
            for v in sorted(variants, key=len, reverse=True):
                c = masked.count(v)
                if c > 0:
                    hits.append((v, c))
                    masked = masked.replace(v, " " * len(v))
            if len(hits) >= 2:
                issues.append(("译名不统一", concept, ", ".join(f"{v}({c}次)" for v, c in hits), f"全文统一为 `{hits[0][0]}`"))
        for a in g.get("acronyms", []):
            acr = a["acr"]
            if re.search(rf"\b{re.escape(acr)}\b", text):
                if a["full"].lower() not in text.lower() and not re.search(rf"[（(][^）)]*{re.escape(acr)}[）)]", text):
                    issues.append(("缩写未首次展开", acr, f"文中出现 `{acr}`，但未见首次括注全称", f"首次出现写为「中文（{a['full']}, {acr}）」"))
        missing_names = [k for k in g.get("keep_as_is", [])[:15] if k not in text]
        if missing_names:
            issues.append(("专有名词疑似丢失/被误译", "keep_as_is", ", ".join(missing_names[:8]), "核对专有模型/数据集名是否被意外意译"))
    else:
        low = text.lower()
        for concept, variants in EN_DRIFT_GROUPS:
            hits = [(v, len(re.findall(rf"\b{re.escape(v)}\b", low))) for v in variants]
            hits = [(v, c) for v, c in hits if c > 0]
            if len(hits) >= 3:
                issues.append(("术语混用", concept, ", ".join(f"`{v}`({c}x)" for v, c in hits), "同一组件/概念尽量固定 1–2 种叫法"))
        for a in g.get("acronyms", []):
            acr = a["acr"]
            if re.search(rf"\b{re.escape(acr)}\b", text) and f"({acr})" not in text:
                issues.append(("缩写未首次定义", acr, f"`{acr}` 出现但无 `Full Name ({acr})`", f"首次出现补全为 `{a['full']} ({acr})`"))

    print(f"# 术语一致性检查报告（lang={args.lang}）\n")
    if not issues:
        print("✅ 未发现明显的术语不一致或缩写遗漏。")
    else:
        print("| 问题类型 | 概念/缩写 | 检出详情 | 建议 |")
        print("|---|---|---|---|")
        for typ, key, det, fix in issues:
            print(f"| {typ} | {key} | {det} | {fix} |")


def main():
    ap = argparse.ArgumentParser(description="Extract and check paper glossaries for translation consistency.")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p1 = sub.add_parser("extract")
    p1.add_argument("input")
    p1.add_argument("--out", required=True)
    p1.add_argument("--md", default=None)
    p1.set_defaults(func=cmd_extract)

    p2 = sub.add_parser("check")
    p2.add_argument("input")
    p2.add_argument("--glossary", required=True)
    p2.add_argument("--lang", choices=["zh", "en"], default="zh")
    p2.set_defaults(func=cmd_check)

    args = ap.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
