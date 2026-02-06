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

- `q`: quit
- `r`: refresh status
- `l`: clear log
- `i`: interrupt running action

## Mouse support

- Click **Run** in the taskbar to start the highlighted action.
- While running, **Run** becomes **Interrupt**.
- Click an action to highlight it.

## Logs and progress

- The UI shows a progress bar while commands run.
- Full command output is saved to `.silicium/logs/<timestamp>_<action>.log`.
- The UI only shows the last ~300 lines to keep it responsive.
- The status panel shows action, command, log file, elapsed time, and exit code.

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
