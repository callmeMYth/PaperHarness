"""First-class Word (.docx), LaTeX (.tex), PDF, Markdown, and arXiv I/O.

Highlights:
- Imports .docx (paragraphs, headings, tables), .tex (preserving preamble & LaTeX commands),
  .pdf (PyMuPDF), .md, and arXiv IDs (lossless LaTeXML HTML math).
- Exports native Microsoft Word (.docx) WITH GENUINE TRACK CHANGES (<w:ins>/<w:del> XML)
  so advisors & co-authors can accept/reject edits inside Microsoft Word!
- Exports clean publication .docx, clean .tex, and MathJax-rendered HTML.
"""
from __future__ import annotations

import difflib
import io
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from docx import Document
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Inches, Pt, RGBColor

ARXIV_RE = re.compile(r"^(?:arxiv:)?(\d{4}\.\d{4,5}(?:v\d+)?)$", re.I)

# ---------- Sample English Paper (Pre-loaded for instant out-of-the-box experience) ----------
SAMPLE_PAPER = {
    "id": "sample-cvpr-2026",
    "title": "HierAttn-Net: Adaptive Cross-Scale Token Routing for High-Resolution Vision-Language Understanding",
    "source_type": "latex",
    "venue": "CVPR / ICCV",
    "content": r"""\section{Abstract}
In recent years, deep learning has developed rapidly and multimodal large language models have achieved remarkable progress in vision-language understanding. However, existing methods always suffer from quadratic computational complexity when processing high-resolution images, which makes them inefficient in practical deployment. To this end, we adopt a novel hierarchical token routing framework named HierAttn-Net, which delves into the intricate interplay between local fine-grained patches and global semantic priors. Specifically, we design a dynamic gating mechanism to selectively preserve informative visual tokens while discarding redundant background regions. The experimental results show that our proposed method completely solves the resolution bottleneck and proves the superiority of our design on DocVQA, ChartQA, and TextVQA benchmarks, significantly outperforming previous baselines by up to 4.8% while reducing FLOPs by 41.2%.

\section{Introduction}
With the rapid development of Vision-Language Models (VLMs), high-resolution perception has become a pivotal capability for document understanding, chart reasoning, and fine-grained visual question answering \cite{liu2024llavanext,chen2024internvl}. Besides, conventional patch-splitting pipelines treat every spatial region equally, producing thousands of redundant background tokens that overwhelm the language backbone.

In this way, naively scaling input resolution leads to prohibitive memory footprint and latency. Meanwhile, existing token pruning approaches rely on static top-k selection or heuristic attention thresholds, which don't adapt well to dense text regions where small characters carry critical semantics \cite{bolya2023tome,chen2024fastv}. Consequently, there is a pressing need for a content-aware routing mechanism that dynamically allocates token capacity according to local information density.

In order to verify the effectiveness of adaptive routing, we formulate token selection as a differentiable budget-constrained optimization problem. Our method seamlessly integrates a lightweight Cross-Scale Importance Estimator (CSIE) with a Residual Semantic Merger (RSM) so that discarded background tokens still contribute global context without inflating sequence length.

\section{Method}
Given an input image $I \in \mathbb{R}^{H \times W \times 3}$, a visual encoder extracts multi-scale patch embeddings $\mathbf{X} \in \mathbb{R}^{N \times D}$, where $N$ denotes the total number of visual patches and $D$ is the hidden dimension. Rather than uniformly downsampling all spatial locations, we estimate the semantic saliency score of each patch conditioned on the text query embedding $\mathbf{q} \in \mathbb{R}^{D}$:
\begin{equation}
s_i = \sigma\left( \frac{(\mathbf{W}_q \mathbf{q})^\top (\mathbf{W}_k \mathbf{x}_i)}{\sqrt{D}} + \alpha \cdot \mathrm{MLP}(\mathbf{x}_i) \right), \quad i = 1, \dots, N
\label{eq:saliency}
\end{equation}
where $\sigma(\cdot)$ is the sigmoid activation, $\mathbf{W}_q, \mathbf{W}_k \in \mathbb{R}^{D \times D}$ are learnable projection matrices, and $\alpha$ balances query-guided relevance against intrinsic visual salience.

Based on the saliency distribution, we partition visual tokens into a retained high-resolution set $\mathcal{R}$ and a pruned background set $\mathcal{P}$. To prevent loss of global scene layout, the pruned tokens are aggregated into $M$ compact summary tokens via saliency-weighted pooling:
\begin{equation}
\mathbf{z}_m = \sum_{j \in \mathcal{P}_m} \frac{\exp(s_j / \tau)}{\sum_{u \in \mathcal{P}_m} \exp(s_u / \tau)} \mathbf{x}_j
\label{eq:merge}
\end{equation}
where $\tau$ is a learnable temperature parameter controlling aggregation sharpness. Finally, the LLM backbone receives the concatenated token sequence $[\mathbf{X}_{\mathcal{R}}; \mathbf{Z}]$, reducing visual token length from $N$ to $|\mathcal{R}| + M$.

\section{Experiments}
We evaluate HierAttn-Net on five high-resolution benchmarks: DocVQA, ChartQA, InfoVQA, TextVQA, and OCRBench. All experiments are conducted on 8 NVIDIA A100 GPUs using identical training recipes for fair comparison. As shown in Table 1, our approach achieves 91.4% ANLS on DocVQA and 83.6% relaxed accuracy on ChartQA while cutting visual token FLOPs by 41.2%. Moreover, ablation studies confirm that combining query-guided gating with residual merging yields consistent gains across both 7B and 13B language backbones.
""",
    "bibtex": r"""@inproceedings{liu2024llavanext,
  title={Improved Baselines with Visual Instruction Tuning},
  author={Liu, Haotian and Li, Chunyuan and Li, Yuheng and Lee, Yong Jae},
  booktitle={Proceedings of the IEEE/CVF Conference on Computer Vision and Pattern Recognition (CVPR)},
  year={2024}
}

@inproceedings{chen2024internvl,
  title={InternVL: Scaling up Vision Foundation Models and Aligning for Generic Visual-Linguistic Tasks},
  author={Chen, Zhe and Wu, Jiannan and Wang, Wenhai and Su, Weijie and Chen, Guo and Xing, Sen and Zhong, Muyan and Zhang, Qinglong and Zhu, Xizhou and Lu, Lewei and others},
  booktitle={Proceedings of the IEEE/CVF Conference on Computer Vision and Pattern Recognition (CVPR)},
  year={2024}
}

@inproceedings{bolya2023tome,
  title={Token Merging: Your ViT But Faster},
  author={Bolya, Daniel and Fu, Cheng-Yang and Dai, Xiaoliang and Zhang, Peizhao and Feichtenhofer, Christoph and Hoffman, Judy},
  booktitle={International Conference on Learning Representations (ICLR)},
  year={2023}
}

@inproceedings{chen2024fastv,
  title={An Image is Worth 1/2 Tokens After Layer 2: Plug-and-Play Inference Acceleration for Large Vision-Language Models},
  author={Chen, Liang and Zhao, Haozhe and Liu, Tianyu and Bai, Shuai and Lin, Junyang and Zhou, Chang and Chang, Baobao},
  booktitle={European Conference on Computer Vision (ECCV)},
  year={2024}
}
""",
}


