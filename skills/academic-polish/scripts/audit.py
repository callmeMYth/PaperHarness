#!/usr/bin/env python
"""Dependency-free academic English manuscript auditor grounded in top-venue DL corpus baselines.

Usage:
  python audit.py <file_path>
  python audit.py --text "In recent years, deep learning has developed rapidly..."

Checks:
  1. Long sentences (>40 words) & average sentence length (target 18-25 words)
  2. Over-used Chinglish sentence-initial connectives (In this way, Besides, Meanwhile, etc.)
  3. High-frequency Chinglish phrases (we adopt, verify the effectiveness, experimental results show, superiority)
  4. AI-ism buzzwords (delve, pivotal, intricate, showcase, underscore, tapestry, holistic, seamless...)
  5. Overclaim / hedging warnings (prove, completely solve, significantly without p-value, always/never)
  6. Banned clichés & informal contractions (In recent years, With the rapid development of, don't, etc.)
  7. Consecutive passive sentences (>=3) & repeated sentence openers (>=3)
  8. Decorative adverb stacking (>1 per paragraph)
"""
import argparse, re, sys
from pathlib import Path

SPLIT = re.compile(r"(?<=[.!?])\s+(?=[A-Z\"])")
ABBR = re.compile(r"\b(e\.g|i\.e|et al|etc|vs|Fig|Eq|Sec|Tab|resp|cf)\.$")

CHINGLISH_OPENERS = {
    "besides": ("4.0x more common in CN than native papers; informal", "改为 `In addition,` / `Furthermore,` / `Moreover,`"),
    "in this way": ("3.5x more common in CN than native papers", "改用分词 `thereby + -ing` 或删去"),
    "meanwhile": ("3.0x more common in CN when not temporal", "非“同时发生”时改 `In addition,` / `Additionally,`"),
    "consequently": ("2.0x more common in CN", "交替使用 `Thus,` / `Hence,` / `As a result,`"),
    "specifically": ("2.0x more common in CN", "避免每段重复，交替使用 `In particular,` 或直接展开"),
    "therefore": ("1.9x more common in CN", "交替使用 `Thus,` / `Hence,` 或因果从句"),
    "to this end": ("1.5x more common in CN", "交替使用 `To achieve this,` / `Motivated by this,`"),
}

CHINGLISH_PHRASES = [
    (r"\bwe adopt\b|\bis adopted\b", "华人组高频直译 (`adopt`, z=+8.2)", "母语作者显著偏好 `we use` / `using` / `we employ`"),
    (r"\bverify the effectiveness\b|\beffectiveness of our proposed\b", "中式实验套话 (z=+10.6)", "改为 `we show that our method improves ... by X%`"),
    (r"\bthe experimental results\b|\bexperimental results show\b", "高频中式主语 (z=+8.6)", "交替使用 `Table X shows` / `Our results show` / `We find that`"),
    (r"\bsuperiority of\b", "语气偏夸张 (z=+6.4)", "改为 `stronger performance` / `gains over baselines`"),
    (r"\bmore and more\b", "口语化直译", "改为 `increasing` / `growing`"),
    (r"\bmake an improvement\b|\bdo an experiment\b", "冗余名词化/空泛动词", "改为 `improve` / `conduct an experiment` 或 `evaluate`"),
    (r"\bwith the rapid development of\b|\bin recent years,\s+deep learning", "中文引言高频套话", "删除泛泛背景，直接切入具体任务与研究瓶颈"),
    (r"\bin order to\b", "冗长表达", "可直接精简为 `to`"),
    (r"\bdue to the fact that\b", "冗长表达", "精简为 `because`"),
    (r"\ba large number of\b|\blots of\b|\ba lot of\b", "冗长/口语", "改为 `numerous` / `many` / `extensive`"),
    (r"\bthe reason is because\b", "语法冗余", "改为 `the reason is that`"),
    (r"\bdiscuss about\b|\bemphasize on\b", "介词误用", "及物动词后不加介词：`discuss` / `emphasize`"),
]

