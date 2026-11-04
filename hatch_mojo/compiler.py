"""Mojo compiler discovery and invocation."""

from __future__ import annotations

import importlib
import os
import shutil
import subprocess
import sys
from pathlib import Path

from hatch_mojo.types import BuildJob


def _discover_mojo_from_package() -> str | None:
    """Locate the Mojo binary bundled inside the ``mojo`` / ``mojo-compiler`` wheel."""
    try:
        pkg_root_mod = importlib.import_module("mojo._package_root")
        pkg_root = pkg_root_mod.get_package_root()
    except (ImportError, AttributeError, RuntimeError, OSError):
        return None
    if not pkg_root:
        return None
    binary_name = "mojo.exe" if sys.platform == "win32" else "mojo"
    candidate = Path(pkg_root) / "bin" / binary_name
    if candidate.exists():
        return str(candidate)
    return None


def discover_mojo(root: Path, configured: str | None) -> str:
    """Find the Mojo compiler binary from config, env, PyPI package, PATH, or ``.venv``."""
    if configured:
        return configured

    env_override = os.getenv("HATCH_MOJO_BIN")
    if env_override:
        return env_override

    packaged = _discover_mojo_from_package()
    if packaged:
        return packaged

    found = shutil.which("mojo")
    if found:
        return found

    venv_candidates: tuple[Path, ...]
    if sys.platform == "win32":
        scripts_dir = root / ".venv" / "Scripts"
        venv_candidates = (
            scripts_dir / "mojo.exe",
            scripts_dir / "mojo.cmd",
            scripts_dir / "mojo.bat",
            scripts_dir / "mojo",
        )
    else:
        venv_candidates = (root / ".venv" / "bin" / "mojo",)

    for candidate in venv_candidates:
        if candidate.exists():
            return str(candidate)

    msg = "mojo executable not found (checked config, HATCH_MOJO_BIN, mojo-compiler package, PATH, and local .venv)"
    raise FileNotFoundError(msg)


def _format_cli_path(path: Path, root: Path) -> str:
    """Format *path* relative to *root* when inside *root*, else as a full path string."""
    if path.is_relative_to(root):
        return str(path.relative_to(root))
    return str(path)


def build_command(mojo_bin: str, root: Path, job: BuildJob) -> list[str]:
    """Build the Mojo CLI argv for *job*.

    Jobs with ``emit == "mojoc"`` invoke ``mojo precompile`` without ``--emit`` or
    Mach-O linker flags. Linkable native targets invoke ``mojo build --emit`` (mapping
    ``"executable"`` to ``"exe"``) and append ``-Xlinker -headerpad_max_install_names``
    on macOS so ``install_name_tool`` has sufficient Mach-O header space during bundling.
    """
    input_arg = _format_cli_path(job.input_path, root)
    output_arg = _format_cli_path(job.output_path, root)

    if job.emit == "mojoc":
        precompile_cmd: list[str] = [mojo_bin, "precompile"]
        for include_dir in job.include_dirs:
            precompile_cmd.extend(["-I", include_dir])
        for define in job.defines:
            precompile_cmd.extend(["-D", define])
        precompile_cmd.extend([*job.flags, input_arg, "-o", output_arg])
        return precompile_cmd

    emit_map = {
        "python-extension": "shared-lib",
        "shared-lib": "shared-lib",
        "object": "object",
        "executable": "exe",
    }
    command: list[str] = [mojo_bin, "build", "--emit", emit_map[job.emit]]
    for include_dir in job.include_dirs:
        command.extend(["-I", include_dir])
    for define in job.defines:
        command.extend(["-D", define])

    if sys.platform == "darwin" and job.emit in {"python-extension", "shared-lib", "executable"}:
        command.extend(["-Xlinker", "-headerpad_max_install_names"])

    command.extend([*job.flags, input_arg, "-o", output_arg])
    return command


def _has_shebang(path: Path) -> bool:
    """Return True when *path* is an existing file starting with a ``#!`` shebang."""
    try:
        if not path.is_file():
            return False
        with path.open("rb") as handle:
            return handle.read(2) == b"#!"
    except OSError:
        return False


def _resolve_win32_mojo_bin(mojo_bin: str, root: Path) -> str:
    """Resolve bare command names or missing Windows executable suffixes for *mojo_bin*."""
    raw_path = Path(mojo_bin)
    candidate = raw_path if raw_path.is_absolute() else root / raw_path
    if candidate.exists():
        return mojo_bin
    which_match = shutil.which(mojo_bin)
    if which_match:
        return which_match
    if not mojo_bin.lower().endswith((".exe", ".cmd", ".bat")):
        for suffix in (".exe", ".cmd", ".bat"):
            if Path(f"{candidate}{suffix}").exists():
                return f"{mojo_bin}{suffix}"
    return mojo_bin


def compile_job(*, mojo_bin: str, root: Path, job: BuildJob, fail_fast: bool = True) -> tuple[bool, str]:
    """Compile a single job and return status with output."""
    if sys.platform == "win32":
        mojo_bin = _resolve_win32_mojo_bin(mojo_bin, root)
    job.output_path.parent.mkdir(parents=True, exist_ok=True)
    command = build_command(mojo_bin, root, job)
    if sys.platform == "win32" and not command[0].lower().endswith((".exe", ".cmd", ".bat")):
        cmd_path = Path(command[0]) if Path(command[0]).is_absolute() else root / command[0]
        if _has_shebang(cmd_path):
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