def parse_outline(content: str, source_type: str = "latex") -> list[dict[str, Any]]:
    """Extract clean structural outline (sections, equations, figures, tables) for the left drawer."""
    outline: list[dict[str, Any]] = []
    lines = content.splitlines()
    for lineno, line in enumerate(lines, 1):
        s = line.strip()
        # LaTeX headings
        m_tex = re.match(r"^\\(section|subsection|subsubsection)\*?\{((?:[^{}]|\{[^{}]*\})*)\}", s)
        if m_tex:
            lvl = {"section": 1, "subsection": 2, "subsubsection": 3}[m_tex.group(1)]
            outline.append({"kind": "section", "level": lvl, "title": m_tex.group(2).strip(), "line": lineno})
            continue
        # Markdown headings
        m_md = re.match(r"^(#{1,3})\s+(.+)$", s)
        if m_md:
            outline.append({"kind": "section", "level": len(m_md.group(1)), "title": m_md.group(2).strip(), "line": lineno})
            continue
        # Equation labels
        m_eq = re.search(r"\\label\{(eq:[^}]+)\}", s)
        if m_eq:
            outline.append({"kind": "equation", "level": 2, "title": m_eq.group(1), "line": lineno})
    return outline


def import_docx_bytes(filename: str, data: bytes) -> dict[str, Any]:
    """Read a Word .docx file cleanly into structured editable manuscript text."""
    doc = Document(io.BytesIO(data))
    blocks: list[str] = []
    title = Path(filename).stem

    for p in doc.paragraphs:
        txt = p.text.strip()
        if not txt:
            continue
        style_name = (p.style.name if p.style else "").lower()
        if "title" in style_name and title == Path(filename).stem:
            title = txt
            continue
        if "heading 1" in style_name:
            blocks.append(f"## {txt}")
        elif "heading 2" in style_name:
            blocks.append(f"### {txt}")
        elif "heading 3" in style_name:
            blocks.append(f"#### {txt}")
        else:
            blocks.append(txt)

    # Also capture simple tables as markdown
    for ti, tbl in enumerate(doc.tables, 1):
        rows = [[cell.text.strip().replace("\n", " ") for cell in row.cells] for row in tbl.rows]
        if rows:
            header = "| " + " | ".join(rows[0]) + " |"
            sep = "| " + " | ".join(["---"] * len(rows[0])) + " |"
            body = ["| " + " | ".join(r) + " |" for r in rows[1:]]
            blocks.append(f"<!-- Table {ti} -->\n" + "\n".join([header, sep] + body))

    content = "\n\n".join(blocks)
    return {
        "title": title,
        "source_type": "docx",
        "filename": filename,
        "content": content,
        "outline": parse_outline(content, "docx"),
    }


