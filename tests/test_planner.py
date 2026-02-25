from __future__ import annotations

from pathlib import Path

import pytest

from hatch_mojo.config import parse_config
from hatch_mojo.planner import plan_jobs


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
    with pytest.raises(ValueError, match="No input files resolved"):
        plan_jobs(tmp_path, config)
