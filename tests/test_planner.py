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
                    "module": "pkg._{stem}",
                }
            ]
        },
        target_name="wheel",
    )
    jobs = plan_jobs(tmp_path, config)
    suffix = _get_suffix_map()["python-extension"]
    assert [job.name for job in jobs] == ["core[1]", "core[2]"]
    assert [job.module for job in jobs] == ["pkg._a", "pkg._b"]
    assert [job.output_path for job in jobs] == [
        tmp_path / "build/mojo/pkg" / f"_a{suffix}",
        tmp_path / "build/mojo/pkg" / f"_b{suffix}",
    ]


def test_plan_jobs_glob_collision_rejected(tmp_path: Path) -> None:
    (tmp_path / "src/mo/pkg").mkdir(parents=True)
    (tmp_path / "src/mo/pkg/a.mojo").write_text("", encoding="utf-8")
    (tmp_path / "src/mo/pkg/b.mojo").write_text("", encoding="utf-8")

    fixed_mod_cfg = parse_config(
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
    with pytest.raises(ValueError, match="Duplicate"):
        plan_jobs(tmp_path, fixed_mod_cfg)

    (tmp_path / "src/cpu").mkdir(parents=True)
    (tmp_path / "src/gpu").mkdir(parents=True)
    (tmp_path / "src/cpu/kernel.mojo").write_text("", encoding="utf-8")
    (tmp_path / "src/gpu/kernel.mojo").write_text("", encoding="utf-8")
    same_stem_cfg = parse_config(
        {
            "jobs": [
                {
                    "name": "kernels",
                    "input": "src/**/kernel.mojo",
                    "emit": "object",
                    "install": {"kind": "package", "path": "pkg"},
                }
            ]
        },
        target_name="wheel",
    )
    with pytest.raises(ValueError, match="Duplicate"):
        plan_jobs(tmp_path, same_stem_cfg)

    same_install_cfg = parse_config(
        {
            "jobs": [
                {
                    "name": "clis",
                    "input": "src/mo/pkg/*.mojo",
                    "emit": "executable",
                    "output": "build/mojo/{stem}",
                    "install": {"kind": "scripts", "path": "my-cli"},
                }
            ]
        },
        target_name="wheel",
    )
    with pytest.raises(ValueError, match="Duplicate"):
        plan_jobs(tmp_path, same_install_cfg)


def test_plan_jobs_glob_and_excluded_literal_depends_on_rewrites(tmp_path: Path) -> None:
    (tmp_path / "src/mo").mkdir(parents=True)
    (tmp_path / "src/mo/a.mojo").write_text("", encoding="utf-8")
    (tmp_path / "src/mo/b.mojo").write_text("", encoding="utf-8")
    (tmp_path / "src/mo/helper.mojo").write_text("", encoding="utf-8")
    (tmp_path / "src/mo/main.mojo").write_text("", encoding="utf-8")

    config = parse_config(
        {
            "exclude": ["**/helper.mojo"],
            "jobs": [
                {
                    "name": "kernels",
                    "input": "src/mo/[ab].mojo",
                    "emit": "python-extension",
                    "module": "pkg._{stem}",
                },
                {
                    "name": "excluded_helper",
                    "input": "src/mo/helper.mojo",
                    "emit": "python-extension",
                    "module": "pkg._helper",
                },
                {
                    "name": "ghost_os",
                    "input": "src/mo/a.mojo",
                    "emit": "python-extension",
                    "module": "pkg._ghost",
                    "platforms": ["nonexistent-os"],
                },
                {
                    "name": "main",
                    "input": "src/mo/main.mojo",
                    "emit": "python-extension",
                    "module": "pkg._main",
                    "depends-on": ["kernels", "excluded_helper", "ghost_os"],
                },
            ],
        },
        target_name="wheel",
    )
    jobs = plan_jobs(tmp_path, config)
    assert [job.name for job in jobs] == ["kernels[1]", "kernels[2]", "main"]
    assert jobs[2].depends_on == ("kernels[1]", "kernels[2]")


def test_plan_jobs_git_style_include_exclude_on_glob_inputs(tmp_path: Path) -> None:
    (tmp_path / "src/mo/sub").mkdir(parents=True)
    (tmp_path / "src/mo/a.mojo").write_text("", encoding="utf-8")
    (tmp_path / "src/mo/sub/experimental_b.mojo").write_text("", encoding="utf-8")
    (tmp_path / "src/mo/sub/keep_c.mojo").write_text("", encoding="utf-8")

    config = parse_config(
        {
            "include": ["src/mo/**/*.mojo"],
            "exclude": ["**/experimental*.mojo"],
            "jobs": [
                {
                    "name": "all",
                    "input": "src/mo/**/*.mojo",
                    "emit": "python-extension",
                    "module": "pkg._{stem}",
                }
            ],
        },
        target_name="wheel",
    )
    jobs = plan_jobs(tmp_path, config)
    assert [job.module for job in jobs] == ["pkg._a", "pkg._keep_c"]


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
    assert m["mojoc"] == ".mojoc"
    assert m["executable"] == ".exe"
    assert "static-lib" not in m


def test_get_suffix_map_darwin(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("hatch_mojo.planner.sys", type("sys", (), {"platform": "darwin"})())
    m = _get_suffix_map()
    assert m["python-extension"] == ".so"
    assert m["shared-lib"] == ".dylib"
    assert m["mojoc"] == ".mojoc"
    assert "static-lib" not in m


def test_get_suffix_map_linux(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("hatch_mojo.planner.sys", type("sys", (), {"platform": "linux"})())
    m = _get_suffix_map()
    assert m["python-extension"] == ".so"
    assert m["shared-lib"] == ".so"
    assert m["mojoc"] == ".mojoc"
    assert "static-lib" not in m


def test_plan_jobs_mojoc_default_output(tmp_path: Path) -> None:
    (tmp_path / "src/mo").mkdir(parents=True)
    (tmp_path / "src/mo/core.mojo").write_text("", encoding="utf-8")
    config = parse_config(
        {
            "jobs": [
                {
                    "name": "core_ir",
                    "input": "src/mo/core.mojo",
                    "emit": "mojoc",
                    "install": {"kind": "package", "path": "mogemma"},
                }
            ]
        },
        target_name="wheel",
    )
    jobs = plan_jobs(tmp_path, config)
    assert jobs[0].output_path == tmp_path / "build/mojo/core.mojoc"


def test_custom_build_dir_default_output(tmp_path: Path) -> None:
    (tmp_path / "src/mo").mkdir(parents=True)
    (tmp_path / "src/mo/core.mojo").write_text("", encoding="utf-8")
    (tmp_path / "src/mo/tool.mojo").write_text("", encoding="utf-8")
    config = parse_config(
        {
            "build-dir": "build/custom_mojo",
            "jobs": [
                {
                    "name": "core",
                    "input": "src/mo/core.mojo",
                    "emit": "python-extension",
                    "module": "mogemma._core",
                },
                {
                    "name": "tool",
                    "input": "src/mo/tool.mojo",
                    "emit": "mojoc",
                    "install": {"kind": "package", "path": "mogemma"},
                },
            ],
        },
        target_name="wheel",
    )
    jobs = plan_jobs(tmp_path, config)
    by_name = {job.name: job for job in jobs}
    suffix = _get_suffix_map()["python-extension"]
    assert by_name["core"].output_path == tmp_path / "build/custom_mojo/mogemma" / f"_core{suffix}"
    assert by_name["tool"].output_path == tmp_path / "build/custom_mojo/tool.mojoc"


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
    suffix = _get_suffix_map()["python-extension"]
    assert jobs[0].output_path == tmp_path / "build/mojo" / "mogemma" / f"_core{suffix}"


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
