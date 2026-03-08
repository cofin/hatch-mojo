"""Mojo compiler discovery and invocation."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

from hatch_mojo.types import BuildJob


def discover_mojo(root: Path, configured: str | None) -> str:
    """Find mojo binary from config, env, PATH, or local venv."""
    if configured:
        return configured

    env_override = os.getenv("HATCH_MOJO_BIN")
    if env_override:
        return env_override

    found = shutil.which("mojo")
    if found:
        return found

    candidate = root / ".venv" / "bin" / "mojo"
    if candidate.exists():
        return str(candidate)

    msg = "mojo executable not found (config, HATCH_MOJO_BIN, PATH, .venv/bin/mojo)"
    raise FileNotFoundError(msg)


def build_command(mojo_bin: str, root: Path, job: BuildJob) -> list[str]:
    """Build the mojo compiler command for one job."""
    emit_map = {
        "python-extension": "shared-lib",
        "shared-lib": "shared-lib",
        "static-lib": "static-lib",
        "object": "object",
        "executable": "executable",
    }
    command: list[str] = [mojo_bin, "build", "--emit", emit_map[job.emit]]
    for include_dir in job.include_dirs:
        command.extend(["-I", include_dir])
    for define in job.defines:
        command.extend(["-D", define])

    if sys.platform == "darwin" and job.emit in {"python-extension", "shared-lib", "executable"}:
        # Ensure we have enough Mach-O header space to run install_name_tool later
        command.extend(["-Xlinker", "-headerpad_max_install_names"])

    command.extend([*job.flags, str(job.input_path.relative_to(root)), "-o", str(job.output_path.relative_to(root))])
    return command


def compile_job(*, mojo_bin: str, root: Path, job: BuildJob, fail_fast: bool = True) -> tuple[bool, str]:
    """Compile a single job and return status with output."""
    if sys.platform == "win32" and not mojo_bin.lower().endswith(".exe"):
        if Path(f"{mojo_bin}.exe").exists():
            mojo_bin = f"{mojo_bin}.exe"
    job.output_path.parent.mkdir(parents=True, exist_ok=True)
    command = build_command(mojo_bin, root, job)
    if sys.platform == "win32" and not command[0].lower().endswith(".exe"):
        command = [sys.executable, *command]
    env = dict(os.environ)
    env.update(job.env)
    result = subprocess.run(command, cwd=str(root), env=env, capture_output=True, text=True, check=False)
    log = "\n".join(
        [
            f"job={job.name}",
            f"cmd={' '.join(command)}",
            f"exit={result.returncode}",
            result.stdout.strip(),
            result.stderr.strip(),
        ]
    ).strip()
    success = result.returncode == 0
    if not success and fail_fast:
        raise RuntimeError(log)
    return success, log
