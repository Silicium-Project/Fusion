"""`alias`: append a `silicium` shell helper function and short aliases to
the user shell rc file (bash, zsh, fish or a custom `--path`).
"""

from __future__ import annotations

import argparse
from pathlib import Path

from tools.cli.context import Context


def _alias_snippet() -> str:
    """Return the text appended to the rc file (helper function + aliases)."""
    function = '''silicium() {
    local cmd=$1
    shift
    case "$cmd" in
        test|smoke|clean|shell)
            ./silicium "$cmd" "$@"
            ;;
        ledger)
            ./silicium ledger "$@"
            ;;
        history)
            ./silicium history "$@"
            ;;
        start)
            ./silicium start "$@"
            ;;
        stop)
            ./silicium stop "$@"
            ;;
        start-local)
            ./silicium start localnet "$@"
            ;;
        start-dev)
            ./silicium start devnet "$@"
            ;;
        start-test)
            ./silicium start testnet "$@"
            ;;
        start-main)
            ./silicium start mainnet "$@"
            ;;
        *)
            ./silicium "$cmd" "$@"
            ;;
    esac
}'''
    alias_snippet = f"""
# Silicium helper function
{function}
alias sl='silicium ledger list'
alias st='silicium test'
alias ss='silicium smoke'
alias sc='silicium clean cache'
alias sca='silicium clean all -y'
alias shist='silicium history show --tail 20'
alias sstart='silicium start localnet'
alias sstop='silicium stop'
"""
    return alias_snippet


def cmd_alias(args: argparse.Namespace, ctx: Context) -> None:
    """Append the Silicium helper function and aliases to the shell rc file."""
    shell = args.shell or "bash"
    alias_snippet = _alias_snippet()

    rc_map = {
        "bash": "~/.bashrc",
        "zsh": "~/.zshrc",
        "fish": "~/.config/fish/config.fish",
    }
    path = args.path or rc_map.get(shell)
    if not path:
        print("Unsupported shell; provide --path to append manually.")
        return
    target = Path(path).expanduser()
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("a", encoding="utf-8") as fh:
        fh.write("\n" + alias_snippet + "\n")
    print(f"Aliases appended to {target}")


def configure_alias(parser: argparse.ArgumentParser) -> None:
    """Register the `alias` options."""
    parser.add_argument(
        "--shell",
        choices=["bash", "zsh", "fish"],
        help="Shell type for auto-detection (default bash).",
    )
    parser.add_argument(
        "--path",
        help="Custom rc file to append aliases.",
    )
