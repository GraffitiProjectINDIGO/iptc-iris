"""Configuration loading for imgregion."""

from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path

from .spec import IPTC_STANDARDS, Standard

DEFAULT_CONFIG_FILENAME = "iptc-iris.toml"


def _read_config(config_path: str | Path | None) -> dict[str, object]:
    """Read the TOML config file, or return an empty mapping when it does not exist."""

    path = Path(config_path) if config_path is not None else Path(DEFAULT_CONFIG_FILENAME)
    if not path.exists():
        return {}
    with path.open("rb") as handle:
        return tomllib.load(handle)


@dataclass(frozen=True)
class ValidationConfig:
    """Validation settings from the `[validation]` table.

    Attributes:
        standard: Configured standard profile, or None to use the default.
    """

    standard: Standard | None = None

    @classmethod
    def load(cls, config_path: str | Path | None = None) -> ValidationConfig:
        """Load validation settings from `iptc-iris.toml` or the given file.

        Args:
            config_path: Optional path to a TOML config file. When omitted,
                `iptc-iris.toml` in the current working directory is used.

        Returns:
            Loaded validation configuration. Missing files return an empty config.

        Raises:
            ValueError: If the `[validation]` table or its values are invalid.
        """

        validation = _read_config(config_path).get("validation", {})
        if not isinstance(validation, dict):
            raise ValueError("[validation] must be a TOML table")
        standard = validation.get("standard")
        if standard is None:
            return cls()
        if standard not in IPTC_STANDARDS:
            raise ValueError(f"[validation].standard must be one of: {', '.join(IPTC_STANDARDS)}")
        return cls(standard=standard)


def _optional_string(values: dict[str, object], key: str) -> str | None:
    """Read an optional string value and reject mistyped config entries.

    Args:
        values: TOML table values.
        key: Key to read from the table.

    Returns:
        Non-empty string value, or None when absent/blank.

    Raises:
        ValueError: If the value exists but is not a string.
    """

    value = values.get(key)
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError(f"[tools].{key} must be a string")
    if not value.strip():
        return None
    return value


@dataclass(frozen=True)
class ToolConfig:
    """Configured executable paths for optional metadata tools.

    Attributes:
        exiftool: Optional command or executable path for ExifTool.
        exiv2: Optional command or executable path for Exiv2.
    """

    exiftool: str | None = None
    exiv2: str | None = None

    @classmethod
    def load(cls, config_path: str | Path | None = None) -> ToolConfig:
        """Load optional external-tool configuration from an independent TOML file.

        The default file is deliberately separate from pyproject.toml because
        these values are local runtime configuration, not package metadata.

        Args:
            config_path: Optional path to a TOML config file. When omitted,
                `iptc-iris.toml` in the current working directory is used.

        Returns:
            Loaded tool configuration. Missing files return an empty config.

        Raises:
            ValueError: If the `[tools]` table or tool values have invalid
                types.
        """

        path = Path(config_path) if config_path is not None else Path(DEFAULT_CONFIG_FILENAME)
        if not path.exists():
            # Missing configuration is not an error; the caller will fall back
            # to normal PATH lookup for exiftool/exiv2.
            return cls()

        with path.open("rb") as handle:
            data = tomllib.load(handle)

        tools = data.get("tools", {})
        if not isinstance(tools, dict):
            raise ValueError("[tools] must be a TOML table")

        return cls(
            exiftool=_optional_string(tools, "exiftool"),
            exiv2=_optional_string(tools, "exiv2"),
        )

    def executable_for(self, tool: str) -> str | None:
        """Return the configured executable for a supported tool name.

        Args:
            tool: Tool name such as `exiftool` or `exiv2`.

        Returns:
            Configured command/path, or None for unknown or unconfigured tools.
        """

        if tool == "exiftool":
            return self.exiftool
        if tool == "exiv2":
            return self.exiv2
        return None