AI_WORDS = [
    "delve", "delves", "delving", "pivotal", "intricate", "paramount", "underscore", "underscores",
    "showcase", "showcases", "showcasing", "tapestry", "holistic", "seamless", "seamlessly",
    "groundbreaking", "cutting-edge", "meticulous", "meticulously", "realm", "landscape",
    "harness", "harnessing", "testament", "game-changer", "revolutionize", "revolutionizing",
]

OVERCLAIM = [
    (r"\bprove[sd]?\b", "无严格数学定理证明时忌用 `prove`", "改用 `demonstrate` / `show` / `indicate`"),
    (r"\bcompletely solve[sd]?\b|\bperfectly\b|\balways\b|\bnever\b", "绝对化表述（Overclaim）", "改为适度弱化：`effectively mitigates` / `consistently`"),
    (r"\bsignificantly\b", "仅在做了统计显著性检验时使用", "无显著性检验时改用 `substantially` / `notably` / `markedly`"),
    (r"\bobviously\b|\bundoubtedly\b|\bclearly\b", "主观武断副词", "删去或用数据/分析直接支撑"),
]

DECORATIVE_ADVERBS = re.compile(r"\b(notably|remarkably|significantly|substantially|dramatically|considerably|importantly|crucially)\b", re.I)
PASSIVE_RE = re.compile(r"\b(is|are|was|were|be|been|being)\s+[a-z]+(ed|en|built|shown|found|done|made|seen|given|taken|used|set)\b", re.I)
CONTRACTIONS = re.compile(r"\b(don't|doesn't|didn't|can't|couldn't|won't|wouldn't|isn't|aren't|wasn't|weren't|it's|that's|we're|they're|haven't|hasn't)\b", re.I)


def strip_latex_noise(text):
    t = re.sub(r"(?<!\\)%.*", "", text)
    t = re.sub(r"\$\$.*?\$\$", " [MATH] ", t, flags=re.S)
    t = re.sub(r"\$[^$\n]+\$", "[MATH]", t)
    t = re.sub(r"\\cite[a-zA-Z]*\*?(?:\[[^\]]*\])*\{[^}]*\}", "[CITE]", t)
    t = re.sub(r"\\(?:ref|eqref|autoref|cref|Cref)\{[^}]*\}", "[REF]", t)
    return t


def split_sentences(para):
    raw, out, buf = SPLIT.split(para.strip()), [], ""
    for s in raw:
        buf = f"{buf} {s}".strip() if buf else s
        if ABBR.search(buf):
            continue
        if len(buf.split()) >= 3:
            out.append(buf)
        buf = ""
    if buf and len(buf.split()) >= 3:
        out.append(buf)
    return out


