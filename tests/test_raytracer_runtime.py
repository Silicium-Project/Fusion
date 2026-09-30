"""Staging of the native raytracer binary before a render."""

import os
import stat

import pytest

from workloads.raytracer.raytracer_workload import prepare_runtime_dir


@pytest.mark.skipif(os.name == "nt", reason="POSIX executable mode is not represented on Windows")
def test_runtime_copy_restores_owner_execute_bit(tmp_path) -> None:
    binary = tmp_path / "raytracer"
    binary.write_bytes(b"#!/bin/sh\nexit 0\n")
    binary.chmod(0o644)

    runtime_binary = prepare_runtime_dir(binary, tmp_path / "runtime")

    assert runtime_binary.stat().st_mode & stat.S_IXUSR


def test_runtime_copy_includes_binary_companion_files(tmp_path) -> None:
    binary = tmp_path / "raytracer"
    binary.write_bytes(b"launcher")
    (tmp_path / "raytracer.py").write_bytes(b"implementation")

    runtime_binary = prepare_runtime_dir(binary, tmp_path / "runtime")

    assert runtime_binary.read_bytes() == b"launcher"
    assert (runtime_binary.parent / "raytracer.py").read_bytes() == b"implementation"
