"""Lean Multi-Provider LLM Gateway & Academic Agent Harness.

- Live `/models` discovery using user's API key (zero stale hardcoded model lists).
- Native Anthropic `/v1/messages` + smart Claude 3rd-party relay adapter (auto-handles
  both `x-api-key` and `Authorization: Bearer` headers and `/v1` path normalization).
- OpenAI-compatible protocol covering domestic presets, international presets, local
  Ollama/vLLM, and One-API/New-API relays.
"""
from __future__ import annotations

import base64
import json
import re
import time
from typing import Any, AsyncGenerator

import httpx

from backend.config import load_settings
from backend.services.academic_engine import (
    extract_glossary,
    load_skill_context,
    retrieve_native_examples,
)
from backend.services.corpus_trainer import get_active_custom_style_guidance
from backend.services.terminology_and_search import (
    check_translation_consistency,
    match_glossary_in_text,
)


def _normalize_base(url: str) -> str:
    u = url.strip().rstrip("/")
    u = re.sub(r"/(chat/completions|messages|models)$", "", u)
    return u


def _anthropic_headers_variants(api_key: str, protocol: str) -> list[dict[str, str]]:
    """Build auth header candidates: Anthropic official uses x-api-key; 3rd-party Claude relays may expect x-api-key, Bearer, or both."""
    base = {"anthropic-version": "2023-06-01", "content-type": "application/json"}
    if protocol == "anthropic_relay":
        return [
            {**base, "x-api-key": api_key, "Authorization": f"Bearer {api_key}"},
            {**base, "x-api-key": api_key},
            {**base, "Authorization": f"Bearer {api_key}"},
        ]
    return [{**base, "x-api-key": api_key}]


def _candidate_endpoint(base_url: str, suffix: str) -> list[str]:
    b = _normalize_base(base_url)
    urls = [f"{b}{suffix}"]
    if not b.endswith("/v1") and not re.search(r"/v\d+$", b):
        urls.append(f"{b}/v1{suffix}")
    return urls


def resolve_role_provider(
    role: str = "writing",
    provider_id: str | None = None,
    model: str | None = None,
) -> tuple[dict[str, Any] | None, str]:
    cfg = load_settings()
    providers = {p["id"]: p for p in cfg.get("providers", [])}
    route = cfg.get("routing", {}).get(role, {})
    pid = provider_id or route.get("provider_id")
    prov = providers.get(pid) if pid else None

    if prov and not prov.get("api_key") and prov.get("region") != "local":
        for p in cfg.get("providers", []):
            if p.get("api_key") and p.get("region") != "local":
                prov = p
                model = model or p.get("default_model") or (p.get("models") or [""])[0]
                break

    if not prov:
        return None, model or ""
    chosen_model = model or route.get("model") or prov.get("default_model") or (prov.get("models") or [""])[0]
    return prov, chosen_model


async def fetch_provider_models(base_url: str, api_key: str, protocol: str = "openai") -> dict[str, Any]:
    """Query the provider's live `/models` endpoint using the supplied API key."""
    t0 = time.perf_counter()
    if not base_url.strip():
        return {"ok": False, "latency_ms": 0, "error": "请先填写 Base URL", "models": []}

    endpoints = _candidate_endpoint(base_url, "/models")
    header_sets = (
        _anthropic_headers_variants(api_key, protocol)
        if protocol in ("anthropic", "anthropic_relay")
        else ([{"Authorization": f"Bearer {api_key}"}] if api_key else [{}])
    )

    last_err = "无法连接到接口"
    try:
        async with httpx.AsyncClient(timeout=14.0, follow_redirects=True) as client:
            for ep in endpoints:
                for hdrs in header_sets:
                    try:
                        r = await client.get(ep, headers=hdrs)
                        ms = int((time.perf_counter() - t0) * 1000)
                        if r.status_code == 200:
                            data = r.json()
                            raw = data.get("data") or data.get("models") or (data if isinstance(data, list) else [])
                            models = sorted({m["id"] if isinstance(m, dict) and "id" in m else str(m) for m in raw if m})
                            return {"ok": True, "latency_ms": ms, "models": models[:200], "count": len(models)}
                        last_err = f"HTTP {r.status_code}: {r.text[:180]}"
                        if r.status_code in (401, 403):
                            continue  # Try alternate auth header on 3rd-party relays
                    except Exception as e:
                        last_err = str(e)
    except Exception as e:
        last_err = str(e)

    return {"ok": False, "latency_ms": int((time.perf_counter() - t0) * 1000), "error": last_err, "models": []}


