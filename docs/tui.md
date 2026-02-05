# Terminal UI (TUI)

The Silicium TUI provides a clean, keyboard-first console interface for core workflows.

## Install

```bash
python -m pip install -r requirements-tui.txt
```

## Run

```bash
./silicium tui
```

## Key bindings

- `Enter`: run selected action
- `q`: quit
- `r`: refresh status
- `l`: clear log

## Screenshot (text)

```text
Silicium TUI
================================================================================
Actions                               Output
--------------------------------------------------------------------------------
> [status] Status (docker compose)    $ python silicium status
  [start_localnet] Start localnet     Name                Command   State
  [stop_all] Stop all services        silicium-localnet   ...       Up
  [logs_proxy] Logs (proxy)           silicium-proxy      ...       Up
  [workloads] List workloads
  [check_quick] Core check (quick)
  [clean_cache] Clean cache

Status: Done: Status (docker compose) (exit 0)
```
