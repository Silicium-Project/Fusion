"""What the runtime does for each task: read one item's inputs, run the
model, write the output in the shape of the Hub's task schema
(``@huggingface/tasks``), so that the node's verifiers compare like with
like (Network, ``workload/hf/compare``).

Parameters are those of the Hub's schemas, limited to what is safe and
bounded here; unknown parameters are ignored. Generation is greedy (no
sampling): two honest machines then differ only by rounding.
"""

from __future__ import annotations

from typing import Any, Callable

from . import inputs
from .inputs import InputError
from .loader import Loaded

MAX_NEW_TOKENS = 512


# Parameters -----------------------------------------------------------------

def _int(params: dict, key: str, default: int, low: int, high: int) -> int:
    value = params.get(key, default)
    if not isinstance(value, int) or isinstance(value, bool) or not low <= value <= high:
        raise InputError(f"parameter {key} must be an integer from {low} to {high}")
    return value


def _float(params: dict, key: str, default: float, low: float, high: float) -> float:
    value = params.get(key, default)
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not low <= value <= high:
        raise InputError(f"parameter {key} must be a number from {low} to {high}")
    return float(value)


def _bool(params: dict, key: str, default: bool) -> bool:
    value = params.get(key, default)
    if not isinstance(value, bool):
        raise InputError(f"parameter {key} must be true or false")
    return value


def _choice(params: dict, key: str, default: str, choices: tuple[str, ...]) -> str:
    value = params.get(key, default)
    if value not in choices:
        raise InputError(f"parameter {key} must be one of {', '.join(choices)}")
    return value


def _labels(params: dict) -> list[str]:
    labels = params.get("candidate_labels")
    if not isinstance(labels, list) or not 1 <= len(labels) <= 50:
        raise InputError("parameter candidate_labels must list 1 to 50 labels")
    return [inputs.text(label, "label", 80) for label in labels]


def _template(params: dict, default: str) -> str:
    template = params.get("hypothesis_template", default)
    if not isinstance(template, str) or "{}" not in template or len(template) > 200:
        raise InputError("parameter hypothesis_template must contain {} (200 characters at most)")
    return template


def _generation(params: dict, default_tokens: int) -> dict:
    return {
        "max_new_tokens": _int(params, "max_new_tokens", default_tokens, 1, MAX_NEW_TOKENS),
        "do_sample": False,
    }


# Outputs --------------------------------------------------------------------

