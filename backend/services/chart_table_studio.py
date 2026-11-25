"""Smart Data-to-Figure & Publication Table Studio.

- Analyzes CSV/TSV datasets and recommends optimal academic chart types with rationale.
- Generates clean, reproducible matplotlib Python scripts calibrated to exact print widths
  (Single Column 3.5" / Double Column 7.0") and venue aesthetics (CVPR, NeurIPS, Nature, IEEE).
- Executes plotting scripts safely in-process to produce crisp SVG, 300 DPI PNG, and Vector PDF.
- Generates LaTeX `booktabs` AND native Word Three-Line Tables (`.docx`) with automatic
  best (bold) and second-best (underline) highlighting per metric.
"""
from __future__ import annotations

import base64
import csv
import io
import math
import re
from typing import Any

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from docx import Document
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.oxml import parse_xml
from docx.oxml.ns import nsdecls
from docx.shared import Pt

SAMPLE_DATASETS: dict[str, dict[str, Any]] = {
    "benchmark_bars": {
        "name": "高分辨率 VLM 基准对比 (CVPR 分组柱图)",
        "description": "多模型在 4 个基准上的性能对比与 FLOPs 开销",
        "csv": (
            "Method,DocVQA,ChartQA,InfoVQA,TextVQA,GFLOPs\n"
            "LLaVA-NeXT-7B,74.4,69.5,37.1,64.9,842\n"
            "InternVL2-8B,86.9,81.2,71.8,77.4,795\n"
            "ToMe-VLM,84.1,78.6,68.4,75.2,520\n"
            "FastV-7B,85.3,79.8,69.9,76.1,512\n"
            "HierAttn-Net (Ours),91.4,83.6,76.2,80.5,467"
        ),
        "lower_is_better": ["GFLOPs"],
        "recommended_chart": "grouped_bar",
    },
    "scaling_curve": {
        "name": "Token 预算与精度缩放曲线 (NeurIPS 折线图)",
        "description": "保留视觉 Token 比例 15%–100% 下的精度变化趋势",
        "csv": (
            "Token_Budget_Pct,HierAttn_Ours,FastV,ToMe,Random_Prune\n"
            "15,82.1,71.4,68.9,58.2\n"
            "25,86.8,77.2,74.8,64.5\n"
            "40,89.7,81.9,80.1,71.0\n"
            "60,91.4,85.3,84.1,77.6\n"
            "80,91.8,86.5,85.8,82.4\n"
            "100,92.0,87.1,86.9,87.1"
        ),
        "lower_is_better": [],
        "recommended_chart": "line_curve",
    },
    "ablation_hbar": {
        "name": "模块消融实验对比 (ICML 水平条形图)",
        "description": "各核心组件逐步叠加带来的准确率提升",
        "csv": (
            "Variant,DocVQA_ANLS\n"
            "Base ViT-L + Static Top-K,84.2\n"
            "+ Query-Guided Saliency (CSIE),87.6\n"
            "+ Differentiable Budget Gate,89.3\n"
            "+ Residual Semantic Merger (RSM),90.8\n"
            "+ Multi-Scale Alignment (Full),91.4"
        ),
        "lower_is_better": [],
        "recommended_chart": "horizontal_bar",
    },
    "error_bar_runs": {
        "name": "5 次随机种子均值 ± 标准差 (Nature 误差棒图)",
        "description": "含 ± std 波动区间的严谨统计对比",
        "csv": (
            "Method,DocVQA,ChartQA,TextVQA\n"
            "Baseline-7B,84.1±0.6,77.8±0.8,74.9±0.5\n"
            "ToMe-VLM,85.0±0.5,78.6±0.7,75.4±0.6\n"
            "FastV-7B,86.2±0.4,79.9±0.5,76.3±0.4\n"
            "HierAttn-Net (Ours),91.4±0.3,83.6±0.4,80.5±0.3"
        ),
        "lower_is_better": [],
        "recommended_chart": "error_bar",
    },
    "dual_efficiency": {
        "name": "精度 vs 延迟双轴效率图 (TPAMI 双轴图)",
        "description": "左轴准确率柱图 + 右轴推理延迟折线",
        "csv": (
            "Method,Accuracy_Pct,Latency_ms\n"
            "LLaVA-NeXT,74.4,186\n"
            "InternVL2,86.9,172\n"
            "ToMe-VLM,84.1,114\n"
            "FastV-7B,85.3,108\n"
            "HierAttn (Ours),91.4,89"
        ),
        "lower_is_better": ["Latency_ms"],
        "recommended_chart": "dual_axis",
    },
    "ablation_heatmap": {
        "name": "超参数敏感性热力图 (α × τ 网格)",
        "description": "查询权重 α 与聚合温度 τ 的二维消融热力图",
        "csv": (
            "Alpha,Tau_0.1,Tau_0.3,Tau_0.5,Tau_1.0,Tau_2.0\n"
            "0.0,86.4,87.2,87.5,86.9,85.8\n"
            "0.25,88.1,89.6,89.9,88.7,87.1\n"
            "0.5,89.4,91.4,91.1,89.8,88.0\n"
            "1.0,88.9,90.5,90.2,89.1,87.4\n"
            "2.0,87.2,88.8,88.4,87.6,86.2"
        ),
        "lower_is_better": [],
        "recommended_chart": "heatmap",
    },
}