def import_tex_bytes(filename: str, data: bytes) -> dict[str, Any]:
    text = data.decode("utf-8-sig", errors="replace")
    tm = re.search(r"\\title\{((?:[^{}]|\{[^{}]*\})*)\}", text)
    title = tm.group(1).strip() if tm else Path(filename).stem
    preamble = ""
    body = text
    if "\\begin{document}" in text:
        preamble, rest = text.split("\\begin{document}", 1)
        body = rest.split("\\end{document}", 1)[0].strip()
    return {
        "title": title,
        "source_type": "latex",
        "filename": filename,
        "preamble": preamble,
        "content": body,
        "outline": parse_outline(body, "latex"),
    }


def import_pdf_bytes(filename: str, data: bytes) -> dict[str, Any]:
    import fitz  # PyMuPDF

    doc = fitz.open(stream=data, filetype="pdf")
    full: list[str] = []
    for page in doc:
        blocks = page.get_text("blocks")
        blocks.sort(key=lambda b: (round(b[1] / 15), b[0]))
        for b in blocks:
            txt = re.sub(r"-\n(\w)", r"\1", b[4]).replace("\n", " ").strip()
            txt = re.sub(r"\s+", " ", txt)
            if len(txt) >= 15:
                full.append(txt)
    title = full[0] if full else Path(filename).stem
    sec_re = re.compile(r"^(?:Abstract|\d+\.?\s+[A-Z][A-Za-z0-9\s\-:]{2,60}|[IVX]+\.\s+[A-Z\s\-]{3,60})$")
    out_blocks: list[str] = []
    for p in full[1:]:
        if sec_re.match(p) and len(p) < 80:
            out_blocks.append(f"## {p}")
        else:
            out_blocks.append(p)
    content = "\n\n".join(out_blocks)
    return {
        "title": title,
        "source_type": "markdown",
        "filename": filename,
        "content": content,
        "outline": parse_outline(content, "markdown"),
    }


