# Silicium AI runtime

Runs the models of the AI catalogue ("Catalogue IA") for the node, on the
user's computer. It is to the `ai/hf/<task>/<model key>` workloads what
Ollama is to the batch AI workload: an inference engine the desktop app
installs and starts when the user turns AI tasks on. The network side
(scheduling, model download and hash check, verification, results) stays in
Rust in `Network/crates/p2p-node/src/workload/hf/`.

It lives here, next to the desktop app, and not in `Network`: that repository
keeps Python for developer tooling only (`Network/AGENTS.md`).

## What it does

```
node ──HTTP 127.0.0.1:11436──▶ runtime ──▶ transformers / sentence-transformers / timm
        GET  /v1/health   format, version, device, tasks
        POST /v1/load     {model_dir, manifest}              → 200 or 422 + message
        POST /v1/run      {task, model_dir, manifest, parameters, seed, items} → {outputs}
```

- One output per item, in the shape of the Hub's task schema
  (`@huggingface/tasks`), so the node's verifiers compare like with like.
- Greedy generation, fixed seed: two honest machines differ only by rounding.
- 19 tasks for now (text, vision and audio tasks that run on a CPU); the
  others of the Hub page come in the next steps.

## Isolation (`sandbox.py`)

- **Offline**: `HF_HUB_OFFLINE=1` and the other offline variables; an empty
  Hugging Face home of its own; no token.
- **No network**: outgoing connections other than to loopback are refused in
  the process.
- **No code from models**: `trust_remote_code` is never set, weights are read
  from `safetensors` only, and a model directory holding Python files,
  pickle weights or symbolic links is refused. An architecture the installed
  `transformers` does not know is refused.
- **Only the node's models**: it loads directories inside `--models-root`
  (the node's `<data dir>/ai/hf/models`), whose files the node has checked by
  hash.
- Loopback only; with `SILICIUM_AI_RUNTIME_TOKEN` set, every call needs it.

## Run

```bash
pip install -e .[test]
python -m silicium_ai_runtime --models-root ~/.silicium/data/ai/hf/models   # port 11436
SILICIUM_AI_RUNTIME_URL=http://127.0.0.1:11436 p2p_node ...                  # the node uses it
```

Settings: `SILICIUM_AI_DEVICE` (`auto`, `cpu`, `cuda`), `SILICIUM_AI_MAX_LOADED`
(models kept loaded, default 2), `SILICIUM_AI_RUNTIME_LOG=1` (request log).

## Tests

```bash
python -m pytest -q
```

They build tiny models on the spot (random weights saved as safetensors):
nothing is downloaded.
