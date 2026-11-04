"""Mojo compiler discovery and invocation."""

from __future__ import annotations

import hashlib
import importlib
import json
import os
import shutil
import subprocess
import sys
import threading
from pathlib import Path

from hatch_mojo.types import BuildJob

CACHE_FILENAME = "cache.json"
RAW_CACHE_DIRNAME = ".raw"
_CACHE_LOCK = threading.Lock()


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


def _sha256_file(path: Path) -> str:
    """Return the hex SHA-256 digest of *path*."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _compiler_fingerprint(mojo_bin: str, root: Path) -> tuple[str, int | None, int | None]:
    """Return resolved path, nanosecond mtime, and byte size for *mojo_bin* when stat-able."""
    resolved = shutil.which(mojo_bin) or mojo_bin
    bin_path = Path(resolved) if Path(resolved).is_absolute() else root / resolved
    try:
        st = bin_path.stat()
        return (str(bin_path.resolve()), st.st_mtime_ns, st.st_size)
    except OSError:
        return (resolved, None, None)


def _read_cache(cache_dir: Path | None) -> dict[str, str]:
    """Load ``cache.json`` from *cache_dir* thread-safely."""
    if cache_dir is None:
        return {}
    cache_file = cache_dir / CACHE_FILENAME
    with _CACHE_LOCK:
        if not cache_file.is_file():
            return {}
        try:
            payload = json.loads(cache_file.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}
    if not isinstance(payload, dict):
        return {}
    return {str(key): str(val) for key, val in payload.items()}


def _record_cache_result(
    *,
    cache_dir: Path,
    job: BuildJob,
    digest: str,
    raw_artifact: Path,
) -> None:
    """Persist a pristine copy of ``job.output_path`` and update ``cache.json`` under lock."""
    cache_file = cache_dir / CACHE_FILENAME
    with _CACHE_LOCK:
        if job.output_path.is_file():
            raw_artifact.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(job.output_path, raw_artifact)
        existing: dict[str, str] = {}
        if cache_file.is_file():
            try:
                loaded = json.loads(cache_file.read_text(encoding="utf-8"))
                if isinstance(loaded, dict):
                    existing = {str(k): str(v) for k, v in loaded.items()}
            except (OSError, ValueError):
                existing = {}
        existing[job.name] = digest
        cache_dir.mkdir(parents=True, exist_ok=True)
        cache_file.write_text(json.dumps(existing, indent=2, sort_keys=True), encoding="utf-8")


def _collect_source_tree_hashes(
    root: Path,
    job: BuildJob,
    cache_dir: Path | None,
) -> list[tuple[str, str]]:
    """Collect deterministic ``(path_label, sha256)`` pairs for all sources, includes, and flag files."""
    resolved_root = root.resolve()
    resolved_cache = cache_dir.resolve() if cache_dir is not None else None
    raw_dir = resolved_cache / RAW_CACHE_DIRNAME if resolved_cache is not None else None
    explicit_incs = [(Path(inc) if Path(inc).is_absolute() else root / inc).resolve() for inc in job.include_dirs]
    cache_explicit = resolved_cache is not None and any(
        inc == resolved_cache or inc.is_relative_to(resolved_cache) for inc in explicit_incs
    )

    tracked: set[Path] = set()
    if job.input_path.is_file():
        tracked.add(job.input_path.resolve())

    input_parent = job.input_path.parent
    if input_parent.is_dir():
        for pattern in ("*.mojo", "*.mojoc"):
            for candidate in input_parent.rglob(pattern):
                if not candidate.is_file():
                    continue
                res = candidate.resolve()
                if raw_dir is not None and res.is_relative_to(raw_dir):
                    continue
                if not cache_explicit and resolved_cache is not None and res.is_relative_to(resolved_cache):
                    continue
                tracked.add(res)

    for inc_dir in explicit_incs:
        if not inc_dir.is_dir():
            continue
        for pattern in ("*.mojo", "*.mojoc"):
            for candidate in inc_dir.rglob(pattern):
                if not candidate.is_file():
                    continue
                res = candidate.resolve()
                if raw_dir is not None and res.is_relative_to(raw_dir):
                    continue
                tracked.add(res)

    for flag in job.flags:
        flag_path = Path(flag) if Path(flag).is_absolute() else root / flag
        if flag_path.is_file():
            tracked.add(flag_path.resolve())

    labeled: list[tuple[str, Path]] = []
    for res in tracked:
        label = res.relative_to(resolved_root).as_posix() if res.is_relative_to(resolved_root) else res.as_posix()
        labeled.append((label, res))
    labeled.sort(key=lambda item: item[0])
    return [(label, _sha256_file(res)) for label, res in labeled]


def compute_job_digest(
    *,
    mojo_bin: str,
    root: Path,
    job: BuildJob,
    cache_dir: Path | None = None,
) -> str:
    """Compute a deterministic SHA-256 build digest for *job*."""
    cache_map = _read_cache(cache_dir)
    payload = {
        "compiler": _compiler_fingerprint(mojo_bin, root),
        "defines": list(job.defines),
        "depends_on": [(dep, cache_map.get(dep)) for dep in job.depends_on],
        "emit": job.emit,
        "env": sorted(job.env.items()),
        "files": _collect_source_tree_hashes(root, job, cache_dir),
        "flags": list(job.flags),
        "include_dirs": list(job.include_dirs),
        "module": job.module,
        "output_path": str(job.output_path),
    }
    encoded = json.dumps(payload, sort_keys=True).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def compile_job(
    *,
    mojo_bin: str,
    root: Path,
    job: BuildJob,
    fail_fast: bool = True,
    use_cache: bool = False,
    cache_dir: Path | None = None,
) -> tuple[bool, str]:
    """Compile a single job and return status with output, restoring cached ``.raw`` binaries on hits."""
    if sys.platform == "win32":
        mojo_bin = _resolve_win32_mojo_bin(mojo_bin, root)

    digest: str | None = None
    raw_artifact: Path | None = None
    if use_cache and cache_dir is not None:
        digest = compute_job_digest(mojo_bin=mojo_bin, root=root, job=job, cache_dir=cache_dir)
        raw_artifact = cache_dir / RAW_CACHE_DIRNAME / f"{digest}{job.output_path.suffix}"
        if _read_cache(cache_dir).get(job.name) == digest and raw_artifact.is_file():
            job.output_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(raw_artifact, job.output_path)
            return True, f"job={job.name}\ncache=hit\noutput={job.output_path}"

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
    if success and use_cache and cache_dir is not None and digest is not None and raw_artifact is not None:
        _record_cache_result(cache_dir=cache_dir, job=job, digest=digest, raw_artifact=raw_artifact)
    if not success and fail_fast:
        raise RuntimeError(log)
    return success, log
