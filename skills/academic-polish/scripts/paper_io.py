#!/usr/bin/env python
"""Paper I/O helper for full-paper translation (en2zh) and format mimicry (mimic).

Subcommands:
  extract <source> --out-dir <dir>
      <source> can be:
        - arXiv ID (e.g. 2103.14030 or arxiv:2103.14030) -> fetches LaTeXML HTML with lossless LaTeX math!
        - local .tex / .md / .txt / .pdf (PDF requires optional pymupdf)
      Writes:
        <dir>/paper.json            structured sections + paragraphs + metadata
        <dir>/sections/00_*.md      clean section-by-section English chunks for batch translation
        <dir>/translated/           empty folder where translated 00_*.md files should be saved

  export <work_dir> [--name paper]
      Reads <work_dir>/paper.json and <work_dir>/translated/*.md (same filenames as sections/*.md)
      Writes complete deliverables into <work_dir>/export/:
        <name>_zh.md                complete Chinese paper (Markdown + LaTeX math)
        <name>_bilingual.md         paragraph-by-paragraph English/Chinese bilingual Markdown
        <name>_zh.html              publication-styled HTML + MathJax (Ctrl+P -> clean PDF)
        <name>_bilingual.html       bilingual HTML + MathJax (Ctrl+P -> clean bilingual PDF)
"""
import argparse, html, json, re, sys
from pathlib import Path

ARXIV_RE = re.compile(r"^(?:arxiv:)?(\d{4}\.\d{4,5}(?:v\d+)?)$", re.I)


def slug(s):
    s = re.sub(r"[^a-zA-Z0-9]+", "_", s).strip("_").lower()
    return (s or "section")[:40]


# ---------- Ingestion: arXiv HTML ----------
def extract_arxiv(aid):
    try:
        import requests
        from bs4 import BeautifulSoup
    except ImportError:
        sys.exit("Fetching arXiv requires 'requests' and 'beautifulsoup4'. Install: pip install requests beautifulsoup4")

    headers = {"User-Agent": "academic-polish-paper-io/0.2"}
    raw_html = None
    for url in [f"https://arxiv.org/html/{aid}", f"https://ar5iv.labs.arxiv.org/html/{aid}"]:
        try:
            r = requests.get(url, headers=headers, timeout=40, allow_redirects=True)
            if r.status_code == 200 and "ltx_document" in r.text[:60000]:
                raw_html = r.content
                break
        except Exception:
            continue
    if raw_html is None:
        sys.exit(f"Could not fetch HTML for arXiv:{aid}. Download the PDF or .tex source and pass the local path.")

    soup = BeautifulSoup(raw_html, "html.parser")
    title_el = soup.find(class_="ltx_title_document")
    title = title_el.get_text(" ", strip=True) if title_el else f"arXiv:{aid}"
    authors = [a.get_text(" ", strip=True) for a in soup.find_all(class_="ltx_personname")]

    def node_to_md(node):
        # Preserve inline/display LaTeX math via alttext
        for m in node.find_all("math"):
            tex = (m.get("alttext") or m.get_text(" ", strip=True)).strip()
            disp = m.get("display") == "block"
            m.replace_with(f"\n\n$${tex}$$\n\n" if disp else f" ${tex}$ ")
        for tag in node.find_all(class_=re.compile(r"\bltx_note_outer\b")):
            tag.decompose()
        txt = node.get_text(" ", strip=True)
        txt = re.sub(r"\s+([,.;:!?\)])", r"\1", txt)
        txt = re.sub(r"\(\s+", "(", txt)
        txt = re.sub(r"[ \t]{2,}", " ", txt)
        return txt.strip()

    sections = []
    # Abstract
    abs_div = soup.find(class_="ltx_abstract")
    if abs_div:
        ps = [node_to_md(p) for p in abs_div.find_all("p", class_="ltx_p")]
        ps = [p for p in ps if p]
        if ps:
            sections.append({"heading": "Abstract", "level": 2, "paragraphs": ps})

    # Remove bibliography & figures/tables from main flow (keep captions as notes!)
    for fig in soup.find_all(class_=["ltx_figure", "ltx_table"]):
        cap = fig.find(class_="ltx_caption")
        if cap:
            cap_txt = node_to_md(cap)
            new_p = soup.new_tag("p", **{"class": "ltx_p ltx_extracted_caption"})
            new_p.string = f"> **[{ 'Table' if 'ltx_table' in (fig.get('class') or []) else 'Figure' } Caption]** {cap_txt}"
            fig.replace_with(new_p)
        else:
            fig.decompose()

    for sec in soup.find_all("section", class_=["ltx_section", "ltx_appendix"]):
        h = sec.find(["h2", "h3", "h4"], class_="ltx_title")
        head = h.get_text(" ", strip=True) if h else "Section"
        if re.search(r"^references$|^bibliography$", head, re.I):
            continue
        paras = []
        # Walk direct content and subsections in order
        for el in sec.find_all(["h3", "h4", "p", "table"], recursive=True):
            cls = el.get("class") or []
            if "ltx_title_subsection" in cls:
                paras.append(f"### {el.get_text(' ', strip=True)}")
            elif "ltx_title_subsubsection" in cls:
                paras.append(f"#### {el.get_text(' ', strip=True)}")
            elif el.name == "p" and "ltx_p" in cls:
                if el.find_parent(class_="ltx_bibliography"):
                    continue
                txt = node_to_md(el)
                if len(txt) >= 10:
                    paras.append(txt)
            elif el.name == "table" and ("ltx_equation" in cls or "ltx_equationgroup" in cls):
                if el.find_parent("table", class_="ltx_equationgroup"):
                    continue
                ms = [m.get("alttext", "").strip() for m in el.find_all("math") if m.get("alttext")]
                if ms:
                    body = " \\\\\n".join(ms) if len(ms) > 1 else ms[0]
                    paras.append(f"$$\n\\begin{{aligned}}\n{body}\n\\end{{aligned}}\n$$" if len(ms) > 1 else f"$$\n{body}\n$$")
        if paras:
            sections.append({"heading": head, "level": 2, "paragraphs": paras})

    return {"title": title, "authors": authors, "source": f"arxiv:{aid}", "sections": sections}