def import_arxiv_paper(arxiv_id: str) -> dict[str, Any]:
    """Fetch arXiv LaTeXML HTML preserving math formulas via existing paper_io logic."""
    import requests
    from bs4 import BeautifulSoup

    m = ARXIV_RE.match(arxiv_id.strip())
    aid = m.group(1) if m else arxiv_id.strip()
    headers = {"User-Agent": "PaperHarness/0.1"}
    raw_html = None
    for url in [f"https://arxiv.org/html/{aid}", f"https://ar5iv.labs.arxiv.org/html/{aid}"]:
        try:
            r = requests.get(url, headers=headers, timeout=35, allow_redirects=True)
            if r.status_code == 200 and "ltx_document" in r.text[:60000]:
                raw_html = r.content
                break
        except Exception:
            continue
    if raw_html is None:
        raise ValueError(f"Could not fetch LaTeXML HTML for arXiv:{aid}. Please upload the PDF or .tex file.")

    soup = BeautifulSoup(raw_html, "html.parser")
    title_el = soup.find(class_="ltx_title_document")
    title = title_el.get_text(" ", strip=True) if title_el else f"arXiv:{aid}"

    def node_to_md(node) -> str:
        for mm in node.find_all("math"):
            tex = (mm.get("alttext") or mm.get_text(" ", strip=True)).strip()
            disp = mm.get("display") == "block"
            mm.replace_with(f"\n\n$${tex}$$\n\n" if disp else f" ${tex}$ ")
        for tag in node.find_all(class_=re.compile(r"\bltx_note_outer\b")):
            tag.decompose()
        txt = node.get_text(" ", strip=True)
        txt = re.sub(r"\s+([,.;:!?\)])", r"\1", txt)
        txt = re.sub(r"\(\s+", "(", txt)
        txt = re.sub(r"[ \t]{2,}", " ", txt)
        return txt.strip()

    md_parts: list[str] = []
    abs_div = soup.find(class_="ltx_abstract")
    if abs_div:
        md_parts.append("## Abstract")
        for p in abs_div.find_all("p", class_="ltx_p"):
            t = node_to_md(p)
            if t:
                md_parts.append(t)

    for sec in soup.find_all("section", class_=["ltx_section", "ltx_appendix"]):
        h = sec.find(["h2", "h3", "h4"], class_="ltx_title")
        head = h.get_text(" ", strip=True) if h else "Section"
        if re.search(r"^references$|^bibliography$", head, re.I):
            continue
        md_parts.append(f"## {head}")
        for el in sec.find_all(["h3", "h4", "p"], recursive=True):
            cls = el.get("class") or []
            if "ltx_title_subsection" in cls:
                md_parts.append(f"### {el.get_text(' ', strip=True)}")
            elif el.name == "p" and "ltx_p" in cls:
                if el.find_parent(class_="ltx_bibliography"):
                    continue
                t = node_to_md(el)
                if len(t) >= 12:
                    md_parts.append(t)

    content = "\n\n".join(md_parts)
    return {
        "title": title,
        "source_type": "arxiv",
        "filename": f"arxiv_{aid}.md",
        "content": content,
        "outline": parse_outline(content, "markdown"),
    }


