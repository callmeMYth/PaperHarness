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
    """Always prefer `/v1<suffix>` first when base_url lacks a version segment (prevents hitting SPA HTML pages at `/messages`)."""
    b = _normalize_base(base_url)
    if not b.endswith("/v1") and not re.search(r"/v\d+$", b):
        return [f"{b}/v1{suffix}", f"{b}{suffix}"]
    return [f"{b}{suffix}"]


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
                            ctype = (r.headers.get("content-type") or "").lower()
                            if "text/html" in ctype or r.text.lstrip().startswith("<"):
                                last_err = f"接口返回了网页 HTML ({ep})，请检查 Base URL"
                                continue
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


def _format_messages_gemini(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for msg in messages:
        role = "model" if msg.get("role") == "assistant" else "user"
        text = str(msg.get("content") or "")
        images = msg.get("images") or []
        parts: list[dict[str, Any]] = []
        if images and role == "user":
            for img in images:
                mime, b64 = _split_data_url(str(img))
                parts.append({"inlineData": {"mimeType": mime, "data": b64}})
        if text or not parts:
            parts.append({"text": text or "请查看这张图片"})
        out.append({"role": role, "parts": parts})
    return out


def _extract_events_from_json_chunk(evt: dict[str, Any]) -> list[dict[str, str]]:
    """Extract normalized `thinking` and `text` chunks from Anthropic SSE, OpenAI SSE, Gemini v1beta SSE, or non-stream JSON."""
    out: list[dict[str, str]] = []
    # 1. Gemini native v1beta (`candidates[].content.parts[]` with `thought: true`)
    cands = evt.get("candidates")
    if isinstance(cands, list) and cands:
        parts = ((cands[0] or {}).get("content") or {}).get("parts") or []
        for part in parts:
            if not isinstance(part, dict):
                continue
            ptxt = part.get("text") or ""
            if not ptxt:
                continue
            if part.get("thought") is True:
                out.append({"kind": "thinking", "text": str(ptxt)})
            else:
                out.append({"kind": "text", "text": str(ptxt)})
        return out
    etype = evt.get("type")
    if etype == "content_block_delta":
        d = evt.get("delta") or {}
        th = d.get("thinking") or d.get("reasoning") or ""
        tx = d.get("text") or ""
        if th:
            out.append({"kind": "thinking", "text": str(th)})
        if tx:
            out.append({"kind": "text", "text": str(tx)})
        return out
    if etype == "message" or (isinstance(evt.get("content"), list) and not evt.get("choices")):
        for blk in evt.get("content") or []:
            if not isinstance(blk, dict):
                continue
            if blk.get("type") == "thinking" and blk.get("thinking"):
                out.append({"kind": "thinking", "text": str(blk["thinking"])})
            elif blk.get("type") == "text" and blk.get("text"):
                out.append({"kind": "text", "text": str(blk["text"])})
        return out
    choices = evt.get("choices") or []
    if choices:
        c0 = choices[0] or {}
        delta = c0.get("delta") or c0.get("message") or {}
        th = delta.get("reasoning_content") or delta.get("reasoning") or delta.get("thinking") or ""
        tx = delta.get("content") or ""
        if th:
            out.append({"kind": "thinking", "text": str(th)})
        if isinstance(tx, str) and tx:
            out.append({"kind": "text", "text": tx})
        elif isinstance(tx, list):
            for blk in tx:
                if isinstance(blk, dict):
                    if blk.get("type") == "thinking" and blk.get("thinking"):
                        out.append({"kind": "thinking", "text": str(blk["thinking"])})
                    elif blk.get("text"):
                        out.append({"kind": "text", "text": str(blk["text"])})
    return out


async def _split_inline_think_tags(
    raw_stream: AsyncGenerator[dict[str, str], None],
) -> AsyncGenerator[dict[str, str], None]:
    """Also route inline `<think>...</think>` blocks (DeepSeek-R1 / QwQ / local relays) into `thinking` events."""
    buf = ""
    in_think = False
    async for ev in raw_stream:
        if ev["kind"] == "thinking":
            yield ev
            continue
        buf += ev["text"]
        while buf:
            if not in_think:
                idx = buf.find("<think>")
                if idx != -1:
                    if idx > 0:
                        yield {"kind": "text", "text": buf[:idx]}
                    buf = buf[idx + 7 :]
                    in_think = True
                else:
                    safe = max(0, len(buf) - 7)
                    if safe > 0:
                        yield {"kind": "text", "text": buf[:safe]}
                        buf = buf[safe:]
                    break
            else:
                end = buf.find("</think>")
                if end != -1:
                    if end > 0:
                        yield {"kind": "thinking", "text": buf[:end]}
                    buf = buf[end + 8 :]
                    in_think = False
                else:
                    safe = max(0, len(buf) - 8)
                    if safe > 0:
                        yield {"kind": "thinking", "text": buf[:safe]}
                        buf = buf[safe:]
                    break
    if buf:
        yield {"kind": "thinking" if in_think else "text", "text": buf}


async def _raw_stream_multimodal_events(
    prov: dict[str, Any],
    model: str,
    system_prompt: str,
    messages: list[dict[str, Any]],
    temperature: float = 0.25,
    enable_thinking: bool = False,
) -> AsyncGenerator[dict[str, str], None]:
    protocol = prov.get("protocol", "openai")
    base_url = _normalize_base(prov.get("base_url", ""))
    api_key = prov.get("api_key", "")
    if not base_url:
        raise RuntimeError("Base URL 为空，请在 API 设置中填写服务地址。")
    if not model:
        raise RuntimeError("尚未选择模型，请点击「拉取模型」后选择具体模型 ID。")

    async with httpx.AsyncClient(timeout=120.0, follow_redirects=True) as client:
        # Gemini Native v1beta protocol (also auto-used when selecting a `gemini*` model on a multi-protocol relay!)
        use_gemini_native = protocol == "gemini_native" or (
            protocol == "anthropic_relay" and "gemini" in model.lower()
        )
        if use_gemini_native:
            g_base = re.sub(r"/v1beta(?:/openai)?$|/v1$", "", base_url)
            ep_sse = f"{g_base}/v1beta/models/{model}:streamGenerateContent?alt=sse"
            ep_sync = f"{g_base}/v1beta/models/{model}:generateContent"
            hdrs = {
                "content-type": "application/json",
                "x-goog-api-key": api_key,
                "Authorization": f"Bearer {api_key}",
            }
            gen_cfg: dict[str, Any] = {"temperature": temperature}
            if enable_thinking:
                gen_cfg["thinkingConfig"] = {"includeThoughts": True}
            base_g_payload: dict[str, Any] = {
                "systemInstruction": {"parts": [{"text": system_prompt}]},
                "contents": _format_messages_gemini(messages),
                "generationConfig": gen_cfg,
            }
            payload_variants = [base_g_payload]
            if enable_thinking:
                fallback_g = {
                    **base_g_payload,
                    "generationConfig": {"temperature": temperature},
                }
                payload_variants.append(fallback_g)

            last_err = ""
            for p_idx, g_payload in enumerate(payload_variants):
                async with client.stream("POST", ep_sse, headers=hdrs, json=g_payload) as resp:
                    ctype = (resp.headers.get("content-type") or "").lower()
                    if resp.status_code == 400 and enable_thinking and p_idx == 0:
                        body = await resp.aread()
                        last_err = f"HTTP 400: {body.decode('utf-8', 'ignore')[:220]}"
                        continue
                    if resp.status_code >= 400:
                        body = await resp.aread()
                        last_err = f"Gemini API HTTP {resp.status_code} ({ep_sse}): {body.decode('utf-8', 'ignore')[:260]}"
                        if resp.status_code == 404:
                            break
                        raise RuntimeError(last_err)
                    if "text/html" in ctype:
                        last_err = f"接口 {ep_sse} 返回了网页 HTML"
                        break
                    if "application/json" in ctype and "event-stream" not in ctype:
                        body = await resp.aread()
                        obj = json.loads(body.decode("utf-8", "ignore"))
                        items = obj if isinstance(obj, list) else [obj]
                        for item in items:
                            if isinstance(item, dict):
                                if "error" in item:
                                    raise RuntimeError(f"Gemini API 错误：{item['error']}")
                                for ev in _extract_events_from_json_chunk(item):
                                    yield ev
                        return
                    yielded_any = False
                    async for line in resp.aiter_lines():
                        if not line.startswith("data:"):
                            continue
                        raw = line[5:].strip()
                        if not raw or raw == "[DONE]":
                            continue
                        try:
                            evt = json.loads(raw)
                            if "error" in evt and not evt.get("candidates"):
                                raise RuntimeError(f"Gemini API 流错误：{evt['error']}")
                            for ev in _extract_events_from_json_chunk(evt):
                                yielded_any = True
                                yield ev
                        except RuntimeError:
                            raise
                        except Exception:
                            continue
                    if yielded_any:
                        return
            # Fallback to non-stream `:generateContent` if SSE stream wasn't supported by relay
            r_sync = await client.post(ep_sync, headers=hdrs, json=payload_variants[-1])
            if r_sync.status_code >= 400:
                raise RuntimeError(f"Gemini API HTTP {r_sync.status_code}: {r_sync.text[:260]}")
            obj = r_sync.json()
            if "error" in obj:
                raise RuntimeError(f"Gemini API 错误：{obj['error']}")
            for ev in _extract_events_from_json_chunk(obj):
                yield ev
            return

        if protocol in ("anthropic", "anthropic_relay"):
            base_payload: dict[str, Any] = {
                "model": model,
                "max_tokens": 8192 if enable_thinking else 4096,
                "system": system_prompt,
                "messages": _format_messages_anthropic(messages),
                "stream": True,
            }
            if enable_thinking:
                base_payload["thinking"] = {"type": "enabled", "budget_tokens": 4096}
            else:
                base_payload["temperature"] = temperature

            endpoints = _candidate_endpoint(base_url, "/messages")
            header_sets = _anthropic_headers_variants(api_key, protocol)
            payload_variants = [base_payload]
            if enable_thinking:
                fallback_p = {k: v for k, v in base_payload.items() if k != "thinking"}
                fallback_p["max_tokens"] = 4096
                fallback_p["temperature"] = temperature
                payload_variants.append(fallback_p)

            last_err = ""
            for ep in endpoints:
                for hdrs in header_sets:
                    for p_idx, payload in enumerate(payload_variants):
                        async with client.stream("POST", ep, headers=hdrs, json=payload) as resp:
                            ctype = (resp.headers.get("content-type") or "").lower()
                            if resp.status_code == 400 and enable_thinking and p_idx == 0:
                                body = await resp.aread()
                                last_err = f"HTTP 400: {body.decode('utf-8', 'ignore')[:220]}"
                                continue  # Retry cleanly without `thinking` if model doesn't support it
                            if resp.status_code in (401, 403, 404) and protocol == "anthropic_relay":
                                body = await resp.aread()
                                last_err = f"HTTP {resp.status_code} ({ep}): {body.decode('utf-8', 'ignore')[:220]}"
                                break
                            if resp.status_code >= 400:
                                body = await resp.aread()
                                raise RuntimeError(f"Claude API HTTP {resp.status_code} ({ep}): {body.decode('utf-8', 'ignore')[:260]}")
                            if "text/html" in ctype:
                                body = await resp.aread()
                                last_err = f"接口 {ep} 返回了网页 HTML 而非模型数据流（请确认 Base URL 或中转站路径）"
                                break
                            if "application/json" in ctype and "event-stream" not in ctype:
                                body = await resp.aread()
                                txt = body.decode("utf-8", "ignore").strip()
                                if txt.startswith("<"):
                                    last_err = f"接口 {ep} 返回了网页 HTML 而非模型数据流"
                                    break
                                obj = json.loads(txt)
                                if "error" in obj:
                                    raise RuntimeError(f"Claude API 错误：{obj['error']}")
                                for ev in _extract_events_from_json_chunk(obj):
                                    yield ev
                                return
                            yielded_any = False
                            raw_preview: list[str] = []
                            async for line in resp.aiter_lines():
                                if len(raw_preview) < 4 and line.strip():
                                    raw_preview.append(line.strip()[:160])
                                if not line.startswith("data:"):
                                    continue
                                raw = line[5:].strip()
                                if not raw or raw == "[DONE]":
                                    continue
                                try:
                                    evt = json.loads(raw)
                                    if evt.get("type") == "error" or ("error" in evt and not evt.get("choices")):
                                        raise RuntimeError(f"API 流错误：{evt.get('error') or evt}")
                                    for ev in _extract_events_from_json_chunk(evt):
                                        yielded_any = True
                                        yield ev
                                except RuntimeError:
                                    raise
                                except Exception:
                                    continue
                            if not yielded_any and raw_preview and raw_preview[0].startswith("<"):
                                last_err = f"接口 {ep} 返回了网页 HTML，未输出模型内容"
                                break
                            return
            raise RuntimeError(f"Claude 第三方中转连接失败：{last_err or '未获取到有效响应'}")

        # OpenAI-compatible protocol (supports vision `image_url` blocks & reasoning_content natively)
        headers = {"content-type": "application/json"}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        payload = {
            "model": model,
            "temperature": temperature,
            "messages": _format_messages_openai(system_prompt, messages),
            "stream": True,
        }
        endpoints = _candidate_endpoint(base_url, "/chat/completions")
        last_err = ""
        for ep in endpoints:
            async with client.stream("POST", ep, headers=headers, json=payload) as resp:
                ctype = (resp.headers.get("content-type") or "").lower()
                if resp.status_code == 404 and len(endpoints) > 1:
                    body = await resp.aread()
                    last_err = f"HTTP 404 ({ep}): {body.decode('utf-8', 'ignore')[:200]}"
                    continue
                if resp.status_code >= 400:
                    body = await resp.aread()
                    raise RuntimeError(f"API HTTP {resp.status_code}: {body.decode('utf-8', 'ignore')[:260]}")
                if "text/html" in ctype:
                    last_err = f"接口 {ep} 返回了网页 HTML 而非模型数据流"
                    continue
                if "application/json" in ctype and "event-stream" not in ctype:
                    body = await resp.aread()
                    obj = json.loads(body.decode("utf-8", "ignore"))
                    if "error" in obj:
                        raise RuntimeError(f"API 错误：{obj['error']}")
                    for ev in _extract_events_from_json_chunk(obj):
                        yield ev
                    return
                async for line in resp.aiter_lines():
                    if not line.startswith("data:"):
                        continue
                    raw = line[5:].strip()
                    if not raw or raw == "[DONE]":
                        continue
                    try:
                        evt = json.loads(raw)
                        if "error" in evt and not evt.get("choices"):
                            raise RuntimeError(f"API 流错误：{evt['error']}")
                        for ev in _extract_events_from_json_chunk(evt):
                            yield ev
                    except RuntimeError:
                        raise
                    except Exception:
                        continue
                return
        raise RuntimeError(f"API 连接失败：{last_err or '未获取到有效响应'}")


async def stream_multimodal_events(
    prov: dict[str, Any],
    model: str,
    system_prompt: str,
    messages: list[dict[str, Any]],
    temperature: float = 0.25,
    enable_thinking: bool = False,
) -> AsyncGenerator[dict[str, str], None]:
    """Stream structured `thinking` and `text` chunks across OpenAI, Anthropic, and 3rd-party relays."""
    async for ev in _split_inline_think_tags(
        _raw_stream_multimodal_events(prov, model, system_prompt, messages, temperature=temperature, enable_thinking=enable_thinking)
    ):
        yield ev


async def stream_multimodal_messages(
    prov: dict[str, Any],
    model: str,
    system_prompt: str,
    messages: list[dict[str, Any]],
    temperature: float = 0.25,
) -> AsyncGenerator[str, None]:
    """Backward-compatible text-only token stream (filters out reasoning/thinking tokens for structured callers)."""
    async for ev in stream_multimodal_events(prov, model, system_prompt, messages, temperature=temperature, enable_thinking=False):
        if ev["kind"] == "text":
            yield ev["text"]


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