def clean(value: Any) -> Any:
    """JSON values only, floats rounded to 6 decimals."""
    try:
        import numpy as np
    except ImportError:  # pragma: no cover
        np = None
    if hasattr(value, "tolist"):
        value = value.tolist()
    if np is not None and isinstance(value, np.generic):
        value = value.item()
    if isinstance(value, float):
        return round(value, 6)
    if isinstance(value, dict):
        return {str(k): clean(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [clean(v) for v in value]
    if value is None or isinstance(value, (bool, int, str)):
        return value
    return str(value)


def _first(result: Any) -> Any:
    """Pipelines answer one input as a list of one result for some tasks."""
    if isinstance(result, list) and len(result) == 1 and isinstance(result[0], (list, dict)):
        return result[0]
    return result


def _pooled(vectors: Any, pooling: str) -> list[float]:
    import numpy as np

    array = np.asarray(vectors, dtype=np.float32)
    while array.ndim > 2:
        array = array[0]
    if array.ndim == 2:
        array = array[0] if pooling == "cls" else array.mean(axis=0)
    return array.tolist()


def _normalized(vector: list[float], normalize: bool) -> list[float]:
    if not normalize:
        return vector
    norm = sum(x * x for x in vector) ** 0.5
    return [x / norm for x in vector] if norm else vector


# Tasks ----------------------------------------------------------------------

def text_classification(m: Loaded, value: Any, params: dict) -> Any:
    top_k = _int(params, "top_k", 3, 1, 50)
    return _first(m.model(inputs.text(value), top_k=top_k, truncation=True))


def token_classification(m: Loaded, value: Any, params: dict) -> Any:
    strategy = _choice(params, "aggregation_strategy", "simple", ("none", "simple", "first", "average", "max"))
    return m.model(inputs.text(value), aggregation_strategy=strategy)


def question_answering(m: Loaded, value: Any, params: dict) -> Any:
    question = inputs.text(inputs.field(value, "question"), "question", 2_000)
    context = inputs.text(inputs.field(value, "context"), "context")
    max_answer = _int(params, "max_answer_len", 30, 1, 200)
    return m.model(question=question, context=context, max_answer_len=max_answer)


def zero_shot_classification(m: Loaded, value: Any, params: dict) -> Any:
    return m.model(
        inputs.text(value),
        candidate_labels=_labels(params),
        multi_label=_bool(params, "multi_label", False),
        hypothesis_template=_template(params, "This example is {}."),
    )


def translation(m: Loaded, value: Any, params: dict) -> Any:
    kwargs = _generation(params, 256)
    for key in ("src_lang", "tgt_lang"):
        if key in params:
            kwargs[key] = inputs.text(params[key], key, 20)
    return m.model(inputs.text(value), truncation=True, **kwargs)


def summarization(m: Loaded, value: Any, params: dict) -> Any:
    return m.model(inputs.text(value), truncation=True, **_generation(params, 160))


def text_generation(m: Loaded, value: Any, params: dict) -> Any:
    kwargs = _generation(params, 128)
    kwargs["repetition_penalty"] = _float(params, "repetition_penalty", 1.0, 1.0, 2.0)
    return m.model(inputs.text(value), return_full_text=False, **kwargs)


def fill_mask(m: Loaded, value: Any, params: dict) -> Any:
    return m.model(inputs.text(value), top_k=_int(params, "top_k", 5, 1, 20))


def feature_extraction(m: Loaded, value: Any, params: dict) -> Any:
    normalize = _bool(params, "normalize", True)
    text = inputs.text(value)
    if m.kind == "sentence-transformer":
        return m.model.encode(text, normalize_embeddings=normalize, convert_to_numpy=True).tolist()
    pooling = _choice(params, "pooling", "mean", ("mean", "cls"))
    return _normalized(_pooled(m.model(text, truncation=True), pooling), normalize)


def sentence_similarity(m: Loaded, value: Any, params: dict) -> Any:
    source = inputs.text(inputs.field(value, "source_sentence"), "source_sentence")
    others = inputs.texts(inputs.field(value, "sentences"), "sentences")
    if m.kind != "sentence-transformer":
        raise InputError("this model does not compare sentences")
    vectors = m.model.encode([source, *others], normalize_embeddings=True, convert_to_numpy=True)
    return [float(vectors[0] @ vector) for vector in vectors[1:]]


def text_ranking(m: Loaded, value: Any, params: dict) -> Any:
    query = inputs.text(inputs.field(value, "query"), "query", 2_000)
    texts = inputs.texts(inputs.field(value, "texts"), "texts")
    if m.kind == "cross-encoder":
        scores = m.model.predict([(query, text) for text in texts])
    else:  # A sequence-classification pipeline scoring (query, text) pairs.
        scores = [
            _first(m.model({"text": query, "text_pair": text}, top_k=1, function_to_apply="none"))["score"]
            for text in texts
        ]
    ranked = sorted(range(len(texts)), key=lambda index: (-float(scores[index]), index))
    return [{"index": index, "score": float(scores[index])} for index in ranked]


def table_question_answering(m: Loaded, value: Any, params: dict) -> Any:
    query = inputs.text(inputs.field(value, "query"), "query", 2_000)
    table = inputs.field(value, "table")
    if not isinstance(table, dict) or not table:
        raise InputError('expected "table" as {"column": ["cell", ...]}')
    rows = None
    for column, cells in table.items():
        if not isinstance(cells, list) or len(cells) > 1_000 or (rows is not None and len(cells) != rows):
            raise InputError("every column needs the same number of cells (1000 at most)")
        rows = len(cells)
    table = {str(column): [str(cell) for cell in cells] for column, cells in table.items()}
    return m.model(table=table, query=query)


def image_classification(m: Loaded, value: Any, params: dict) -> Any:
    top_k = _int(params, "top_k", 5, 1, 50)
    picture = inputs.image(value)
    if m.kind == "timm":
        import torch

        tensor = m.extra["transform"](picture).unsqueeze(0).to(next(m.model.parameters()).device)
        with torch.no_grad():
            probabilities = m.model(tensor).softmax(dim=-1)[0]
        scores, indices = probabilities.topk(min(top_k, probabilities.shape[0]))
        labels = m.extra["labels"]
        return [
            {"label": labels[i] if labels and i < len(labels) else str(i), "score": float(s)}
            for s, i in zip(scores.tolist(), indices.tolist())
        ]
    return m.model(picture, top_k=top_k)


def zero_shot_image_classification(m: Loaded, value: Any, params: dict) -> Any:
    return m.model(
        inputs.image(value),
        candidate_labels=_labels(params),
        hypothesis_template=_template(params, "This is a photo of {}."),
    )


def object_detection(m: Loaded, value: Any, params: dict) -> Any:
    return m.model(inputs.image(value), threshold=_float(params, "threshold", 0.5, 0.0, 1.0))


def image_to_text(m: Loaded, value: Any, params: dict) -> Any:
    return m.model(inputs.image(value), generate_kwargs=_generation(params, 64))


def image_feature_extraction(m: Loaded, value: Any, params: dict) -> Any:
    normalize = _bool(params, "normalize", True)
    picture = inputs.image(value)
    if m.kind == "timm":
        import torch

        tensor = m.extra["transform"](picture).unsqueeze(0).to(next(m.model.parameters()).device)
        with torch.no_grad():
            vector = m.model(tensor)[0].tolist()
        return _normalized(vector, normalize)
    pooling = _choice(params, "pooling", "mean", ("mean", "cls"))
    return _normalized(_pooled(m.model(picture), pooling), normalize)


def automatic_speech_recognition(m: Loaded, value: Any, params: dict) -> Any:
    generate = _generation(params, 440)
    for key in ("language", "task"):
        if key in params:
            generate[key] = inputs.text(params[key], key, 20)
    result = m.model(inputs.audio(value), chunk_length_s=30, generate_kwargs=generate)
    return {"text": result.get("text", "") if isinstance(result, dict) else str(result)}


def audio_classification(m: Loaded, value: Any, params: dict) -> Any:
    return m.model(inputs.audio(value), top_k=_int(params, "top_k", 5, 1, 50))


TASKS: dict[str, Callable[[Loaded, Any, dict], Any]] = {
    "text-classification": text_classification,
    "token-classification": token_classification,
    "question-answering": question_answering,
    "zero-shot-classification": zero_shot_classification,
    "translation": translation,
    "summarization": summarization,
    "feature-extraction": feature_extraction,
    "text-generation": text_generation,
    "fill-mask": fill_mask,
    "sentence-similarity": sentence_similarity,
    "text-ranking": text_ranking,
    "table-question-answering": table_question_answering,
    "image-classification": image_classification,
    "zero-shot-image-classification": zero_shot_image_classification,
    "object-detection": object_detection,
    "image-to-text": image_to_text,
    "image-feature-extraction": image_feature_extraction,
    "automatic-speech-recognition": automatic_speech_recognition,
    "audio-classification": audio_classification,
}


def run(m: Loaded, value: Any, params: dict) -> Any:
    return clean(TASKS[m.task](m, value, params))
