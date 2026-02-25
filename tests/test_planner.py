from __future__ import annotations

from pathlib import Path

import pytest

from hatch_mojo.config import parse_config
from hatch_mojo.planner import _get_suffix_map, plan_jobs, plan_jobs_leveled


def test_plan_jobs_orders_dependencies(tmp_path: Path) -> None:
    (tmp_path / "src/mo/pkg").mkdir(parents=True)
    (tmp_path / "src/mo/pkg/a.mojo").write_text("", encoding="utf-8")
    (tmp_path / "src/mo/pkg/b.mojo").write_text("", encoding="utf-8")

    config = parse_config(
        {
            "jobs": [
                {
                    "name": "a",
                    "input": "src/mo/pkg/a.mojo",
                    "emit": "python-extension",
                    "module": "pkg._a",
                },
                {
                    "name": "b",
                    "input": "src/mo/pkg/b.mojo",
                    "emit": "python-extension",
                    "module": "pkg._b",
                    "depends-on": ["a"],
                },
            ]
        },
        target_name="wheel",
    )

    jobs = plan_jobs(tmp_path, config)
    assert jobs[0].name == "a"
    assert jobs[1].name == "b"


def test_plan_jobs_unknown_dependency(tmp_path: Path) -> None:
    (tmp_path / "src/mo/pkg").mkdir(parents=True)
    (tmp_path / "src/mo/pkg/a.mojo").write_text("", encoding="utf-8")
    config = parse_config(
        {
            "jobs": [
                {
                    "name": "a",
                    "input": "src/mo/pkg/a.mojo",
                    "emit": "python-extension",
                    "module": "pkg._a",
                    "depends-on": ["missing"],
                }
            ]
        },
        target_name="wheel",
    )

    with pytest.raises(ValueError, match="unknown dependencies"):
        plan_jobs(tmp_path, config)


def test_plan_jobs_cycle_detected(tmp_path: Path) -> None:
    (tmp_path / "src/mo/pkg").mkdir(parents=True)
    (tmp_path / "src/mo/pkg/a.mojo").write_text("", encoding="utf-8")
    (tmp_path / "src/mo/pkg/b.mojo").write_text("", encoding="utf-8")
    config = parse_config(
        {
            "jobs": [
                {
                    "name": "a",
                    "input": "src/mo/pkg/a.mojo",
                    "emit": "python-extension",
                    "module": "pkg._a",
                    "depends-on": ["b"],
                },
                {
                    "name": "b",
                    "input": "src/mo/pkg/b.mojo",
                    "emit": "python-extension",
                    "module": "pkg._b",
                    "depends-on": ["a"],
                },
            ]
        },
        target_name="wheel",
    )
    with pytest.raises(ValueError, match="Dependency cycle"):
        plan_jobs(tmp_path, config)


def test_plan_jobs_glob_multi_inputs(tmp_path: Path) -> None:
    (tmp_path / "src/mo/pkg").mkdir(parents=True)
    (tmp_path / "src/mo/pkg/a.mojo").write_text("", encoding="utf-8")
    (tmp_path / "src/mo/pkg/b.mojo").write_text("", encoding="utf-8")
    config = parse_config(
        {
            "jobs": [
                {
                    "name": "core",
                    "input": "src/mo/pkg/*.mojo",
                    "emit": "python-extension",
                    "module": "pkg._core",
                }
            ]
        },
        target_name="wheel",
    )
    jobs = plan_jobs(tmp_path, config)
    assert len(jobs) == 2
    assert jobs[0].name.startswith("core[")


def test_plan_jobs_platform_filter(tmp_path: Path) -> None:
    (tmp_path / "src/mo/pkg").mkdir(parents=True)
    (tmp_path / "src/mo/pkg/a.mojo").write_text("", encoding="utf-8")
    config = parse_config(
        {
            "jobs": [
                {
                    "name": "a",
                    "input": "src/mo/pkg/a.mojo",
                    "emit": "python-extension",
                    "module": "pkg._a",
                    "platforms": ["nonexistent-platform"],
                }
            ]
        },
        target_name="wheel",
    )
    assert plan_jobs(tmp_path, config) == []


