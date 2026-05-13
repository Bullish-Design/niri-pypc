"""Package metadata contract tests."""

from __future__ import annotations

from importlib import resources
from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as dist_version

import niri_pypc


def test_runtime_version_matches_distribution():
    try:
        expected = dist_version("niri-pypc")
    except PackageNotFoundError:
        assert niri_pypc.__version__ == "0.0.0+local"
    else:
        assert niri_pypc.__version__ == expected


def test_py_typed_marker_is_packaged():
    marker = resources.files("niri_pypc").joinpath("py.typed")
    assert marker.is_file()
