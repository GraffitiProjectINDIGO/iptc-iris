import runpy
from pathlib import Path

import pytest

# Collect all top-level example scripts
EXAMPLES = sorted(Path(__file__).resolve().parent.parent.joinpath("examples").glob("*.py"))


@pytest.mark.parametrize("script", EXAMPLES, ids=lambda p: p.name)
def test_example_script_runs(script, monkeypatch, capsys):
    # Ensure relative data paths in examples keep working
    monkeypatch.chdir(script.parent)
    # Execute the example as a script; any exception will fail the test
    runpy.run_path(str(script), run_name="__main__")
    # Printing is what the examples are for; collect it so the test log stays readable.
    assert capsys.readouterr().out