PALETTES: dict[str, list[str]] = {
    "oxford_academic": ["#1E3A5F", "#3B7A9E", "#C25934", "#2E7D5B", "#7C6396", "#B68D40"],
    "okabe_ito": ["#0072B2", "#E69F00", "#009E73", "#D55E00", "#CC79A7", "#56B4E9"],
    "nature_npg": ["#E64B35", "#4DBBD5", "#00A087", "#3C5488", "#F39B7F", "#8491B4"],
    "acl_pastel": ["#4E79A7", "#F28E2B", "#76B7B2", "#E15759", "#59A14F", "#B07AA1"],
    "iclr_indigo": ["#2B3A67", "#E84855", "#3B9C9C", "#F9C74F", "#725AC1", "#6C757D"],
    "cvpr_slate": ["#223843", "#50808E", "#D77A61", "#69A297", "#846A6A", "#C4A35A"],
    "monochrome_print": ["#1A1A1A", "#4D4D4D", "#7F7F7F", "#A6A6A6", "#CCCCCC", "#383838"],
}

VENUE_PRESETS: dict[str, dict[str, Any]] = {
    "CVPR / ICCV": {"font_family": "DejaVu Serif", "font_size": 11.0, "line_width": 2.0, "palette": "oxford_academic", "grid": True},
    "NeurIPS / ICML": {"font_family": "DejaVu Sans", "font_size": 11.0, "line_width": 2.1, "palette": "okabe_ito", "grid": True},
    "Nature / Science": {"font_family": "DejaVu Sans", "font_size": 10.5, "line_width": 1.8, "palette": "nature_npg", "grid": False},
    "IEEE / TPAMI": {"font_family": "DejaVu Serif", "font_size": 10.5, "line_width": 1.9, "palette": "cvpr_slate", "grid": True},
    "ACL / EMNLP": {"font_family": "DejaVu Sans", "font_size": 11.0, "line_width": 2.0, "palette": "acl_pastel", "grid": True},
    "ICLR Modern": {"font_family": "DejaVu Sans", "font_size": 11.0, "line_width": 2.1, "palette": "iclr_indigo", "grid": True},
    "中文核心 / 学位论文": {"font_family": "SimSun", "font_size": 11.0, "line_width": 1.9, "palette": "oxford_academic", "grid": True},
    "黑白灰度打印 (Grayscale)": {"font_family": "DejaVu Serif", "font_size": 11.0, "line_width": 2.0, "palette": "monochrome_print", "grid": True},
}


def parse_csv_data(csv_text: str) -> dict[str, Any]:
    """Parse CSV/TSV text cleanly into headers, rows, and numeric column profiles."""
    cleaned = csv_text.strip()
    if not cleaned:
        raise ValueError("Dataset is empty.")
    delimiter = "\t" if ("\t" in cleaned.splitlines()[0] and "," not in cleaned.splitlines()[0]) else ","
    reader = list(csv.reader(io.StringIO(cleaned), delimiter=delimiter))
    headers = [h.strip() for h in reader[0] if h.strip()]
    rows = []
    for r in reader[1:]:
        if not any(c.strip() for c in r):
            continue
        padded = [c.strip() for c in r[: len(headers)]] + [""] * max(0, len(headers) - len(r))
        rows.append(padded)

    num_cols: list[str] = []
    cat_cols: list[str] = []
    col_stats: dict[str, dict[str, Any]] = {}

    for ci, h in enumerate(headers):
        vals: list[float] = []
        for r in rows:
            raw = r[ci].split("±")[0].replace("%", "").strip()
            try:
                vals.append(float(raw))
            except ValueError:
                pass
        if rows and len(vals) >= max(1, int(len(rows) * 0.8)):
            num_cols.append(h)
            col_stats[h] = {
                "min": min(vals),
                "max": max(vals),
                "mean": round(sum(vals) / len(vals), 2),
                "monotonic": all(vals[i] <= vals[i + 1] for i in range(len(vals) - 1)),
            }
        else:
            cat_cols.append(h)

    return {"headers": headers, "rows": rows, "num_cols": num_cols, "cat_cols": cat_cols, "col_stats": col_stats}


