"""Shared pytest fixtures."""

from __future__ import annotations

import base64
import html
import subprocess
from dataclasses import dataclass, field

import pytest


@dataclass
class ToolCall:
    """One captured metadata-tool invocation.

    Attributes:
        command: The real command line.
        arguments: ExifTool arguments passed as an argument file on stdin.
    """

    command: list[str]
    arguments: list[str] = field(default_factory=list)

    @property
    def region_argument(self) -> str | None:
        """Return the decoded `-XMP:ImageRegion=...` structure argument.

        The writer entity-encodes the structure twice for ExifTool's -E option.
        """

        for argument in self.arguments:
            if argument.startswith("-XMP:ImageRegion="):
                return html.unescape(html.unescape(argument))
        return None


@pytest.fixture
def capture_tool_calls(monkeypatch):
    """Replace subprocess.run in iptc_iris.io and record every invocation."""

    calls: list[ToolCall] = []

    def fake_run(command, **kwargs):
        call = ToolCall(command=list(command))
        if "-@" in command:
            call.arguments = kwargs["input"].splitlines()
        calls.append(call)
        return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

    monkeypatch.setattr("iptc_iris.io.subprocess.run", fake_run)
    return calls


_MINIMAL_JPEG = base64.b64decode(
    "/9j/4AAQSkZJRgABAQAAAQABAAD/2wBDABALDA4MChAODQ4SERATGCgaGBYWGDEjJR0oOjM9PDkzODdASFxOQERXRTc4UG1RV19i"
    "Z2hnPk1xeXBkeFxlZ2P/2wBDARESEhgVGC8aGi9jQjhCY2NjY2NjY2NjY2NjY2NjY2NjY2NjY2NjY2NjY2NjY2NjY2NjY2NjY2Nj"
    "Y2NjY2NjY2P/wAARCAABAAEDASIAAhEBAxEB/8QAHwAAAQUBAQEBAQEAAAAAAAAAAAECAwQFBgcICQoL/8QAtRAAAgEDAwIEAwUF"
    "BAQAAAF9AQIDAAQRBRIhMUEGE1FhByJxFDKBkaEII0KxwRVS0fAkM2JyggkKFhcYGRolJicoKSo0NTY3ODk6Q0RFRkdISUpTVFVW"
    "V1hZWmNkZWZnaGlqc3R1dnd4eXqDhIWGh4iJipKTlJWWl5iZmqKjpKWmp6ipqrKztLW2t7i5usLDxMXGx8jJytLT1NXW19jZ2uHi"
    "4+Tl5ufo6erx8vP09fb3+Pn6/8QAHwEAAwEBAQEBAQEBAQAAAAAAAAECAwQFBgcICQoL/8QAtREAAgECBAQDBAcFBAQAAQJ3AAEC"
    "AxEEBSExBhJBUQdhcRMiMoEIFEKRobHBCSMzUvAVYnLRChYkNOEl8RcYGRomJygpKjU2Nzg5OkNERUZHSElKU1RVVldYWVpjZGVm"
    "Z2hpanN0dXZ3eHl6goOEhYaHiImKkpOUlZaXmJmaoqOkpaanqKmqsrO0tba3uLm6wsPExcbHyMnK0tPU1dbX2Nna4uPk5ebn6Onq"
    "8vP09fb3+Pn6/9oADAMBAAIRAxEAPwDz+iiigD//2Q=="
)


@pytest.fixture
def minimal_jpeg() -> bytes:
    """Return a self-made 1x1 JPEG without metadata segments, used as a write target for tool tests."""

    return _MINIMAL_JPEG
