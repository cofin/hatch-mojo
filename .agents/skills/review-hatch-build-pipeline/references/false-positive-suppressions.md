# False-Positive Suppressions (`FP-HBP-01..FP-HBP-05`)

Reviewers **MUST NOT** flag the intentional repository patterns below:

- **`FP-HBP-01` — DO NOT FLAG `MojoBuildHook` lacking `__slots__`**:
  `hatch_mojo/plugin.py::MojoBuildHook` subclasses Hatchling's external `BuildHookInterface[Any]`, which is unslotted; `[tool.slotscheck] strict-imports = false` in `pyproject.toml` intentionally allows this host-plugin boundary class.
- **`FP-HBP-02` — DO NOT FLAG `subprocess.run(command, ...)` (`S603`) in `hatch_mojo/compiler.py`**:
  Invoking user-configured `mojo_bin` and compiler flags as an argument list (`shell=False`) is the core purpose of a Hatch compiler hook, and `S603` is intentionally ignored in `pyproject.toml`.
- **`FP-HBP-03` — DO NOT FLAG shebang-guarded `[sys.executable, *command]` on `win32` in `hatch_mojo/compiler.py::compile_job`**:
  Prefixing `sys.executable` when `command[0]` does not end with `.exe`/`.cmd`/`.bat` AND `_has_shebang(cmd_path)` is `True` on Windows is intentional so Python-script `mojo` stubs in `tests/test_integration_*.py` execute cleanly on `windows-latest` CI runners without breaking `.cmd`/`.bat` shims.
- **`FP-HBP-04` — DO NOT FLAG `from __future__ import annotations` in existing modules supporting Python `3.10`**:
  `FA100` is ignored in `pyproject.toml` and existing `hatch_mojo/*.py` files use `from __future__ import annotations` while targeting `requires-python = ">=3.10"`. Still require PEP 585/604 syntax (`list[...]`, `X | None`) rather than `typing.List` or `typing.Optional`.
- **`FP-HBP-05` — DO NOT FLAG `SimpleNamespace` Hatch host stubs in `tests/test_plugin.py`**:
  `MojoBuildHook` inherits Hatchling's runtime properties (`self.root`, `self.config`, `self.target_name`, `self.app`, `self.build_config`), which require full Hatch builder instantiation unless isolated with `SimpleNamespace` in unit orchestration tests; end-to-end Hatchling wiring is covered separately by `tests/test_integration_wheel.py`.
