"""Built-in provider presets used by the settings dialog.

This module is intentionally minimal: the ``PRESETS`` table historically
lived inside ``ui/settings_dialog.py`` and was extracted as part of the
alert-rate-limit refactor (see commit 663a9fa).  The dialog was not yet
updated to consume the extracted constants, so this file exists only to
keep the ``from ui.presets import PRESETS, PRETTY_NAMES`` import working
and to give downstream code a stable home when the dialog is wired up.

When the settings dialog is reworked to render preset buttons, populate
``PRESETS`` with tuples of ``(display_name, spec_id, base_url)`` and
``PRETTY_NAMES`` with the ``{spec_id: human_label}`` overrides.

The historical inline PRESETS that previously lived in settings_dialog
is kept here as a reference; it is **not** imported by any consumer.
"""
from __future__ import annotations

PRESETS: list[tuple[str, str, str]] = []

PRETTY_NAMES: dict[str, str] = {}

__all__ = ["PRESETS", "PRETTY_NAMES"]
