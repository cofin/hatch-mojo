from __future__ import annotations

import subprocess
import sys
import textwrap
import zipfile
from pathlib import Path


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
