"""Lean local configuration & company-only API presets for PaperHarness.

No stale hardcoded model lists — models are discovered live via the user's API key.
Supports frozen PyInstaller portable builds on Windows (`local_data/` lives beside the `.exe`).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

# Frozen `.exe` portable paths vs source paths
if getattr(sys, "frozen", False):
    APP_DIR = Path(sys.executable).resolve().parent
    BUNDLE_DIR = Path(getattr(sys, "_MEIPASS", APP_DIR))
else:
    APP_DIR = Path(__file__).resolve().parents[1]
    BUNDLE_DIR = APP_DIR

PROJECT_ROOT = APP_DIR
DATA_DIR = APP_DIR / "local_data"
DATA_DIR.mkdir(parents=True, exist_ok=True)
CONFIG_FILE = DATA_DIR / "settings.json"


def get_skill_dir() -> Path | None:
    """Locate external hot-swap `local_data/knowledge_pack/` FIRST, then bundled/sibling skill directory."""
    candidates = [
        DATA_DIR / "knowledge_pack",
        APP_DIR / "knowledge_pack",
        APP_DIR / "skills" / "academic-polish",
        BUNDLE_DIR / "skills" / "academic-polish",
        APP_DIR.parent / "academic-polish-plugin" / "skills" / "academic-polish",
    ]
    return next((p for p in candidates if (p / "SKILL.md").exists()), None)


# Company-only presets: zero stale model arrays (fetched dynamically using API key)
# protocol: "openai" | "anthropic" | "anthropic_relay"
_PRESET_SPECS: list[tuple[str, str, str, str, str]] = [
    # 国内主流
    ("deepseek", "DeepSeek", "domestic", "openai", "https://api.deepseek.com/v1"),
    ("dashscope", "阿里云 · 通义千问 (DashScope)", "domestic", "openai", "https://dashscope.aliyuncs.com/compatible-mode/v1"),
    ("moonshot", "月之暗面 · Kimi", "domestic", "openai", "https://api.moonshot.cn/v1"),
    ("zhipu", "智谱 AI (GLM)", "domestic", "openai", "https://open.bigmodel.cn/api/paas/v4"),
    ("ark", "字节跳动 · 火山方舟 (豆包)", "domestic", "openai", "https://ark.cn-beijing.volces.com/api/v3"),
    ("siliconflow", "硅基流动 (SiliconFlow)", "domestic", "openai", "https://api.siliconflow.cn/v1"),
    ("minimax", "MiniMax", "domestic", "openai", "https://api.minimax.chat/v1"),
    ("qianfan", "百度智能云 · 千帆", "domestic", "openai", "https://qianfan.baidubce.com/v2"),
    ("stepfun", "阶跃星辰 (StepFun)", "domestic", "openai", "https://api.stepfun.com/v1"),
    # 国外主流 & Claude 第三方适配
    ("anthropic", "Anthropic (Claude 官方)", "international", "anthropic", "https://api.anthropic.com/v1"),
    ("claude_relay", "Claude 第三方中转 (Anthropic 协议)", "international", "anthropic_relay", ""),
    ("openai", "OpenAI", "international", "openai", "https://api.openai.com/v1"),
    ("gemini", "Google Gemini", "international", "openai", "https://generativelanguage.googleapis.com/v1beta/openai"),
    ("openrouter", "OpenRouter", "international", "openai", "https://openrouter.ai/api/v1"),
    ("xai", "xAI (Grok)", "international", "openai", "https://api.x.ai/v1"),
    ("groq", "Groq", "international", "openai", "https://api.groq.com/openai/v1"),
    # 本地隐私部署
    ("ollama", "Ollama (本机)", "local", "openai", "http://127.0.0.1:11434/v1"),
    ("lmstudio", "LM Studio (本机)", "local", "openai", "http://127.0.0.1:1234/v1"),
    ("vllm", "实验室 vLLM / SGLang", "local", "openai", "http://127.0.0.1:8000/v1"),
]


def _build_default_providers() -> list[dict[str, Any]]:
    return [
        {
            "id": pid,
            "name": name,
            "region": region,
            "protocol": proto,
            "base_url": url,
            "api_key": "ollama" if pid == "ollama" else ("lm-studio" if pid == "lmstudio" else ""),
            "models": [],
            "default_model": "",
        }
        for pid, name, region, proto, url in _PRESET_SPECS
    ]


def default_settings() -> dict[str, Any]:
    return {
        "providers": _build_default_providers(),
        "routing": {
            "writing": {"provider_id": "deepseek", "model": ""},
            "vision": {"provider_id": "dashscope", "model": ""},
            "image": {"provider_id": "siliconflow", "model": ""},
        },
        "search": {
            "provider": "builtin_free",  # builtin_free | bocha | tavily | serper
            "api_key": "",
        },
        "preferences": {
            "default_venue": "CVPR / ICCV",
            "cjk_latin_space": False,
            "author_name": "PaperHarness Co-Author",
            "theme": "paper",
            "lang": "zh",
            "style_strength": "balanced",  # natural | balanced | venue_strict
            "first_mention_en": True,
        },
    }


def load_settings() -> dict[str, Any]:
    if not CONFIG_FILE.exists():
        cfg = default_settings()
        save_settings(cfg)
        return cfg
    try:
        saved = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
    except Exception:
        return default_settings()

    defaults = {p["id"]: p for p in _build_default_providers()}
    saved_map = {p["id"]: p for p in saved.get("providers", [])}
    merged: list[dict[str, Any]] = []
    # Keep built-ins in clean order, preserving user's keys, fetched models & custom URLs
    for pid, dp in defaults.items():
        if pid in saved_map:
            sp = saved_map[pid]
            merged.append({
                "id": pid,
                "name": sp.get("name") or dp["name"],
                "region": dp["region"],
                "protocol": sp.get("protocol") or dp["protocol"],
                "base_url": sp.get("base_url") if sp.get("base_url") is not None else dp["base_url"],
                "api_key": sp.get("api_key", dp["api_key"]),
                "models": sp.get("models") if sp.get("api_key") or dp["region"] == "local" else [],
                "default_model": sp.get("default_model", ""),
            })
        else:
            merged.append(dp)
    # Append user-added custom 3rd-party relays
    for p in saved.get("providers", []):
        if p["id"] not in defaults:
            merged.append(p)

    saved["providers"] = merged
    saved.setdefault("routing", default_settings()["routing"])
    saved["search"] = {**default_settings()["search"], **saved.get("search", {})}
    prefs = {**default_settings()["preferences"], **saved.get("preferences", {})}
    saved["preferences"] = prefs
    return saved


def save_settings(cfg: dict[str, Any]) -> None:
    CONFIG_FILE.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")


def mask_key(key: str) -> str:
    if not key:
        return ""
    return "*" * len(key) if len(key) <= 8 else f"{key[:4]}••••{key[-4:]}"
