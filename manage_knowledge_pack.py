"""Developer CLI for updating PaperHarness external knowledge pack & exporting fine-tuning data.

Usage (for project maintainer — hidden from end-user classmate UI):
  python manage_knowledge_pack.py ingest --pack lab_v2 --files paper1.pdf paper2.tex --venue CVPR
  python manage_knowledge_pack.py export-sft --format sft_openai --out train_sft.jsonl
  python manage_knowledge_pack.py package-override --out knowledge_pack.zip
"""
from __future__ import annotations

import argparse
import shutil
import zipfile
from pathlib import Path

from backend.config import DATA_DIR, get_skill_dir
from backend.services.corpus_trainer import (
    create_corpus_pack,
    export_training_dataset_jsonl,
    ingest_uploaded_file_into_pack,
    list_corpus_packs,
)


def main() -> None:
    parser = argparse.ArgumentParser(description="PaperHarness Maintainer Knowledge Pack CLI")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_ing = sub.add_parser("ingest", help="Ingest PDF/TeX/Docx papers into a local corpus pack")
    p_ing.add_argument("--pack", default="maintainer_pack", help="Pack name")
    p_ing.add_argument("--venue", default="CVPR", help="Target venue tag")
    p_ing.add_argument("--year", type=int, default=2026)
    p_ing.add_argument("--files", nargs="+", required=True, help="Paths to .pdf/.tex/.docx files")

    p_exp = sub.add_parser("export-sft", help="Export SFT or DPO training JSONL")
    p_exp.add_argument("--format", default="sft_openai", choices=["sft_openai", "sft_sharegpt", "dpo"])
    p_exp.add_argument("--out", default="paperharness_train.jsonl")

    p_pkg = sub.add_parser("package-override", help="Bundle current skill/corpus as hot-swap knowledge_pack.zip")
    p_pkg.add_argument("--out", default="knowledge_pack.zip")

    args = parser.parse_args()
    if args.cmd == "ingest":
        packs = list_corpus_packs().get("packs") or []
        target = next((p for p in packs if not p.get("builtin") and p["name"] == args.pack), None)
        if not target:
            target = create_corpus_pack(args.pack, "Multimodal DL", args.venue)
        total = 0
        for fp_str in args.files:
            fp = Path(fp_str)
            res = ingest_uploaded_file_into_pack(target["id"], fp.name, fp.read_bytes(), venue=args.venue, year=args.year)
            added = res.get("sentences_added", 0)
            total += added
            print(f"[+] {fp.name}: +{added} sentences")
        print(f"Done. Pack '{args.pack}' total added: {total}")
    elif args.cmd == "export-sft":
        jsonl, count = export_training_dataset_jsonl(fmt=args.format)
        Path(args.out).write_text(jsonl, encoding="utf-8")
        print(f"Exported {count} rows -> {args.out}")
    elif args.cmd == "package-override":
        src = get_skill_dir()
        assert src and src.exists(), "No skill directory found!"
        out = Path(args.out)
        with zipfile.ZipFile(out, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            for f in sorted(src.rglob("*")):
                if f.is_file() and "__pycache__" not in f.parts and f.suffix != ".pyc":
                    zf.write(f, f"knowledge_pack/{f.relative_to(src).as_posix()}")
        print(f"Hot-swap pack ready: {out} (extract into PaperHarness/local_data/knowledge_pack/ to override)")


if __name__ == "__main__":
    main()
