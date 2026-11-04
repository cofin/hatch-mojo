from __future__ import annotations

from pathlib import Path
from typing import Any, cast

import pytest

from hatch_mojo.artifacts import register_artifacts, resolve_install_target
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
    bin_b = tmp_path / "b.mojoc"
    bin_c = tmp_path / "c"
    bin_d = tmp_path / "d.bin"
    for item in (bin_a, bin_b, bin_c, bin_d):
        item.write_bytes(b"x")

    jobs = [
        BuildJob("a", tmp_path / "a.mojo", bin_a, "shared-lib", None, "package", "mypkg", (), (), (), {}, ()),
        BuildJob("b", tmp_path / "b.mojo", bin_b, "mojoc", None, "root", "ignored", (), (), (), {}, ()),
        BuildJob("c", tmp_path / "c.mojo", bin_c, "executable", None, "force-include", "bin/tool", (), (), (), {}, ()),
        BuildJob("d", tmp_path / "d.mojo", bin_d, "object", None, "data", "share", (), (), (), {}, ()),
    ]
    register_artifacts(root=tmp_path, build_data=build_data, jobs=jobs, target_name="wheel")
    force_include = build_data["force_include"]
    shared_data = build_data["shared_data"]
    assert isinstance(force_include, dict)
    assert isinstance(shared_data, dict)
    assert force_include[str(bin_a)] == "mypkg/a.so"
    assert force_include[str(bin_b)] == "b.mojoc"
    assert force_include[str(bin_c)] == "bin/tool"
    assert str(bin_d) not in force_include
    assert shared_data[str(bin_d)] == "share/d.bin"


def test_register_scripts_and_data_use_shared_maps(tmp_path: Path) -> None:
    root = tmp_path / "project"
    root.mkdir()
    external_dir = tmp_path / "external_build"
    external_dir.mkdir()

    cli_exact = external_dir / "cli_bin"
    cli_sub = external_dir / "my-cli"
    data_dir_item = external_dir / "d.bin"
    data_exact_item = external_dir / "raw.bin"
    fi_dir_item = external_dir / "lib.so"
    fi_exact_item = external_dir / "exact.so"
    root_item = external_dir / "top.mojoc"
    for item in (cli_exact, cli_sub, data_dir_item, data_exact_item, fi_dir_item, fi_exact_item, root_item):
        item.write_bytes(b"x")

    jobs = [
        BuildJob("cli1", root / "a.mojo", cli_exact, "executable", None, "scripts", "my-cli", (), (), (), {}, ()),
        BuildJob("cli2", root / "b.mojo", cli_sub, "executable", None, "scripts", "sub/", (), (), (), {}, ()),
        BuildJob("dat1", root / "c.mojo", data_dir_item, "object", None, "data", "share", (), (), (), {}, ()),
        BuildJob(
            "dat2", root / "d.mojo", data_exact_item, "object", None, "data", "share/custom.dat", (), (), (), {}, ()
        ),
        BuildJob("fi1", root / "e.mojo", fi_dir_item, "shared-lib", None, "force-include", "lib/", (), (), (), {}, ()),
        BuildJob(
            "fi2",
            root / "f.mojo",
            fi_exact_item,
            "shared-lib",
            None,
            "force-include",
            "custom/lib.so",
            (),
            (),
            (),
            {},
            (),
        ),
        BuildJob("rt", root / "g.mojo", root_item, "mojoc", None, "root", None, (), (), (), {}, ()),
    ]

    assert [resolve_install_target(job) for job in jobs] == [
        "my-cli",
        "sub/my-cli",
        "share/d.bin",
        "share/custom.dat",
        "lib/lib.so",
        "custom/lib.so",
        "top.mojoc",
    ]

    build_data: dict[str, object] = {}
    register_artifacts(root=root, build_data=build_data, jobs=jobs, target_name="wheel")

    force_include = cast("dict[str, str]", build_data["force_include"])
    shared_scripts = cast("dict[str, str]", build_data["shared_scripts"])
    shared_data = cast("dict[str, str]", build_data["shared_data"])

    assert shared_scripts == {
        str(cli_exact): "my-cli",
        str(cli_sub): "sub/my-cli",
    }
    assert shared_data == {
        str(data_dir_item): "share/d.bin",
        str(data_exact_item): "share/custom.dat",
    }
    assert str(cli_exact) not in force_include
    assert str(cli_sub) not in force_include
    assert str(data_dir_item) not in force_include
    assert str(data_exact_item) not in force_include
    assert force_include[str(fi_dir_item)] == "lib/lib.so"
    assert force_include[str(fi_exact_item)] == "custom/lib.so"
    assert force_include[str(root_item)] == "top.mojoc"


def test_register_mojoc_only_keeps_pure_python(tmp_path: Path) -> None:
    build_data: dict[str, object] = {}
    ir_file = tmp_path / "mod.mojoc"
    obj_file = tmp_path / "mod.o"
    ir_file.write_bytes(b"x")
    obj_file.write_bytes(b"x")
    jobs = [
        BuildJob("ir", tmp_path / "mod.mojo", ir_file, "mojoc", None, "package", "mypkg", (), (), (), {}, ()),
        BuildJob("obj", tmp_path / "mod.mojo", obj_file, "object", None, "package", "mypkg", (), (), (), {}, ()),
    ]
    register_artifacts(root=tmp_path, build_data=build_data, jobs=jobs, target_name="wheel")
    assert "infer_tag" not in build_data
    assert "pure_python" not in build_data


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
