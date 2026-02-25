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
