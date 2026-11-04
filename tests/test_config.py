from __future__ import annotations

import pytest
from packaging.markers import InvalidMarker

from hatch_mojo.config import parse_config


def test_parse_config_python_extension() -> None:
    config = parse_config(
        {
            "jobs": [
                {
                    "name": "core",
                    "input": "src/mo/pkg/core.mojo",
                    "emit": "python-extension",
                    "module": "pkg._core",
                }
            ]
        },
        target_name="wheel",
    )
    assert len(config.jobs) == 1
    assert config.jobs[0].module == "pkg._core"


def test_parse_config_requires_install_for_non_python() -> None:
    with pytest.raises(ValueError, match="requires explicit install mapping"):
        parse_config(
            {
                "jobs": [
                    {
                        "name": "lib",
                        "input": "src/mo/pkg/lib.mojo",
                        "emit": "shared-lib",
                    }
                ]
            },
            target_name="wheel",
        )


def test_parse_config_profile_merge() -> None:
    config = parse_config(
        {
            "profiles": {"common": {"include-dirs": ["src/mo"]}},
            "jobs": [
                {
                    "name": "core",
                    "profiles": ["common"],
                    "input": "src/mo/pkg/core.mojo",
                    "emit": "python-extension",
                    "module": "pkg._core",
                }
            ],
        },
        target_name="wheel",
    )
    assert config.jobs[0].include_dirs == ("src/mo",)


def test_parse_config_target_filter_returns_no_jobs() -> None:
    config = parse_config(
        {
            "targets": ["wheel"],
            "jobs": [
                {
                    "name": "core",
                    "input": "src/mo/pkg/core.mojo",
                    "emit": "python-extension",
                    "module": "pkg._core",
                }
            ],
        },
        target_name="sdist",
    )
    assert config.jobs == ()


def test_parse_config_invalid_profile_type() -> None:
    with pytest.raises(TypeError):
        parse_config({"profiles": []}, target_name="wheel")


def test_parse_config_invalid_jobs_type() -> None:
    with pytest.raises(TypeError, match="jobs/sources must be a list"):
        parse_config({"jobs": {}}, target_name="wheel")
    with pytest.raises(TypeError, match="jobs/sources must be a list"):
        parse_config({"sources": 123}, target_name="wheel")


def test_parse_config_unknown_profile() -> None:
    with pytest.raises(ValueError, match="Unknown profile"):
        parse_config(
            {
                "profiles": {"common": {"flags": ["--x"]}},
                "jobs": [
                    {
                        "profiles": ["missing"],
                        "input": "src/mo/pkg/core.mojo",
                        "emit": "python-extension",
                        "module": "pkg._core",
                    }
                ],
            },
            target_name="wheel",
        )


def test_parse_config_include_exclude() -> None:
    config = parse_config(
        {
            "include": ["src/mo/pkg/*.mojo"],
            "exclude": ["*skip.mojo"],
            "jobs": [
                {
                    "name": "keep",
                    "input": "src/mo/pkg/core.mojo",
                    "emit": "python-extension",
                    "module": "pkg._core",
                },
                {
                    "name": "skip",
                    "input": "src/mo/pkg/skip.mojo",
                    "emit": "python-extension",
                    "module": "pkg._skip",
                },
            ],
        },
        target_name="wheel",
    )
    assert [job.name for job in config.jobs] == ["keep"]


def test_parse_config_rejects_bad_install_kind() -> None:
    with pytest.raises(ValueError, match=r"invalid install\.kind"):
        parse_config(
            {
                "jobs": [
                    {
                        "name": "bin",
                        "input": "src/mo/pkg/bin.mojo",
                        "emit": "executable",
                        "install": {"kind": "nope", "path": "bin/x"},
                    }
                ]
            },
            target_name="wheel",
        )


def test_parse_config_rejects_install_without_path() -> None:
    with pytest.raises(ValueError, match="requires 'path'"):
        parse_config(
            {
                "jobs": [
                    {
                        "name": "bin",
                        "input": "src/mo/pkg/bin.mojo",
                        "emit": "executable",
                        "install": {"kind": "force-include"},
                    }
                ]
            },
            target_name="wheel",
        )


def test_parse_config_bundle_libs_defaults_true() -> None:
    config = parse_config(
        {
            "jobs": [
                {
                    "name": "core",
                    "input": "src/mo/pkg/core.mojo",
                    "emit": "python-extension",
                    "module": "pkg._core",
                }
            ]
        },
        target_name="wheel",
    )
    assert config.bundle_libs is True


