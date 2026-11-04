from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import TYPE_CHECKING, Any, cast

from typing_extensions import Self

from hatch_mojo.plugin import MojoBuildHook
from hatch_mojo.types import BuildJob, RuntimeBundleResult

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


def _config(
    *,
    parallel: bool = False,
    clean_before: bool = False,
    clean_after: bool = False,
    bundle_libs: bool = True,
    cache: bool = True,
) -> Any:
    return SimpleNamespace(
        jobs=(object(),),
        skip_editable=True,
        clean_before_build=clean_before,
        clean_after_build=clean_after,
        build_dir="build/mojo",
        parallel=parallel,
        fail_fast=True,
        mojo_bin=None,
        bundle_libs=bundle_libs,
        cache=cache,
        excluded_jobs=(),
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
    saved_manifests: list[tuple[str, list[Path]]] = []

    def _record_save(root: Path, build_dir: str, outputs: list[Path], *, filename: str = "manifest.json") -> Path:
        seq.append("save")
        saved_manifests.append((filename, list(outputs)))
        return root / build_dir / filename

    monkeypatch.setattr("hatch_mojo.plugin.clean_from_manifest", lambda *_args, **_kwargs: seq.append("clean"))
    monkeypatch.setattr("hatch_mojo.plugin.compile_job", lambda **_kwargs: (True, "ok"))
    monkeypatch.setattr(
        "hatch_mojo.plugin.bundle_runtime_libs",
        lambda **_kwargs: RuntimeBundleResult(
            force_include={str(tmp_path / "staged.so"): "pkg.libs/libFoo.so"},
            shared_data={str(tmp_path / "shared_lib.so"): "lib/pkg.libs/libBar.so"},
            staged_files=(tmp_path / "staged.so", tmp_path / "shared_lib.so"),
        ),
    )
    monkeypatch.setattr("hatch_mojo.plugin.register_artifacts", lambda **_kwargs: seq.append("register"))
    monkeypatch.setattr("hatch_mojo.plugin.save_manifest", _record_save)

    build_data: dict[str, Any] = {}
    MojoBuildHook.initialize(cast("Any", fake), "standard", build_data)
    assert "ok" in debugs
    assert warnings == []
    assert seq.count("clean") == 1
    assert "register" in seq
    assert "save" in seq
    assert build_data["force_include"][str(tmp_path / "staged.so")] == "pkg.libs/libFoo.so"
    assert build_data["shared_data"][str(tmp_path / "shared_lib.so")] == "lib/pkg.libs/libBar.so"
    assert saved_manifests == [("manifest.json", [job.output_path, tmp_path / "staged.so", tmp_path / "shared_lib.so"])]


def test_initialize_parallel_path(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    warnings: list[str] = []
    debugs: list[str] = []
    app = SimpleNamespace(display_warning=warnings.append, display_debug=debugs.append)
    fake = SimpleNamespace(root=str(tmp_path), config={}, target_name="wheel", app=app)
    jobs = [_job(tmp_path, name="a"), _job(tmp_path, name="b")]
    monkeypatch.setattr("hatch_mojo.plugin.parse_config", lambda *_args, **_kwargs: _config(parallel=True))
    monkeypatch.setattr("hatch_mojo.plugin.plan_jobs_leveled", lambda *_args, **_kwargs: [jobs])
    monkeypatch.setattr("hatch_mojo.plugin.discover_mojo", lambda *_args, **_kwargs: "mojo")
    monkeypatch.setattr(
        "hatch_mojo.plugin.bundle_runtime_libs",
        lambda **_kwargs: RuntimeBundleResult(force_include={}, shared_data={}, staged_files=()),
    )
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


def test_initialize_editable_copies_artifacts(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    # Set up source tree with __init__.py
    pkg_dir = tmp_path / "src" / "py" / "mogemma"
    pkg_dir.mkdir(parents=True)
    (pkg_dir / "__init__.py").write_text("", encoding="utf-8")

    # Create a fake built artifact
    build_dir = tmp_path / "build/mojo" / "mogemma"
    build_dir.mkdir(parents=True)
    artifact = build_dir / "_core.so"
    artifact.write_text("fake-binary", encoding="utf-8")

    job = BuildJob(
        name="core",
        input_path=tmp_path / "src" / "mo" / "core.mojo",
        output_path=artifact,
        emit="python-extension",
        module="mogemma._core",
        install_kind=None,
        install_path=None,
        include_dirs=(),
        defines=(),
        flags=(),
        env={},
        depends_on=(),
    )

    cfg = _config()
    cfg.skip_editable = False
    warnings: list[str] = []
    debugs: list[str] = []
    app = SimpleNamespace(display_warning=warnings.append, display_debug=debugs.append)
    fake = SimpleNamespace(root=str(tmp_path), config={}, target_name="wheel", app=app)
    saved_manifests: list[tuple[str, list[Path]]] = []

    def _record_save(root: Path, build_dir: str, outputs: list[Path], *, filename: str = "manifest.json") -> Path:
        saved_manifests.append((filename, list(outputs)))
        return root / build_dir / filename

    monkeypatch.setattr("hatch_mojo.plugin.parse_config", lambda *_args, **_kwargs: cfg)
    monkeypatch.setattr("hatch_mojo.plugin.plan_jobs", lambda *_args, **_kwargs: [job])
    monkeypatch.setattr("hatch_mojo.plugin.discover_mojo", lambda *_args, **_kwargs: "mojo")
    monkeypatch.setattr("hatch_mojo.plugin.compile_job", lambda **_kwargs: (True, "ok"))
    monkeypatch.setattr("hatch_mojo.plugin.patch_editable_runtime", lambda *_a, **_kw: ())
    monkeypatch.setattr(
        "hatch_mojo.plugin.bundle_runtime_libs",
        lambda **_kwargs: (_ for _ in ()).throw(AssertionError("bundle_runtime_libs must not run on editable")),
    )
    monkeypatch.setattr("hatch_mojo.plugin.register_artifacts", lambda **_kwargs: None)
    monkeypatch.setattr("hatch_mojo.plugin.save_manifest", _record_save)

    MojoBuildHook.initialize(cast("Any", fake), "editable", {})
    copied = pkg_dir / "_core.so"
    assert copied.exists()
    assert copied.read_text(encoding="utf-8") == "fake-binary"
    assert ("editable-manifest.json", [copied]) in saved_manifests


def test_initialize_calls_bundle_when_enabled(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    warnings: list[str] = []
    debugs: list[str] = []
    app = SimpleNamespace(display_warning=warnings.append, display_debug=debugs.append)
    metadata = SimpleNamespace(core=SimpleNamespace(name="my-dist"))
    fake = SimpleNamespace(root=str(tmp_path), config={}, target_name="wheel", app=app, metadata=metadata)
    job = _job(tmp_path)
    monkeypatch.setattr("hatch_mojo.plugin.parse_config", lambda *_args, **_kwargs: _config(bundle_libs=True))
    monkeypatch.setattr("hatch_mojo.plugin.plan_jobs", lambda *_args, **_kwargs: [job])
    monkeypatch.setattr("hatch_mojo.plugin.discover_mojo", lambda *_args, **_kwargs: "mojo")
    monkeypatch.setattr("hatch_mojo.plugin.compile_job", lambda **_kwargs: (True, "ok"))
    monkeypatch.setattr("hatch_mojo.plugin.register_artifacts", lambda **_kwargs: None)
    monkeypatch.setattr("hatch_mojo.plugin.save_manifest", lambda *_args, **_kwargs: None)

    bundle_called: dict[str, Any] = {"yes": False, "dist_name": None}

    def _fake_bundle(**kwargs: Any) -> RuntimeBundleResult:
        bundle_called["yes"] = True
        bundle_called["dist_name"] = kwargs.get("dist_name")
        return RuntimeBundleResult(
            force_include={"/tmp/staged.so": "pkg.libs/libFoo.so"},
            shared_data={},
            staged_files=(Path("/tmp/staged.so"),),
        )

    monkeypatch.setattr("hatch_mojo.plugin.bundle_runtime_libs", _fake_bundle)

    build_data: dict[str, Any] = {}
    MojoBuildHook.initialize(cast("Any", fake), "standard", build_data)
    assert bundle_called["yes"] is True
    assert bundle_called["dist_name"] == "my-dist"
    assert build_data["force_include"]["/tmp/staged.so"] == "pkg.libs/libFoo.so"


def test_initialize_skips_bundle_when_disabled(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    warnings: list[str] = []
    debugs: list[str] = []
    app = SimpleNamespace(display_warning=warnings.append, display_debug=debugs.append)
    fake = SimpleNamespace(root=str(tmp_path), config={}, target_name="wheel", app=app)
    job = _job(tmp_path)
    monkeypatch.setattr("hatch_mojo.plugin.parse_config", lambda *_args, **_kwargs: _config(bundle_libs=False))
    monkeypatch.setattr("hatch_mojo.plugin.plan_jobs", lambda *_args, **_kwargs: [job])
    monkeypatch.setattr("hatch_mojo.plugin.discover_mojo", lambda *_args, **_kwargs: "mojo")
    monkeypatch.setattr("hatch_mojo.plugin.compile_job", lambda **_kwargs: (True, "ok"))
    monkeypatch.setattr("hatch_mojo.plugin.register_artifacts", lambda **_kwargs: None)
    monkeypatch.setattr("hatch_mojo.plugin.save_manifest", lambda *_args, **_kwargs: None)

    bundle_called = {"yes": False}

    def _fake_bundle(**_kwargs: Any) -> RuntimeBundleResult:
        bundle_called["yes"] = True
        return RuntimeBundleResult(force_include={}, shared_data={}, staged_files=())

    monkeypatch.setattr("hatch_mojo.plugin.bundle_runtime_libs", _fake_bundle)

    MojoBuildHook.initialize(cast("Any", fake), "standard", {})
    assert bundle_called["yes"] is False


def test_clean_calls_clean_from_manifest(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    fake = SimpleNamespace(root=str(tmp_path), config={}, target_name="wheel")
    monkeypatch.setattr("hatch_mojo.plugin.parse_config", lambda *_args, **_kwargs: _config())
    called: list[bool] = []
    monkeypatch.setattr(
        "hatch_mojo.plugin.clean_from_manifest",
        lambda *_args, include_editable=False, **_kwargs: called.append(include_editable),
    )
    MojoBuildHook.clean(cast("Any", fake), ["wheel"])
    assert called == [True]


def test_finalize_runs_clean_when_clean_after_build_enabled(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    fake = SimpleNamespace(root=str(tmp_path), config={}, target_name="wheel")
    monkeypatch.setattr(
        "hatch_mojo.plugin.parse_config",
        lambda *_args, **_kwargs: _config(clean_after=True),
    )
    calls: list[tuple[Path, str, bool]] = []
    monkeypatch.setattr(
        "hatch_mojo.plugin.clean_from_manifest",
        lambda root, build_dir, *, include_editable=False: calls.append((root, build_dir, include_editable)),
    )
    MojoBuildHook.finalize(cast("Any", fake), "standard", {}, "dist/pkg.whl")
    assert calls == [(tmp_path, "build/mojo", False)]


def test_finalize_skips_editable_even_when_clean_after_build_enabled(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    fake = SimpleNamespace(root=str(tmp_path), config={}, target_name="wheel")
    monkeypatch.setattr(
        "hatch_mojo.plugin.parse_config",
        lambda *_args, **_kwargs: _config(clean_after=True),
    )
    calls: list[str] = []
    monkeypatch.setattr("hatch_mojo.plugin.clean_from_manifest", lambda *_a, **_kw: calls.append("clean"))
    MojoBuildHook.finalize(cast("Any", fake), "editable", {}, "dist/pkg.whl")
    assert calls == []


def test_finalize_noop_when_clean_after_build_disabled(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    fake = SimpleNamespace(root=str(tmp_path), config={}, target_name="wheel")
    monkeypatch.setattr(
        "hatch_mojo.plugin.parse_config",
        lambda *_args, **_kwargs: _config(clean_after=False),
    )
    calls: list[str] = []
    monkeypatch.setattr("hatch_mojo.plugin.clean_from_manifest", lambda *_a, **_kw: calls.append("clean"))
    MojoBuildHook.finalize(cast("Any", fake), "standard", {}, "dist/pkg.whl")
    assert calls == []


def test_initialize_sets_bypass_selection_for_standalone_shared_scripts(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    cfg = _config(bundle_libs=False)
    job = BuildJob(
        name="cli",
        input_path=tmp_path / "cli.mojo",
        output_path=tmp_path / "build/mojo/my-cli",
        emit="executable",
        module=None,
        install_kind="scripts",
        install_path="my-cli",
        include_dirs=(),
        defines=(),
        flags=(),
        env={},
        depends_on=(),
    )
    app = SimpleNamespace(display_warning=lambda *_a: None, display_debug=lambda *_a: None)
    target_config: dict[str, Any] = {}
    build_config = SimpleNamespace(target_config=target_config)
    fake = SimpleNamespace(root=str(tmp_path), config={}, target_name="wheel", app=app, build_config=build_config)

    monkeypatch.setattr("hatch_mojo.plugin.parse_config", lambda *_a, **_kw: cfg)
    monkeypatch.setattr("hatch_mojo.plugin.plan_jobs", lambda *_a, **_kw: [job])
    monkeypatch.setattr("hatch_mojo.plugin.discover_mojo", lambda *_a, **_kw: "mojo")
    monkeypatch.setattr("hatch_mojo.plugin.compile_job", lambda **_kw: (True, "ok"))
    monkeypatch.setattr("hatch_mojo.plugin.save_manifest", lambda *_a, **_kw: tmp_path / "manifest.json")

    build_data: dict[str, Any] = {}
    MojoBuildHook.initialize(cast("Any", fake), "standard", build_data)
    assert build_data.get("shared_scripts") == {str(job.output_path): "my-cli"}
    assert not build_data.get("force_include")
    assert target_config["bypass-selection"] is True

    explicit_target_config: dict[str, Any] = {"bypass-selection": False}
    fake_explicit = SimpleNamespace(
        root=str(tmp_path),
        config={},
        target_name="wheel",
        app=app,
        build_config=SimpleNamespace(target_config=explicit_target_config),
    )
    MojoBuildHook.initialize(cast("Any", fake_explicit), "standard", {})
    assert explicit_target_config["bypass-selection"] is False


def test_initialize_fail_fast_false_filters_failed_and_dependent_jobs(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    cfg = _config(bundle_libs=True)
    cfg.fail_fast = False
    job_ok = _job(tmp_path, name="ok")
    job_ok.output_path.write_bytes(b"ok")
    job_bad = _job(tmp_path, name="bad")
    job_dep = BuildJob(
        name="dep",
        input_path=tmp_path / "dep.mojo",
        output_path=tmp_path / "dep.so",
        emit="python-extension",
        module="pkg._dep",
        install_kind=None,
        install_path=None,
        include_dirs=(),
        defines=(),
        flags=(),
        env={},
        depends_on=("bad",),
    )

    warnings: list[str] = []
    debugs: list[str] = []
    app = SimpleNamespace(display_warning=warnings.append, display_debug=debugs.append)
    fake = SimpleNamespace(root=str(tmp_path), config={}, target_name="wheel", app=app)

    monkeypatch.setattr("hatch_mojo.plugin.parse_config", lambda *_a, **_kw: cfg)
    monkeypatch.setattr("hatch_mojo.plugin.plan_jobs", lambda *_a, **_kw: [job_ok, job_bad, job_dep])
    monkeypatch.setattr("hatch_mojo.plugin.discover_mojo", lambda *_a, **_kw: "mojo")
    monkeypatch.setattr(
        "hatch_mojo.plugin.compile_job",
        lambda *, job, **_kw: (False, f"failed:{job.name}") if job.name == "bad" else (True, f"ok:{job.name}"),
    )

    bundled_jobs: list[str] = []
    registered_jobs: list[str] = []
    saved_outputs: list[Path] = []

    def _fake_bundle(*, jobs: list[BuildJob], **_kw: Any) -> RuntimeBundleResult:
        bundled_jobs.extend(j.name for j in jobs)
        return RuntimeBundleResult(force_include={}, shared_data={}, staged_files=())

    def _fake_register(*, jobs: list[BuildJob], **_kw: Any) -> None:
        registered_jobs.extend(j.name for j in jobs)

    def _fake_save(root: Path, build_dir: str, outputs: list[Path], **_kw: Any) -> Path:
        saved_outputs.extend(outputs)
        return root / build_dir / "manifest.json"

    monkeypatch.setattr("hatch_mojo.plugin.bundle_runtime_libs", _fake_bundle)
    monkeypatch.setattr("hatch_mojo.plugin.register_artifacts", _fake_register)
    monkeypatch.setattr("hatch_mojo.plugin.save_manifest", _fake_save)

    MojoBuildHook.initialize(cast("Any", fake), "standard", {})
    assert bundled_jobs == ["ok"]
    assert registered_jobs == ["ok"]
    assert saved_outputs == [job_ok.output_path]
    assert any("failed:bad" in w for w in warnings)
    assert any("dep" in w for w in warnings)


def test_initialize_editable_uses_raw_target_config_packages_without_force_include(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    custom_pkg = tmp_path / "python" / "my_pkg"
    custom_pkg.mkdir(parents=True)
    (custom_pkg / "__init__.py").write_text("", encoding="utf-8")

    raw_out = tmp_path / "build" / "mojo" / "my_pkg" / "_core.so"
    raw_out.parent.mkdir(parents=True)
    raw_out.write_bytes(b"pristine-compiler-bytes")

    job = BuildJob(
        name="core",
        input_path=tmp_path / "core.mojo",
        output_path=raw_out,
        emit="python-extension",
        module="my_pkg._core",
        install_kind=None,
        install_path=None,
        include_dirs=(),
        defines=(),
        flags=(),
        env={},
        depends_on=(),
    )

    class _ExplodingBuildConfig:
        def __init__(self) -> None:
            self.target_config: dict[str, Any] = {"packages": ["python/my_pkg"]}
            self.build_config: dict[str, Any] = {}

        @property
        def packages(self) -> list[str]:
            raise AssertionError("build_config.packages property must not be evaluated prematurely")

    cfg = _config(bundle_libs=True)
    cfg.skip_editable = False
    app = SimpleNamespace(display_warning=lambda *_a: None, display_debug=lambda *_a: None)
    fake = SimpleNamespace(
        root=str(tmp_path),
        config={},
        target_name="wheel",
        app=app,
        build_config=_ExplodingBuildConfig(),
    )

    patched_targets: list[Path] = []

    def _fake_patch_editable(
        _root: Path, _build_dir: str, jobs: list[BuildJob], _mojo_bin: str | None
    ) -> tuple[Path, ...]:
        for j in jobs:
            patched_targets.append(j.output_path)
            j.output_path.write_bytes(b"patched-editable-bytes")
        return ()

    monkeypatch.setattr("hatch_mojo.plugin.parse_config", lambda *_a, **_kw: cfg)
    monkeypatch.setattr("hatch_mojo.plugin.plan_jobs", lambda *_a, **_kw: [job])
    monkeypatch.setattr("hatch_mojo.plugin.discover_mojo", lambda *_a, **_kw: "mojo")
    monkeypatch.setattr("hatch_mojo.plugin.compile_job", lambda **_kw: (True, "ok"))
    monkeypatch.setattr("hatch_mojo.plugin.patch_editable_runtime", _fake_patch_editable)

    build_data: dict[str, Any] = {}
    MojoBuildHook.initialize(cast("Any", fake), "editable", build_data)

    copied = custom_pkg / "_core.so"
    assert copied.read_bytes() == b"patched-editable-bytes"
    assert raw_out.read_bytes() == b"pristine-compiler-bytes"
    assert patched_targets == [copied]
    assert not build_data.get("force_include")


def test_initialize_editable_dev_mode_exact_copies_submodules_and_preserves_force_include(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    pkg_dir = tmp_path / "src" / "my_pkg"
    pkg_dir.mkdir(parents=True)
    (pkg_dir / "__init__.py").write_text("", encoding="utf-8")

    sub_out = tmp_path / "build" / "mojo" / "my_pkg" / "_core.so"
    top_out = tmp_path / "build" / "mojo" / "_top.so"
    sub_out.parent.mkdir(parents=True)
    sub_out.write_bytes(b"sub")
    top_out.write_bytes(b"top")

    jobs = [
        BuildJob(
            "sub", tmp_path / "a.mojo", sub_out, "python-extension", "my_pkg._core", None, None, (), (), (), {}, ()
        ),
        BuildJob("top", tmp_path / "b.mojo", top_out, "python-extension", "_top", None, None, (), (), (), {}, ()),
    ]

    cfg = _config(bundle_libs=False)
    cfg.skip_editable = False
    app = SimpleNamespace(display_warning=lambda *_a: None, display_debug=lambda *_a: None)
    build_config = SimpleNamespace(
        target_config={"dev-mode-exact": True},
        build_config={},
        get_force_include=lambda: {"/existing/readme.txt": "readme.txt"},
    )
    fake = SimpleNamespace(root=str(tmp_path), config={}, target_name="wheel", app=app, build_config=build_config)

    monkeypatch.setattr("hatch_mojo.plugin.parse_config", lambda *_a, **_kw: cfg)
    monkeypatch.setattr("hatch_mojo.plugin.plan_jobs", lambda *_a, **_kw: jobs)
    monkeypatch.setattr("hatch_mojo.plugin.discover_mojo", lambda *_a, **_kw: "mojo")
    monkeypatch.setattr("hatch_mojo.plugin.compile_job", lambda **_kw: (True, "ok"))

    build_data: dict[str, Any] = {}
    MojoBuildHook.initialize(cast("Any", fake), "editable", build_data)

    assert (pkg_dir / "_core.so").read_bytes() == b"sub"
    assert not build_data.get("force_include")
    fi_editable = build_data["force_include_editable"]
    assert fi_editable["/existing/readme.txt"] == "readme.txt"
    assert "_top.so" in fi_editable.values()
    assert "my_pkg/_core.so" not in fi_editable.values()
