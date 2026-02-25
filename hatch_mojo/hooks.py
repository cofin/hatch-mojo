"""Hatch hook registration."""

from hatchling.plugin import hookimpl

from hatch_mojo.plugin import MojoBuildHook


@hookimpl
def hatch_register_build_hook() -> type[MojoBuildHook]:
    """Register build hook plugin with Hatch."""
    return MojoBuildHook
