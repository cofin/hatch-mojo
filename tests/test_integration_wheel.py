from __future__ import annotations

import subprocess
import sys
import textwrap
import zipfile
from pathlib import Path

from hatchling.builders.wheel import WheelBuilder


def _write_fake_mojo(path: Path) -> None:
    path.write_text(
        "#!/usr/bin/env python3\n"
        "import pathlib\n"
        "import sys\n"
        "output = pathlib.Path(sys.argv[sys.argv.index('-o') + 1])\n"
        "output.parent.mkdir(parents=True, exist_ok=True)\n"
        "output.write_bytes(b'fake-native-lib')\n",
        encoding="utf-8",
    )
    path.chmod(0o755)


def test_wheel_build_includes_native_extension(tmp_path: Path) -> None:
    repo_root = Path(__file__).parent.parent.absolute()
    project_dir = tmp_path / "my_pkg"
    project_dir.mkdir()

    fake_mojo = project_dir / "mojo"
    _write_fake_mojo(fake_mojo)

    pyproject = project_dir / "pyproject.toml"
    content = textwrap.dedent(f"""
        [project]
        name = "my_pkg"
        version = "1.0.0"

        [build-system]
        build-backend = "hatchling.build"
        requires = ["hatchling", "hatch-mojo @ file://{repo_root.as_posix()}"]

        [tool.hatch.build.targets.wheel.hooks.mojo]
        targets = ["wheel"]
        mojo-bin = "{fake_mojo.as_posix()}"
        bundle-libs = false

        [[tool.hatch.build.targets.wheel.hooks.mojo.jobs]]
        name = "core"
        input = "src/mo/core.mojo"
        emit = "python-extension"
        module = "my_pkg._core"
    """)
    pyproject.write_text(content, encoding="utf-8")

    src_mo = project_dir / "src" / "mo" / "core.mojo"
    src_mo.parent.mkdir(parents=True, exist_ok=True)
    src_mo.write_text(
        "from std.python import PythonObject\n"
        "from std.python.bindings import PythonModuleBuilder\n\n"
        "@export\n"
        'def PyInit__core() abi("C") -> PythonObject:\n'
        '    var b = PythonModuleBuilder("_core")\n'
        "    return b.finalize()\n",
        encoding="utf-8",
    )

    src_py = project_dir / "src" / "my_pkg" / "__init__.py"
    src_py.parent.mkdir(parents=True, exist_ok=True)
    src_py.write_text("print('hello')", encoding="utf-8")

    res = subprocess.run(
        ["uv", "build", "--wheel", "--refresh-package", "hatch-mojo"],
        cwd=project_dir,
        capture_output=True,
        text=True,
        check=False,
    )
    assert res.returncode == 0, f"uv build failed!\nSTDOUT: {res.stdout}\nSTDERR: {res.stderr}"

    dist_dir = project_dir / "dist"
    wheels = list(dist_dir.glob("*.whl"))
    assert len(wheels) == 1, f"Expected 1 wheel, found {len(wheels)}"

    wheel_path = wheels[0]
    with zipfile.ZipFile(wheel_path, "r") as zf:
        namelist = zf.namelist()

    suffix = ".pyd" if sys.platform == "win32" else ".so"
    expected_extension = f"my_pkg/_core{suffix}"
    assert expected_extension in namelist, (
        f"Native extension {expected_extension} not found in wheel! Contents: {namelist}"
    )
    assert "my_pkg/__init__.py" in namelist


def test_wheel_build_with_clean_after_build_and_custom_build_dir(tmp_path: Path) -> None:
    repo_root = Path(__file__).parent.parent.absolute()
    project_dir = tmp_path / "clean_pkg"
    project_dir.mkdir()

    fake_mojo = project_dir / "mojo"
    _write_fake_mojo(fake_mojo)

    pyproject = project_dir / "pyproject.toml"
    content = textwrap.dedent(f"""
        [project]
        name = "my_pkg"
        version = "1.0.0"

        [build-system]
        build-backend = "hatchling.build"
        requires = ["hatchling", "hatch-mojo @ file://{repo_root.as_posix()}"]

        [tool.hatch.build.targets.wheel.hooks.mojo]
        targets = ["wheel"]
        mojo-bin = "{fake_mojo.as_posix()}"
        bundle-libs = false
        build-dir = "build/custom_mojo"
        clean-after-build = true

        [[tool.hatch.build.targets.wheel.hooks.mojo.jobs]]
        name = "core"
        input = "src/mo/core.mojo"
        emit = "python-extension"
        module = "my_pkg._core"
    """)
    pyproject.write_text(content, encoding="utf-8")

    src_mo = project_dir / "src" / "mo" / "core.mojo"
    src_mo.parent.mkdir(parents=True, exist_ok=True)
    src_mo.write_text("def main():\n    pass\n", encoding="utf-8")

    src_py = project_dir / "src" / "my_pkg" / "__init__.py"
    src_py.parent.mkdir(parents=True, exist_ok=True)
    src_py.write_text("", encoding="utf-8")

    res = subprocess.run(
        ["uv", "build", "--wheel", "--refresh-package", "hatch-mojo"],
        cwd=project_dir,
        capture_output=True,
        text=True,
        check=False,
    )
    assert res.returncode == 0, f"uv build failed!\nSTDOUT: {res.stdout}\nSTDERR: {res.stderr}"

    wheels = list((project_dir / "dist").glob("*.whl"))
    assert len(wheels) == 1
    with zipfile.ZipFile(wheels[0], "r") as zf:
        namelist = zf.namelist()

    suffix = ".pyd" if sys.platform == "win32" else ".so"
    assert f"my_pkg/_core{suffix}" in namelist
    assert not (project_dir / "build" / "custom_mojo").exists()


