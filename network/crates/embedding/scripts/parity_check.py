#!/usr/bin/env python3
"""Compares an index built by `silicium-embed index` with the reference
implementation (sentence-transformers), passage by passage.

Developer tool, not run in CI (needs PyTorch and Hugging Face access):

    pip install sentence-transformers numpy
    silicium-embed prepare documents.zip -o corpus.jsonl
    silicium-embed index corpus.jsonl -o index/
    python3 crates/embedding/scripts/parity_check.py index/

Exits with 1 when a vector differs from the reference by more than the
verification threshold of the network (cosine 0.999).
"""

import argparse
import json
import sys
from pathlib import Path

import numpy as np
from sentence_transformers import SentenceTransformer

REPOSITORY = "intfloat/multilingual-e5-small"
REVISION = "614241f622f53c4eeff9890bdc4f31cfecc418b3"
THRESHOLD = 0.999


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("index", type=Path, help="directory written by silicium-embed index")
    parser.add_argument("--limit", type=int, default=200, help="passages compared (default 200)")
    args = parser.parse_args()

    manifest = json.loads((args.index / "index.json").read_text())
    vectors = np.fromfile(args.index / "vectors.f32", dtype="<f4").reshape(-1, manifest["dimension"])
    passages = [json.loads(line) for line in (args.index / "passages.jsonl").read_text().splitlines()]
    count = min(args.limit, len(passages))

    model = SentenceTransformer(REPOSITORY, revision=REVISION, device="cpu")
    reference = model.encode(
        ["passage: " + p["text"] for p in passages[:count]],
        normalize_embeddings=True,
        batch_size=16,
    )
    similarities = np.sum(reference * vectors[:count], axis=1)
    worst = int(np.argmin(similarities))
    print(f"{count} passages: min cosine {similarities.min():.6f} (passage {worst}), mean {similarities.mean():.6f}")
    return 0 if similarities.min() >= THRESHOLD else 1


if __name__ == "__main__":
    sys.exit(main())
