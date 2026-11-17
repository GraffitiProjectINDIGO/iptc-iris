from iptc_iris import normalize_metadata, standard_exif_json


def test_standard_exif_json_from_exiftool_raw_metadata():
    metadata = normalize_metadata(
        [
            {
                "SourceFile": "image.jpg",
                "EXIF:Orientation": 6,
                "EXIF:Make": "Canon",
                "EXIF:Model": "EOS R5",
                "EXIF:LensModel": "RF24-70mm F2.8 L IS USM",
                "EXIF:DateTimeOriginal": "2024:03:11 14:22:01",
                "EXIF:ISO": 400,
                "XMP-iptcExt:ImageRegion": [],
            }
        ],
        source_format="exiftool-json",
    )

    assert standard_exif_json(metadata) == {
        "orientation": 6,
        "make": "Canon",
        "model": "EOS R5",
        "lens_model": "RF24-70mm F2.8 L IS USM",
        "date_time_original": "2024:03:11 14:22:01",
        "iso": 400,
    }


def test_standard_exif_json_from_exiftool_grouped_exififd_and_composite_metadata():
    metadata = normalize_metadata(
        [
            {
                "SourceFile": "image.jpg",
                "File:MIMEType": "image/jpeg",
                "File:ImageWidth": 8256,
                "File:ImageHeight": 5504,
                "IFD0:Make": "NIKON CORPORATION",
                "IFD0:Model": "NIKON Z 7_2",
                "IFD0:Orientation": "Rotate 270 CW",
                "ExifIFD:ExposureTime": "1/200",
                "ExifIFD:FNumber": 5.6,
                "ExifIFD:ISO": 90,
                "ExifIFD:ExposureProgram": "Aperture-priority AE",
                "ExifIFD:ColorSpace": "sRGB",
                "ExifIFD:LensInfo": "20mm f/1.8",
                "ExifIFD:LensModel": "NIKKOR Z 20mm f/1.8 S",
                "ExifIFD:LensSerialNumber": "20015016",
                "Composite:ImageSize": "8256x5504",
                "Composite:LightValue": 12.8,
                "Composite:GPSPosition": "48 deg 13' 53.67\" N, 16 deg 21' 42.45\" E",
                "Composite:AutoFocus": "Off",
                "Composite:CircleOfConfusion": "0.030 mm",
                "Composite:HyperfocalDistance": "2.38 m",
                "XMP-iptcExt:ImageRegion": [],
            }
        ],
        source_format="exiftool-json",
    )

    assert standard_exif_json(metadata) == {
        "orientation": "Rotate 270 CW",
        "mime_type": "image/jpeg",
        "image_width": 8256,
        "image_height": 5504,
        "make": "NIKON CORPORATION",
        "model": "NIKON Z 7_2",
        "lens_info": "20mm f/1.8",
        "lens_model": "NIKKOR Z 20mm f/1.8 S",
        "lens_serial_number": "20015016",
        "exposure_time": "1/200",
        "f_number": 5.6,
        "iso": 90,
        "exposure_program": "Aperture-priority AE",
        "color_space": "sRGB",
        "gps_position": "48 deg 13' 53.67\" N, 16 deg 21' 42.45\" E",
        "auto_focus": "Off",
        "circle_of_confusion": "0.030 mm",
        "hyperfocal_distance": "2.38 m",
        "light_value": 12.8,
    }


def test_standard_exif_json_from_exiv2_flat_metadata():
    metadata = normalize_metadata(
        {
            "Exif.Image.Orientation": 8,
            "Exif.Image.Make": "Nikon",
            "Exif.Image.Model": "Z 8",
            "Exif.Photo.LensModel": "NIKKOR Z 24-120mm f/4 S",
            "Exif.Photo.ExposureTime": "1/125",
            "Exif.Photo.FNumber": "4",
        },
        source_format="exiv2",
    )

    assert standard_exif_json(metadata) == {
        "orientation": 8,
        "make": "Nikon",
        "model": "Z 8",
        "lens_model": "NIKKOR Z 24-120mm f/4 S",
        "exposure_time": "1/125",
        "f_number": "4",
    }


def test_standard_exif_json_from_exiv2_common_capture_settings():
    metadata = normalize_metadata(
        {
            "Exif.Photo.ColorSpace": "sRGB",
            "Exif.Photo.ExposureProgram": "Aperture priority",
            "Exif.Photo.ExposureMode": "Auto",
            "Exif.Photo.WhiteBalance": "Auto",
            "Exif.Photo.Contrast": "Normal",
            "Exif.Photo.Saturation": "Normal",
            "Exif.Photo.Sharpness": "Normal",
            "Exif.Photo.AutoFocus": "On",
            "Exif.Photo.CircleOfConfusion": "0.030 mm",
            "Exif.Photo.HyperfocalDistance": "2.38 m",
            "Exif.GPSInfo.GPSImgDirection": 195.9,
        },
        source_format="exiv2",
    )

    assert standard_exif_json(metadata) == {
        "exposure_program": "Aperture priority",
        "exposure_mode": "Auto",
        "white_balance": "Auto",
        "color_space": "sRGB",
        "contrast": "Normal",
        "saturation": "Normal",
        "sharpness": "Normal",
        "auto_focus": "On",
        "circle_of_confusion": "0.030 mm",
        "hyperfocal_distance": "2.38 m",
        "gps_image_direction": 195.9,
    }


def test_standard_exif_json_omits_missing_and_empty_values():
    assert standard_exif_json({"EXIF:Orientation": "", "EXIF:Make": None}) == {}
