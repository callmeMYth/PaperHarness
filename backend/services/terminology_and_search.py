"""Multimodal Deep Learning Glossary, Multi-Provider Web Search & Translation Consistency Audit.

Web Search supports:
  - `builtin_free` (Default, zero API key required): Bing Web/Academic HTML + arXiv Atom API + Wikipedia ZH
  - `bocha`: Bocha AI Search API (fast in China)
  - `tavily`: Tavily Search API
  - `serper`: Serper Google Search API
"""
from __future__ import annotations

import json
import re
import urllib.parse
import xml.etree.ElementTree as ET
from typing import Any

import httpx
from bs4 import BeautifulSoup

from backend.config import DATA_DIR, load_settings

USER_GLOSSARY_FILE = DATA_DIR / "user_glossary.json"

# Default Multimodal Deep Learning Glossary (en -> zh, keep_en, note)
DEFAULT_MULTIMODAL_GLOSSARY: list[dict[str, Any]] = [
    {"en": "multimodal", "zh": "多模态", "keep_en": False, "note": "核心领域词"},
    {"en": "vision-language model", "zh": "视觉-语言模型", "keep_en": False, "note": "缩写保留 VLM"},
    {"en": "large language model", "zh": "大语言模型", "keep_en": False, "note": "缩写保留 LLM"},
    {"en": "token", "zh": "词元（或保留 Token）", "keep_en": True, "note": "多模态视觉/文本 Token 惯例常保留英文"},
    {"en": "token pruning", "zh": "Token 剪枝", "keep_en": False, "note": "视觉冗余裁剪"},
    {"en": "token merging", "zh": "Token 合并", "keep_en": False, "note": "语义聚合"},
    {"en": "patch", "zh": "图像块（Patch）", "keep_en": False, "note": "ViT 切块"},
    {"en": "patchify", "zh": "图像分块编码", "keep_en": False, "note": "切块映射"},
    {"en": "cross-attention", "zh": "交叉注意力", "keep_en": False, "note": "跨模态交互"},
    {"en": "self-attention", "zh": "自注意力", "keep_en": False, "note": "序列内部建模"},
    {"en": "multi-head attention", "zh": "多头注意力", "keep_en": False, "note": "MHA"},
    {"en": "feature fusion", "zh": "特征融合", "keep_en": False, "note": "多源融合"},
    {"en": "alignment", "zh": "对齐", "keep_en": False, "note": "跨模态语义对齐"},
    {"en": "contrastive learning", "zh": "对比学习", "keep_en": False, "note": "CLIP 等范式"},
    {"en": "grounding", "zh": "视觉定位 / 语义锚定", "keep_en": False, "note": "Visual Grounding"},
    {"en": "hallucination", "zh": "幻觉", "keep_en": False, "note": "大模型幻觉"},
    {"en": "backbone", "zh": "主干网络", "keep_en": False, "note": "视觉/语言主干"},
    {"en": "projector", "zh": "投影层 / 模态映射器", "keep_en": False, "note": "视觉到语言投影"},
    {"en": "adapter", "zh": "适配器（Adapter）", "keep_en": False, "note": "参数高效微调"},
    {"en": "LoRA", "zh": "LoRA", "keep_en": True, "note": "惯例保留英文"},
    {"en": "KV Cache", "zh": "KV Cache（键值缓存）", "keep_en": True, "note": "推理缓存"},
    {"en": "Mixture of Experts", "zh": "混合专家模型（MoE）", "keep_en": False, "note": "稀疏路由架构"},
    {"en": "router", "zh": "路由模块", "keep_en": False, "note": "门控/专家路由"},
    {"en": "gating", "zh": "门控机制", "keep_en": False, "note": "动态加权"},
    {"en": "residual connection", "zh": "残差连接", "keep_en": False, "note": "跳连"},
    {"en": "embedding", "zh": "嵌入表示", "keep_en": False, "note": "向量映射"},
    {"en": "latent space", "zh": "隐空间 / 潜空间", "keep_en": False, "note": "扩散/自编码"},
    {"en": "diffusion model", "zh": "扩散模型", "keep_en": False, "note": "生成范式"},
    {"en": "flow matching", "zh": "流匹配", "keep_en": False, "note": "连续归一化流生成"},
    {"en": "zero-shot", "zh": "零样本", "keep_en": False, "note": "无需微调泛化"},
    {"en": "few-shot", "zh": "少样本", "keep_en": False, "note": "少量示例"},
    {"en": "in-context learning", "zh": "上下文学习", "keep_en": False, "note": "ICL"},
    {"en": "instruction tuning", "zh": "指令微调", "keep_en": False, "note": "SFT"},
    {"en": "reinforcement learning", "zh": "强化学习", "keep_en": False, "note": "RLHF/GRPO"},
    {"en": "ablation study", "zh": "消融实验", "keep_en": False, "note": "模块有效性验证"},
    {"en": "baseline", "zh": "基线方法", "keep_en": False, "note": "对照基准"},
    {"en": "benchmark", "zh": "基准测试集", "keep_en": False, "note": "评测集"},
    {"en": "generalization", "zh": "泛化能力", "keep_en": False, "note": "域外泛化"},
    {"en": "robustness", "zh": "鲁棒性（统计/农工检测建议改用：稳健性）", "keep_en": False, "note": "可按期刊偏好点击修改"},
    {"en": "saliency", "zh": "显著性", "keep_en": False, "note": "视觉重要度"},
    {"en": "inductive bias", "zh": "归纳偏置", "keep_en": False, "note": "结构先验"},
    {"en": "throughput", "zh": "吞吐量", "keep_en": False, "note": "推理效率"},
    {"en": "latency", "zh": "推理延迟", "keep_en": False, "note": "时延"},
    {"en": "FLOPs", "zh": "FLOPs（浮点运算量）", "keep_en": True, "note": "计算复杂度"},
]