# ---------- Ingestion: local .tex / .md / .pdf ----------
def extract_md(path: Path):
    text = path.read_text(encoding="utf-8-sig")
    title = path.stem
    sections, cur_head, cur_ps = [], "Main", []
    for block in re.split(r"\n\s*\n", text):
        b = block.strip()
        if not b:
            continue
        m = re.match(r"^(#{1,3})\s+(.+)$", b)
        if m:
            lvl, h = len(m.group(1)), m.group(2).strip()
            if lvl == 1 and title == path.stem:
                title = h
                continue
            if cur_ps:
                sections.append({"heading": cur_head, "level": 2, "paragraphs": cur_ps})
            cur_head, cur_ps = h, []
        else:
            cur_ps.append(b)
    if cur_ps:
        sections.append({"heading": cur_head, "level": 2, "paragraphs": cur_ps})
    return {"title": title, "authors": [], "source": str(path), "sections": sections}


def extract_tex(path: Path):
    t = path.read_text(encoding="utf-8-sig", errors="ignore")
    t = re.sub(r"(?<!\\)%.*", "", t)
    tm = re.search(r"\\title\{((?:[^{}]|\{[^{}]*\})*)\}", t)
    title = tm.group(1).strip() if tm else path.stem
    body = t.split("\\begin{document}", 1)[-1].split("\\end{document}", 1)[0]
    body = re.split(r"\\bibliography\{|\\begin\{thebibliography\}", body)[0]
    sections = []
    am = re.search(r"\\begin\{abstract\}(.*?)\\end\{abstract\}", body, flags=re.S)
    if am:
        ps = [p.strip() for p in re.split(r"\n\s*\n", am.group(1)) if p.strip()]
        sections.append({"heading": "Abstract", "level": 2, "paragraphs": ps})
        body = body[am.end():]
    chunks = re.split(r"\\section\*?\{((?:[^{}]|\{[^{}]*\})*)\}", body)
    for i in range(1, len(chunks) - 1, 2):
        head, content = chunks[i].strip(), chunks[i + 1]
        content = re.sub(r"\\subsection\*?\{((?:[^{}]|\{[^{}]*\})*)\}", r"\n\n### \1\n\n", content)
        content = re.sub(r"\\subsubsection\*?\{((?:[^{}]|\{[^{}]*\})*)\}", r"\n\n#### \1\n\n", content)
        ps = [re.sub(r"\s+", " ", p).strip() for p in re.split(r"\n\s*\n", content) if len(p.strip()) >= 10]
        if ps:
            sections.append({"heading": head, "level": 2, "paragraphs": ps})
    return {"title": title, "authors": [], "source": str(path), "sections": sections}


