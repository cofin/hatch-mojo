from __future__ import annotations

from pathlib import Path

from hatch_mojo.cleaning import clean_from_manifest, manifest_path, save_manifest


def test_manifest_roundtrip_and_cleanup(tmp_path: Path) -> None:
    out_a = tmp_path / "build" / "a.bin"
    out_b = tmp_path / "build" / "b.bin"
    out_a.parent.mkdir(parents=True, exist_ok=True)
    out_a.write_bytes(b"a")
    out_b.write_bytes(b"b")

    save_manifest(tmp_path, "build/mojo", [out_a, out_b])
    path = manifest_path(tmp_path, "build/mojo")
    assert path.exists()

    clean_from_manifest(tmp_path, "build/mojo")
    assert not out_a.exists()
    assert not out_b.exists()
    assert not path.exists()


def test_clean_from_manifest_missing_file_is_noop(tmp_path: Path) -> None:
    clean_from_manifest(tmp_path, "build/mojo")


def test_clean_from_manifest_prunes_empty_build_dirs(tmp_path: Path) -> None:
    build_root = tmp_path / "build" / "mojo"
    ext_file = build_root / "pkg" / "_core.so"
    lib_file = build_root / "pkg.libs" / "libFoo.so"
    ext_file.parent.mkdir(parents=True)
    lib_file.parent.mkdir(parents=True)
    ext_file.write_bytes(b"ext")
    lib_file.write_bytes(b"lib")

    save_manifest(tmp_path, "build/mojo", [ext_file, lib_file])
    clean_from_manifest(tmp_path, "build/mojo")

    assert not ext_file.exists()
    assert not lib_file.exists()
    assert not build_root.exists()

    keep_file = build_root / "keep" / "untracked.txt"
    tracked_sibling = build_root / "remove_me" / "tracked.so"
    keep_file.parent.mkdir(parents=True)
    tracked_sibling.parent.mkdir(parents=True)
    keep_file.write_text("keep", encoding="utf-8")
    tracked_sibling.write_bytes(b"x")

    save_manifest(tmp_path, "build/mojo", [tracked_sibling])
    clean_from_manifest(tmp_path, "build/mojo")

    assert not tracked_sibling.parent.exists()
    assert keep_file.exists()
    assert build_root.exists()


def test_editable_manifest_isolated_from_standard_clean(tmp_path: Path) -> None:
    std_out = tmp_path / "build" / "mojo" / "_core.so"
    edit_out = tmp_path / "src" / "pkg" / "_core.so"
    std_out.parent.mkdir(parents=True)
    edit_out.parent.mkdir(parents=True)
    std_out.write_bytes(b"std")
    edit_out.write_bytes(b"edit")

    save_manifest(tmp_path, "build/mojo", [std_out])
    save_manifest(tmp_path, "build/mojo", [edit_out], filename="editable-manifest.json")

    clean_from_manifest(tmp_path, "build/mojo", include_editable=False)
    assert not std_out.exists()
    assert edit_out.exists()
    assert manifest_path(tmp_path, "build/mojo", filename="editable-manifest.json").exists()

    clean_from_manifest(tmp_path, "build/mojo", include_editable=True)
    assert not edit_out.exists()
    assert not (tmp_path / "build" / "mojo").exists()


def test_clean_from_manifest_removes_cache_json_and_raw_dir(tmp_path: Path) -> None:
    build_root = tmp_path / "build" / "mojo"
    out_file = build_root / "pkg" / "_core.so"
    raw_file = build_root / ".raw" / "abc123.so"
    cache_file = build_root / "cache.json"
    out_file.parent.mkdir(parents=True)
    raw_file.parent.mkdir(parents=True)
    out_file.write_bytes(b"ext")
    raw_file.write_bytes(b"raw")
    cache_file.write_text('{"core": "abc123"}', encoding="utf-8")

    save_manifest(tmp_path, "build/mojo", [out_file])
    clean_from_manifest(tmp_path, "build/mojo")

    assert not out_file.exists()
    assert not raw_file.exists()
    assert not (build_root / ".raw").exists()
    assert not cache_file.exists()
    assert not build_root.exists()


def test_clean_from_manifest_removes_orphan_cache_without_manifest(tmp_path: Path) -> None:
    build_root = tmp_path / "build" / "mojo"
    cache_file = build_root / "cache.json"
    cache_file.parent.mkdir(parents=True)
    cache_file.write_text('{"core": "abc123"}', encoding="utf-8")

    clean_from_manifest(tmp_path, "build/mojo")
    assert not cache_file.exists()
    assert not build_root.exists()
