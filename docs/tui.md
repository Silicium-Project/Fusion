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

## Frontend Selection

- CLI option: `./silicium tui --tui-frontend textual|curses|headless`
- Env override: `SILICIUM_TUI_FRONTEND=textual|curses|headless`
- Non-interactive probe: `./silicium tui --smoke`
- Strict probe: `./silicium tui --smoke --strict-frontend --tui-frontend <name>`
- Precedence: CLI argument first, then env var, then default `textual`
- Fallback policy:
  - invalid value -> warning -> fallback to `textual`
  - `curses` selected -> runs minimal curses frontend
  - curses startup failure -> warning -> fallback to `textual`
  - `textual` unavailable -> warning -> fallback to `headless` shell mode

## Curses Smoke

```bash
./silicium tui --tui-frontend curses
```

- `Up/Down`: select action
- `Enter`: run selected action
- `i`: interrupt selected running action
- `q`: quit

Notes:
- The curses frontend requires a real terminal/TTY.
- On Windows, `windows-curses` is required and currently supported up to Python 3.13.
- If curses is unavailable, startup falls back to `textual`.

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
