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

    # Write the pyproject.toml
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
    src_mo.write_text("fn main(): pass", encoding="utf-8")

    src_py = project_dir / "src" / "my_pkg" / "__init__.py"
    src_py.parent.mkdir(parents=True, exist_ok=True)
    src_py.write_text("print('hello')", encoding="utf-8")

    # Run uv build --wheel
    res = subprocess.run(
        ["uv", "build", "--wheel"],
        cwd=project_dir,
        capture_output=True,
        text=True,
        check=False,
    )

    # We must ensure the command succeeded
    assert res.returncode == 0, f"uv build failed!\nSTDOUT: {res.stdout}\nSTDERR: {res.stderr}"

    dist_dir = project_dir / "dist"
    wheels = list(dist_dir.glob("*.whl"))
    assert len(wheels) == 1, f"Expected 1 wheel, found {len(wheels)}"

    wheel_path = wheels[0]

    # Analyze the ZIP contents of the wheel
    with zipfile.ZipFile(wheel_path, "r") as zf:
        namelist = zf.namelist()

    # Determine the expected suffix for the current platform
    if sys.platform == "win32":
        suffix = ".pyd"
    else:
        suffix = ".so"

    expected_extension = f"my_pkg/_core{suffix}"
    assert expected_extension in namelist, (
        f"Native extension {expected_extension} not found in wheel! Contents: {namelist}"
    )

    # Also verify that the standard __init__.py is included
    assert "my_pkg/__init__.py" in namelist