def test_plan_jobs_missing_input_raises(tmp_path: Path) -> None:
    config = parse_config(
        {
            "jobs": [
                {
                    "name": "missing",
                    "input": "src/mo/pkg/missing.mojo",
                    "emit": "python-extension",
                    "module": "pkg._missing",
                }
            ]
        },
        target_name="wheel",
    )
    with pytest.raises(FileNotFoundError, match="does not exist for job"):
        plan_jobs(tmp_path, config)


def test_get_suffix_map_win32(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("hatch_mojo.planner.sys", type("sys", (), {"platform": "win32"})())
    m = _get_suffix_map()
    assert m["python-extension"] == ".pyd"
    assert m["shared-lib"] == ".dll"
    assert m["executable"] == ".exe"


def test_get_suffix_map_darwin(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("hatch_mojo.planner.sys", type("sys", (), {"platform": "darwin"})())
    m = _get_suffix_map()
    assert m["python-extension"] == ".so"
    assert m["shared-lib"] == ".dylib"


def test_get_suffix_map_linux(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("hatch_mojo.planner.sys", type("sys", (), {"platform": "linux"})())
    m = _get_suffix_map()
    assert m["python-extension"] == ".so"
    assert m["shared-lib"] == ".so"


def test_module_aware_default_output(tmp_path: Path) -> None:
    (tmp_path / "src/mo").mkdir(parents=True)
    (tmp_path / "src/mo/core.mojo").write_text("", encoding="utf-8")
    config = parse_config(
        {
            "jobs": [
                {
                    "name": "core",
                    "input": "src/mo/core.mojo",
                    "emit": "python-extension",
                    "module": "mogemma._core",
                }
            ]
        },
        target_name="wheel",
    )
    jobs = plan_jobs(tmp_path, config)
    assert jobs[0].output_path == tmp_path / ".hatch_mojo" / "mogemma" / "_core.so"


def test_plan_jobs_glob_no_matches_raises(tmp_path: Path) -> None:
    (tmp_path / "src/mo/pkg").mkdir(parents=True)
    config = parse_config(
        {
            "jobs": [
                {
                    "name": "core",
                    "input": "src/mo/pkg/*.mojo",
                    "emit": "python-extension",
                    "module": "pkg._core",
                }
            ]
        },
        target_name="wheel",
    )
    with pytest.raises(ValueError, match="No input files resolved"):
        plan_jobs(tmp_path, config)


def test_plan_jobs_leveled_mixed_deps(tmp_path: Path) -> None:
    (tmp_path / "src/mo/pkg").mkdir(parents=True)
    (tmp_path / "src/mo/pkg/a.mojo").write_text("", encoding="utf-8")
    (tmp_path / "src/mo/pkg/b.mojo").write_text("", encoding="utf-8")
    (tmp_path / "src/mo/pkg/c.mojo").write_text("", encoding="utf-8")
    config = parse_config(
        {
            "jobs": [
                {
                    "name": "a",
                    "input": "src/mo/pkg/a.mojo",
                    "emit": "python-extension",
                    "module": "pkg._a",
                },
                {
                    "name": "b",
                    "input": "src/mo/pkg/b.mojo",
                    "emit": "python-extension",
                    "module": "pkg._b",
                },
                {
                    "name": "c",
                    "input": "src/mo/pkg/c.mojo",
                    "emit": "python-extension",
                    "module": "pkg._c",
                    "depends-on": ["a", "b"],
                },
            ]
        },
        target_name="wheel",
    )
    levels = plan_jobs_leveled(tmp_path, config)
    assert len(levels) == 2
    level0_names = {job.name for job in levels[0]}
    level1_names = {job.name for job in levels[1]}
    assert level0_names == {"a", "b"}
    assert level1_names == {"c"}
