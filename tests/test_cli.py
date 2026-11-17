"""Tests for the iptc-iris command-line interface."""

from __future__ import annotations

import json

import iptc_iris.cli as cli
from iptc_iris.cli import _expand_paths, main
from iptc_iris.geometry import RectangleBoundary
from iptc_iris.models import NormalizedMetadata, ValidationResult
from iptc_iris.region import ImageRegion, ImageRegionList
from iptc_iris.render import (
    _print_human_result,
    format_annotated_image_region,
    format_image_region,
    format_json,
    format_validation,
)


def test_image_region_outputs_normalized_region_json(tmp_path, capsys):
    metadata_path = tmp_path / "metadata.json"
    metadata_path.write_text(
        json.dumps(
            {
                "imageRegion": [
                    {
                        "regionBoundary": {
                            "rbShape": "rectangle",
                            "rbUnit": "relative",
                            "rbX": 0.1,
                            "rbY": 0.2,
                            "rbW": 0.3,
                            "rbH": 0.4,
                        }
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    exit_code = main(["validate", str(metadata_path), "--image-region"])

    assert exit_code == 0
    assert json.loads(capsys.readouterr().out) == {
        "path": str(metadata_path),
        "imageRegion": [
            {
                "regionBoundary": {
                    "rbShape": "rectangle",
                    "rbUnit": "relative",
                    "rbX": 0.1,
                    "rbY": 0.2,
                    "rbW": 0.3,
                    "rbH": 0.4,
                }
            }
        ],
    }


def test_cli_without_arguments_prints_available_commands(capsys):
    exit_code = main([])

    captured = capsys.readouterr()
    assert exit_code == 0
    assert captured.out.startswith("iptc-iris 0.1.0\nusage:")
    assert "commands:" in captured.out
    assert "validate" in captured.out
    assert "convert" in captured.out
    assert "fix" in captured.out
    assert "IPTC Photo Metadata Standard: 2025.1" in captured.out
    assert captured.err == ""


def test_cli_version_uses_project_version(capsys):
    exit_code = main(["--version"])

    captured = capsys.readouterr()
    assert exit_code == 0
    assert captured.out.strip() == "iptc-iris 0.1.0"
    assert captured.err == ""


def test_convert_relative_regions_to_pixel_json(tmp_path, capsys):
    metadata_path = tmp_path / "metadata.json"
    metadata_path.write_text(
        json.dumps(
            {
                "imageRegion": [
                    {
                        "regionBoundary": {
                            "rbShape": "rectangle",
                            "rbUnit": "relative",
                            "rbX": 0.1,
                            "rbY": 0.2,
                            "rbW": 0.3,
                            "rbH": 0.4,
                        }
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    exit_code = main(
        [
            "convert",
            str(metadata_path),
            "--to",
            "pixel",
            "--image-width",
            "1000",
            "--image-height",
            "800",
        ]
    )

    assert exit_code == 0
    assert json.loads(capsys.readouterr().out) == {
        "path": str(metadata_path),
        "imageRegion": [
            {
                "regionBoundary": {
                    "rbShape": "rectangle",
                    "rbUnit": "pixel",
                    "rbX": 100.0,
                    "rbY": 160.0,
                    "rbW": 300.0,
                    "rbH": 320.0,
                }
            }
        ],
        "imageWidth": 1000.0,
        "imageHeight": 800.0,
    }


def test_convert_rejects_invalid_regions_before_conversion(tmp_path, capsys):
    metadata_path = tmp_path / "metadata.json"
    metadata_path.write_text(
        json.dumps({"imageRegion": [{"regionBoundary": {"rbShape": "rectangle", "rbUnit": "relative"}}]}),
        encoding="utf-8",
    )

    exit_code = main(
        [
            "convert",
            str(metadata_path),
            "--to",
            "pixel",
            "--image-width",
            "1000",
            "--image-height",
            "800",
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 1
    assert captured.out == ""
    assert "conversion skipped" in captured.err
    assert "MISSING_BOUNDARY_FIELD" in captured.err


def test_convert_can_write_single_output_file(tmp_path, capsys):
    metadata_path = tmp_path / "metadata.json"
    output_path = tmp_path / "converted.json"
    metadata_path.write_text(
        json.dumps(
            {
                "imageRegion": [
                    {
                        "regionBoundary": {
                            "rbShape": "circle",
                            "rbUnit": "relative",
                            "rbX": 0.5,
                            "rbY": 0.25,
                            "rbRx": 0.1,
                        }
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    exit_code = main(
        [
            "convert",
            str(metadata_path),
            "--to",
            "pixel",
            "--image-width",
            "1000",
            "--image-height",
            "800",
            "--output",
            str(output_path),
        ]
    )

    assert exit_code == 0
    assert capsys.readouterr().out == ""
    output = json.loads(output_path.read_text(encoding="utf-8"))
    assert output["imageRegion"][0]["regionBoundary"]["rbUnit"] == "pixel"
    assert output["imageRegion"][0]["regionBoundary"]["rbX"] == 500.0


def test_convert_output_reports_missing_parent_directory(tmp_path, capsys):
    metadata_path = tmp_path / "metadata.json"
    output_path = tmp_path / "missing" / "converted.json"
    metadata_path.write_text(
        json.dumps(
            {
                "imageRegion": [
                    {
                        "regionBoundary": {
                            "rbShape": "rectangle",
                            "rbUnit": "relative",
                            "rbX": 0.1,
                            "rbY": 0.2,
                            "rbW": 0.3,
                            "rbH": 0.4,
                        }
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    exit_code = main(
        [
            "convert",
            str(metadata_path),
            "--to",
            "pixel",
            "--image-width",
            "1000",
            "--image-height",
            "800",
            "--output",
            str(output_path),
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 2
    assert captured.out == ""
    assert "--output directory does not exist" in captured.err
    assert str(output_path.parent) in captured.err


def test_convert_can_write_merged_output_file_for_multiple_inputs(tmp_path, capsys):
    first = tmp_path / "a.json"
    second = tmp_path / "b.json"
    for path in (first, second):
        path.write_text(
            json.dumps(
                {
                    "imageRegion": [
                        {
                            "regionBoundary": {
                                "rbShape": "rectangle",
                                "rbUnit": "relative",
                                "rbX": 0.1,
                                "rbY": 0.2,
                                "rbW": 0.3,
                                "rbH": 0.4,
                            }
                        }
                    ]
                }
            ),
            encoding="utf-8",
        )
    output_path = tmp_path / "out.json"

    exit_code = main(
        [
            "convert",
            str(tmp_path / "*.json"),
            "--to",
            "pixel",
            "--image-width",
            "1000",
            "--image-height",
            "800",
            "--output",
            str(output_path),
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 0
    assert captured.out == ""
    assert captured.err == ""
    output = json.loads(output_path.read_text(encoding="utf-8"))
    assert [item["path"] for item in output["files"]] == [str(first), str(second)]
    assert output["files"][0]["imageRegion"][0]["regionBoundary"]["rbUnit"] == "pixel"


def test_fix_removes_unsupported_boundary_fields(tmp_path, capsys):
    metadata_path = tmp_path / "metadata.json"
    metadata_path.write_text(
        json.dumps(
            {
                "imageRegion": [
                    {
                        "regionBoundary": {
                            "rbShape": "rectangle",
                            "rbUnit": "relative",
                            "rbX": 0.1,
                            "rbY": 0.2,
                            "rbW": 0.3,
                            "rbH": 0.4,
                            "rbE": "remove me",
                        }
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    exit_code = main(["fix", str(metadata_path)])

    captured = capsys.readouterr()
    assert exit_code == 0
    assert captured.err == ""
    output = json.loads(captured.out)
    assert "rbE" not in output["imageRegion"][0]["regionBoundary"]
    assert output["fixes"] == [
        {
            "action": "remove",
            "path": "imageRegion[0].regionBoundary.rbE",
            "code": "UNKNOWN_BOUNDARY_FIELD",
            "message": "Removed unsupported field at imageRegion[0].regionBoundary.rbE.",
        }
    ]


def test_fix_dry_run_prints_report_without_json(tmp_path, capsys):
    metadata_path = tmp_path / "metadata.json"
    metadata_path.write_text(
        json.dumps(
            {
                "imageRegion": [
                    {
                        "regionBoundary": {
                            "rbShape": "rectangle",
                            "rbUnit": "relative",
                            "rbX": 0.1,
                            "rbY": 0.2,
                            "rbW": 0.3,
                            "rbH": 0.4,
                            "rbVertices": [{"rbX": 0.1, "rbY": 0.2}],
                        }
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    exit_code = main(["fix", str(metadata_path), "--dry-run"])

    captured = capsys.readouterr()
    assert exit_code == 0
    assert captured.err == ""
    assert "REMOVE" in captured.out
    assert "FORBIDDEN_BOUNDARY_FIELD" in captured.out
    assert "imageRegion[0].regionBoundary.rbVertices" in captured.out


def test_fix_produces_no_output_when_errors_are_not_fully_fixable(tmp_path, capsys):
    metadata_path = tmp_path / "metadata.json"
    output_path = tmp_path / "fixed.json"
    metadata_path.write_text(
        json.dumps(
            {
                "imageRegion": [
                    {
                        "regionBoundary": {
                            "rbShape": "rectangle",
                            "rbUnit": "relative",
                            "rbY": 0.2,
                            "rbW": 0.3,
                            "rbH": 0.4,
                            "rbE": "remove me",
                        }
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    exit_code = main(["fix", str(metadata_path), "--output", str(output_path)])

    captured = capsys.readouterr()
    assert exit_code == 1
    assert captured.out == ""
    assert "no complete safe fix available" in captured.err
    assert "MISSING_BOUNDARY_FIELD" in captured.err
    assert not output_path.exists()


def test_fix_wildcard_produces_no_partial_output_when_one_file_is_not_fixable(tmp_path, capsys):
    valid_path = tmp_path / "valid.json"
    invalid_path = tmp_path / "invalid.json"
    output_dir = tmp_path / "fixed"
    valid_path.write_text(
        json.dumps(
            {
                "imageRegion": [
                    {
                        "regionBoundary": {
                            "rbShape": "rectangle",
                            "rbUnit": "relative",
                            "rbX": 0.1,
                            "rbY": 0.2,
                            "rbW": 0.3,
                            "rbH": 0.4,
                        }
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    invalid_path.write_text(
        json.dumps(
            {
                "imageRegion": [
                    {
                        "regionBoundary": {
                            "rbShape": "rectangle",
                            "rbUnit": "relative",
                            "rbY": 0.2,
                            "rbW": 0.3,
                            "rbH": 0.4,
                        }
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    exit_code = main(["fix", str(tmp_path / "*.json"), "--output-dir", str(output_dir)])

    captured = capsys.readouterr()
    assert exit_code == 1
    assert captured.out == ""
    assert "no complete safe fix available" in captured.err
    assert not output_dir.exists()


def test_fix_valid_file_writes_canonical_output(tmp_path, capsys):
    metadata_path = tmp_path / "metadata.json"
    metadata_path.write_text(
        json.dumps(
            {
                "imageRegion": [
                    {
                        "regionBoundary": {
                            "rbShape": "rectangle",
                            "rbUnit": "relative",
                            "rbX": 0.1,
                            "rbY": 0.2,
                            "rbW": 0.3,
                            "rbH": 0.4,
                        }
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    exit_code = main(["fix", str(metadata_path)])

    captured = capsys.readouterr()
    assert exit_code == 0
    assert captured.err == ""
    output = json.loads(captured.out)
    assert output["path"] == str(metadata_path)
    assert output["fixes"] == []
    assert output["imageRegion"] == [
        {
            "regionBoundary": {
                "rbShape": "rectangle",
                "rbUnit": "relative",
                "rbX": 0.1,
                "rbY": 0.2,
                "rbW": 0.3,
                "rbH": 0.4,
            }
        }
    ]


def test_fix_valid_file_writes_output_file_for_chain(tmp_path, capsys):
    metadata_path = tmp_path / "metadata.json"
    output_path = tmp_path / "fixed.json"
    metadata_path.write_text(
        json.dumps(
            {
                "imageRegion": [
                    {
                        "regionBoundary": {
                            "rbShape": "rectangle",
                            "rbUnit": "relative",
                            "rbX": 0.1,
                            "rbY": 0.2,
                            "rbW": 0.3,
                            "rbH": 0.4,
                        }
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    exit_code = main(["fix", str(metadata_path), "--output", str(output_path)])

    captured = capsys.readouterr()
    assert exit_code == 0
    assert captured.out == ""
    assert captured.err == ""
    assert json.loads(output_path.read_text(encoding="utf-8"))["fixes"] == []


def test_fix_output_reports_missing_parent_directory(tmp_path, capsys):
    metadata_path = tmp_path / "metadata.json"
    output_path = tmp_path / "missing" / "fixed.json"
    metadata_path.write_text(
        json.dumps(
            {
                "imageRegion": [
                    {
                        "regionBoundary": {
                            "rbShape": "rectangle",
                            "rbUnit": "relative",
                            "rbX": 0.1,
                            "rbY": 0.2,
                            "rbW": 0.3,
                            "rbH": 0.4,
                        }
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    exit_code = main(["fix", str(metadata_path), "--output", str(output_path)])

    captured = capsys.readouterr()
    assert exit_code == 2
    assert captured.out == ""
    assert "--output directory does not exist" in captured.err
    assert str(output_path.parent) in captured.err


def test_fix_can_write_merged_output_file_for_multiple_inputs(tmp_path, capsys):
    valid_path = tmp_path / "valid.json"
    fixable_path = tmp_path / "fixable.json"
    output_path = tmp_path / "fixed.json"
    valid_path.write_text(
        json.dumps(
            {
                "imageRegion": [
                    {
                        "regionBoundary": {
                            "rbShape": "rectangle",
                            "rbUnit": "relative",
                            "rbX": 0.1,
                            "rbY": 0.2,
                            "rbW": 0.3,
                            "rbH": 0.4,
                        }
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    fixable_path.write_text(
        json.dumps(
            {
                "imageRegion": [
                    {
                        "regionBoundary": {
                            "rbShape": "rectangle",
                            "rbUnit": "relative",
                            "rbX": 0.2,
                            "rbY": 0.3,
                            "rbW": 0.4,
                            "rbH": 0.5,
                            "rbE": "remove me",
                        }
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    exit_code = main(["fix", str(tmp_path / "*.json"), "--output", str(output_path)])

    captured = capsys.readouterr()
    assert exit_code == 0
    assert captured.out == ""
    assert captured.err == ""
    output = json.loads(output_path.read_text(encoding="utf-8"))
    assert [item["path"] for item in output["files"]] == [str(fixable_path), str(valid_path)]
    assert len(output["files"][0]["fixes"]) == 1
    assert output["files"][1]["fixes"] == []
    assert "rbE" not in output["files"][0]["imageRegion"][0]["regionBoundary"]


def test_fix_convert_validate_can_chain_through_merged_batch_file(tmp_path, capsys):
    first = tmp_path / "first.json"
    second = tmp_path / "second.json"
    fixed_path = tmp_path / "fixed.json"
    converted_path = tmp_path / "converted.json"
    for index, path in enumerate((first, second), start=1):
        path.write_text(
            json.dumps(
                {
                    "imageRegion": [
                        {
                            "regionBoundary": {
                                "rbShape": "rectangle",
                                "rbUnit": "relative",
                                "rbX": 0.1 * index,
                                "rbY": 0.2,
                                "rbW": 0.3,
                                "rbH": 0.4,
                            }
                        }
                    ]
                }
            ),
            encoding="utf-8",
        )

    fix_exit = main(["fix", str(tmp_path / "*.json"), "--output", str(fixed_path)])
    capsys.readouterr()
    convert_exit = main(
        [
            "convert",
            str(fixed_path),
            "--to",
            "pixel",
            "--image-width",
            "1000",
            "--image-height",
            "800",
            "--output",
            str(converted_path),
        ]
    )
    capsys.readouterr()
    validate_exit = main(["validate", str(converted_path), "--json"])

    captured = capsys.readouterr()
    assert fix_exit == 0
    assert convert_exit == 0
    assert validate_exit == 0
    converted = json.loads(converted_path.read_text(encoding="utf-8"))
    assert len(converted["files"]) == 2
    assert converted["files"][0]["imageRegion"][0]["regionBoundary"]["rbUnit"] == "pixel"
    validation = json.loads(captured.out)
    assert [item["valid"] for item in validation] == [True, True]


def test_fix_dry_run_reports_noop_for_valid_file(tmp_path, capsys):
    metadata_path = tmp_path / "metadata.json"
    metadata_path.write_text(
        json.dumps(
            {
                "imageRegion": [
                    {
                        "regionBoundary": {
                            "rbShape": "rectangle",
                            "rbUnit": "relative",
                            "rbX": 0.1,
                            "rbY": 0.2,
                            "rbW": 0.3,
                            "rbH": 0.4,
                        }
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    exit_code = main(["fix", str(metadata_path), "--dry-run"])

    captured = capsys.readouterr()
    assert exit_code == 0
    assert captured.err == ""
    assert "NOOP" in captured.out
    assert "No validation errors were found; no fixes needed." in captured.out


def test_single_file_json_output_includes_path(tmp_path, capsys):
    metadata_path = tmp_path / "metadata.json"
    metadata_path.write_text(json.dumps({"imageRegion": []}), encoding="utf-8")

    exit_code = main(["validate", str(metadata_path), "--json"])

    assert exit_code == 0
    assert json.loads(capsys.readouterr().out) == {
        "path": str(metadata_path),
        "valid": True,
        "issues": [
            {
                "severity": "warning",
                "code": "NO_IMAGE_REGION",
                "path": "imageRegion",
                "message": "No IPTC Image Region entries found.",
            }
        ],
    }


def test_wildcard_path_expands_matching_files(tmp_path):
    first = tmp_path / "a.json"
    second = tmp_path / "b.json"
    ignored = tmp_path / "c.xmp"
    first.write_text("{}", encoding="utf-8")
    second.write_text("{}", encoding="utf-8")
    ignored.write_text("", encoding="utf-8")

    paths = _expand_paths(tmp_path / "*.json")

    assert paths == [first, second]


def test_wildcard_json_output_includes_paths(tmp_path, capsys):
    first = tmp_path / "a.json"
    second = tmp_path / "b.json"
    first.write_text(json.dumps({"imageRegion": []}), encoding="utf-8")
    second.write_text(json.dumps({"imageRegion": []}), encoding="utf-8")

    exit_code = main(["validate", str(tmp_path / "*.json"), "--json"])

    assert exit_code == 0
    output = json.loads(capsys.readouterr().out)
    assert output == [
        {
            "path": str(first),
            "valid": True,
            "issues": [
                {
                    "severity": "warning",
                    "code": "NO_IMAGE_REGION",
                    "path": "imageRegion",
                    "message": "No IPTC Image Region entries found.",
                }
            ],
        },
        {
            "path": str(second),
            "valid": True,
            "issues": [
                {
                    "severity": "warning",
                    "code": "NO_IMAGE_REGION",
                    "path": "imageRegion",
                    "message": "No IPTC Image Region entries found.",
                }
            ],
        },
    ]


def test_wildcard_image_region_output_includes_paths(tmp_path, capsys):
    first = tmp_path / "a.json"
    second = tmp_path / "b.json"
    first.write_text(json.dumps({"imageRegion": [{"regionBoundary": {"rbShape": "rectangle"}}]}), encoding="utf-8")
    second.write_text(json.dumps({"imageRegion": [{"regionBoundary": {"rbShape": "circle"}}]}), encoding="utf-8")

    exit_code = main(["validate", str(tmp_path / "*.json"), "--image-region", "--color", "never"])

    assert exit_code == 1
    output = json.loads(capsys.readouterr().out)
    assert output == [
        {
            "path": str(first),
            "imageRegion": [
                {
                    "regionBoundary": {
                        "rbShape": "rectangle",
                    }
                }
            ],
        },
        {
            "path": str(second),
            "imageRegion": [
                {
                    "regionBoundary": {
                        "rbShape": "circle",
                    }
                }
            ],
        },
    ]


def test_annotated_image_region_outputs_jsonc_comments(tmp_path, capsys):
    metadata_path = tmp_path / "metadata.json"
    metadata_path.write_text(
        json.dumps(
            {
                "imageRegion": [
                    {
                        "regionBoundary": {
                            "rbShape": "rectangle",
                            "rbUnit": "relative",
                            "rbY": 0.1,
                            "rbW": 0.2,
                            "rbH": 0.2,
                        }
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    exit_code = main(["validate", str(metadata_path), "--image-region", "--annotate", "--color", "never"])

    captured = capsys.readouterr()
    assert exit_code == 1
    assert "not standard JSON" in captured.err
    assert "// ERROR MISSING_BOUNDARY_FIELD: rectangle requires rbX." in captured.out
    assert '"path":' in captured.out
    assert '"imageRegion":' in captured.out


def test_annotated_image_region_puts_existing_field_comment_after_value(tmp_path, capsys):
    metadata_path = tmp_path / "metadata.json"
    metadata_path.write_text(
        json.dumps(
            {
                "imageRegion": [
                    {
                        "regionBoundary": {
                            "rbShape": "triangle",
                            "rbUnit": "relative",
                        }
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    exit_code = main(["validate", str(metadata_path), "--image-region", "--annotate", "--color", "never"])

    output = capsys.readouterr().out
    assert exit_code == 1
    assert '"rbShape": "triangle" // ERROR INVALID_BOUNDARY_SHAPE:' in output
    assert '// ERROR INVALID_BOUNDARY_SHAPE:\n        "rbShape"' not in output


def test_annotated_image_region_keeps_invalid_raw_number_text(tmp_path, capsys):
    metadata_path = tmp_path / "metadata.json"
    metadata_path.write_text(
        json.dumps(
            {
                "imageRegion": [
                    {
                        "regionBoundary": {
                            "rbShape": "circle",
                            "rbUnit": "relative",
                            "rbX": "not-a-number",
                            "rbY": 0.7,
                            "rbRx": 0.1,
                        }
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    exit_code = main(["validate", str(metadata_path), "--image-region", "--annotate", "--color", "never"])

    output = capsys.readouterr().out
    assert exit_code == 1
    assert '"rbX": "not-a-number" // ERROR INVALID_NUMBER: rbX must be a number.' in output
    assert '"rbX": null // ERROR INVALID_NUMBER:' not in output


def test_annotated_image_region_can_write_plain_jsonc_file(tmp_path, capsys):
    metadata_path = tmp_path / "metadata.json"
    output_path = tmp_path / "regions.jsonc"
    metadata_path.write_text(
        json.dumps({"imageRegion": [{"regionBoundary": {"rbShape": "rectangle", "rbUnit": "relative"}}]}),
        encoding="utf-8",
    )

    exit_code = main(
        [
            "validate",
            str(metadata_path),
            "--image-region",
            "--annotate",
            str(output_path),
            "--color",
            "always",
        ]
    )

    captured = capsys.readouterr()
    output = output_path.read_text(encoding="utf-8")
    assert exit_code == 1
    assert captured.out == ""
    assert "not standard JSON" in captured.err
    assert output.startswith("{")
    assert "\033[" not in output
    assert "// ERROR MISSING_BOUNDARY_FIELD: rectangle requires rbH." in output


def test_annotated_image_region_rejects_non_jsonc_output_path(tmp_path, capsys):
    metadata_path = tmp_path / "metadata.json"
    output_path = tmp_path / "regions.json"
    metadata_path.write_text(json.dumps({"imageRegion": []}), encoding="utf-8")

    exit_code = main(["validate", str(metadata_path), "--image-region", "--annotate", str(output_path)])

    captured = capsys.readouterr()
    assert exit_code == 2
    assert "annotated output path must end with .jsonc" in captured.err
    assert not output_path.exists()


def test_annotate_requires_image_region(tmp_path, capsys):
    metadata_path = tmp_path / "metadata.json"
    metadata_path.write_text(json.dumps({"imageRegion": []}), encoding="utf-8")

    exit_code = main(["validate", str(metadata_path), "--annotate"])

    captured = capsys.readouterr()
    assert exit_code == 2
    assert "--annotate requires --image-region" in captured.err


def test_exiv2_path_implies_exiv2_tool(tmp_path, monkeypatch, capsys):
    image_path = tmp_path / "photo.jpg"
    image_path.write_bytes(b"")
    calls = []

    def fake_run_metadata_tool(path, tool, *, executable=None, standard=None):
        calls.append((path, tool, executable))
        return NormalizedMetadata()

    monkeypatch.setattr(cli, "run_metadata_tool", fake_run_metadata_tool)

    exit_code = main(["validate", str(image_path), "--exiv2", "local-exiv2", "--json"])

    assert exit_code == 0
    assert calls == [(image_path, "exiv2", "local-exiv2")]
    assert json.loads(capsys.readouterr().out)["valid"]


def test_exiftool_path_implies_exiftool_tool(tmp_path, monkeypatch, capsys):
    image_path = tmp_path / "photo.jpg"
    image_path.write_bytes(b"")
    calls = []

    def fake_run_metadata_tool(path, tool, *, executable=None, standard=None):
        calls.append((path, tool, executable))
        return NormalizedMetadata()

    monkeypatch.setattr(cli, "run_metadata_tool", fake_run_metadata_tool)

    exit_code = main(["validate", str(image_path), "--exiftool", "local-exiftool", "--json"])

    assert exit_code == 0
    assert calls == [(image_path, "exiftool", "local-exiftool")]
    assert json.loads(capsys.readouterr().out)["valid"]


def test_both_tool_paths_without_tool_is_ambiguous(tmp_path, capsys):
    image_path = tmp_path / "photo.jpg"
    image_path.write_bytes(b"")

    exit_code = main(
        [
            "validate",
            str(image_path),
            "--exiftool",
            "local-exiftool",
            "--exiv2",
            "local-exiv2",
        ]
    )

    assert exit_code == 2
    assert "--tool is required" in capsys.readouterr().err


def test_human_result_can_color_issue_fields(capsys):
    result = ValidationResult()
    result.add("error", "MISSING_REGION_BOUNDARY", "imageRegion[0].regionBoundary", "Region Boundary is mandatory.")
    result.add("warning", "NO_IMAGE_REGION", "imageRegion", "No IPTC Image Region entries found.")

    _print_human_result(result, color=True)

    output = capsys.readouterr().out
    assert "\033[31mimageRegion[0].regionBoundary\033[0m" in output
    assert "\033[33mimageRegion\033[0m" in output


def test_human_result_prints_overview_issues_once(capsys):
    result = ValidationResult()
    message = "Region identifier 'same' is used by multiple Image Region entries."
    result.add_overview(
        "error",
        "DUPLICATE_REGION_ID",
        message,
        paths=("imageRegion[0].rId", "imageRegion[1].rId"),
        indexes=(0, 1),
    )
    result.add("error", "DUPLICATE_REGION_ID", "imageRegion[0].rId", message)
    result.add("error", "DUPLICATE_REGION_ID", "imageRegion[1].rId", message)

    _print_human_result(result, color=False)

    output = capsys.readouterr().out
    assert output.count("DUPLICATE_REGION_ID") == 1
    assert "imageRegion[0].rId, imageRegion[1].rId" in output


def test_human_result_can_disable_color(capsys):
    result = ValidationResult()
    result.add("error", "MISSING_REGION_BOUNDARY", "imageRegion[0].regionBoundary", "Region Boundary is mandatory.")

    _print_human_result(result, color=False)

    output = capsys.readouterr().out
    assert "\033[" not in output
    assert "imageRegion[0].regionBoundary" in output


def test_human_result_notes_when_errors_are_fixable_by_removal(capsys):
    result = ValidationResult()
    result.add(
        "error",
        "UNKNOWN_BOUNDARY_FIELD",
        "imageRegion[0].regionBoundary.rbE",
        "rbE is not a recognized Region Boundary field.",
    )

    _print_human_result(result, color=False)

    output = capsys.readouterr().out
    assert "Fixable: yes" in output
    assert "removing unsupported boundary or vertex fields" in output


def test_human_result_notes_when_errors_are_partially_fixable(capsys):
    result = ValidationResult()
    result.add(
        "error",
        "UNKNOWN_BOUNDARY_FIELD",
        "imageRegion[0].regionBoundary.rbE",
        "rbE is not a recognized Region Boundary field.",
    )
    result.add(
        "error",
        "MISSING_BOUNDARY_FIELD",
        "imageRegion[0].regionBoundary.rbX",
        "rectangle requires rbX.",
    )

    _print_human_result(result, color=False)

    output = capsys.readouterr().out
    assert "Fixable: partially" in output


def test_image_region_json_can_be_colored():
    output = format_json([{"regionBoundary": {"rbShape": "rectangle", "rbX": 0.1}}], color=True)

    assert '\033[36m"regionBoundary"\033[0m' in output
    assert '\033[32m"rectangle"\033[0m' in output
    assert "\033[32m0.1\033[0m" in output
    assert "\033[31m" not in output
    assert "\033[33m" not in output


def test_image_region_json_uses_issue_colors_for_error_fields():
    result = ValidationResult()
    result.add("error", "INVALID_BOUNDARY_SHAPE", "imageRegion[0].regionBoundary.rbShape", "Invalid shape.")

    output = format_json(
        [{"regionBoundary": {"rbShape": "triangle", "rbUnit": "relative"}}],
        color=True,
        issues=result.issues,
    )

    assert '\033[31m"rbShape"\033[0m' in output
    assert '\033[31m"triangle"\033[0m' in output
    assert '\033[36m"rbUnit"\033[0m' in output


def test_image_region_json_uses_issue_colors_for_warning_fields():
    result = ValidationResult()
    result.add("warning", "DUPLICATE_REGION_NAME", "imageRegion[0].name", "Duplicate name.")

    output = format_json(
        [{"name": "Face", "regionBoundary": {"rbShape": "rectangle"}}],
        color=True,
        issues=result.issues,
    )

    assert '\033[33m"name"\033[0m' in output
    assert '\033[33m"Face"\033[0m' in output
    assert "\033[31m" not in output


def test_image_region_json_inherits_error_color_from_parent_issue():
    result = ValidationResult()
    result.add("error", "BOUNDARY_NOT_OBJECT", "imageRegion[0].regionBoundary", "Boundary is invalid.")

    output = format_json(
        [{"regionBoundary": {"rbShape": "rectangle", "rbUnit": "relative"}}],
        color=True,
        issues=result.issues,
    )

    assert '\033[31m"regionBoundary"\033[0m' in output
    assert '\033[31m"rbShape"\033[0m' in output
    assert '\033[31m"rectangle"\033[0m' in output
    assert '\033[31m"rbUnit"\033[0m' in output
    assert '\033[31m"relative"\033[0m' in output


def test_image_region_json_child_error_overrides_parent_warning_color():
    result = ValidationResult()
    result.add("warning", "PARENT_WARNING", "imageRegion[0].name", "Name warning.")
    result.add("error", "CHILD_ERROR", "imageRegion[0].name.x-default", "Name error.")

    output = format_json(
        [{"name": {"x-default": "Face", "de": "Gesicht"}}],
        color=True,
        issues=result.issues,
    )

    assert '\033[33m"name"\033[0m' in output
    assert '\033[31m"x-default"\033[0m' in output
    assert '\033[31m"Face"\033[0m' in output
    assert '\033[33m"de"\033[0m' in output
    assert '\033[33m"Gesicht"\033[0m' in output


def test_image_region_json_colors_unknown_fields_white():
    output = format_json(
        [
            {
                "customScore": 0.98,
                "customMetadata": {"source": "detector"},
                "regionBoundary": {"rbShape": "rectangle"},
            }
        ],
        color=True,
    )

    assert '\033[37m"customScore"\033[0m' in output
    assert "\033[37m0.98\033[0m" in output
    assert '\033[37m"customMetadata"\033[0m' in output
    assert '\033[37m"source"\033[0m' in output
    assert '\033[37m"detector"\033[0m' in output
    assert '\033[36m"regionBoundary"\033[0m' in output


def test_image_region_json_can_stay_plain():
    output = format_json([{"regionBoundary": {"rbShape": "rectangle"}}], color=False)

    assert "\033[" not in output
    assert json.loads(output) == [{"regionBoundary": {"rbShape": "rectangle"}}]


def test_public_image_region_renderer_accepts_region_list_without_validation_run():
    regions = ImageRegionList(
        ImageRegion(boundary=RectangleBoundary(unit="relative", x=0.1, y=0.2, width=0.3, height=0.4))
    )

    output = format_image_region(regions)

    assert json.loads(output) == [
        {
            "regionBoundary": {
                "rbShape": "rectangle",
                "rbUnit": "relative",
                "rbX": 0.1,
                "rbY": 0.2,
                "rbW": 0.3,
                "rbH": 0.4,
            }
        }
    ]


def test_public_annotated_renderer_accepts_region_without_validation_run():
    region = ImageRegion.from_raw(
        {"regionBoundary": {"rbShape": "rectangle", "rbUnit": "relative", "rbY": 0.2}},
        allow_malformed=True,
    )

    output = format_annotated_image_region(region)

    assert "// ERROR MISSING_BOUNDARY_FIELD: rectangle requires rbX." in output
    assert '"regionBoundary":' in output


def test_public_validation_renderer_accepts_metadata_without_validation_run():
    metadata = NormalizedMetadata(
        image_regions=ImageRegionList.from_raw(
            [{"regionBoundary": {"rbShape": "rectangle", "rbUnit": "relative"}}],
            allow_malformed=True,
        )
    )

    output = format_validation(metadata)

    assert json.loads(output)["issues"][0]["code"] == "MISSING_BOUNDARY_FIELD"