def analyze_dataset(csv_text: str) -> dict[str, Any]:
    """Smart data analyzer recommending the best academic chart types with justification."""
    parsed = parse_csv_data(csv_text)
    headers, rows, num_cols, cat_cols, stats = (
        parsed["headers"],
        parsed["rows"],
        parsed["num_cols"],
        parsed["cat_cols"],
        parsed["col_stats"],
    )

    recommendations: list[dict[str, Any]] = []
    first_col = headers[0] if headers else ""
    first_is_monotonic_num = first_col in stats and stats[first_col]["monotonic"] and len(rows) >= 4

    # Check if 2D matrix / ablation grid
    if len(num_cols) >= 4 and len(rows) >= 4 and (
        any(k in first_col.lower() for k in ("alpha", "beta", "lambda", "lr", "layer", "dim"))
        or all(re.search(r"[\d.]", h) for h in headers[1:])
    ):
        recommendations.append({
            "chart_type": "heatmap",
            "title": "2D Sensitivity Heatmap",
            "confidence": 0.94,
            "reason": f"Detected 2D grid ({len(rows)}×{len(headers)-1}) across numeric parameter sweeps — ideal for ablation heatmaps.",
        })

    if first_is_monotonic_num and len(num_cols) >= 2:
        recommendations.append({
            "chart_type": "line_curve",
            "title": "Multi-Series Scaling Curve",
            "confidence": 0.95,
            "reason": f"First column “{first_col}” is strictly monotonic ({len(rows)} steps) with {len(num_cols)-1} comparison curves.",
        })

    has_std = any("±" in cell for r in rows for cell in r)
    if has_std and cat_cols and len(num_cols) >= 1:
        recommendations.append({
            "chart_type": "error_bar",
            "title": "均值 ± 误差棒对比图",
            "confidence": 0.96,
            "reason": "检测到 ± 标准差波动区间，自动绘制带误差棒的分组柱图。",
        })

    if cat_cols and len(num_cols) == 1:
        recommendations.append({
            "chart_type": "horizontal_bar",
            "title": "水平消融条形图",
            "confidence": 0.95,
            "reason": f"单指标多变体对比（{len(rows)} 行），水平条形图最清晰易读。",
        })

    if cat_cols and len(num_cols) == 2:
        max0 = stats[num_cols[0]]["max"]
        max1 = stats[num_cols[1]]["max"]
        if max(max0, max1) / max(1e-6, min(max0, max1)) >= 1.4:
            recommendations.append({
                "chart_type": "dual_axis",
                "title": "精度-效率双纵轴图",
                "confidence": 0.93,
                "reason": f"两列量纲不同（{num_cols[0]} vs {num_cols[1]}），推荐左轴柱图 + 右轴折线。",
            })

    if cat_cols and len(num_cols) >= 1:
        recommendations.append({
            "chart_type": "grouped_bar",
            "title": "分组基准柱状图",
            "confidence": 0.92,
            "reason": f"多方法在 {len(num_cols)} 个量化指标上的直观分组对比。",
        })

    if len(num_cols) >= 2:
        recommendations.append({
            "chart_type": "scatter_pareto",
            "title": "精度-效率帕累托图",
            "confidence": 0.84,
            "reason": f"展示「{num_cols[-1]}」（横轴代价）与「{num_cols[0]}」（纵轴精度）的权衡前沿。",
        })

    if len(num_cols) >= 3 and len(rows) <= 8:
        recommendations.append({
            "chart_type": "radar",
            "title": "多基准对比雷达图",
            "confidence": 0.78,
            "reason": f"在 {min(6, len(num_cols))} 项量化指标上对比各方法综合能力轮廓。",
        })

    if not recommendations:
        recommendations.append({
            "chart_type": "grouped_bar",
            "title": "分组基准柱状图",
            "confidence": 0.80,
            "reason": "默认学术柱状图对比。",
        })

    recommendations.sort(key=lambda r: -r["confidence"])
    return {
        "headers": headers,
        "row_count": len(rows),
        "num_cols": num_cols,
        "cat_cols": cat_cols,
        "recommendations": recommendations,
        "recommended_chart": recommendations[0]["chart_type"],
    }


