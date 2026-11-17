"""Tests for independent iptc-iris configuration files."""

from __future__ import annotations

from argparse import Namespace

import pytest

from iptc_iris.cli import _tool_executable
from iptc_iris.config import ToolConfig


def test_missing_config_returns_empty_tool_config(tmp_path):
    config = ToolConfig.load(tmp_path / "missing.toml")

    assert config == ToolConfig()


def test_loads_tool_paths_from_toml_config(tmp_path):
    config_path = tmp_path / "iptc-iris.toml"
    config_path.write_text(
        """
        [tools]
        exiftool = "C:/Tools/exiftool/exiftool.exe"
        exiv2 = "/usr/local/bin/exiv2"
        """,
        encoding="utf-8",
    )

    config = ToolConfig.load(config_path)

    assert config.executable_for("exiftool") == "C:/Tools/exiftool/exiftool.exe"
    assert config.executable_for("exiv2") == "/usr/local/bin/exiv2"


def test_rejects_non_table_tools_config(tmp_path):
    config_path = tmp_path / "iptc-iris.toml"
    config_path.write_text('tools = "exiftool"', encoding="utf-8")

    with pytest.raises(ValueError, match=r"\[tools] must be a TOML table"):
        ToolConfig.load(config_path)


def test_cli_tool_path_overrides_config():
    args = Namespace(exiftool="local-exiftool", exiv2=None)
    config = ToolConfig(exiftool="configured-exiftool", exiv2="configured-exiv2")

    assert _tool_executable("exiftool", args, config) == "local-exiftool"
    assert _tool_executable("exiv2", args, config) == "configured-exiv2"
