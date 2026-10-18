"""Transcribe Instagram images with OCR.space before event extraction."""

import os
from io import BytesIO
import warnings

import requests

if __package__:
    from .runtime_utils import ScraperError, error_record, http_failure
else:
    from runtime_utils import ScraperError, error_record, http_failure


OCR_MAX_BYTES = 1_000_000


def prepare_ocr_image(data, mime):
    """Keep small JPEG/PNG originals; compress larger images and convert WebP."""
    if mime in {"image/jpeg", "image/png"} and len(data) < OCR_MAX_BYTES:
        return data, mime
    from PIL import Image, ImageOps, UnidentifiedImageError

    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(BytesIO(data)) as source:
                oriented = ImageOps.exif_transpose(source)
                # Flatten transparency onto white rather than losing dark text.
                rgba = oriented.convert("RGBA")
                picture = Image.new("RGB", rgba.size, "white")
                picture.paste(rgba, mask=rgba.getchannel("A"))
        while True:
            # Preserve resolution first; only resize if quality changes cannot fit.
            for quality in (95, 85, 75, 65):
                output = BytesIO()
                picture.save(output, format="JPEG", quality=quality, optimize=True)
                compressed = output.getvalue()
                if len(compressed) < OCR_MAX_BYTES:
                    return compressed, "image/jpeg"
            width, height = picture.size
            if max(width, height) <= 320:
                raise ScraperError("ocr", "image_size", "Could not compress image below 1 MB.")
            picture = picture.resize((max(1, int(width * 0.8)), max(1, int(height * 0.8))),
                                     Image.Resampling.LANCZOS)
    except (OSError, ValueError, UnidentifiedImageError,
            Image.DecompressionBombWarning, Image.DecompressionBombError):
        raise ScraperError("ocr", "invalid_image", "Could not decode image for OCR compression.") from None


def extract_image_text(images):
    """Return ordered transcriptions; never silently accept partial OCR results."""
    key = os.getenv("OCR_SPACE_API_KEY")
    if not key:
        raise ScraperError("settings", "missing_ocr_key", "Set OCR_SPACE_API_KEY in your terminal first.")
    extensions = {"image/jpeg": "jpg", "image/png": "png"}
    # Prepare the whole carousel before spending any API calls.
    images = [prepare_ocr_image(data, mime) for data, mime in images]
    transcriptions = []
    for position, (data, mime) in enumerate(images, 1):
        try:
            with requests.post(
                "https://api.ocr.space/parse/image",
                headers={"apikey": key},
                files={"file": (f"image-{position}.{extensions[mime]}", data, mime)},
                data={"OCREngine": "2", "isOverlayRequired": "false", "detectOrientation": "true"},
                timeout=(10, 60),
            ) as response:
                if response.status_code != 200:
                    raise http_failure("ocr", response.status_code)
                payload = response.json()
        except (requests.RequestException, ValueError) as error:
            record = error_record(error, "ocr")
            raise ScraperError(record["stage"], record["code"], record["message"]) from None
        if not isinstance(payload, dict):
            raise ScraperError("ocr", "invalid_response", "OCR.space returned an invalid response.")
        if payload.get("IsErroredOnProcessing") or str(payload.get("OCRExitCode")) != "1":
            raise ScraperError("ocr", "processing_failed", "OCR.space could not fully read the image; check key, quota, and image quality.")
        results = payload.get("ParsedResults")
        if not isinstance(results, list) or not results or any(
            not isinstance(result, dict) or str(result.get("FileParseExitCode")) != "1"
            or not isinstance(result.get("ParsedText"), str) for result in results
        ):
            raise ScraperError("ocr", "invalid_response", "OCR.space returned missing or incomplete text results.")
        text = "\n".join(result["ParsedText"] for result in results)
        transcriptions.append(f"Image {position}:\n{text}")
    return "\n\n".join(transcriptions)