def generate_matplotlib_code(
    csv_text: str,
    chart_type: str = "grouped_bar",
    title: str = "",
    xlabel: str = "",
    ylabel: str = "",
    venue: str = "CVPR / ICCV",
    width_in: float = 7.6,
    height_in: float = 4.4,
    font_family: str = "DejaVu Serif",
    font_size: float = 11.0,
    line_width: float = 2.0,
    palette_name: str = "oxford_academic",
    legend_pos: str = "top",
    show_grid: bool = True,
    show_values: bool = True,
    spacing_mode: str = "airy",
    selected_cols: list[str] | None = None,
) -> str:
    """Emit clean, spacious, publication-grade Matplotlib Python code with zero cramped labels."""
    parsed = parse_csv_data(csv_text)
    headers = parsed["headers"]
    colors = PALETTES.get(palette_name, PALETTES["oxford_academic"])
    data_repr = repr(csv_text.strip())

    # Generous breathing room controlled by spacing_mode: airy (default) / standard / compact
    sp = {
        "airy": {"pad": 1.9, "labelpad": 11, "tickpad": 7, "bar_span": 0.72, "bar_fill": 0.84, "leg_y": 1.18, "title_pad": 34, "ylim_top": 1.18, "col_sp": 1.6},
        "standard": {"pad": 1.4, "labelpad": 8, "tickpad": 5, "bar_span": 0.76, "bar_fill": 0.88, "leg_y": 1.15, "title_pad": 28, "ylim_top": 1.14, "col_sp": 1.3},
        "compact": {"pad": 0.9, "labelpad": 5, "tickpad": 3, "bar_span": 0.80, "bar_fill": 0.92, "leg_y": 1.12, "title_pad": 22, "ylim_top": 1.11, "col_sp": 1.0},
    }.get(spacing_mode, {"pad": 1.9, "labelpad": 11, "tickpad": 7, "bar_span": 0.72, "bar_fill": 0.84, "leg_y": 1.18, "title_pad": 34, "ylim_top": 1.18, "col_sp": 1.6})

    num_cols = parsed["num_cols"]
    if selected_cols:
        plot_cols = [c for c in selected_cols if c in headers]
    elif chart_type == "grouped_bar":
        cands = [c for c in num_cols if c != headers[0]]
        if len(cands) >= 3:
            maxes = [parsed["col_stats"][c]["max"] for c in cands]
            med = sorted(maxes)[len(maxes) // 2]
            plot_cols = [c for c in cands if parsed["col_stats"][c]["max"] <= med * 2.5] or cands
        else:
            plot_cols = cands or num_cols
    else:
        plot_cols = [c for c in num_cols if c != headers[0]] or num_cols

    legend_code = {
        "top": f"ax.legend(frameon=False, loc='upper center', bbox_to_anchor=(0.5, {sp['leg_y']}), ncol=min(3, max(1, len(series_names))), columnspacing={sp['col_sp']}, handletextpad=0.6)",
        "best": "ax.legend(frameon=True, facecolor='white', edgecolor='#D9D5CB', framealpha=0.95, loc='best', borderpad=0.6)",
        "right": "ax.legend(frameon=False, loc='center left', bbox_to_anchor=(1.03, 0.5), labelspacing=0.7)",
        "none": "pass",
    }.get(legend_pos, "ax.legend(frameon=False, loc='best')")

    has_cjk = bool(re.search(r"[\u4e00-\u9fff]", f"{title}{xlabel}{ylabel}{csv_text}"))
    eff_font = ("Microsoft YaHei" if font_family in ("DejaVu Sans", "Microsoft YaHei") else "SimSun") if has_cjk else font_family

    code = f"""import csv, io
import numpy as np
import matplotlib.pyplot as plt

CSV_DATA = {data_repr}
delimiter = '\\t' if ('\\t' in CSV_DATA.splitlines()[0] and ',' not in CSV_DATA.splitlines()[0]) else ','
raw = list(csv.reader(io.StringIO(CSV_DATA), delimiter=delimiter))
headers = [h.strip() for h in raw[0]]
rows = [[c.strip() for c in r] for r in raw[1:] if any(c.strip() for c in r)]

def to_float(v):
    return float(v.split('±')[0].replace('%', '').strip())

def to_std(v):
    parts = v.split('±')
    return float(parts[1].replace('%', '').strip()) if len(parts) > 1 else 0.0

def place_non_overlapping_labels(ax, items, span, bar_w, fs):
    # Collision-aware label placer: staggers close bar labels with crisp leader ticks so digits NEVER touch.
    placed = []
    max_y = max((y for _, y, _, _ in items), default=1.0)
    min_dx = max(bar_w * 1.55, 0.22)
    min_dy = span * 0.082
    for x, y, txt, bold in sorted(items, key=lambda it: it[0]):
        ly = y + span * 0.032
        bumped = False
        for _ in range(5):
            clash = any(abs(x - px) < min_dx and abs(ly - py) < min_dy for px, py in placed)
            if not clash:
                break
            ly += span * 0.088
            bumped = True
        if bumped:
            ax.plot([x, x], [y + span * 0.012, ly - span * 0.012], color='#94A3B8', linewidth=0.65, zorder=4)
        ax.text(
            x, ly, txt, ha='center', va='bottom',
            fontsize=fs, fontweight='bold' if bold else 'normal',
            bbox=dict(facecolor='white', edgecolor='none', alpha=0.72, pad=0.6),
            zorder=5,
        )
        placed.append((x, ly))
        max_y = max(max_y, ly + span * 0.07)
    return max_y

plt.rcParams.update({{
    'font.family': 'sans-serif' if {eff_font!r} in ('DejaVu Sans', 'Microsoft YaHei') else 'serif',
    'font.serif': [{eff_font!r}, 'SimSun', 'Microsoft YaHei', 'DejaVu Serif'],
    'font.sans-serif': [{eff_font!r}, 'Microsoft YaHei', 'SimHei', 'DejaVu Sans'],
    'axes.unicode_minus': False,
    'font.size': {font_size},
    'axes.titlesize': {font_size + 2.0},
    'axes.labelsize': {font_size + 0.8},
    'xtick.labelsize': {max(8.0, font_size - 0.5)},
    'ytick.labelsize': {max(8.0, font_size - 0.5)},
    'legend.fontsize': {max(8.0, font_size - 0.8)},
    'axes.linewidth': 0.95,
    'axes.edgecolor': '#2C313A',
    'text.color': '#16191F',
    'axes.labelcolor': '#16191F',
    'xtick.color': '#2C313A',
    'ytick.color': '#2C313A',
    'pdf.fonttype': 42,
    'svg.fonttype': 'none',
}})

COLORS = {colors!r}
HATCHES = ['', '//', '..', 'xx', '\\\\', '++']
USE_HATCH = {palette_name!r} == 'monochrome_print'
PLOT_COLS = {plot_cols!r}
CHART_TYPE = {chart_type!r}

fig, ax = plt.subplots(figsize=({width_in}, {height_in}), dpi=200)
fig.patch.set_facecolor('white')
ax.set_facecolor('white')

labels = [r[0] for r in rows]
series_names = PLOT_COLS

if CHART_TYPE in ('grouped_bar', 'error_bar'):
    x = np.arange(len(PLOT_COLS)) * 1.42
    n_methods = len(rows)
    bar_w = min({sp['bar_span'] + 0.22} / max(1, n_methods), 0.25)
    series_names = labels
    all_v = [to_float(r[headers.index(c)]) for r in rows for c in PLOT_COLS]
    all_e = [to_std(r[headers.index(c)]) for r in rows for c in PLOT_COLS]
    span = max(1.0, max(all_v) - min(all_v))
    group_items = [[] for _ in PLOT_COLS]
    for mi, r in enumerate(rows):
        vals = [to_float(r[headers.index(c)]) for c in PLOT_COLS]
        errs = [to_std(r[headers.index(c)]) for c in PLOT_COLS]
        offset = (mi - (n_methods - 1) / 2.0) * bar_w
        is_ours = ('ours' in r[0].lower()) or (mi == n_methods - 1)
        bars = ax.bar(
            x + offset, vals, width=bar_w * {sp['bar_fill']},
            yerr=errs if (CHART_TYPE == 'error_bar' and any(e > 0 for e in errs)) else None,
            capsize=3.5 if CHART_TYPE == 'error_bar' else 0,
            error_kw=dict(ecolor='#16191F', elinewidth=1.0),
            label=r[0],
            color=COLORS[mi % len(COLORS)],
            hatch=HATCHES[mi % len(HATCHES)] if USE_HATCH else None,
            edgecolor='#16191F' if (is_ours or USE_HATCH) else 'white',
            linewidth=1.0 if is_ours else 0.5,
            zorder=3,
        )
        if {show_values!r} and n_methods <= 6:
            for gi, (b, v, ev) in enumerate(zip(bars, vals, errs)):
                group_items[gi].append((b.get_x() + b.get_width() / 2, b.get_height() + ev, f'{{v:.1f}}', is_ours))
    top_needed = max(all_v) + max(all_e, default=0) + span * ({sp['ylim_top']} - 0.96)
    if {show_values!r} and n_methods <= 6:
        for gi_items in group_items:
            top_needed = max(top_needed, place_non_overlapping_labels(ax, gi_items, span, bar_w, max(7.2, {font_size} - 2.6)))
    ax.set_xticks(x)
    ax.set_xticklabels(PLOT_COLS)
    ax.set_xlabel({(xlabel or "Benchmark")!r}, labelpad={sp['labelpad']})
    ax.set_ylabel({(ylabel or "Score (%)")!r}, labelpad={sp['labelpad']})
    lo = max(0.0, min(all_v) - span * 0.28) if len(all_v) > 1 else 0.0
    ax.set_ylim(lo, top_needed + span * 0.04)

elif CHART_TYPE == 'horizontal_bar':
    col = PLOT_COLS[0]
    vals = [to_float(r[headers.index(col)]) for r in rows]
    y = np.arange(len(rows))
    bar_colors = [COLORS[0] if (i == len(rows) - 1 or 'full' in labels[i].lower() or 'ours' in labels[i].lower()) else COLORS[1] for i in range(len(rows))]
    bars = ax.barh(y, vals, height=0.58, color=bar_colors, edgecolor='#16191F', linewidth=0.6, zorder=3)
    span = max(1.0, max(vals) - min(vals))
    lo = max(0.0, min(vals) - span * 0.35)
    ax.set_xlim(lo, max(vals) + span * 0.26)
    ax.set_yticks(y)
    ax.set_yticklabels(labels)
    ax.invert_yaxis()
    ax.set_xlabel({ylabel!r} or col.replace("_", " "), labelpad={sp['labelpad']})
    if {show_values!r}:
        for i, (b, v) in enumerate(zip(bars, vals)):
            ax.text(b.get_width() + span * 0.03, b.get_y() + b.get_height() / 2, f'{{v:.1f}}', va='center', ha='left', fontsize=max(8.0, {font_size} - 1.2), fontweight='bold' if i == len(rows) - 1 else 'normal')

elif CHART_TYPE == 'dual_axis':
    c1, c2 = PLOT_COLS[0], PLOT_COLS[1] if len(PLOT_COLS) > 1 else PLOT_COLS[0]
    v1 = [to_float(r[headers.index(c1)]) for r in rows]
    v2 = [to_float(r[headers.index(c2)]) for r in rows]
    x = np.arange(len(rows))
    bars = ax.bar(x, v1, width=0.46, color=COLORS[0], alpha=0.86, edgecolor='#16191F', linewidth=0.6, label=c1.replace('_', ' '), zorder=3)
    ax.set_xticks(x)
    ax.set_xticklabels(labels)
    ax.set_ylabel(c1.replace('_', ' '), color=COLORS[0], labelpad={sp['labelpad']})
    ax.set_ylim(max(0.0, min(v1) * 0.8), max(v1) * 1.18)
    if {show_values!r}:
        for b, v in zip(bars, v1):
            ax.text(b.get_x() + b.get_width() / 2, b.get_height() + max(v1) * 0.018, f'{{v:.1f}}', ha='center', va='bottom', fontsize=max(7.5, {font_size} - 2.0), color=COLORS[0], fontweight='semibold')
    ax2 = ax.twinx()
    ax2.plot(x, v2, color=COLORS[2 % len(COLORS)], marker='o', markersize=6.5, linewidth={line_width} * 1.15, label=c2.replace('_', ' '), zorder=5)
    ax2.set_ylabel(c2.replace('_', ' '), color=COLORS[2 % len(COLORS)], labelpad={sp['labelpad']})
    ax2.spines['top'].set_visible(False)
    ax2.set_ylim(0, max(v2) * 1.25)
    h1, l1 = ax.get_legend_handles_labels()
    h2, l2 = ax2.get_legend_handles_labels()
    ax.legend(h1 + h2, l1 + l2, frameon=False, loc='upper center', bbox_to_anchor=(0.5, {sp['leg_y']}), ncol=2)

elif CHART_TYPE == 'line_curve':
    x_vals = [to_float(r[0]) for r in rows]
    markers = ['o', 's', '^', 'D', 'v', 'P']
    for si, col in enumerate(PLOT_COLS):
        ci = headers.index(col)
        y_vals = [to_float(r[ci]) for r in rows]
        is_first = si == 0
        ax.plot(
            x_vals, y_vals,
            marker=markers[si % len(markers)],
            markersize=6.5 if is_first else 5.5,
            linewidth={line_width} * (1.25 if is_first else 0.95),
            linestyle='-' if is_first else ('--' if si % 2 == 1 else '-.'),
            color=COLORS[si % len(COLORS)],
            label=col.replace('_', ' '),
            zorder=4 if is_first else 3,
        )
    ax.set_xlabel({(xlabel or headers[0].replace("_", " "))!r}, labelpad={sp['labelpad']})
    ax.set_ylabel({(ylabel or "Accuracy (%)")!r}, labelpad={sp['labelpad']})
    ax.margins(x=0.06, y=0.14)

elif CHART_TYPE == 'heatmap':
    mat = np.array([[to_float(r[headers.index(c)]) for c in PLOT_COLS] for r in rows])
    im = ax.imshow(mat, cmap='YlGnBu', aspect='auto')
    ax.set_xticks(np.arange(len(PLOT_COLS)))
    ax.set_xticklabels([c.replace('_', ' ') for c in PLOT_COLS])
    ax.set_yticks(np.arange(len(labels)))
    ax.set_yticklabels(labels)
    ax.set_xlabel({(xlabel or "Column Parameter")!r}, labelpad={sp['labelpad']})
    ax.set_ylabel({(ylabel or headers[0])!r}, labelpad={sp['labelpad']})
    mid = (mat.max() + mat.min()) / 2.0
    for i in range(mat.shape[0]):
        for j in range(mat.shape[1]):
            ax.text(
                j, i, f'{{mat[i, j]:.1f}}',
                ha='center', va='center',
                color='white' if mat[i, j] > mid else '#16191F',
                fontweight='bold' if mat[i, j] == mat.max() else 'normal',
                fontsize=max(8.0, {font_size} - 0.8),
            )
    cbar = fig.colorbar(im, ax=ax, fraction=0.046, pad=0.05)
    cbar.outline.set_linewidth(0.6)

elif CHART_TYPE == 'scatter_pareto':
    x_col = headers[-1] if headers[-1] in PLOT_COLS else PLOT_COLS[-1]
    y_col = PLOT_COLS[0] if PLOT_COLS[0] != x_col else (PLOT_COLS[1] if len(PLOT_COLS) > 1 else PLOT_COLS[0])
    xs = [to_float(r[headers.index(x_col)]) for r in rows]
    ys = [to_float(r[headers.index(y_col)]) for r in rows]
    dx_span = max(1.0, max(xs) - min(xs))
    dy_span = max(1.0, max(ys) - min(ys))
    # Iterative repulsion solver so scatter labels NEVER collide
    lx = [xv + dx_span * 0.03 for xv in xs]
    ly = [yv + dy_span * 0.04 for yv in ys]
    for _ in range(14):
        for i in range(len(xs)):
            for j in range(i + 1, len(xs)):
                if abs(lx[i] - lx[j]) < dx_span * 0.24 and abs(ly[i] - ly[j]) < dy_span * 0.12:
                    push = dy_span * 0.065
                    if ly[i] >= ly[j]:
                        ly[i] += push; ly[j] -= push * 0.6
                    else:
                        ly[j] += push; ly[i] -= push * 0.6
    for i, (xv, yv, lbl) in enumerate(zip(xs, ys, labels)):
        is_ours = ('ours' in lbl.lower()) or (i == len(rows) - 1)
        ax.scatter(
            xv, yv,
            s=155 if is_ours else 84,
            marker='*' if is_ours else 'o',
            color=COLORS[0 if is_ours else (i + 1) % len(COLORS)],
            edgecolors='#16191F', linewidths=0.8, zorder=5 if is_ours else 3,
        )
        ax.annotate(
            lbl, (xv, yv), xytext=(lx[i], ly[i]),
            fontsize=max(8.0, {font_size} - 1.2),
            fontweight='bold' if is_ours else 'normal',
            arrowprops=dict(arrowstyle='-', color='#94A3B8', lw=0.75, shrinkA=2, shrinkB=4),
            bbox=dict(facecolor='white', edgecolor='none', alpha=0.8, pad=0.8),
        )
    ax.set_xlabel({(xlabel or "Compute Cost")!r} or x_col, labelpad={sp['labelpad']})
    ax.set_ylabel({(ylabel or "Performance")!r} or y_col, labelpad={sp['labelpad']})
    ax.margins(x=0.22, y=0.22)

elif CHART_TYPE == 'radar':
    plt.close(fig)
    fig, ax = plt.subplots(figsize=({width_in}, {height_in}), dpi=200, subplot_kw={{'polar': True}})
    cols = PLOT_COLS[:6]
    angles = np.linspace(0, 2 * np.pi, len(cols), endpoint=False).tolist()
    angles += angles[:1]
    series_names = labels
    for mi, r in enumerate(rows):
        vals = [to_float(r[headers.index(c)]) for c in cols]
        vals += vals[:1]
        ax.plot(angles, vals, linewidth={line_width}, color=COLORS[mi % len(COLORS)], label=r[0])
        ax.fill(angles, vals, color=COLORS[mi % len(COLORS)], alpha=0.09)
    ax.set_xticks(angles[:-1])
    ax.set_xticklabels(cols)
    ax.tick_params(pad=10)

if CHART_TYPE not in ('heatmap', 'radar'):
    ax.spines['top'].set_visible(False)
    ax.spines['right'].set_visible(False)
    ax.tick_params(axis='both', pad={sp['tickpad']}, length=4.5)
    if {show_grid!r}:
        ax.grid(axis='x' if CHART_TYPE == 'horizontal_bar' else ('y' if CHART_TYPE in ('grouped_bar', 'error_bar', 'dual_axis') else 'both'), linestyle='--', alpha=0.35, color='#9AA1AC', zorder=0)
    if CHART_TYPE in ('grouped_bar', 'error_bar', 'line_curve'):
        {legend_code}
elif CHART_TYPE == 'radar':
    {legend_code}

if {title!r}:
    ax.set_title({title!r}, pad={sp['title_pad']} if ({legend_pos!r} == 'top' and CHART_TYPE in ('grouped_bar', 'error_bar', 'line_curve', 'dual_axis')) else 14, fontweight='semibold')

fig.tight_layout(pad={sp['pad']})
"""
    return code


def execute_matplotlib_code(code: str, dpi: int = 600) -> dict[str, Any]:
    """Safely execute matplotlib code and return Vector SVG, High-DPI PNG (up to 1200 DPI), and Vector PDF."""
    banned = re.search(r"\b(os\.system|subprocess|shutil\.rmtree|eval\(|exec\(|__import__|open\(|socket|urllib|requests|httpx)\b", code)
    if banned:
        raise ValueError(f"Blocked unsafe token in plotting code: `{banned.group(0)}`")

    ns: dict[str, Any] = {"__builtins__": {
        "len": len, "range": range, "min": min, "max": max, "sum": sum, "abs": abs,
        "round": round, "float": float, "int": int, "str": str, "list": list, "dict": dict,
        "tuple": tuple, "set": set, "zip": zip, "enumerate": enumerate, "sorted": sorted,
        "any": any, "all": all, "map": map, "filter": filter, "bool": bool, "print": lambda *a, **k: None,
        "__import__": lambda name, *a, **k: __import__(name, *a, **k) if name in ("csv", "io", "math", "numpy", "matplotlib", "matplotlib.pyplot") else (_ for _ in ()).throw(ImportError(f"Import `{name}` not allowed")),
    }}
    plt.close("all")
    exec(code, ns, ns)
    fig = ns.get("fig") or plt.gcf()

    clamped_dpi = max(150, min(1200, int(dpi)))

    svg_buf = io.StringIO()
    fig.savefig(svg_buf, format="svg", bbox_inches="tight", pad_inches=0.22, facecolor="white")
    svg_str = svg_buf.getvalue()

    png_buf = io.BytesIO()
    fig.savefig(png_buf, format="png", dpi=clamped_dpi, bbox_inches="tight", pad_inches=0.22, facecolor="white")
    png_b64 = base64.b64encode(png_buf.getvalue()).decode("ascii")

    pdf_buf = io.BytesIO()
    fig.savefig(pdf_buf, format="pdf", bbox_inches="tight", pad_inches=0.22, facecolor="white")
    pdf_b64 = base64.b64encode(pdf_buf.getvalue()).decode("ascii")

    plt.close(fig)
    return {"svg": svg_str, "png_b64": png_b64, "pdf_b64": pdf_b64, "dpi": clamped_dpi}


# ---------- Publication Table Generator (LaTeX booktabs + Word Three-Line Table) ----------
def _rank_columns(parsed: dict[str, Any], lower_is_better: list[str]) -> dict[int, tuple[float | None, float | None]]:
    """Find best and second-best numeric value per numeric column."""
    headers, rows, num_cols = parsed["headers"], parsed["rows"], parsed["num_cols"]
    low_set = {c.lower() for c in lower_is_better}
    ranks: dict[int, tuple[float | None, float | None]] = {}
    for ci, h in enumerate(headers):
        if h not in num_cols or ci == 0:
            continue
        vals = []
        for r in rows:
            try:
                vals.append(float(r[ci].split("±")[0].replace("%", "").strip()))
            except ValueError:
                pass
        uniq = sorted(set(vals), reverse=(h.lower() not in low_set))
        best = uniq[0] if len(uniq) >= 1 else None
        second = uniq[1] if len(uniq) >= 2 else None
        ranks[ci] = (best, second)
    return ranks


def generate_academic_table(
    csv_text: str,
    caption: str = "Quantitative comparison across benchmarks. Best results are in bold and second-best are underlined.",
    label: str = "tab:main_results",
    lower_is_better: list[str] | None = None,
    decimals: int | None = None,
    highlight_best: bool = True,
) -> dict[str, Any]:
    """Produce publication-ready LaTeX booktabs + structured preview matrix."""
    parsed = parse_csv_data(csv_text)
    headers, rows = parsed["headers"], parsed["rows"]
    low_list = lower_is_better or []
    low_set = {c.lower() for c in low_list}
    ranks = _rank_columns(parsed, low_list) if highlight_best else {}

    def fmt_val(raw: str, is_num: bool) -> tuple[str, float | None]:
        parts = raw.split("±")
        try:
            v = float(parts[0].replace("%", "").strip())
            s = f"{v:.{decimals}f}" if decimals is not None else parts[0].strip()
            if len(parts) > 1:
                s = f"{s} ± {parts[1].strip()}"
            return s, v
        except ValueError:
            return raw, None

    col_spec = "l" + "c" * (len(headers) - 1)
    tex_headers = []
    for ci, h in enumerate(headers):
        arrow = " $\\downarrow$" if h.lower() in low_set else (" $\\uparrow$" if (h in parsed["num_cols"] and ci > 0) else "")
        tex_headers.append(f"\\textbf{{{h.replace('_', ' ')}}}{arrow}")

    tex_lines = [
        "\\begin{table}[t]",
        "  \\centering",
        f"  \\caption{{{caption}}}",
        f"  \\label{{{label}}}",
        "  \\small",
        "  \\setlength{\\tabcolsep}{6pt}",
        f"  \\begin{{tabular}}{{{col_spec}}}",
        "    \\toprule",
        "    " + " & ".join(tex_headers) + " \\\\",
        "    \\midrule",
    ]

    preview_rows: list[list[dict[str, Any]]] = []
    for ri, r in enumerate(rows):
        row_cells = []
        tex_cells = []
        is_ours = "ours" in r[0].lower()
        if is_ours and ri == len(rows) - 1 and len(rows) > 1:
            tex_lines.append("    \\midrule")
        for ci, raw in enumerate(r):
            disp, num_v = fmt_val(raw, headers[ci] in parsed["num_cols"])
            best, second = ranks.get(ci, (None, None))
            rank_tag = "normal"
            tex_cell = disp.replace("±", "$\\pm$").replace("_", "\\_").replace("%", "\\%")
            if num_v is not None and best is not None and math.isclose(num_v, best, rel_tol=1e-9):
                rank_tag = "best"
                tex_cell = f"\\textbf{{{tex_cell}}}"
            elif num_v is not None and second is not None and math.isclose(num_v, second, rel_tol=1e-9):
                rank_tag = "second"
                tex_cell = f"\\underline{{{tex_cell}}}"
            elif ci == 0 and is_ours:
                tex_cell = f"\\textbf{{{tex_cell}}}"
            tex_cells.append(tex_cell)
            row_cells.append({"text": disp, "rank": rank_tag, "is_ours": is_ours})
        tex_lines.append("    " + " & ".join(tex_cells) + " \\\\")
        preview_rows.append(row_cells)

    tex_lines += [
        "    \\bottomrule",
        "  \\end{tabular}",
        "\\end{table}",
    ]

    return {
        "headers": [
            {"label": h.replace("_", " "), "direction": "down" if h.lower() in low_set else ("up" if (h in parsed["num_cols"] and ci > 0) else "none")}
            for ci, h in enumerate(headers)
        ],
        "rows": preview_rows,
        "latex": "\n".join(tex_lines),
    }


def export_word_threeline_table_bytes(
    csv_text: str,
    caption: str = "Table 1. Quantitative comparison across benchmarks.",
    lower_is_better: list[str] | None = None,
    decimals: int | None = None,
) -> bytes:
    """Export a true academic Word Three-Line Table (.docx) with bold best & underlined second-best."""
    tbl_data = generate_academic_table(csv_text, caption=caption, lower_is_better=lower_is_better, decimals=decimals)
    doc = Document()
    normal = doc.styles["Normal"]
    normal.font.name = "Times New Roman"
    normal.font.size = Pt(10.5)

    cap_p = doc.add_paragraph()
    cap_p.paragraph_format.space_after = Pt(6)
    c_run = cap_p.add_run(caption)
    c_run.bold = True
    c_run.font.size = Pt(10)

    n_cols = len(tbl_data["headers"])
    table = doc.add_table(rows=1 + len(tbl_data["rows"]), cols=n_cols)
    table.alignment = WD_TABLE_ALIGNMENT.CENTER

    # Remove all default cell borders
    tblPr = table._tbl.tblPr
    borders = parse_xml(
        f'<w:tblBorders {nsdecls("w")}>'
        '<w:top w:val="single" w:sz="12" w:space="0" w:color="16191F"/>'
        '<w:bottom w:val="single" w:sz="12" w:space="0" w:color="16191F"/>'
        '<w:left w:val="none"/><w:right w:val="none"/>'
        '<w:insideH w:val="none"/><w:insideV w:val="none"/>'
        "</w:tblBorders>"
    )
    tblPr.append(borders)

    # Header row with crisp bottom thin rule
    for ci, h in enumerate(tbl_data["headers"]):
        cell = table.rows[0].cells[ci]
        tcPr = cell._tc.get_or_add_tcPr()
        tcPr.append(parse_xml(f'<w:tcBorders {nsdecls("w")}><w:bottom w:val="single" w:sz="6" w:space="0" w:color="16191F"/></w:tcBorders>'))
        p = cell.paragraphs[0]
        arrow = " ↓" if h["direction"] == "down" else (" ↑" if h["direction"] == "up" else "")
        run = p.add_run(h["label"] + arrow)
        run.bold = True
        run.font.name = "Times New Roman"
        run.font.size = Pt(10)

    for ri, row in enumerate(tbl_data["rows"], 1):
        for ci, cell_info in enumerate(row):
            cell = table.rows[ri].cells[ci]
            p = cell.paragraphs[0]
            run = p.add_run(cell_info["text"])
            run.font.name = "Times New Roman"
            run.font.size = Pt(10)
            if cell_info["rank"] == "best" or (ci == 0 and cell_info["is_ours"]):
                run.bold = True
            elif cell_info["rank"] == "second":
                run.underline = True

    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()