def test_parse_config_bundle_libs_explicit_false() -> None:
    config = parse_config(
        {
            "bundle-libs": False,
            "jobs": [
                {
                    "name": "core",
                    "input": "src/mo/pkg/core.mojo",
                    "emit": "python-extension",
                    "module": "pkg._core",
                }
            ],
        },
        target_name="wheel",
    )
    assert config.bundle_libs is False


def test_parse_config_rejects_invalid_marker() -> None:
    with pytest.raises(InvalidMarker):
        parse_config(
            {
                "jobs": [
                    {
                        "name": "bin",
                        "input": "src/mo/pkg/bin.mojo",
                        "emit": "python-extension",
                        "module": "pkg._bin",
                        "marker": "python_version ? '3.10'",
                    }
                ]
            },
            target_name="wheel",
        )


def test_parse_config_accepts_mojoc_with_install() -> None:
    config = parse_config(
        {
            "jobs": [
                {
                    "name": "pkg_ir",
                    "input": "src/mo/pkg/lib.mojo",
                    "emit": "mojoc",
                    "install": {"kind": "package", "path": "pkg"},
                }
            ]
        },
        target_name="wheel",
    )
    assert len(config.jobs) == 1
    assert config.jobs[0].emit == "mojoc"
    assert config.jobs[0].install_kind == "package"


def test_parse_config_mojoc_requires_install() -> None:
    with pytest.raises(ValueError, match="requires explicit install mapping"):
        parse_config(
            {
                "jobs": [
                    {
                        "name": "pkg_ir",
                        "input": "src/mo/pkg/lib.mojo",
                        "emit": "mojoc",
                    }
                ]
            },
            target_name="wheel",
        )


def test_parse_config_rejects_removed_static_lib() -> None:
    with pytest.raises(ValueError, match=r"static-lib.*Mojo 1\.x"):
        parse_config(
            {
                "jobs": [
                    {
                        "name": "legacy_static",
                        "input": "src/mo/pkg/lib.mojo",
                        "emit": "static-lib",
                        "install": {"kind": "package", "path": "pkg"},
                    }
                ]
            },
            target_name="wheel",
        )


@pytest.mark.parametrize(
    ("field", "bad_path"),
    [
        ("input", "src/core.🔥"),
        ("input", "src/pkg📦"),
        ("input", "dist/core.mojopkg"),
        ("output", "pkg.mojopkg"),
        ("output", "build/core.🔥"),
        ("output", "build/pkg📦"),
    ],
)
def test_parse_config_rejects_removed_mojo_0x_paths(field: str, bad_path: str) -> None:
    job_dict: dict[str, object] = {
        "name": "legacy_path",
        "input": "src/mo/pkg/core.mojo",
        "emit": "shared-lib",
    }
    job_dict[field] = bad_path
    with pytest.raises(ValueError, match=r"Mojo 0\.x"):
        parse_config({"jobs": [job_dict]}, target_name="wheel")


def test_parse_config_profile_deep_merge() -> None:
    config = parse_config(
        {
            "profiles": {
                "base": {
                    "include-dirs": ["src/mo", "src/shared"],
                    "defines": ["A=1", "B=2"],
                    "flags": ["-Xlinker", "-foo"],
                    "depends-on": ["prep"],
                    "env": {"FOO": "base", "SHARED": "1"},
                },
                "opt": {
                    "include_dirs": ["src/shared", "src/opt"],
                    "defines": ["B=2", "C=3"],
                    "extra-args": ["-O3", "-Xlinker", "-bar"],
                    "depends_on": ["prep", "codegen"],
                    "env": {"BAR": "opt", "SHARED": "2"},
                },
            },
            "jobs": [
                {
                    "name": "core",
                    "profiles": ["base", "opt"],
                    "input": "src/mo/pkg/core.mojo",
                    "emit": "python-extension",
                    "module": "pkg._core",
                    "include-dirs": ["src/mo", "src/local"],
                    "defines": ["A=1", "D=4"],
                    "flags": ["-Xlinker", "-baz"],
                    "depends-on": ["codegen", "post"],
                    "env": {"SHARED": "job", "LOCAL": "yes"},
                }
            ],
        },
        target_name="wheel",
    )
    job = config.jobs[0]
    assert job.flags == ("-Xlinker", "-foo", "-O3", "-Xlinker", "-bar", "-Xlinker", "-baz")
    assert job.include_dirs == ("src/mo", "src/shared", "src/opt", "src/local")
    assert job.defines == ("A=1", "B=2", "C=3", "D=4")
    assert job.depends_on == ("prep", "codegen", "post")
    assert job.env == {"FOO": "base", "BAR": "opt", "SHARED": "job", "LOCAL": "yes"}