def test_wheel_build_installs_executable_in_data_scripts(tmp_path: Path) -> None:
    repo_root = Path(__file__).parent.parent.absolute()
    project_dir = tmp_path / "cli_pkg"
    project_dir.mkdir()

    binary_payload = b"\x7fELF\x02\x01\x01\x00\xff\xfe-native-cli"
    fake_mojo = project_dir / "mojo"
    fake_mojo.write_text(
        "#!/usr/bin/env python3\n"
        "import pathlib\n"
        "import sys\n"
        "output = pathlib.Path(sys.argv[sys.argv.index('-o') + 1])\n"
        "output.parent.mkdir(parents=True, exist_ok=True)\n"
        f"output.write_bytes({binary_payload!r})\n",
        encoding="utf-8",
    )
    fake_mojo.chmod(0o755)

    pyproject = project_dir / "pyproject.toml"
    pyproject.write_text(
        textwrap.dedent(f"""
            [project]
            name = "my-pkg"
            version = "1.0.0"

            [build-system]
            build-backend = "hatchling.build"
            requires = ["hatchling", "hatch-mojo @ file://{repo_root.as_posix()}"]

            [tool.hatch.build.targets.wheel.hooks.mojo]
            targets = ["wheel"]
            mojo-bin = "{fake_mojo.as_posix()}"
            bundle-libs = false

            [[tool.hatch.build.targets.wheel.hooks.mojo.jobs]]
            name = "cli"
            input = "cli.mojo"
            emit = "executable"
            install = {{ kind = "scripts", path = "my-cli" }}
        """),
        encoding="utf-8",
    )
    (project_dir / "cli.mojo").write_text("def main():\n    pass\n", encoding="utf-8")

    res = subprocess.run(
        ["uv", "build", "--wheel", "--refresh-package", "hatch-mojo"],
        cwd=project_dir,
        capture_output=True,
        text=True,
        check=False,
    )
    assert res.returncode == 0, f"uv build failed!\nSTDOUT: {res.stdout}\nSTDERR: {res.stderr}"

    wheels = list((project_dir / "dist").glob("*.whl"))
    assert len(wheels) == 1
    with zipfile.ZipFile(wheels[0], "r") as zf:
        namelist = zf.namelist()
        assert "my_pkg-1.0.0.data/scripts/my-cli" in namelist, f"Contents: {namelist}"
        assert zf.read("my_pkg-1.0.0.data/scripts/my-cli") == binary_payload


def test_editable_wheel_build_succeeds_by_default(tmp_path: Path) -> None:
    project_dir = tmp_path / "editable_pkg"
    project_dir.mkdir()

    fake_mojo = project_dir / "mojo"
    _write_fake_mojo(fake_mojo)

    pyproject = project_dir / "pyproject.toml"
    pyproject.write_text(
        textwrap.dedent(f"""
            [project]
            name = "my-pkg"
            version = "1.0.0"

            [build-system]
            build-backend = "hatchling.build"
            requires = ["hatchling", "hatch-mojo"]

            [tool.hatch.build.targets.wheel.hooks.mojo]
            mojo-bin = "{fake_mojo.as_posix()}"
            bundle-libs = false

            [[tool.hatch.build.targets.wheel.hooks.mojo.jobs]]
            name = "core"
            input = "src/mo/core.mojo"
            emit = "python-extension"
            module = "my_pkg._core"
        """),
        encoding="utf-8",
    )

    src_mo = project_dir / "src" / "mo" / "core.mojo"
    src_mo.parent.mkdir(parents=True)
    src_mo.write_text("def main():\n    pass\n", encoding="utf-8")

    pkg_dir = project_dir / "src" / "my_pkg"
    pkg_dir.mkdir(parents=True)
    (pkg_dir / "__init__.py").write_text("", encoding="utf-8")

    dist_dir = project_dir / "dist"
    builder = WheelBuilder(str(project_dir))
    artifacts = list(builder.build(directory=str(dist_dir), versions=["editable"]))
    assert len(artifacts) == 1

    suffix = ".pyd" if sys.platform == "win32" else ".so"
    copied_ext = pkg_dir / f"_core{suffix}"
    assert copied_ext.is_file()

    with zipfile.ZipFile(artifacts[0], "r") as zf:
        namelist = zf.namelist()
    assert f"my_pkg/_core{suffix}" not in namelist
    assert any(name.endswith(".pth") for name in namelist)


