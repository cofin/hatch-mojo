from hatch_mojo.hooks import hatch_register_build_hook
from hatch_mojo.plugin import MojoBuildHook


def test_register_build_hook_returns_plugin() -> None:
    assert hatch_register_build_hook() is MojoBuildHook
