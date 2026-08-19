"""Defense-in-depth validation for Rocky's private normalized image blocks."""

from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import warnings
from io import BytesIO

from PIL import Image, UnidentifiedImageError


SUPPORTED_IMAGE_FORMATS = {
    "image/jpeg": "JPEG",
    "image/png": "PNG",
    "image/webp": "WEBP",
}
INTERNAL_IMAGE_FIELDS = {
    "type",
    "mime_type",
    "image_base64",
    "detail",
    "byte_length",
    "width",
    "height",
    "sha256",
}


def _invalid(message):
    raise ValueError(message)


def _decode_base64(encoded, max_bytes, remaining_bytes):
    if not isinstance(encoded, str) or not encoded or len(encoded) % 4:
        _invalid("input_image.image_base64 is invalid.")
    padding = len(encoded) - len(encoded.rstrip("="))
    if padding > 2:
        _invalid("input_image.image_base64 is invalid.")
    decoded_size = (len(encoded) // 4) * 3 - padding
    if decoded_size > max_bytes:
        _invalid("input_image exceeds the per-image byte limit.")
    if decoded_size > remaining_bytes:
        _invalid("input_image values exceed the request byte limit.")
    try:
        image_bytes = base64.b64decode(encoded, validate=True)
    except (binascii.Error, ValueError) as error:
        raise ValueError("input_image.image_base64 is invalid.") from error
    if not image_bytes or len(image_bytes) != decoded_size:
        _invalid("input_image.image_base64 is invalid.")
    return image_bytes


def _verify_pixels(image_bytes, image_format, width, height, max_pixels):
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(BytesIO(image_bytes)) as image:
                if image.format != image_format or image.size != (width, height):
                    _invalid("input_image metadata does not match its image data.")
                if width * height > max_pixels:
                    _invalid("input_image exceeds the pixel limit.")
                if getattr(image, "n_frames", 1) != 1:
                    _invalid("Animated input images are not supported.")
                image.verify()
            with Image.open(BytesIO(image_bytes)) as image:
                image.load()
    except ValueError:
        raise
    except (
        Image.DecompressionBombError,
        Image.DecompressionBombWarning,
        UnidentifiedImageError,
        OSError,
        SyntaxError,
    ) as error:
        raise ValueError("input_image does not contain a valid image.") from error


def validate_internal_image_block(
    block,
    *,
    max_image_bytes,
    remaining_bytes,
    max_pixels,
    remaining_pixels,
):
    """Validate one normalized block and return its Ollama base64 value and size."""
    if not isinstance(block, dict) or set(block) != INTERNAL_IMAGE_FIELDS:
        _invalid("input_image contains unsupported or missing fields.")
    if block.get("type") != "input_image" or block.get("detail") != "auto":
        _invalid("input_image contains unsupported values.")

    mime_type = block.get("mime_type")
    image_format = SUPPORTED_IMAGE_FORMATS.get(mime_type)
    if image_format is None:
        _invalid("input_image.mime_type is not supported.")
    byte_length = block.get("byte_length")
    width = block.get("width")
    height = block.get("height")
    sha256 = block.get("sha256")
    for name, value in (
        ("byte_length", byte_length),
        ("width", width),
        ("height", height),
    ):
        if not isinstance(value, int) or isinstance(value, bool) or value < 1:
            _invalid(f"input_image.{name} is invalid.")
    if (
        not isinstance(sha256, str)
        or len(sha256) != 64
        or any(character not in "0123456789abcdef" for character in sha256)
    ):
        _invalid("input_image.sha256 is invalid.")

    encoded = block.get("image_base64")
    image_bytes = _decode_base64(encoded, max_image_bytes, remaining_bytes)
    if len(image_bytes) != byte_length:
        _invalid("input_image.byte_length does not match its image data.")
    if not hmac.compare_digest(hashlib.sha256(image_bytes).hexdigest(), sha256):
        _invalid("input_image.sha256 does not match its image data.")
    _verify_pixels(image_bytes, image_format, width, height, max_pixels)
    pixel_count = width * height
    if pixel_count > remaining_pixels:
        _invalid("input_image values exceed the request pixel limit.")
    return encoded, len(image_bytes), pixel_count
