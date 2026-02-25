from __future__ import annotations

from pathlib import Path

from hatch_mojo.compiler import compile_job
from hatch_mojo.types import BuildJob


def _write_fake_mojo(path: Path) -> None:
    path.write_text(
        "#!/usr/bin/env python3\n"
        "import pathlib\n"
        "import sys\n"
        "output = pathlib.Path(sys.argv[sys.argv.index('-o') + 1])\n"
        "output.parent.mkdir(parents=True, exist_ok=True)\n"
        "output.write_bytes(b'ok')\n",
        encoding="utf-8",
    )
    path.chmod(0o755)


def test_compile_job_creates_output(tmp_path: Path) -> None:
    fake_mojo = tmp_path / "mojo"
    _write_fake_mojo(fake_mojo)
    source = tmp_path / "src/mo/pkg/core.mojo"
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_text("fn main():\n    pass\n", encoding="utf-8")
    output = tmp_path / "src/py/pkg/_core.so"

    job = BuildJob(
        name="core",
        input_path=source,
        output_path=output,
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
    success, _ = compile_job(mojo_bin=str(fake_mojo), root=tmp_path, job=job)
    assert success
    assert output.exists()