def test_parse_config_rejects_non_dict_install_and_extension_install() -> None:
    with pytest.raises(TypeError, match="install"):
        parse_config(
            {
                "jobs": [
                    {
                        "name": "cli",
                        "input": "cli.mojo",
                        "emit": "executable",
                        "install": "bin",
                    }
                ]
            },
            target_name="wheel",
        )

    with pytest.raises(ValueError, match="path"):
        parse_config(
            {
                "jobs": [
                    {
                        "name": "cli",
                        "input": "cli.mojo",
                        "emit": "executable",
                        "install": {"kind": "scripts", "path": " / "},
                    }
                ]
            },
            target_name="wheel",
        )

    with pytest.raises(ValueError, match="install"):
        parse_config(
            {
                "jobs": [
                    {
                        "name": "ext",
                        "input": "core.mojo",
                        "emit": "python-extension",
                        "module": "pkg._core",
                        "install": {"kind": "root", "path": "x"},
                    }
                ]
            },
            target_name="wheel",
        )

    root_cfg = parse_config(
        {
            "jobs": [
                {
                    "name": "top",
                    "input": "top.mojo",
                    "emit": "shared-lib",
                    "install": {"kind": "root"},
                }
            ]
        },
        target_name="wheel",
    )
    assert root_cfg.jobs[0].install_kind == "root"
    assert root_cfg.jobs[0].install_path is None


def test_parse_config_skip_editable_and_cache_defaults_and_env_overrides(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("HATCH_MOJO_SKIP_EDITABLE", raising=False)
    monkeypatch.delenv("HATCH_MOJO_CACHE", raising=False)

    raw = {
        "jobs": [
            {
                "name": "core",
                "input": "src/mo/pkg/core.mojo",
                "emit": "python-extension",
                "module": "pkg._core",
            }
        ]
    }
    cfg = parse_config(raw, target_name="wheel")
    assert cfg.skip_editable is False
    assert cfg.cache is True

    inactive = parse_config(raw, target_name="sdist")
    assert inactive.skip_editable is False
    assert inactive.cache is True

    monkeypatch.setenv("HATCH_MOJO_SKIP_EDITABLE", "1")
    monkeypatch.setenv("HATCH_MOJO_CACHE", "false")
    overridden = parse_config({**raw, "skip-editable": False, "cache": True}, target_name="wheel")
    assert overridden.skip_editable is True
    assert overridden.cache is False

    monkeypatch.setenv("HATCH_MOJO_CACHE", "maybe")
    with pytest.raises(ValueError, match="HATCH_MOJO_CACHE"):
        parse_config(raw, target_name="wheel")


def test_parse_config_empty_vs_excluded_jobs() -> None:
    with pytest.raises(ValueError, match="No build jobs resolved"):
        parse_config({"jobs": []}, target_name="wheel")

    filtered = parse_config(
        {
            "exclude": ["src/mo/**/*.mojo"],
            "jobs": [
                {
                    "name": "only",
                    "input": "src/mo/core.mojo",
                    "emit": "python-extension",
                    "module": "pkg._core",
                }
            ],
        },
        target_name="wheel",
    )
    assert filtered.jobs == ()
    assert filtered.excluded_jobs == ("only",)


def test_parse_config_wheel_tag_variants_and_validation(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("HATCH_MOJO_WHEEL_TAG", raising=False)
    job = {
        "name": "core",
        "input": "src/mo/core.mojo",
        "emit": "python-extension",
        "module": "pkg._core",
    }

    default_cfg = parse_config({"jobs": [job]}, target_name="wheel")
    assert default_cfg.wheel_tag == "auto"

    for valid in ("infer", "py3-none", "py3-none-manylinux_2_34_x86_64"):
        cfg = parse_config({"wheel-tag": valid, "jobs": [job]}, target_name="wheel")
        assert cfg.wheel_tag == valid

    alias_cfg = parse_config({"wheel_tag": "py3-none", "jobs": [job]}, target_name="wheel")
    assert alias_cfg.wheel_tag == "py3-none"

    monkeypatch.setenv("HATCH_MOJO_WHEEL_TAG", "cp312-abi3-manylinux_2_34_x86_64")
    env_cfg = parse_config({"wheel-tag": "infer", "jobs": [job]}, target_name="wheel")
    assert env_cfg.wheel_tag == "cp312-abi3-manylinux_2_34_x86_64"
    monkeypatch.delenv("HATCH_MOJO_WHEEL_TAG", raising=False)

    with pytest.raises(TypeError, match="wheel-tag"):
        parse_config({"wheel-tag": 123, "jobs": [job]}, target_name="wheel")

    for bad_tag in ("", "bad", "py3-none-", "-none-any", "a-b-c-d"):
        with pytest.raises(ValueError, match="wheel-tag"):
            parse_config({"wheel-tag": bad_tag, "jobs": [job]}, target_name="wheel")