def audit(text):
    clean = strip_latex_noise(text)
    paras = [p.strip() for p in re.split(r"\n\s*\n", clean) if len(p.strip().split()) >= 8]
    all_sents = []
    findings = []

    for pi, para in enumerate(paras, 1):
        sents = split_sentences(para)
        all_sents.extend(sents)

        # Paragraph-level decorative adverb stacking
        advs = DECORATIVE_ADVERBS.findall(para)
        if len(advs) >= 2:
            findings.append(("P2", "修饰副词堆叠", f"第 {pi} 段", f"单段出现 {len(advs)} 个修饰副词 ({', '.join(advs)})", "每段 ≤ 1 个修饰副词，用具体动词和数据替代"))

        # Consecutive passives & repeated openers
        passive_run = 0
        openers = []
        for si, s in enumerate(sents, 1):
            loc = f"P{pi}.S{si}"
            words = s.split()
            low = s.lower()

            # 1. Long sentence
            if len(words) > 40:
                findings.append(("P1", "超长句", loc, f"{len(words)} 词: \"{s[:90]}...\"", "建议拆分为 2 句（目标 18–25 词/句）"))

            # 2. Chinglish openers
            for op, (why, fix) in CHINGLISH_OPENERS.items():
                if low.startswith(op + ",") or low.startswith(op + " "):
                    findings.append(("P2", "中式高频句首", loc, f"`{op}` ({why})", fix))

            # 3. Chinglish phrases
            for pat, why, fix in CHINGLISH_PHRASES:
                m = re.search(pat, s, re.I)
                if m:
                    findings.append(("P1", "中式表达/冗长", loc, f"`{m.group(0)}` — {why}", fix))

            # 4. AI-isms
            ai_hits = [w for w in AI_WORDS if re.search(rf"\b{re.escape(w)}\b", low)]
            if ai_hits:
                findings.append(("P1", "AI 腔高频词", loc, f"命中: {', '.join(sorted(set(ai_hits)))}", "替换为朴素精准的学术动词/形容词"))

            # 5. Overclaim
            for pat, why, fix in OVERCLAIM:
                m = re.search(pat, s, re.I)
                if m:
                    findings.append(("P1", "过度声称/语气", loc, f"`{m.group(0)}` — {why}", fix))

            # 6. Contractions
            cm = CONTRACTIONS.search(s)
            if cm:
                findings.append(("P0", "口语缩写", loc, f"`{cm.group(0)}`", "学术正文展开为完整形式（如 `do not`, `it is`）"))

            # 7. Consecutive passive
            if PASSIVE_RE.search(s) and not re.search(r"\bwe\s+[a-z]+", low):
                passive_run += 1
                if passive_run == 3:
                    findings.append(("P2", "被动语态连用", loc, "连续 3 句以上使用被动语态", "穿插主动语态（如 `We ...` / `Table X shows ...`）"))
            else:
                passive_run = 0

            # 8. Repeated openers
            first_word = re.sub(r"[^a-z]", "", words[0].lower())
            openers.append(first_word)
            if len(openers) >= 3 and openers[-1] == openers[-2] == openers[-3] and first_word:
                findings.append(("P2", "句首重复", loc, f"连续 3 句以 `{first_word}` 开头", "变换句式结构（如使用 `While ...`, 介词短语或分词开头）"))

    # Summary stats
    n_sents = max(1, len(all_sents))
    avg_len = sum(len(s.split()) for s in all_sents) / n_sents
    long_cnt = sum(1 for s in all_sents if len(s.split()) > 40)
    while_cnt = sum(1 for s in all_sents if s.lower().startswith("while "))

    lines = [
        "# 英文稿件自动化体检报告（基于 3,000 篇顶会语料基线）\n",
        "## 1. 整体指标",
        "| 指标 | 当前稿件 | 顶会母语基线 | 判定 |",
        "|---|---|---|---|",
        f"| 总段落 / 总句数 | {len(paras)} 段 / {len(all_sents)} 句 | — | — |",
        f"| 平均句长 | **{avg_len:.1f} 词** | 18–25 词 | {'✅ 适中' if 16 <= avg_len <= 27 else '⚠️ 偏长/偏短'} |",
        f"| 超长句 (>40 词) | **{long_cnt} 句** | 0 句 | {'✅' if long_cnt == 0 else '⚠️ 建议拆分'} |",
        f"| 句首 `While` 对比结构 | {while_cnt} 次 | ~10 次/千句 | {'✅' if while_cnt > 0 or len(all_sents) < 15 else '💡 可适当用 `While A, B` 替代机械 `However`'} |",
        f"| 检出问题总数 | **{len(findings)} 处** | — | — |\n",
    ]
    if findings:
        lines.append("## 2. 详细诊断清单")
        lines.append("| 级别 | 类别 | 位置 | 检出内容 | 修改建议 |")
        lines.append("|---|---|---|---|---|")
        order = {"P0": 0, "P1": 1, "P2": 2}
        for sev, cat, loc, detail, fix in sorted(findings, key=lambda x: order[x[0]]):
            lines.append(f"| {sev} | {cat} | {loc} | {detail} | {fix} |")
    else:
        lines.append("## 2. 详细诊断清单\n✅ 未检出明显中式模板、AI 腔或语法格式问题。")

    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser(description="Audit an English academic draft for Chinglish, AI-isms, and readability.")
    ap.add_argument("file", nargs="?")
    ap.add_argument("--text", default=None)
    args = ap.parse_args()
    if args.text:
        text = args.text
    elif args.file:
        text = Path(args.file).read_text(encoding="utf-8-sig")
    else:
        text = sys.stdin.read()
    print(audit(text))


if __name__ == "__main__":
    main()
