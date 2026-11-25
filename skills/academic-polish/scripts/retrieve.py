#!/usr/bin/env python
"""Retrieve real sentences from published deep-learning papers as style references.

Usage:
  python retrieve.py "draft English sentence or paragraph" [--section introduction] [--k 6] [--group native|cn|all]
  python retrieve.py --file draft.txt --section method

Query in ENGLISH (translate the Chinese first, then query with the draft).
Sections: abstract, introduction, related_work, method, experiments, conclusion, other.

Backends: vector search (sentence-transformers + BAAI/bge-small-en-v1.5, supports compact int8 or fp16)
when available, otherwise a dependency-free BM25 fallback. Force with --backend bm25.
"""
import argparse, json, math, os, re, sys
from collections import Counter
from pathlib import Path

os.environ.setdefault("USE_TF", "0")
os.environ.setdefault("TRANSFORMERS_NO_TF", "1")
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
DATA = Path(__file__).resolve().parents[1] / "data"
MODEL = "BAAI/bge-small-en-v1.5"
QUERY_PREFIX = "Represent this sentence for searching relevant passages: "
TOK = re.compile(r"[a-z][a-z\-]+")
STOP = set("the a an of to in and or for on with by is are was were be been this that these those we our it its as at from which can".split())


def load_rows():
    with (DATA / "examples.jsonl").open(encoding="utf-8") as fh:
        return [json.loads(l) for l in fh]


def load_embeddings():
    import numpy as np
    i8_path = DATA / "embeddings_i8.npz"
    if i8_path.exists():
        z = np.load(i8_path)
        return z["emb"].astype("float32") * float(z["scale"])
    return np.load(DATA / "embeddings.npy").astype("float32")


def vector_scores(queries, rows):
    from sentence_transformers import SentenceTransformer
    emb = load_embeddings()
    model = SentenceTransformer(MODEL, device="cpu")
    q = model.encode([QUERY_PREFIX + x for x in queries], normalize_embeddings=True)
    return (q @ emb.T).max(axis=0).tolist()


def bm25_scores(queries, rows, k1=1.5, b=0.75):
    docs = [[t for t in TOK.findall(r["text"].lower()) if t not in STOP] for r in rows]
    N, avg = len(docs), sum(map(len, docs)) / max(1, len(docs))
    df = Counter(t for d in docs for t in set(d))
    idf = {t: math.log(1 + (N - n + 0.5) / (n + 0.5)) for t, n in df.items()}
    qt = Counter(t for q in queries for t in TOK.findall(q.lower()) if t not in STOP)
    out = []
    for d in docs:
        tf, s = Counter(d), 0.0
        for t in qt:
            if t in tf:
                s += idf[t] * tf[t] * (k1 + 1) / (tf[t] + k1 * (1 - b + b * len(d) / avg))
        out.append(s)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("query", nargs="?")
    ap.add_argument("--file")
    ap.add_argument("--section", default=None)
    ap.add_argument("--group", default="native", choices=["all", "native", "cn"])
    ap.add_argument("--k", type=int, default=6)
    ap.add_argument("--backend", default="auto", choices=["auto", "vector", "bm25"])
    a = ap.parse_args()
    text = Path(a.file).read_text(encoding="utf-8-sig") if a.file else (a.query or sys.stdin.read())
    queries = [s for s in re.split(r"(?<=[.!?])\s+", text.strip()) if len(s.split()) >= 4] or [text]

    rows = load_rows()
    backend = a.backend
    if backend in ("auto", "vector"):
        try:
            scores = vector_scores(queries, rows); backend = "vector"
        except Exception as e:  # noqa
            if a.backend == "vector":
                sys.exit(f"vector backend unavailable: {e}")
            scores = bm25_scores(queries, rows); backend = "bm25"
    else:
        scores = bm25_scores(queries, rows)

    idx = [i for i in range(len(rows))
           if (not a.section or rows[i]["section"] == a.section) and (a.group == "all" or rows[i]["group"] == a.group)]
    idx.sort(key=lambda i: -scores[i])
    seen, shown = set(), 0
    print(f"# backend={backend} section={a.section or 'any'} group={a.group}")
    for i in idx:
        r = rows[i]
        if r["text"] in seen:
            continue
        seen.add(r["text"]); shown += 1
        print(f"\n[{shown}] ({r['section']}, {r['venue']} {r['year']}, score={scores[i]:.3f})")
        if r.get("prev"):
            print(f"    context: {r['prev'][:220]}")
        print(f"    >> {r['text']}")
        if shown >= a.k:
            break


if __name__ == "__main__":
    main()
