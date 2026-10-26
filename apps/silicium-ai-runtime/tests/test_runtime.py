"""The runtime over HTTP, as the node calls it: health, loading, running the
tasks with tiny local models, and the fences (no network, no code, no file
out of the models root)."""

from __future__ import annotations

import json
import shutil
import socket
import threading
import urllib.error
import urllib.request

import pytest

from conftest import manifest, png_bytes, write_json
from silicium_ai_runtime import sandbox
from silicium_ai_runtime.server import serve

TOKEN = "test-token"


@pytest.fixture(scope="module")
def runtime(models_root):
    server = serve("127.0.0.1", 0, models_root, TOKEN)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_address[1]}"
    server.shutdown()


def call(url: str, path: str, body: dict | None = None, token: str = TOKEN):
    data = None if body is None else json.dumps(body).encode()
    request = urllib.request.Request(url + path, data=data, method="POST" if body is not None else "GET")
    request.add_header("Content-Type", "application/json")
    if token:
        request.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            return response.status, json.loads(response.read())
    except urllib.error.HTTPError as err:
        return err.code, json.loads(err.read())


def run(url, models_root, task, items, parameters=None, **manifest_args):
    return call(url, "/v1/run", {
        "task": task,
        "model_dir": str(models_root / task),
        "manifest": manifest(task, **manifest_args),
        "parameters": parameters or {},
        "seed": 7,
        "items": [{"id": i, "inputs": item} for i, item in enumerate(items)],
    })


def test_health_lists_the_tasks_and_needs_the_token(runtime):
    status, health = call(runtime, "/v1/health")
    assert status == 200 and health["format"] == "silicium-ai-runtime/1"
    assert "text-classification" in health["tasks"] and len(health["tasks"]) == 19
    assert call(runtime, "/v1/health", token="")[0] == 401
    assert call(runtime, "/v1/health", token="wrong")[0] == 401


def test_text_tasks_answer_in_the_hub_shapes(runtime, models_root):
    status, body = run(runtime, models_root, "text-classification", ["le chat dort", "le chien mange"], {"top_k": 2})
    assert status == 200, body
    first = body["outputs"][0]
    assert {entry["label"] for entry in first} == {"négatif", "positif"} and all(0 <= e["score"] <= 1 for e in first)

    status, body = run(runtime, models_root, "zero-shot-classification", ["le chat dort"],
                       {"candidate_labels": ["chat", "chien"]})
    assert status == 200, body
    assert sorted(body["outputs"][0]["labels"]) == ["chat", "chien"]

    status, body = run(runtime, models_root, "token-classification", ["marie est à lyon"], {"aggregation_strategy": "none"})
    assert status == 200, body
    assert all("entity" in entry and "word" in entry for entry in body["outputs"][0])

    status, body = run(runtime, models_root, "question-answering",
                       [{"question": "le chat", "context": "le chat dort à paris"}])
    assert status == 200, body
    assert isinstance(body["outputs"][0]["answer"], str)

    status, body = run(runtime, models_root, "fill-mask", ["le [MASK] dort"], {"top_k": 3})
    assert status == 200, body
    assert len(body["outputs"][0]) == 3 and "token_str" in body["outputs"][0][0]

    status, body = run(runtime, models_root, "feature-extraction", ["le chat dort"])
    assert status == 200, body
    vector = body["outputs"][0]
    assert len(vector) == 16 and abs(sum(x * x for x in vector) - 1) < 1e-3


def test_image_tasks_read_base64_files(runtime, models_root):
    status, body = run(runtime, models_root, "image-classification", [png_bytes()], {"top_k": 1}, model_type="vit")
    assert status == 200, body
    assert body["outputs"][0][0]["label"] in ("chat", "chien")
    status, body = run(runtime, models_root, "image-feature-extraction", [png_bytes()], model_type="vit")
    assert status == 200, body
    assert len(body["outputs"][0]) == 16
    status, body = run(runtime, models_root, "image-classification", [{"$bytes": "bm90IGFuIGltYWdl"}], model_type="vit")
    assert status == 400 and "unreadable image" in body["message"]


def test_runs_are_repeatable(runtime, models_root):
    first = run(runtime, models_root, "text-classification", ["le chat dort"])[1]
    second = run(runtime, models_root, "text-classification", ["le chat dort"])[1]
    assert first == second


def test_bad_inputs_and_parameters_are_refused(runtime, models_root):
    status, body = run(runtime, models_root, "text-classification", ["le chat"], {"top_k": 999})
    assert status == 400 and "top_k" in body["message"]
    status, body = run(runtime, models_root, "zero-shot-classification", ["le chat"])
    assert status == 400 and "candidate_labels" in body["message"]
    status, body = run(runtime, models_root, "text-to-video", ["un chat"])
    assert status == 400


def test_models_out_of_the_root_with_code_or_unknown_are_refused(runtime, models_root, tmp_path):
    outside = tmp_path / "outside"
    shutil.copytree(models_root / "text-classification", outside)
    status, body = call(runtime, "/v1/load", {"model_dir": str(outside), "manifest": manifest("text-classification")})
    assert status == 422 and "outside" in body["message"]
    status, _ = call(runtime, "/v1/load", {"model_dir": str(models_root / ".." / "x"), "manifest": manifest("text-classification")})
    assert status == 422

    with_code = models_root / "with-code"
    shutil.copytree(models_root / "text-classification", with_code)
    (with_code / "modeling_evil.py").write_text("import os\n")
    status, body = call(runtime, "/v1/load", {"model_dir": str(with_code), "manifest": manifest("text-classification")})
    assert status == 422 and "forbidden" in body["message"]

    pickled = models_root / "pickled"
    shutil.copytree(models_root / "text-classification", pickled)
    (pickled / "pytorch_model.bin").write_bytes(b"\x80\x04")
    assert call(runtime, "/v1/load", {"model_dir": str(pickled), "manifest": manifest("text-classification")})[0] == 422

    unknown = models_root / "unknown"
    shutil.copytree(models_root / "text-classification", unknown)
    config = json.loads((unknown / "config.json").read_text())
    config["model_type"] = "not-a-real-architecture"
    write_json(unknown / "config.json", config)
    status, body = call(runtime, "/v1/load", {
        "model_dir": str(unknown), "manifest": manifest("text-classification", model_type="not-a-real-architecture"),
    })
    assert status == 422 and "unknown" in body["message"]


def test_no_outgoing_connection_and_offline_libraries():
    with pytest.raises(sandbox.NetworkRefused):
        socket.create_connection(("huggingface.co", 443), timeout=2)
    probe = socket.socket()
    with pytest.raises(sandbox.NetworkRefused):
        probe.connect(("8.8.8.8", 53))
    probe.close()
    import os

    assert os.environ["HF_HUB_OFFLINE"] == "1" and "HF_TOKEN" not in os.environ
