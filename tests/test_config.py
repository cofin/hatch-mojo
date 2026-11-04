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
    with pytest.raises(ValueError, match="No build jobs resolved"):
        parse_config({"jobs": {}}, target_name="wheel")


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
