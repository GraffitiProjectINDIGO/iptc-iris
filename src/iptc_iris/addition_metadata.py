"""Helpers for extracting non-Image-Region metadata from tool output."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .models import NormalizedMetadata

STANDARD_EXIF_TAGS: dict[str, tuple[str, ...]] = {
    "orientation": (
        "EXIF:Orientation",
        "IFD0:Orientation",
        "Exif.Image.Orientation",
        "Exif.Photo.Orientation",
        "Orientation",
    ),
    "file_type": ("File:FileType", "Exif.Image.ProcessingSoftware", "FileType"),
    "file_type_extension": ("File:FileTypeExtension", "FileTypeExtension"),
    "mime_type": ("File:MIMEType", "MIMEType"),
    "exif_byte_order": ("File:ExifByteOrder", "ExifByteOrder"),
    "image_width": (
        "File:ImageWidth",
        "EXIF:ExifImageWidth",
        "ExifIFD:ExifImageWidth",
        "Exif.Photo.PixelXDimension",
        "ImageWidth",
    ),
    "image_height": (
        "File:ImageHeight",
        "EXIF:ExifImageHeight",
        "ExifIFD:ExifImageHeight",
        "Exif.Photo.PixelYDimension",
        "ImageHeight",
    ),
    "bits_per_sample": ("File:BitsPerSample", "BitsPerSample"),
    "color_components": ("File:ColorComponents", "ColorComponents"),
    "ycbcr_subsampling": ("File:YCbCrSubSampling", "YCbCrSubSampling"),
    "make": ("EXIF:Make", "IFD0:Make", "Exif.Image.Make", "Make"),
    "model": ("EXIF:Model", "IFD0:Model", "Exif.Image.Model", "Model"),
    "lens_make": ("EXIF:LensMake", "ExifIFD:LensMake", "Exif.Photo.LensMake", "LensMake"),
    "lens_info": ("EXIF:LensInfo", "ExifIFD:LensInfo", "Exif.Photo.LensSpecification", "LensInfo"),
    "lens_model": (
        "EXIF:LensModel",
        "ExifIFD:LensModel",
        "Composite:LensID",
        "Exif.Photo.LensModel",
        "Exif.CanonCs.LensType",
        "LensModel",
        "LensID",
    ),
    "camera_serial_number": (
        "EXIF:SerialNumber",
        "EXIF:BodySerialNumber",
        "ExifIFD:SerialNumber",
        "Exif.Photo.BodySerialNumber",
        "Exif.Image.CameraSerialNumber",
        "SerialNumber",
        "BodySerialNumber",
    ),
    "lens_serial_number": (
        "EXIF:LensSerialNumber",
        "ExifIFD:LensSerialNumber",
        "Exif.Photo.LensSerialNumber",
        "LensSerialNumber",
    ),
    "date_time_original": (
        "EXIF:DateTimeOriginal",
        "ExifIFD:DateTimeOriginal",
        "Exif.Photo.DateTimeOriginal",
        "DateTimeOriginal",
    ),
    "create_date": ("EXIF:CreateDate", "ExifIFD:CreateDate", "Exif.Photo.DateTimeDigitized", "CreateDate"),
    "offset_time": ("EXIF:OffsetTime", "ExifIFD:OffsetTime", "Exif.Photo.OffsetTime", "OffsetTime"),
    "offset_time_original": (
        "EXIF:OffsetTimeOriginal",
        "ExifIFD:OffsetTimeOriginal",
        "Exif.Photo.OffsetTimeOriginal",
        "OffsetTimeOriginal",
    ),
    "software": ("EXIF:Software", "IFD0:Software", "Exif.Image.Software", "Software"),
    "artist": ("EXIF:Artist", "IFD0:Artist", "Exif.Image.Artist", "Artist"),
    "copyright": ("EXIF:Copyright", "IFD0:Copyright", "Exif.Image.Copyright", "Copyright"),
    "focal_length": ("EXIF:FocalLength", "ExifIFD:FocalLength", "Exif.Photo.FocalLength", "FocalLength"),
    "focal_length_35mm": (
        "EXIF:FocalLengthIn35mmFormat",
        "ExifIFD:FocalLengthIn35mmFormat",
        "Composite:FocalLength35efl",
        "Exif.Photo.FocalLengthIn35mmFilm",
        "FocalLengthIn35mmFormat",
    ),
    "aperture": ("Composite:Aperture", "EXIF:Aperture", "ExifIFD:Aperture", "Exif.Photo.Aperture", "Aperture"),
    "shutter_speed": (
        "Composite:ShutterSpeed",
        "EXIF:ShutterSpeed",
        "ExifIFD:ShutterSpeed",
        "Exif.Photo.ShutterSpeed",
        "ShutterSpeed",
    ),
    "exposure_time": ("EXIF:ExposureTime", "ExifIFD:ExposureTime", "Exif.Photo.ExposureTime", "ExposureTime"),
    "f_number": ("EXIF:FNumber", "ExifIFD:FNumber", "Exif.Photo.FNumber", "FNumber"),
    "iso": ("EXIF:ISO", "ExifIFD:ISO", "Exif.Photo.ISOSpeedRatings", "ISO"),
    "sensitivity_type": (
        "EXIF:SensitivityType",
        "ExifIFD:SensitivityType",
        "Exif.Photo.SensitivityType",
        "SensitivityType",
    ),
    "recommended_exposure_index": (
        "EXIF:RecommendedExposureIndex",
        "ExifIFD:RecommendedExposureIndex",
        "Exif.Photo.RecommendedExposureIndex",
        "RecommendedExposureIndex",
    ),
    "exposure_program": (
        "EXIF:ExposureProgram",
        "ExifIFD:ExposureProgram",
        "Exif.Photo.ExposureProgram",
        "ExposureProgram",
    ),
    "exposure_bias": (
        "EXIF:ExposureCompensation",
        "ExifIFD:ExposureCompensation",
        "Exif.Photo.ExposureBiasValue",
        "ExposureBiasValue",
    ),
    "exposure_mode": ("EXIF:ExposureMode", "ExifIFD:ExposureMode", "Exif.Photo.ExposureMode", "ExposureMode"),
    "metering_mode": ("EXIF:MeteringMode", "ExifIFD:MeteringMode", "Exif.Photo.MeteringMode", "MeteringMode"),
    "light_source": ("EXIF:LightSource", "ExifIFD:LightSource", "Exif.Photo.LightSource", "LightSource"),
    "flash": ("EXIF:Flash", "ExifIFD:Flash", "Exif.Photo.Flash", "Flash"),
    "white_balance": ("EXIF:WhiteBalance", "ExifIFD:WhiteBalance", "Exif.Photo.WhiteBalance", "WhiteBalance"),
    "color_space": (
        "EXIF:ColorSpace",
        "ExifIFD:ColorSpace",
        "Exif.Photo.ColorSpace",
        "Nikon:ColorSpace",
        "Exif.Nikon3.ColorSpace",
        "ColorSpace",
    ),
    "sensing_method": ("EXIF:SensingMethod", "ExifIFD:SensingMethod", "Exif.Photo.SensingMethod", "SensingMethod"),
    "file_source": ("EXIF:FileSource", "ExifIFD:FileSource", "Exif.Photo.FileSource", "FileSource"),
    "scene_type": ("EXIF:SceneType", "ExifIFD:SceneType", "Exif.Photo.SceneType", "SceneType"),
    "scene_capture_type": (
        "EXIF:SceneCaptureType",
        "ExifIFD:SceneCaptureType",
        "Exif.Photo.SceneCaptureType",
        "SceneCaptureType",
    ),
    "custom_rendered": (
        "EXIF:CustomRendered",
        "ExifIFD:CustomRendered",
        "Exif.Photo.CustomRendered",
        "CustomRendered",
    ),
    "gain_control": ("EXIF:GainControl", "ExifIFD:GainControl", "Exif.Photo.GainControl", "GainControl"),
    "contrast": ("EXIF:Contrast", "ExifIFD:Contrast", "Exif.Photo.Contrast", "Contrast"),
    "saturation": ("EXIF:Saturation", "ExifIFD:Saturation", "Exif.Photo.Saturation", "Saturation"),
    "sharpness": ("EXIF:Sharpness", "ExifIFD:Sharpness", "Exif.Photo.Sharpness", "Sharpness"),
    "subject_distance_range": (
        "EXIF:SubjectDistanceRange",
        "ExifIFD:SubjectDistanceRange",
        "Exif.Photo.SubjectDistanceRange",
        "SubjectDistanceRange",
    ),
    "user_comment": ("EXIF:UserComment", "ExifIFD:UserComment", "Exif.Photo.UserComment", "UserComment"),
    "gps_latitude": ("EXIF:GPSLatitude", "Composite:GPSLatitude", "Exif.GPSInfo.GPSLatitude", "GPSLatitude"),
    "gps_longitude": ("EXIF:GPSLongitude", "Composite:GPSLongitude", "Exif.GPSInfo.GPSLongitude", "GPSLongitude"),
    "gps_altitude": ("EXIF:GPSAltitude", "Composite:GPSAltitude", "Exif.GPSInfo.GPSAltitude", "GPSAltitude"),
    "gps_date_time": ("Composite:GPSDateTime", "GPSDateTime"),
    "gps_position": ("Composite:GPSPosition", "GPSPosition"),
    "auto_focus": (
        "Composite:AutoFocus",
        "EXIF:AutoFocus",
        "ExifIFD:AutoFocus",
        "Exif.Photo.AutoFocus",
        "AutoFocus",
        "Autofocus",
    ),
    "circle_of_confusion": (
        "Composite:CircleOfConfusion",
        "EXIF:CircleOfConfusion",
        "ExifIFD:CircleOfConfusion",
        "Exif.Photo.CircleOfConfusion",
        "CircleOfConfusion",
    ),
    "hyperfocal_distance": (
        "Composite:HyperfocalDistance",
        "EXIF:HyperfocalDistance",
        "ExifIFD:HyperfocalDistance",
        "Exif.Photo.HyperfocalDistance",
        "HyperfocalDistance",
    ),
    "depth_of_field": ("Composite:DOF", "EXIF:DOF", "ExifIFD:DOF", "Exif.Photo.DOF", "DOF"),
    "field_of_view": ("Composite:FOV", "EXIF:FOV", "ExifIFD:FOV", "Exif.Photo.FOV", "FOV"),
    "light_value": (
        "Composite:LightValue",
        "EXIF:LightValue",
        "ExifIFD:LightValue",
        "Exif.Photo.LightValue",
        "LightValue",
    ),
    "megapixels": (
        "Composite:Megapixels",
        "EXIF:Megapixels",
        "ExifIFD:Megapixels",
        "Exif.Photo.Megapixels",
        "Megapixels",
    ),
    "gps_image_direction": (
        "GPS:GPSImgDirection",
        "Exif.GPSInfo.GPSImgDirection",
        "GPSImgDirection",
    ),
    "gps_map_datum": ("GPS:GPSMapDatum", "Exif.GPSInfo.GPSMapDatum", "GPSMapDatum"),
}


def standard_exif_json(metadata: NormalizedMetadata | Mapping[str, Any] | list[Any] | None) -> dict[str, Any]:
    """Return selected standard EXIF metadata as a JSON-ready dictionary.

    Args:
        metadata: A NormalizedMetadata object, raw ExifTool JSON object/list,
            or flat Exiv2-style key/value mapping.

    Returns:
        Compact dictionary keyed by stable snake_case names. Missing or empty
        fields are omitted.
    """

    raw = metadata.raw if isinstance(metadata, NormalizedMetadata) else metadata
    raw = _single_metadata_record(raw)
    if not isinstance(raw, Mapping):
        return {}

    flat = _flatten_mapping(raw)
    standard_exif: dict[str, Any] = {}
    for output_key, aliases in STANDARD_EXIF_TAGS.items():
        value = _first_present(flat, aliases)
        if value is not None:
            standard_exif[output_key] = _json_value(value)
    return standard_exif


def _single_metadata_record(value: Any) -> Any:
    if isinstance(value, list) and len(value) == 1 and isinstance(value[0], Mapping):
        return value[0]
    return value


def _flatten_mapping(value: Mapping[str, Any]) -> dict[str, Any]:
    flat: dict[str, Any] = {}

    def add(prefix: str, child: Any) -> None:
        if isinstance(child, Mapping):
            for key, nested in child.items():
                nested_key = f"{prefix}:{key}" if prefix else str(key)
                add(nested_key, nested)
            return
        flat[prefix] = child

    add("", value)
    return flat


def _first_present(flat: Mapping[str, Any], aliases: tuple[str, ...]) -> Any:
    for alias in aliases:
        candidates = (alias, alias.replace(":", "."), alias.split(":")[-1], alias.split(".")[-1])
        for candidate in candidates:
            if candidate in flat and not _is_empty(flat[candidate]):
                return flat[candidate]
    return None


def _is_empty(value: Any) -> bool:
    return value is None or value == "" or value == []


def _json_value(value: Any) -> Any:
    if isinstance(value, tuple):
        return [_json_value(item) for item in value]
    if isinstance(value, list):
        return [_json_value(item) for item in value]
    if isinstance(value, Mapping):
        return {str(key): _json_value(child) for key, child in value.items()}
    return value