def extract_pdf(path: Path):
    try:
        import fitz
    except ImportError:
        sys.exit("Local PDF extraction requires PyMuPDF: pip install pymupdf (or pass an arXiv ID instead).")
    doc = fitz.open(path)
    full = []
    for page in doc:
        blocks = page.get_text("blocks")
        blocks.sort(key=lambda b: (round(b[1] / 15), b[0]))
        for b in blocks:
            txt = re.sub(r"-\n(\w)", r"\1", b[4]).replace("\n", " ").strip()
            txt = re.sub(r"\s+", " ", txt)
            if len(txt) >= 15:
                full.append(txt)
    title = full[0] if full else path.stem
    sec_re = re.compile(r"^(?:Abstract|\d+\.?\s+[A-Z][A-Za-z0-9\s\-:]{2,60}|[IVX]+\.\s+[A-Z\s\-]{3,60})$")
    sections, cur_head, cur_ps = [], "Front Matter", []
    for p in full[1:]:
        if sec_re.match(p) and len(p) < 80:
            if cur_ps:
                sections.append({"heading": cur_head, "level": 2, "paragraphs": cur_ps})
            cur_head, cur_ps = p, []
        else:
            cur_ps.append(p)
    if cur_ps:
        sections.append({"heading": cur_head, "level": 2, "paragraphs": cur_ps})
    return {"title": title, "authors": [], "source": str(path), "sections": sections}