def _split_data_url(uri: str) -> tuple[str, str]:
    m = re.match(r"^data:(image/[a-zA-Z0-9.+-]+);base64,(.+)$", uri.strip(), re.S)
    if m:
        return m.group(1), m.group(2)
    return "image/png", uri.split(",")[-1].strip()


def _format_messages_openai(system_prompt: str, messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = [{"role": "system", "content": system_prompt}]
    for msg in messages:
        role = msg.get("role", "user")
        text = str(msg.get("content") or "")
        images = msg.get("images") or []
        if images and role == "user":
            blocks: list[dict[str, Any]] = [{"type": "text", "text": text or "请查看这张图片"}]
            for img in images:
                url = img if str(img).startswith("data:") or str(img).startswith("http") else f"data:image/png;base64,{img}"
                blocks.append({"type": "image_url", "image_url": {"url": url}})
            out.append({"role": role, "content": blocks})
        else:
            out.append({"role": role, "content": text})
    return out


def _format_messages_anthropic(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for msg in messages:
        role = msg.get("role", "user")
        if role not in ("user", "assistant"):
            continue
        text = str(msg.get("content") or "")
        images = msg.get("images") or []
        if images and role == "user":
            blocks: list[dict[str, Any]] = []
            for img in images:
                mime, b64 = _split_data_url(str(img))
                blocks.append({"type": "image", "source": {"type": "base64", "media_type": mime, "data": b64}})
            blocks.append({"type": "text", "text": text or "请查看这张图片"})
            out.append({"role": role, "content": blocks})
        else:
            out.append({"role": role, "content": text})
    return out


async def stream_multimodal_messages(
    prov: dict[str, Any],
    model: str,
    system_prompt: str,
    messages: list[dict[str, Any]],
    temperature: float = 0.25,
) -> AsyncGenerator[str, None]:
    """Stream tokens for text or multimodal (text + images) turns across OpenAI, Anthropic, and Claude 3rd-party relays."""
    protocol = prov.get("protocol", "openai")
    base_url = _normalize_base(prov.get("base_url", ""))
    api_key = prov.get("api_key", "")
    if not base_url:
        raise RuntimeError("Base URL 为空，请在 API 设置中填写服务地址。")
    if not model:
        raise RuntimeError("尚未选择模型，请点击「拉取模型」后选择具体模型 ID。")

    async with httpx.AsyncClient(timeout=120.0, follow_redirects=True) as client:
        if protocol in ("anthropic", "anthropic_relay"):
            payload = {
                "model": model,
                "max_tokens": 4096,
                "temperature": temperature,
                "system": system_prompt,
                "messages": _format_messages_anthropic(messages),
                "stream": True,
            }
            endpoints = _candidate_endpoint(base_url, "/messages")
            header_sets = _anthropic_headers_variants(api_key, protocol)
            last_err = ""
            for ep in endpoints:
                for hdrs in header_sets:
                    async with client.stream("POST", ep, headers=hdrs, json=payload) as resp:
                        if resp.status_code in (401, 403, 404) and protocol == "anthropic_relay":
                            body = await resp.aread()
                            last_err = f"HTTP {resp.status_code}: {body.decode('utf-8', 'ignore')[:220]}"
                            continue
                        if resp.status_code >= 400:
                            body = await resp.aread()
                            raise RuntimeError(f"Claude API HTTP {resp.status_code}: {body.decode('utf-8', 'ignore')[:260]}")
                        async for line in resp.aiter_lines():
                            if not line.startswith("data:"):
                                continue
                            raw = line[5:].strip()
                            if not raw or raw == "[DONE]":
                                continue
                            try:
                                evt = json.loads(raw)
                                if evt.get("type") == "content_block_delta":
                                    delta = evt.get("delta", {}).get("text", "")
                                    if delta:
                                        yield delta
                                elif "choices" in evt:
                                    delta = (evt["choices"][0].get("delta") or {}).get("content") or ""
                                    if delta:
                                        yield delta
                            except Exception:
                                continue
                        return
            raise RuntimeError(f"Claude 第三方中转连接失败：{last_err}")

        # OpenAI-compatible protocol (supports vision `image_url` blocks natively)
        headers = {"content-type": "application/json"}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        payload = {
            "model": model,
            "temperature": temperature,
            "messages": _format_messages_openai(system_prompt, messages),
            "stream": True,
        }
        async with client.stream("POST", f"{base_url}/chat/completions", headers=headers, json=payload) as resp:
            if resp.status_code >= 400:
                body = await resp.aread()
                raise RuntimeError(f"API HTTP {resp.status_code}: {body.decode('utf-8', 'ignore')[:260]}")
            async for line in resp.aiter_lines():
                if not line.startswith("data:"):
                    continue
                raw = line[5:].strip()
                if not raw or raw == "[DONE]":
                    continue
                try:
                    evt = json.loads(raw)
                    choices = evt.get("choices") or []
                    if choices:
                        delta = choices[0].get("delta", {}).get("content") or ""
                        if delta:
                            yield delta
                except Exception:
                    continue


async def stream_llm_completion(
    prov: dict[str, Any],
    model: str,
    system_prompt: str,
    user_prompt: str,
    temperature: float = 0.25,
) -> AsyncGenerator[str, None]:
    """Single-turn streaming convenience wrapper over `stream_multimodal_messages`."""
    async for delta in stream_multimodal_messages(
        prov, model, system_prompt, [{"role": "user", "content": user_prompt}], temperature=temperature
    ):
        yield delta


async def complete_llm_text(
    system_prompt: str,
    user_prompt: str,
    role: str = "writing",
    temperature: float = 0.2,
) -> str | None:
    prov, chosen_model = resolve_role_provider(role)
    if not prov or not chosen_model or (not prov.get("api_key") and prov.get("region") != "local"):
        return None
    parts: list[str] = []
    async for tok in stream_llm_completion(prov, chosen_model, system_prompt, user_prompt, temperature=temperature):
        parts.append(tok)
    return "".join(parts)


async def generate_ai_image_b64(prompt: str, size: str = "512x512") -> dict[str, Any]:
    prov, model = resolve_role_provider("image")
    if not prov or not prov.get("api_key") or not model:
        return {"ok": False, "reason": "no_image_api_key"}
    url = _normalize_base(prov["base_url"]) + "/images/generations"
    headers = {"Authorization": f"Bearer {prov['api_key']}", "Content-Type": "application/json"}
    payload = {"model": model, "prompt": prompt, "size": size, "n": 1, "response_format": "b64_json"}
    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            r = await client.post(url, headers=headers, json=payload)
            if r.status_code >= 400:
                return {"ok": False, "reason": f"HTTP {r.status_code}: {r.text[:180]}"}
            item = (r.json().get("data") or [{}])[0]
            if item.get("b64_json"):
                return {"ok": True, "b64": item["b64_json"], "mime": "image/png"}
            if item.get("url"):
                img_r = await client.get(item["url"])
                return {"ok": True, "b64": base64.b64encode(img_r.content).decode(), "mime": "image/png"}
            return {"ok": False, "reason": "图像接口未返回内容"}
    except Exception as e:
        return {"ok": False, "reason": str(e)}


# ---------- Structured Edit Extraction & Local Deterministic Preview ----------
def _extract_edit_cards(markdown_text: str) -> list[dict[str, Any]]:
    m = re.search(r"```json_edits\s*([\s\S]*?)```", markdown_text)
    if m:
        try:
            items = json.loads(m.group(1))
            if isinstance(items, list):
                return [
                    {
                        "id": f"edit-{i}",
                        "original": str(it["original"]).strip(),
                        "revised": str(it["revised"]).strip(),
                        "tag": str(it.get("tag", "Style")),
                        "reason": str(it.get("reason", "")),
                        "status": "pending",
                    }
                    for i, it in enumerate(items, 1)
                    if it.get("original") and it.get("revised") and it["original"] != it["revised"]
                ]
        except Exception:
            pass
    return []


async def stream_academic_agent(
    mode: str,
    text: str,
    instruction: str = "",
    section: str = "introduction",
    venue: str = "CVPR / ICCV",
    provider_id: str | None = None,
    model: str | None = None,
) -> AsyncGenerator[dict[str, Any], None]:
    """Live LLM academic agent loop with gated retrieval, locked multimodal glossary, and 2-step fluency smoothing."""
    prov, chosen_model = resolve_role_provider("writing", provider_id, model)
    has_live_llm = bool(prov and chosen_model and (prov.get("api_key") or prov.get("region") == "local"))

    if not has_live_llm:
        yield {
            "type": "need_api_key",
            "message": "请先在「配置 API」中填写模型密钥并拉取选择具体模型。所有论文诊断、润色、翻译与审稿均由大模型通读全文后实时生成，不提供离线猜测。",
        }
        return

    cfg = load_settings()
    prefs = cfg.get("preferences", {})
    style_strength = str(prefs.get("style_strength") or "balanced")  # natural | balanced | venue_strict
    first_mention_en = bool(prefs.get("first_mention_en", True))

    # 1. Strict Language Isolation & Similarity Gating: NEVER inject English vector exemplars into `en2zh`!
    exemplar_block = ""
    if mode != "en2zh" and style_strength != "natural":
        k_top = 3 if style_strength == "balanced" else 5
        yield {"type": "tool_start", "tool": "retrieve.py", "label": f"正在按阈值门控检索 {venue} 同章节母语例句..."}
        corpus_res = retrieve_native_examples(" ".join(text.split()[:80]), section=section if section != "all" else None, group="native", k=k_top)
        gated = [r for r in corpus_res["results"] if float(r.get("score", 0)) >= 0.18][:k_top]
        exemplar_block = "\n".join(
            f"- [{r['venue']} {r['year']} | {r['section']}] {r['text']}" for r in gated
        )
        yield {
            "type": "tool_result",
            "tool": "retrieve.py",
            "summary": f"通过相似度门控精选 {len(gated)} 条同域例句（仅作学术动词与语域参考，不生搬硬套句法）",
        }

    # 2. Multimodal DL Glossary Lock + Skill Rules
    yield {"type": "tool_start", "tool": "glossary.py", "label": "锁定多模态深度学习术语表与学科写作规范..."}
    gloss = extract_glossary(text)
    locked_terms = match_glossary_in_text(text)
    skill_rules = load_skill_context(mode, section=section if section != "all" else "introduction")
    yield {
        "type": "tool_result",
        "tool": "glossary.py",
        "summary": f"已锁定 {len(gloss['acronyms'])} 个缩写 · {len(locked_terms)} 条多模态术语译法",
    }

    locked_term_block = "\n".join(
        f"- {it['en']} => {it['zh']}" + ("（建议保留英文）" if it.get("keep_en") else "")
        for it in locked_terms[:28]
    )
    custom_style = get_active_custom_style_guidance()

    system_prompt = (
        f"You are PaperHarness, an elite multimodal deep learning co-author targeting {venue}.\n"
        "Invariants: NEVER change numbers, metrics, datasets, model names, \\cite{}, \\ref{}, or math formulas; NEVER fabricate claims/refs.\n"
        "Fluency rule: Prioritize natural paragraph flow and logical cohesion over rigid sentence-by-sentence copying.\n"
        "For Chinese output, enforce full-width Chinese punctuation with zero redundant spaces.\n"
        + ("For Chinese translation, bracket the original English term on its first appearance when helpful (e.g., 交叉注意力（cross-attention）).\n" if first_mention_en and mode == "en2zh" else "")
        + (f"\nLocked Domain Glossary (MUST honor exact preferred translations):\n{locked_term_block}\n" if locked_term_block else "")
        + (f"\nActive Custom Style Baselines:\n{custom_style}\n" if custom_style else "")
        + f"\n{skill_rules}"
    )

    directives = {
        "polish": 'Read the manuscript thoroughly first. Give a concise Chinese editorial diagnosis grounded in the actual text, then output a ```json_edits``` JSON array: [{"original":"<exact verbatim substring>","revised":"<polished sentence>","tag":"表达|逻辑|防过度声称|简洁|语法|术语","reason":"<中文具体理由>"}].',
        "zh2en": 'Translate the Chinese draft into native top-venue English by rebuilding sentence syntax naturally (zero translationese). Output polished English + ```json_edits``` mapping source paragraphs to English.',
        "en2zh": "Translate the English paper into natural, publication-grade Chinese without translationese, preserving all LaTeX math, citations, and locked domain terms.",
        "mimic": "Align rhetoric, transitions, and LaTeX conventions to the target venue style without copying content. Output a 6-dimension blueprint + ```json_edits```.",
        "review": "Act as a strict Area Chair for the target venue. Read the paper carefully and output a 5-dimension Scorecard, Major Concerns, Claim Calibration flags, and P0/P1/P2 Action Items in Chinese.",
    }

    # 3. Two-Step Fluency Smoothing for Translation (`en2zh` / `zh2en`): Draft -> De-Translationese Smooth -> Consistency Audit
    if mode in ("en2zh", "zh2en"):
        yield {"type": "tool_start", "tool": "step1_draft", "label": f"第 1/2 步：由 {prov['name']} ({chosen_model}) 忠实直译并锁定全部术语与公式..."}
        draft_prompt = (
            f"Step 1 (Faithful Terminology-Locked Draft): {directives[mode]}\n"
            + (f"Author instruction: {instruction}\n" if instruction.strip() else "")
            + (f"\nHigh-relevance verb/tone exemplars (reference only, never stitch awkwardly):\n{exemplar_block}\n" if exemplar_block else "")
            + f"\nSource Manuscript:\n\"\"\"\n{text}\n\"\"\""
        )
        draft_parts: list[str] = []
        try:
            async for delta in stream_llm_completion(prov, chosen_model, system_prompt, draft_prompt, temperature=0.2):
                draft_parts.append(delta)
        except Exception as e:
            yield {"type": "error", "message": f"{prov['name']} ({chosen_model}) 调用失败：{e}"}
            return
        draft_text = "".join(draft_parts).strip()
        yield {"type": "tool_result", "tool": "step1_draft", "summary": "忠实初译完成，进入第 2 步脱稿顺句与去翻译腔"}

        yield {"type": "tool_start", "tool": "step2_smooth", "label": "第 2/2 步：脱稿顺句消除翻译腔、衔接段落并核对术语一致..."}
        smooth_sys = (
            "You are a senior native academic editor specializing in de-translationese smoothing.\n"
            "Rewrite the draft below so it reads effortlessly like a native top-venue paper while keeping 100% factual accuracy, "
            "all LaTeX equations/citations/numbers, and every locked glossary term intact.\n"
            + ("Break up stacked Chinese '的/进行/被' clauses, ensure smooth topic continuity across adjacent sentences, and use crisp full-width Chinese punctuation.\n" if mode == "en2zh" else "Rebuild stiff Chinese-ordered English clauses into crisp, active academic English and include a ```json_edits``` block mapping source paragraphs to final English.\n")
            + (f"Locked Glossary (DO NOT alter these translations):\n{locked_term_block}\n" if locked_term_block else "")
        )
        smooth_parts: list[str] = []
        try:
            async for delta in stream_llm_completion(prov, chosen_model, smooth_sys, f"Draft to smooth:\n\"\"\"\n{draft_text}\n\"\"\"", temperature=0.22):
                smooth_parts.append(delta)
                yield {"type": "token", "text": delta}
        except Exception as e:
            yield {"type": "error", "message": f"顺句润色阶段失败：{e}"}
            return

        final_out = "".join(smooth_parts)
        if mode == "en2zh" and locked_terms:
            warns = check_translation_consistency(text, final_out)
            yield {
                "type": "tool_result",
                "tool": "step2_smooth",
                "summary": "顺句完成 · 全部锁定术语一致性校验通过" if not warns else f"顺句完成 · 检出 {len(warns)} 处术语提醒：" + "；".join(f"{w['en']}→{w['expected']}" for w in warns[:4]),
            }
        else:
            yield {"type": "tool_result", "tool": "step2_smooth", "summary": "脱稿顺句完成，已消除翻译腔"}

        edits = _extract_edit_cards(final_out)
        if edits:
            yield {"type": "edits", "edits": edits}
        yield {"type": "done", "provider": prov["name"], "model": chosen_model}
        return

    user_prompt = (
        f"Task: {directives.get(mode, directives['polish'])}\n"
        + (f"Author instruction: {instruction}\n" if instruction.strip() else "")
        + (f"\nStyle exemplars (verb/tone reference ONLY — never force awkward phrasing):\n{exemplar_block}\n" if exemplar_block else "")
        + f"\nManuscript:\n\"\"\"\n{text}\n\"\"\""
    )

    yield {"type": "tool_start", "tool": prov["name"], "label": f"正在由 {prov['name']} ({chosen_model}) 通读论文并流式分析..."}
    parts: list[str] = []
    try:
        async for delta in stream_llm_completion(prov, chosen_model, system_prompt, user_prompt):
            parts.append(delta)
            yield {"type": "token", "text": delta}
    except Exception as e:
        yield {"type": "error", "message": f"{prov['name']} ({chosen_model}) 调用失败：{e}"}
        return

    edits = _extract_edit_cards("".join(parts))
    if edits:
        yield {"type": "edits", "edits": edits}
    yield {"type": "done", "provider": prov["name"], "model": chosen_model}