def load_glossary() -> list[dict[str, Any]]:
    """Merge built-in multimodal DL defaults with user's local overrides."""
    base = {it["en"].lower(): dict(it) for it in DEFAULT_MULTIMODAL_GLOSSARY}
    if USER_GLOSSARY_FILE.exists():
        try:
            saved = json.loads(USER_GLOSSARY_FILE.read_text(encoding="utf-8"))
            if isinstance(saved, list):
                for it in saved:
                    if it.get("en"):
                        base[str(it["en"]).lower()] = {
                            "en": str(it["en"]).strip(),
                            "zh": str(it.get("zh", "")).strip(),
                            "keep_en": bool(it.get("keep_en", False)),
                            "note": str(it.get("note", "")).strip(),
                            "custom": True,
                        }
        except Exception:
            pass
    return sorted(base.values(), key=lambda x: (0 if x.get("custom") else 1, x["en"].lower()))


def upsert_glossary_term(en: str, zh: str, keep_en: bool = False, note: str = "") -> list[dict[str, Any]]:
    en_clean = en.strip()
    if not en_clean:
        return load_glossary()
    custom_list: list[dict[str, Any]] = []
    if USER_GLOSSARY_FILE.exists():
        try:
            custom_list = json.loads(USER_GLOSSARY_FILE.read_text(encoding="utf-8"))
        except Exception:
            custom_list = []
    custom_list = [x for x in custom_list if str(x.get("en", "")).lower() != en_clean.lower()]
    custom_list.insert(0, {"en": en_clean, "zh": zh.strip(), "keep_en": keep_en, "note": note.strip(), "custom": True})
    USER_GLOSSARY_FILE.write_text(json.dumps(custom_list, ensure_ascii=False, indent=2), encoding="utf-8")
    return load_glossary()


