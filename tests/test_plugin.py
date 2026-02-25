from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import TYPE_CHECKING, Any, cast

from typing_extensions import Self

from hatch_mojo.plugin import MojoBuildHook
from hatch_mojo.types import BuildJob

if TYPE_CHECKING:
    import pytest


def _job(tmp_path: Path, *, name: str = "core") -> BuildJob:
    input_path = tmp_path / f"{name}.mojo"
    input_path.write_text("", encoding="utf-8")
    return BuildJob(
        name=name,
        input_path=input_path,
        output_path=tmp_path / f"{name}.so",
        emit="python-extension",
        module=f"pkg._{name}",
        install_kind=None,
        install_path=None,
        include_dirs=(),
        defines=(),
        flags=(),
        env={},
        depends_on=(),
    )


def _config(*, parallel: bool = False, clean_before: bool = False, clean_after: bool = False) -> Any:
    return SimpleNamespace(
        jobs=(object(),),
        skip_editable=True,
        clean_before_build=clean_before,
        clean_after_build=clean_after,
        build_dir=".hatch_mojo",
        parallel=parallel,
        fail_fast=True,
        mojo_bin=None,
    )


def test_initialize_skips_editable(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    fake = SimpleNamespace(root=str(tmp_path), config={}, target_name="wheel", app=SimpleNamespace())
    monkeypatch.setattr("hatch_mojo.plugin.parse_config", lambda *_args, **_kwargs: _config())

    called: dict[str, bool] = {"planned": False}

    def _plan(*_args: Any, **_kwargs: Any) -> list[BuildJob]:
        called["planned"] = True
        return []

    monkeypatch.setattr("hatch_mojo.plugin.plan_jobs", _plan)
    MojoBuildHook.initialize(cast("Any", fake), "editable", {})
    assert called["planned"] is False


def test_initialize_returns_when_no_jobs(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    cfg = _config()
    cfg.jobs = ()
    fake = SimpleNamespace(root=str(tmp_path), config={}, target_name="wheel", app=SimpleNamespace())
    monkeypatch.setattr("hatch_mojo.plugin.parse_config", lambda *_args, **_kwargs: cfg)
    MojoBuildHook.initialize(cast("Any", fake), "standard", {})


def test_initialize_serial_path(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    warnings: list[str] = []
    debugs: list[str] = []
    app = SimpleNamespace(display_warning=warnings.append, display_debug=debugs.append)
    fake = SimpleNamespace(root=str(tmp_path), config={}, target_name="wheel", app=app)
    job = _job(tmp_path)
    monkeypatch.setattr(
        "hatch_mojo.plugin.parse_config", lambda *_args, **_kwargs: _config(clean_before=True, clean_after=True)
    )
    monkeypatch.setattr("hatch_mojo.plugin.plan_jobs", lambda *_args, **_kwargs: [job])
    monkeypatch.setattr("hatch_mojo.plugin.discover_mojo", lambda *_args, **_kwargs: "mojo")

    seq: list[str] = []
    monkeypatch.setattr("hatch_mojo.plugin.clean_from_manifest", lambda *_args, **_kwargs: seq.append("clean"))
    monkeypatch.setattr("hatch_mojo.plugin.compile_job", lambda **_kwargs: (True, "ok"))
    monkeypatch.setattr("hatch_mojo.plugin.register_artifacts", lambda **_kwargs: seq.append("register"))
    monkeypatch.setattr("hatch_mojo.plugin.save_manifest", lambda *_args, **_kwargs: seq.append("save"))

    build_data: dict[str, Any] = {}
    MojoBuildHook.initialize(cast("Any", fake), "standard", build_data)
    assert "ok" in debugs
    assert warnings == []
    assert seq.count("clean") == 2
    assert "register" in seq
    assert "save" in seq


def test_initialize_parallel_path(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    warnings: list[str] = []
    debugs: list[str] = []
    app = SimpleNamespace(display_warning=warnings.append, display_debug=debugs.append)
    fake = SimpleNamespace(root=str(tmp_path), config={}, target_name="wheel", app=app)
    jobs = [_job(tmp_path, name="a"), _job(tmp_path, name="b")]
    monkeypatch.setattr("hatch_mojo.plugin.parse_config", lambda *_args, **_kwargs: _config(parallel=True))
    monkeypatch.setattr("hatch_mojo.plugin.plan_jobs", lambda *_args, **_kwargs: jobs)
    monkeypatch.setattr("hatch_mojo.plugin.discover_mojo", lambda *_args, **_kwargs: "mojo")
    monkeypatch.setattr("hatch_mojo.plugin.register_artifacts", lambda **_kwargs: None)
    monkeypatch.setattr("hatch_mojo.plugin.save_manifest", lambda *_args, **_kwargs: None)

    results = iter([(False, "bad"), (True, "good")])

    def _compile_job(**_kwargs: Any) -> tuple[bool, str]:
        return next(results)

    monkeypatch.setattr("hatch_mojo.plugin.compile_job", _compile_job)

    class _Future:
        def __init__(self, value: tuple[bool, str]) -> None:
            self._value = value

        def result(self) -> tuple[bool, str]:
            return self._value

    class _Pool:
        def __enter__(self) -> Self:
            return self

        def __exit__(self, *_args: object) -> None:
            return None

        def submit(self, fn: Any, **kwargs: Any) -> _Future:
            return _Future(fn(**kwargs))

    monkeypatch.setattr("hatch_mojo.plugin.ThreadPoolExecutor", _Pool)
    MojoBuildHook.initialize(cast("Any", fake), "standard", {})
    assert "bad" in warnings
    assert "good" in debugs


def test_clean_calls_clean_from_manifest(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    fake = SimpleNamespace(root=str(tmp_path), config={}, target_name="wheel")
    monkeypatch.setattr("hatch_mojo.plugin.parse_config", lambda *_args, **_kwargs: _config())
    called: list[str] = []
    monkeypatch.setattr("hatch_mojo.plugin.clean_from_manifest", lambda *_args, **_kwargs: called.append("clean"))
    MojoBuildHook.clean(cast("Any", fake), ["wheel"])
    assert called == ["clean"]
