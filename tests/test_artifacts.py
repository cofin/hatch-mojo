from __future__ import annotations

from pathlib import Path
from typing import Any, cast

import pytest

from hatch_mojo.artifacts import register_artifacts
from hatch_mojo.types import BuildJob


def test_register_python_extension_sets_native_flags(tmp_path: Path) -> None:
    build_data: dict[str, object] = {}
    job = BuildJob(
        name="core",
        input_path=tmp_path / "src/mo/pkg/core.mojo",
        output_path=tmp_path / "src/py/pkg/_core.so",
        emit="python-extension",
        module="pkg._core",
        install_kind=None,
        install_path=None,
        include_dirs=(),
        defines=(),
        flags=(),
        env={},
        depends_on=(),
    )
    register_artifacts(root=tmp_path, build_data=build_data, jobs=[job], target_name="wheel")

    force_include = build_data["force_include"]
    assert isinstance(force_include, dict)
    assert str(job.output_path) in force_include
    assert build_data["infer_tag"] is True
    assert build_data["pure_python"] is False


def test_register_python_extension_requires_module(tmp_path: Path) -> None:
    build_data: dict[str, object] = {}
    job = BuildJob(
        name="core",
        input_path=tmp_path / "core.mojo",
        output_path=tmp_path / "_core.so",
        emit="python-extension",
        module=None,
        install_kind=None,
        install_path=None,
        include_dirs=(),
        defines=(),
        flags=(),
        env={},
        depends_on=(),
    )
    with pytest.raises(ValueError, match="missing module"):
        register_artifacts(root=tmp_path, build_data=build_data, jobs=[job], target_name="wheel")


def test_register_non_python_variants(tmp_path: Path) -> None:
    build_data: dict[str, object] = {}
    bin_a = tmp_path / "a.so"
    bin_b = tmp_path / "b.a"
    bin_c = tmp_path / "c"
    bin_d = tmp_path / "d.bin"
    for item in (bin_a, bin_b, bin_c, bin_d):
        item.write_bytes(b"x")

    jobs = [
        BuildJob("a", tmp_path / "a.mojo", bin_a, "shared-lib", None, "package", "mypkg", (), (), (), {}, ()),
        BuildJob("b", tmp_path / "b.mojo", bin_b, "static-lib", None, "root", "ignored", (), (), (), {}, ()),
        BuildJob("c", tmp_path / "c.mojo", bin_c, "executable", None, "force-include", "bin/tool", (), (), (), {}, ()),
        BuildJob("d", tmp_path / "d.mojo", bin_d, "object", None, "data", "share", (), (), (), {}, ()),
    ]
    register_artifacts(root=tmp_path, build_data=build_data, jobs=jobs, target_name="wheel")
    force_include = build_data["force_include"]
    artifacts = build_data["artifacts"]
    assert isinstance(force_include, dict)
    assert isinstance(artifacts, list)
    assert force_include[str(bin_a)] == "mypkg/a.so"
    assert force_include[str(bin_b)] == "b.a"
    assert force_include[str(bin_c)] == "bin/tool"
    assert force_include[str(bin_d)] == "share/d.bin"
    assert "d.bin" in artifacts[0]


def test_register_requires_install_for_non_python(tmp_path: Path) -> None:
    build_data: dict[str, object] = {}
    job = BuildJob(
        name="lib",
        input_path=tmp_path / "lib.mojo",
        output_path=tmp_path / "lib.so",
        emit="shared-lib",
        module=None,
        install_kind=None,
        install_path=None,
        include_dirs=(),
        defines=(),
        flags=(),
        env={},
        depends_on=(),
    )
    with pytest.raises(ValueError, match="missing install mapping"):
        register_artifacts(root=tmp_path, build_data=build_data, jobs=[job], target_name="wheel")


def test_register_unknown_install_kind_raises(tmp_path: Path) -> None:
    build_data: dict[str, object] = {}
    out = tmp_path / "x.bin"
    out.write_bytes(b"x")
    job = BuildJob(
        name="x",
        input_path=tmp_path / "x.mojo",
        output_path=out,
        emit="executable",
        module=None,
        install_kind=cast("Any", "invalid"),
        install_path="bin",
        include_dirs=(),
        defines=(),
        flags=(),
        env={},
        depends_on=(),
    )
    with pytest.raises(ValueError, match="Unknown install kind"):
        register_artifacts(root=tmp_path, build_data=build_data, jobs=[job], target_name="wheel")
