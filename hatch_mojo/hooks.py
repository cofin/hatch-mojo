"""Hatch hook registration."""

from hatch_mojo.plugin import MojoBuildHook


def hatch_register_build_hook() -> type[MojoBuildHook]:
    """Register build hook plugin with Hatch."""
    return MojoBuildHook
