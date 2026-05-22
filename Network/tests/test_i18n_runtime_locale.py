from __future__ import annotations

from tools.i18n import set_runtime_locale, tr


def test_tr_switches_locale_and_formats() -> None:
    set_runtime_locale("fr-FR")
    assert "Shell Silicium" in tr("cli.shell.banner")
    assert tr("cli.tui.frontend_ok", "headless").startswith("Frontend ")
    assert "auto" in tr("tui.button.runner", mode="auto")

    set_runtime_locale("en-US")
    assert "Silicium shell" in tr("cli.shell.banner")
    assert tr("cli.tui.frontend_ok", "headless") == "Frontend headless: OK"
    assert tr("tui.button.runner", mode="auto") == "Runner: auto"

