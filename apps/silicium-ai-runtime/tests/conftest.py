"""Tiny models built on the spot (random weights, saved as safetensors), so
the tests never download anything: what matters is the loading path and the
shape of the outputs, not their quality."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from silicium_ai_runtime import sandbox

ROOT = Path(__file__).resolve().parent
MODELS_ROOT_NAME = "models"

# The runtime's fences apply to the test process too.
sandbox.apply(ROOT / ".hf-home-test")

WORDS = ["le", "la", "chat", "chien", "dort", "mange", "paris", "lyon", "marie", "est", "à", "bon", "mauvais"]


def manifest(task: str, library: str = "transformers", model_type: str = "bert") -> dict:
    return {
        "format": "silicium-model/1",
        "key": f"test--{task}-000000000000",
        "digest": task,
        "repository": "test/model",
        "revision": "0" * 40,
        "task": task,
        "library": library,
        "runtime": "python",
        "loader": {"model_type": model_type},
        "files": [],
        "total_bytes": 0,
        "hardware_class": "A",
        "licence": "apache-2.0",
    }


def _bert_tokenizer(path: Path) -> None:
    from transformers import BertTokenizerFast

    vocab = path / "vocab.txt"
    vocab.write_text("\n".join(["[PAD]", "[UNK]", "[CLS]", "[SEP]", "[MASK]", *WORDS]) + "\n")
    BertTokenizerFast(vocab_file=str(vocab)).save_pretrained(path)


def _bert(path: Path, head: str, labels: list[str] | None = None) -> Path:
    import torch
    import transformers

    torch.manual_seed(0)
    config = transformers.BertConfig(
        vocab_size=len(WORDS) + 5, hidden_size=16, num_hidden_layers=1, num_attention_heads=2,
        intermediate_size=32, max_position_embeddings=64,
    )
    if labels:
        config.id2label = dict(enumerate(labels))
        config.label2id = {label: i for i, label in enumerate(labels)}
    getattr(transformers, head)(config).save_pretrained(path, safe_serialization=True)
    _bert_tokenizer(path)
    return path


def _vit(path: Path, head: str) -> Path:
    import torch
    import transformers

    torch.manual_seed(0)
    config = transformers.ViTConfig(
        image_size=32, patch_size=8, hidden_size=16, num_hidden_layers=1, num_attention_heads=2,
        intermediate_size=32, id2label={0: "chat", 1: "chien"}, label2id={"chat": 0, "chien": 1},
    )
    getattr(transformers, head)(config).save_pretrained(path, safe_serialization=True)
    transformers.ViTImageProcessor(size={"height": 32, "width": 32}).save_pretrained(path)
    return path


@pytest.fixture(scope="session")
def models_root(tmp_path_factory) -> Path:
    root = tmp_path_factory.mktemp("ai") / MODELS_ROOT_NAME
    root.mkdir()
    _bert(root / "text-classification", "BertForSequenceClassification", ["négatif", "positif"])
    _bert(root / "zero-shot-classification", "BertForSequenceClassification", ["entailment", "neutral", "contradiction"])
    _bert(root / "token-classification", "BertForTokenClassification", ["O", "B-PER", "I-PER", "B-LOC", "I-LOC"])
    _bert(root / "question-answering", "BertForQuestionAnswering")
    _bert(root / "fill-mask", "BertForMaskedLM")
    _bert(root / "feature-extraction", "BertModel")
    _vit(root / "image-classification", "ViTForImageClassification")
    _vit(root / "image-feature-extraction", "ViTModel")
    return root


def png_bytes() -> dict:
    import base64
    import io

    from PIL import Image

    buffer = io.BytesIO()
    Image.new("RGB", (40, 30), (200, 100, 50)).save(buffer, format="PNG")
    return {"$bytes": base64.b64encode(buffer.getvalue()).decode()}


def write_json(path: Path, value) -> None:
    path.write_text(json.dumps(value))