def delete_glossary_term(en: str) -> list[dict[str, Any]]:
    if USER_GLOSSARY_FILE.exists():
        try:
            cur = json.loads(USER_GLOSSARY_FILE.read_text(encoding="utf-8"))
            cur = [x for x in cur if str(x.get("en", "")).lower() != en.strip().lower()]
            USER_GLOSSARY_FILE.write_text(json.dumps(cur, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception:
            pass
    return load_glossary()


def match_glossary_in_text(text: str) -> list[dict[str, Any]]:
    low = text.lower()
    hits = []
    for item in load_glossary():
        term = item["en"].lower()
        if re.search(rf"(?<![a-z0-9]){re.escape(term)}(?![a-z0-9])", low):
            hits.append(item)
    return hits


def check_translation_consistency(source_en: str, translated_zh: str) -> list[dict[str, Any]]:
    """Post-check translated Chinese against matched locked glossary entries."""
    warnings: list[dict[str, Any]] = []
    for item in match_glossary_in_text(source_en):
        zh_core = re.split(r"[（(/]", item["zh"])[0].strip()
        if not zh_core:
            continue
        if item.get("keep_en"):
            if item["en"].lower() not in translated_zh.lower() and zh_core not in translated_zh:
                warnings.append({"en": item["en"], "expected": item["zh"], "issue": "未检出锁定术语（建议保留英文或采用词表译法）"})
        else:
            if zh_core not in translated_zh:
                warnings.append({"en": item["en"], "expected": item["zh"], "issue": f"译文未采用锁定译法「{zh_core}」"})
    return warnings


# ---------- Multi-Provider Web & Academic Search (Zero-Key Built-in + Custom API Keys) ----------
async def _search_arxiv(query: str, max_results: int = 3) -> list[dict[str, str]]:
    url = f"https://export.arxiv.org/api/query?search_query=all:{urllib.parse.quote(query)}&start=0&max_results={max_results}"
    try:
        async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
            r = await client.get(url)
            if r.status_code != 200:
                return []
            root = ET.fromstring(r.text)
            ns = {"a": "http://www.w3.org/2005/Atom"}
            out = []
            for entry in root.findall("a:entry", ns):
                title = re.sub(r"\s+", " ", (entry.findtext("a:title", "", ns) or "")).strip()
                summ = re.sub(r"\s+", " ", (entry.findtext("a:summary", "", ns) or "")).strip()[:220]
                link = (entry.findtext("a:id", "", ns) or "").strip()
                if title:
                    out.append({"title": title, "snippet": summ, "url": link, "source": "arXiv"})
            return out
    except Exception:
        return []


async def _search_bing_free(query: str, max_results: int = 5) -> list[dict[str, str]]:
    url = f"https://cn.bing.com/search?q={urllib.parse.quote(query)}&mkt=zh-CN"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    }
    try:
        async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
            r = await client.get(url, headers=headers)
            if r.status_code != 200:
                return []
            soup = BeautifulSoup(r.text, "html.parser")
            out = []
            for li in soup.select("li.b_algo"):
                if "b_ad" in (li.get("class") or []) or li.select_one(".b_adSlug"):
                    continue
                a = li.select_one("h2 a")
                p = li.select_one("p") or li.select_one(".b_caption")
                if a:
                    title = a.get_text(" ", strip=True)
                    href = str(a.get("href", ""))
                    if not title or "bing.com/aclick" in href:
                        continue
                    out.append({
                        "title": title,
                        "snippet": (p.get_text(" ", strip=True) if p else "")[:260],
                        "url": href,
                        "source": "Bing",
                    })
                    if len(out) >= max_results:
                        break
            return out
    except Exception:
        return []


async def web_search(query: str, max_results: int = 5, academic: bool = True) -> dict[str, Any]:
    """Execute live web/academic search using configured provider (or built-in zero-key search)."""
    cfg = load_settings()
    scfg = cfg.get("search", {})
    provider = str(scfg.get("provider") or "builtin_free")
    api_key = str(scfg.get("api_key") or "").strip()

    results: list[dict[str, str]] = []
    used_provider = provider

    if provider == "bocha" and api_key:
        try:
            async with httpx.AsyncClient(timeout=12.0) as client:
                r = await client.post(
                    "https://api.bochaai.com/v1/web-search",
                    headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                    json={"query": query, "count": max_results, "summary": True},
                )
                if r.status_code == 200:
                    for it in ((r.json().get("data") or {}).get("webPages") or {}).get("value") or []:
                        results.append({"title": it.get("name", ""), "snippet": (it.get("summary") or it.get("snippet") or "")[:260], "url": it.get("url", ""), "source": "博查 AI"})
        except Exception:
            pass
    elif provider == "tavily" and api_key:
        try:
            async with httpx.AsyncClient(timeout=12.0) as client:
                r = await client.post(
                    "https://api.tavily.com/search",
                    json={"api_key": api_key, "query": query, "max_results": max_results, "search_depth": "basic"},
                )
                if r.status_code == 200:
                    for it in r.json().get("results") or []:
                        results.append({"title": it.get("title", ""), "snippet": (it.get("content") or "")[:260], "url": it.get("url", ""), "source": "Tavily"})
        except Exception:
            pass
    elif provider == "serper" and api_key:
        try:
            async with httpx.AsyncClient(timeout=12.0) as client:
                r = await client.post(
                    "https://google.serper.dev/search",
                    headers={"X-API-KEY": api_key, "Content-Type": "application/json"},
                    json={"q": query, "num": max_results, "hl": "zh-cn"},
                )
                if r.status_code == 200:
                    for it in r.json().get("organic") or []:
                        results.append({"title": it.get("title", ""), "snippet": (it.get("snippet") or "")[:260], "url": it.get("link", ""), "source": "Serper"})
        except Exception:
            pass

    # Fallback or default: Built-in Zero-Key Search (arXiv academic + Bing CN)
    if not results:
        used_provider = "builtin_free"
        has_cjk = bool(re.search(r"[\u4e00-\u9fff]", query))
        if academic and not has_cjk:
            ax = await _search_arxiv(query, max_results=min(3, max_results))
            results.extend(ax)
        if len(results) < max_results:
            bing = await _search_bing_free(query, max_results=max_results - len(results))
            results.extend(bing)
        if academic and has_cjk and len(results) < max_results:
            ax = await _search_arxiv(query, max_results=max(2, max_results - len(results)))
            results.extend(ax)

    return {"ok": True, "provider": used_provider, "query": query, "results": results[:max_results]}


async def lookup_term_online(term: str, domain: str = "多模态深度学习") -> dict[str, Any]:
    """Search online for authoritative Chinese translations of a new academic term + LLM synthesis."""
    from backend.services.llm_gateway import complete_llm_text

    q = f'"{term}" 中文 翻译 术语 {domain}'
    s_res = await web_search(q, max_results=5, academic=True)
    evidence = "\n".join(f"- [{r['source']}] {r['title']}: {r['snippet']}" for r in s_res["results"])

    candidates: list[dict[str, Any]] = []
    if evidence or term:
        sys_p = (
            f"你是资深{domain}学术审稿人与科技翻译专家。请根据联网检索证据，为英文学术术语给出 2-3 个最地道、符合国内核心期刊与顶会中文社区习惯的译法候选。\n"
            '仅返回合法 JSON：{"term":"...","keep_en_recommended":false,"candidates":[{"zh":"推荐中文译法","scene":"适用子领域/说明","recommended":true}],"note":"一句话解释首次出现是否建议括注原文"}'
        )
        raw = await complete_llm_text(sys_p, f"待查术语：{term}\n领域：{domain}\n联网检索证据：\n{evidence or '（无直接网页命中，请基于最新多模态深度学习文献惯例给出建议）'}", temperature=0.15)
        if raw:
            m = re.search(r"\{[\s\S]*\}", raw)
            if m:
                try:
                    parsed = json.loads(m.group(0))
                    return {
                        "ok": True,
                        "term": term,
                        "search_provider": s_res["provider"],
                        "sources": s_res["results"][:4],
                        "keep_en_recommended": bool(parsed.get("keep_en_recommended", False)),
                        "candidates": parsed.get("candidates") or [],
                        "note": str(parsed.get("note") or ""),
                    }
                except Exception:
                    pass

    return {
        "ok": True,
        "term": term,
        "search_provider": s_res["provider"],
        "sources": s_res["results"][:4],
        "keep_en_recommended": False,
        "candidates": candidates,
        "note": "已返回联网搜索证据（配置写作模型 API Key 后可自动提炼标准候选译法）。",
    }