def cmd_extract(args):
    src = args.source.strip()
    m = ARXIV_RE.match(src)
    if m:
        paper = extract_arxiv(m.group(1))
    else:
        p = Path(src)
        if not p.exists():
            sys.exit(f"Source not found: {src}")
        ext = p.suffix.lower()
        if ext == ".pdf":
            paper = extract_pdf(p)
        elif ext == ".tex":
            paper = extract_tex(p)
        else:
            paper = extract_md(p)

    out_dir = Path(args.out_dir)
    sec_dir = out_dir / "sections"
    tr_dir = out_dir / "translated"
    sec_dir.mkdir(parents=True, exist_ok=True)
    tr_dir.mkdir(parents=True, exist_ok=True)

    manifest = []
    for i, sec in enumerate(paper["sections"]):
        fname = f"{i:02d}_{slug(sec['heading'])}.md"
        md = f"## {sec['heading']}\n\n" + "\n\n".join(sec["paragraphs"]) + "\n"
        (sec_dir / fname).write_text(md, encoding="utf-8")
        sec["file"] = fname
        manifest.append((fname, sec["heading"], len(sec["paragraphs"]), sum(len(p.split()) for p in sec["paragraphs"])))

    (out_dir / "paper.json").write_text(json.dumps(paper, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Extracted: {paper['title']}")
    print(f"Sections ({len(manifest)}) saved to {sec_dir}:")
    for fn, h, np_, nw in manifest:
        print(f"  {fn:36s} | {np_:3d} paras | {nw:5d} words | {h}")


# ---------- Export: Markdown + Self-Contained MathJax HTML ----------
HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<script>
window.MathJax = {{
  tex: {{ inlineMath: [['$', '$'], ['\\\\(', '\\\\)']], displayMath: [['$$', '$$'], ['\\\\[', '\\\\]']] }},
  svg: {{ fontCache: 'global' }}
}};
</script>
<script defer src="https://cdn.jsdelivr.net/npm/mathjax@3/es5/tex-svg.js"></script>
<style>
  :root {{ --fg: #1f2937; --muted: #6b7280; --border: #e5e7eb; --accent: #2563eb; --bg-en: #f8fafc; }}
  body {{ font-family: "Noto Serif SC", "Songti SC", "Microsoft YaHei", Georgia, serif; color: var(--fg);
         max-width: 860px; margin: 2.2rem auto; padding: 0 1.4rem; line-height: 1.85; font-size: 16px; }}
  h1 {{ font-size: 1.75rem; line-height: 1.35; margin-bottom: 0.4rem; border-bottom: 2px solid var(--accent); padding-bottom: 0.5rem; }}
  .meta {{ color: var(--muted); font-size: 0.92rem; margin-bottom: 1.8rem; }}
  h2 {{ font-size: 1.35rem; margin-top: 2rem; border-left: 4px solid var(--accent); padding-left: 0.6rem; }}
  h3 {{ font-size: 1.12rem; margin-top: 1.4rem; color: #111827; }}
  h4 {{ font-size: 1rem; margin-top: 1rem; color: #374151; }}
  p {{ margin: 0.8rem 0; text-align: justify; }}
  blockquote {{ margin: 0.9rem 0; padding: 0.6rem 1rem; background: #f1f5f9; border-left: 3px solid #64748b; font-size: 0.94rem; }}
  .bi-pair {{ margin: 1.1rem 0; padding-bottom: 0.9rem; border-bottom: 1px dashed var(--border); }}
  .bi-en {{ background: var(--bg-en); padding: 0.6rem 0.9rem; border-radius: 6px; color: #475569; font-size: 0.92rem; line-height: 1.65; margin-bottom: 0.5rem; }}
  .bi-zh {{ padding: 0.2rem 0.2rem; }}
  code {{ background: #f3f4f6; padding: 0.1rem 0.35rem; border-radius: 4px; font-size: 0.9em; }}
  @media print {{
    body {{ max-width: none; margin: 0; font-size: 11pt; line-height: 1.65; }}
    h2 {{ page-break-after: avoid; }}
    .bi-pair {{ page-break-inside: avoid; }}
  }}
</style>
</head>
<body>
<h1>{title}</h1>
<div class="meta">{meta}</div>
{body}
</body>
</html>
"""


def md_inline_to_html(text):
    # Protect math spans before escaping HTML
    maths = []
    def keep_math(m):
        maths.append(m.group(0))
        return f"@@MATH{len(maths)-1}@@"
    t = re.sub(r"\$\$.*?\$\$|\$[^$\n]+\$", keep_math, text, flags=re.S)
    t = html.escape(t)
    t = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", t)
    t = re.sub(r"\*(.+?)\*", r"<em>\1</em>", t)
    t = re.sub(r"`([^`]+)`", r"<code>\1</code>", t)
    for i, m in enumerate(maths):
        t = t.replace(f"@@MATH{i}@@", m)
    return t


def block_to_html(b):
    b = b.strip()
    if b.startswith("#### "):
        return f"<h4>{md_inline_to_html(b[5:])}</h4>"
    if b.startswith("### "):
        return f"<h3>{md_inline_to_html(b[4:])}</h3>"
    if b.startswith("## "):
        return f"<h2>{md_inline_to_html(b[3:])}</h2>"
    if b.startswith("> "):
        return f"<blockquote>{md_inline_to_html(b[2:])}</blockquote>"
    return f"<p>{md_inline_to_html(b)}</p>"


def parse_blocks(md_text):
    blocks = [b.strip() for b in re.split(r"\n\s*\n", md_text.strip()) if b.strip()]
    head = None
    if blocks and blocks[0].startswith("## "):
        head = blocks[0][3:].strip()
        blocks = blocks[1:]
    return head, blocks


def cmd_export(args):
    work_dir = Path(args.work_dir)
    paper = json.loads((work_dir / "paper.json").read_text(encoding="utf-8"))
    tr_dir = work_dir / "translated"
    exp_dir = work_dir / "export"
    exp_dir.mkdir(parents=True, exist_ok=True)
    name = args.name or slug(paper["title"])

    zh_title = args.zh_title or paper["title"]
    authors_str = ", ".join(paper.get("authors") or [])
    meta_line = f"Source: {paper.get('source', '')}" + (f" | Authors: {authors_str}" if authors_str else "")

    zh_md = [f"# {zh_title}\n", f"> 原题：{paper['title']}  \n> {meta_line}\n"]
    bi_md = [f"# {zh_title}（中英对照）\n", f"> Original Title: {paper['title']}  \n> {meta_line}\n"]
    zh_html_parts, bi_html_parts = [], []

    missing = []
    for sec in paper["sections"]:
        en_head = sec["heading"]
        en_paras = sec["paragraphs"]
        tr_file = tr_dir / sec["file"]
        if tr_file.exists():
            zh_head, zh_paras = parse_blocks(tr_file.read_text(encoding="utf-8-sig"))
            zh_head = zh_head or en_head
        else:
            missing.append(sec["file"])
            zh_head, zh_paras = en_head, [f"*(待翻译 / Untranslated)* {p}" for p in en_paras]

        zh_md.append(f"\n## {zh_head}\n")
        bi_md.append(f"\n## {zh_head} / {en_head}\n")
        zh_html_parts.append(f"<h2>{md_inline_to_html(zh_head)}</h2>")
        bi_html_parts.append(f"<h2>{md_inline_to_html(zh_head)} <span style='color:#6b7280;font-weight:normal'>/ {html.escape(en_head)}</span></h2>")

        for zp in zh_paras:
            zh_md.append(zp + "\n")
            zh_html_parts.append(block_to_html(zp))

        n = max(len(en_paras), len(zh_paras))
        for i in range(n):
            ep = en_paras[i] if i < len(en_paras) else ""
            zp = zh_paras[i] if i < len(zh_paras) else ""
            if ep:
                bi_md.append(f"> {ep}\n")
            if zp:
                bi_md.append(f"{zp}\n")
            bi_html_parts.append(
                "<div class='bi-pair'>"
                + (f"<div class='bi-en'>{block_to_html(ep)}</div>" if ep else "")
                + (f"<div class='bi-zh'>{block_to_html(zp)}</div>" if zp else "")
                + "</div>"
            )

    (exp_dir / f"{name}_zh.md").write_text("\n".join(zh_md), encoding="utf-8")
    (exp_dir / f"{name}_bilingual.md").write_text("\n".join(bi_md), encoding="utf-8")
    (exp_dir / f"{name}_zh.html").write_text(
        HTML_TEMPLATE.format(title=html.escape(zh_title), meta=html.escape(meta_line), body="\n".join(zh_html_parts)),
        encoding="utf-8",
    )
    (exp_dir / f"{name}_bilingual.html").write_text(
        HTML_TEMPLATE.format(title=html.escape(zh_title + "（中英对照）"), meta=html.escape(meta_line), body="\n".join(bi_html_parts)),
        encoding="utf-8",
    )
    print(f"Exported 4 files to {exp_dir}:")
    for suffix in ("_zh.md", "_bilingual.md", "_zh.html", "_bilingual.html"):
        print("  -", exp_dir / f"{name}{suffix}")
    if missing:
        print(f"Warning: {len(missing)} untranslated section(s): {missing}")


def main():
    ap = argparse.ArgumentParser(description="Extract and export full academic papers for en2zh / mimic.")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p1 = sub.add_parser("extract", help="Extract sections from arXiv ID, .tex, .md, or .pdf")
    p1.add_argument("source", help="arXiv ID (e.g. 2103.14030) or local file path")
    p1.add_argument("--out-dir", required=True)
    p1.set_defaults(func=cmd_extract)

    p2 = sub.add_parser("export", help="Assemble translated sections into MD & MathJax HTML")
    p2.add_argument("work_dir")
    p2.add_argument("--name", default=None)
    p2.add_argument("--zh-title", default=None)
    p2.set_defaults(func=cmd_export)

    args = ap.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