# ---------- Export: Microsoft Word (.docx) WITH NATIVE TRACK CHANGES ----------
def _make_run_xml(text: str, font_name: str = "Times New Roman", font_size_half_pt: int = 22) -> OxmlElement:
    r = OxmlElement("w:r")
    rPr = OxmlElement("w:rPr")
    rFonts = OxmlElement("w:rFonts")
    rFonts.set(qn("w:ascii"), font_name)
    rFonts.set(qn("w:hAnsi"), font_name)
    rFonts.set(qn("w:eastAsia"), "SimSun")
    rPr.append(rFonts)
    sz = OxmlElement("w:sz")
    sz.set(qn("w:val"), str(font_size_half_pt))
    rPr.append(sz)
    r.append(rPr)
    t = OxmlElement("w:t")
    t.set(qn("xml:space"), "preserve")
    t.text = text
    r.append(t)
    return r


def _make_del_xml(text: str, rev_id: int, author: str, ts: str) -> OxmlElement:
    d = OxmlElement("w:del")
    d.set(qn("w:id"), str(rev_id))
    d.set(qn("w:author"), author)
    d.set(qn("w:date"), ts)
    r = OxmlElement("w:r")
    dt = OxmlElement("w:delText")
    dt.set(qn("xml:space"), "preserve")
    dt.text = text
    r.append(dt)
    d.append(r)
    return d


def _make_ins_xml(text: str, rev_id: int, author: str, ts: str) -> OxmlElement:
    ins = OxmlElement("w:ins")
    ins.set(qn("w:id"), str(rev_id))
    ins.set(qn("w:author"), author)
    ins.set(qn("w:date"), ts)
    ins.append(_make_run_xml(text))
    return ins


def _tokenize_for_diff(text: str) -> list[str]:
    return re.findall(r"\s+|[\u4e00-\u9fff]|[^\s\u4e00-\u9fff]+", text)