def test_wheel_build_py3_none_extension_and_auto_executable(tmp_path: Path) -> None:
    repo_root = Path(__file__).parent.parent.absolute()

    ext_dir = tmp_path / "py3_ext_pkg"
    ext_dir.mkdir()
    fake_mojo_ext = ext_dir / "mojo"
    _write_fake_mojo(fake_mojo_ext)
    (ext_dir / "pyproject.toml").write_text(
        textwrap.dedent(f"""
            [project]
            name = "py3-ext-pkg"
            version = "1.0.0"

            [build-system]
            build-backend = "hatchling.build"
            requires = ["hatchling", "hatch-mojo @ file://{repo_root.as_posix()}"]

            [tool.hatch.build.targets.wheel.hooks.mojo]
            mojo-bin = "{fake_mojo_ext.as_posix()}"
            bundle-libs = false
            wheel-tag = "py3-none"

            [[tool.hatch.build.targets.wheel.hooks.mojo.jobs]]
            name = "core"
            input = "src/mo/core.mojo"
            emit = "python-extension"
            module = "py3_ext_pkg._core"
        """),
        encoding="utf-8",
    )
    (ext_dir / "src" / "mo").mkdir(parents=True)
    (ext_dir / "src" / "mo" / "core.mojo").write_text("def main(): pass\n", encoding="utf-8")
    (ext_dir / "src" / "py3_ext_pkg").mkdir(parents=True)
    (ext_dir / "src" / "py3_ext_pkg" / "__init__.py").write_text("", encoding="utf-8")

    res_ext = subprocess.run(
        ["uv", "build", "--wheel", "--refresh-package", "hatch-mojo"],
        cwd=ext_dir,
        capture_output=True,
        text=True,
        check=False,
    )
    assert res_ext.returncode == 0, f"STDOUT: {res_ext.stdout}\nSTDERR: {res_ext.stderr}"
    ext_wheels = list((ext_dir / "dist").glob("*.whl"))
    assert len(ext_wheels) == 1
    assert "-py3-none-" in ext_wheels[0].name
    with zipfile.ZipFile(ext_wheels[0], "r") as zf:
        wheel_meta = zf.read("py3_ext_pkg-1.0.0.dist-info/WHEEL").decode("utf-8")
    assert "Root-Is-Purelib: false" in wheel_meta
    assert "Tag: py3-none-" in wheel_meta

    cli_dir = tmp_path / "auto_cli_pkg"
    cli_dir.mkdir()
    fake_mojo_cli = cli_dir / "mojo"
    _write_fake_mojo(fake_mojo_cli)
    (cli_dir / "pyproject.toml").write_text(
        textwrap.dedent(f"""
            [project]
            name = "auto-cli-pkg"
            version = "1.0.0"

            [build-system]
            build-backend = "hatchling.build"
            requires = ["hatchling", "hatch-mojo @ file://{repo_root.as_posix()}"]

            [tool.hatch.build.targets.wheel.hooks.mojo]
            mojo-bin = "{fake_mojo_cli.as_posix()}"
            bundle-libs = false

            [[tool.hatch.build.targets.wheel.hooks.mojo.jobs]]
            name = "cli"
            input = "cli.mojo"
            emit = "executable"
            install = {{ kind = "scripts", path = "my-cli" }}
        """),
        encoding="utf-8",
    )
    (cli_dir / "cli.mojo").write_text("def main(): pass\n", encoding="utf-8")

    res_cli = subprocess.run(
        ["uv", "build", "--wheel", "--refresh-package", "hatch-mojo"],
        cwd=cli_dir,
        capture_output=True,
        text=True,
        check=False,
    )
    assert res_cli.returncode == 0, f"STDOUT: {res_cli.stdout}\nSTDERR: {res_cli.stderr}"
    cli_wheels = list((cli_dir / "dist").glob("*.whl"))
    assert len(cli_wheels) == 1
    assert "-py3-none-" in cli_wheels[0].name
    with zipfile.ZipFile(cli_wheels[0], "r") as zf:
        cli_wheel_meta = zf.read("auto_cli_pkg-1.0.0.dist-info/WHEEL").decode("utf-8")
    assert "Root-Is-Purelib: false" in cli_wheel_meta
    assert "Tag: py3-none-" in cli_wheel_meta
