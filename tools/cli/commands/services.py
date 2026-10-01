"""Local services commands, re-exported from their feature modules.

Kept as the single import point used by `tools/cli/registry.py`:

- `setup.py`: `setup up`, `setup down` (with `setup_steps.py`, `setup_summary.py`)
- `compose_services.py`: `start`, `stop`, `status`, `logs`, `exec`
- `alias.py`: `alias`
- `history.py`: `history show`, `history clear`

To replace one of these functions in a test, patch it in the module that
calls it (`cli.patch(...)` in `tests/test_silicium_test_cli.py` does so in
every CLI module), not only here.
"""

from __future__ import annotations

from tools.cli.commands.alias import cmd_alias, configure_alias
from tools.cli.commands.compose_services import (
    cmd_exec,
    cmd_logs,
    cmd_start,
    cmd_status,
    cmd_stop,
    configure_exec,
    configure_logs,
    configure_start,
    configure_status,
    configure_stop,
)
from tools.cli.commands.history import (
    cmd_history_clear,
    cmd_history_show,
    configure_history_clear,
    configure_history_show,
)
from tools.cli.commands.setup import (
    cmd_setup_down,
    cmd_setup_up,
    configure_setup_down,
    configure_setup_up,
)

__all__ = [
    "cmd_alias",
    "cmd_exec",
    "cmd_history_clear",
    "cmd_history_show",
    "cmd_logs",
    "cmd_setup_down",
    "cmd_setup_up",
    "cmd_start",
    "cmd_status",
    "cmd_stop",
    "configure_alias",
    "configure_exec",
    "configure_history_clear",
    "configure_history_show",
    "configure_logs",
    "configure_setup_down",
    "configure_setup_up",
    "configure_start",
    "configure_status",
    "configure_stop",
]