def export_docx_bytes(
    title: str,
    revised_text: str,
    original_text: str | None = None,
    track_changes: bool = True,
    author: str = "PaperHarness Co-Author",
) -> bytes:
    """Export publication-styled Word (.docx) with optional REAL Track Changes (w:ins / w:del)."""
    doc = Document()

    # Academic page margins (1 inch)
    for section in doc.sections:
        section.top_margin = Inches(1.0)
        section.bottom_margin = Inches(1.0)
        section.left_margin = Inches(1.0)
        section.right_margin = Inches(1.0)

    # Normal style: Times New Roman + SimSun 11pt
    normal = doc.styles["Normal"]
    normal.font.name = "Times New Roman"
    normal.font.size = Pt(11)
    normal._element.rPr.rFonts.set(qn("w:eastAsia"), "SimSun")

    # Enable trackRevisions flag in document settings when track_changes is True
    if track_changes and original_text is not None:
        settings_el = doc.settings.element
        if settings_el.find(qn("w:trackRevisions")) is None:
            settings_el.append(OxmlElement("w:trackRevisions"))

    # Paper Title
    tp = doc.add_paragraph()
    tp.paragraph_format.space_after = Pt(14)
    trun = tp.add_run(title or "Untitled Manuscript")
    trun.bold = True
    trun.font.size = Pt(16)
    trun.font.name = "Times New Roman"
    trun.font.color.rgb = RGBColor(0x16, 0x19, 0x1F)

    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    rev_id = 1

    def parse_blocks(txt: str) -> list[tuple[str, str]]:
        blocks = []
        for raw in re.split(r"\n\s*\n", txt.strip()):
            b = raw.strip()
            if not b:
                continue
            m_tex = re.match(r"^\\(section|subsection|subsubsection)\*?\{((?:[^{}]|\{[^{}]*\})*)\}([\s\S]*)", b)
            if m_tex:
                lvl = {"section": "h1", "subsection": "h2", "subsubsection": "h3"}[m_tex.group(1)]
                blocks.append((lvl, m_tex.group(2).strip()))
                rest = m_tex.group(3).strip()
                if rest:
                    blocks.append(("p", rest))
                continue
            m_md = re.match(r"^(#{1,3})\s+(.+?)(?:\n([\s\S]*))?$", b)
            if m_md:
                lvl = f"h{min(3, len(m_md.group(1)))}"
                blocks.append((lvl, m_md.group(2).strip()))
                if m_md.group(3) and m_md.group(3).strip():
                    blocks.append(("p", m_md.group(3).strip()))
                continue
            blocks.append(("p", b))
        return blocks

    rev_blocks = parse_blocks(revised_text)
    orig_blocks = parse_blocks(original_text) if (track_changes and original_text is not None) else []

    if track_changes and original_text is not None and len(orig_blocks) == len(rev_blocks):
        # Paragraph-aligned Track Changes!
        for (kind_r, txt_r), (_, txt_o) in zip(rev_blocks, orig_blocks):
            if kind_r.startswith("h"):
                lvl = int(kind_r[1])
                h = doc.add_heading(txt_r, level=lvl)
                for run in h.runs:
                    run.font.name = "Times New Roman"
                    run.font.color.rgb = RGBColor(0x1E, 0x3A, 0x5F)
                continue
            p = doc.add_paragraph()
            p.paragraph_format.line_spacing = 1.35
            p.paragraph_format.space_after = Pt(6)
            if txt_o == txt_r:
                p._p.append(_make_run_xml(txt_r))
            else:
                a_toks = _tokenize_for_diff(txt_o)
                b_toks = _tokenize_for_diff(txt_r)
                sm = difflib.SequenceMatcher(None, a_toks, b_toks)
                for tag, i1, i2, j1, j2 in sm.get_opcodes():
                    if tag == "equal":
                        p._p.append(_make_run_xml("".join(a_toks[i1:i2])))
                    elif tag == "delete":
                        p._p.append(_make_del_xml("".join(a_toks[i1:i2]), rev_id, author, ts))
                        rev_id += 1
                    elif tag == "insert":
                        p._p.append(_make_ins_xml("".join(b_toks[j1:j2]), rev_id, author, ts))
                        rev_id += 1
                    elif tag == "replace":
                        p._p.append(_make_del_xml("".join(a_toks[i1:i2]), rev_id, author, ts))
                        rev_id += 1
                        p._p.append(_make_ins_xml("".join(b_toks[j1:j2]), rev_id, author, ts))
                        rev_id += 1
    else:
        for kind_r, txt_r in rev_blocks:
            if kind_r.startswith("h"):
                lvl = int(kind_r[1])
                h = doc.add_heading(txt_r, level=lvl)
                for run in h.runs:
                    run.font.name = "Times New Roman"
                    run.font.color.rgb = RGBColor(0x1E, 0x3A, 0x5F)
            else:
                p = doc.add_paragraph()
                p.paragraph_format.line_spacing = 1.35
                p.paragraph_format.space_after = Pt(6)
                p._p.append(_make_run_xml(txt_r))

    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


def export_latex_string(title: str, content: str, preamble: str = "") -> str:
    """Produce a clean compilable LaTeX document."""
    if preamble.strip():
        return f"{preamble.strip()}\n\n\\begin{{document}}\n\\maketitle\n\n{content.strip()}\n\n\\end{{document}}\n"
    # Convert markdown headings if the user started from docx/md
    tex_body = content
    tex_body = re.sub(r"^##\s+(.+)$", r"\\section{\1}", tex_body, flags=re.M)
    tex_body = re.sub(r"^###\s+(.+)$", r"\\subsection{\1}", tex_body, flags=re.M)
    tex_body = re.sub(r"^####\s+(.+)$", r"\\subsubsection{\1}", tex_body, flags=re.M)
    return (
        "\\documentclass[10pt,twocolumn,letterpaper]{article}\n"
        "\\usepackage{amsmath,amssymb,booktabs,graphicx,hyperref}\n"
        f"\\title{{{title}}}\n"
        "\\author{PaperHarness Author}\n"
        "\\date{}\n\n"
        "\\begin{document}\n"
        "\\maketitle\n\n"
        f"{tex_body.strip()}\n\n"
        "\\end{document}\n"
    )
