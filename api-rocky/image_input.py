"""Strict validation for Rocky's deliberately small public image-input subset."""

from __future__ import annotations

import base64
import binascii
import hashlib
import warnings
from dataclasses import dataclass
from io import BytesIO

from PIL import Image, UnidentifiedImageError


SUPPORTED_IMAGE_FORMATS = {
    "image/jpeg": "JPEG",
    "image/png": "PNG",
    "image/webp": "WEBP",
}
_DATA_URL_PREFIXES = {
    f"data:{mime_type};base64,": (mime_type, image_format)
    for mime_type, image_format in SUPPORTED_IMAGE_FORMATS.items()
}


class ImageInputValidationError(ValueError):
    """A stable public validation failure with its exact request parameter."""

    def __init__(self, message, param, code="invalid_image"):
        super().__init__(message)
        self.message = message
        self.param = param
        self.code = code


@dataclass(frozen=True)
class ImageInputLimits:
    max_images: int
    max_image_bytes: int
    max_total_bytes: int
    max_pixels: int
    max_total_pixels: int


@dataclass(frozen=True)
class ValidatedImageInput:
    message_index: int
    block_index: int
    mime_type: str
    image_format: str
    base64_data: str
    byte_length: int
    width: int
    height: int
    sha256: str
    detail: str

    def internal_block(self):
        """Return the provider-neutral block sent only across Rocky's boundary."""
        return {
            "type": "input_image",
            "mime_type": self.mime_type,
            "image_base64": self.base64_data,
            "detail": self.detail,
            "byte_length": self.byte_length,
            "width": self.width,
            "height": self.height,
            "sha256": self.sha256,
        }

    def telemetry_record(self):
        """Describe the stored image without duplicating its base64 payload."""
        return {
            "message_index": self.message_index,
            "block_index": self.block_index,
            "mime_type": self.mime_type,
            "byte_length": self.byte_length,
            "width": self.width,
            "height": self.height,
            "pixel_count": self.width * self.height,
            "sha256": self.sha256,
            "detail": self.detail,
        }


def _invalid(message, param, code="invalid_image"):
    raise ImageInputValidationError(message, param, code)


def _split_data_url(value, param):
    if not isinstance(value, str) or not value:
        _invalid("image_url must be a non-empty string.", param, "invalid_type")

    for prefix, format_details in _DATA_URL_PREFIXES.items():
        if value.startswith(prefix):
            encoded = value[len(prefix):]
            if not encoded:
                _invalid("image_url contains no image data.", param)
            return (*format_details, encoded)

    _invalid(
        "image_url must be a base64 data URL containing a JPEG, PNG, or WebP image.",
        param,
        "unsupported_image_source",
    )


def _decoded_size(encoded, param):
    if len(encoded) % 4:
        _invalid("image_url contains invalid base64 data.", param)
    padding = len(encoded) - len(encoded.rstrip("="))
    if padding > 2:
        _invalid("image_url contains invalid base64 data.", param)
    return (len(encoded) // 4) * 3 - padding


def _decode_image(encoded, param, limits, remaining_bytes):
    decoded_size = _decoded_size(encoded, param)
    if decoded_size > limits.max_image_bytes:
        _invalid(
            f"Each image must be at most {limits.max_image_bytes} decoded bytes.",
            param,
            "image_too_large",
        )
    if decoded_size > remaining_bytes:
        _invalid(
            f"Images must total at most {limits.max_total_bytes} decoded bytes.",
            param,
            "image_total_too_large",
        )
    try:
        image_bytes = base64.b64decode(encoded, validate=True)
    except (binascii.Error, ValueError) as error:
        raise ImageInputValidationError(
            "image_url contains invalid base64 data.",
            param,
        ) from error
    if len(image_bytes) != decoded_size or not image_bytes:
        _invalid("image_url contains invalid base64 data.", param)
    return image_bytes


def _inspect_image(image_bytes, expected_format, param, max_pixels):
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(BytesIO(image_bytes)) as image:
                image_format = image.format
                width, height = image.size
                frame_count = getattr(image, "n_frames", 1)
                if image_format != expected_format:
                    _invalid(
                        "The image data does not match its declared media type.",
                        param,
                        "image_type_mismatch",
                    )
                if (
                    not isinstance(width, int)
                    or not isinstance(height, int)
                    or width < 1
                    or height < 1
                ):
                    _invalid("The image has invalid dimensions.", param)
                if width * height > max_pixels:
                    _invalid(
                        f"Each image must contain at most {max_pixels} pixels.",
                        param,
                        "image_too_many_pixels",
                    )
                if frame_count != 1:
                    _invalid(
                        "Animated images are not supported.",
                        param,
                        "animated_image_not_supported",
                    )
                image.verify()

            # verify() checks the container. A separate load catches truncated or
            # otherwise invalid pixel data before it reaches the model process.
            with Image.open(BytesIO(image_bytes)) as image:
                image.load()
    except ImageInputValidationError:
        raise
    except (
        Image.DecompressionBombError,
        Image.DecompressionBombWarning,
        UnidentifiedImageError,
        OSError,
        SyntaxError,
        ValueError,
    ) as error:
        raise ImageInputValidationError(
            "image_url does not contain a valid supported image.",
            param,
        ) from error
    return width, height


def validate_image_inputs(input_value, limits):
    """Validate all public input_image blocks and return normalized descriptors."""
    if not isinstance(limits, ImageInputLimits):
        raise TypeError("Image input limits are required.")
    if not isinstance(input_value, list):
        return []

    validated = []
    total_bytes = 0
    total_pixels = 0
    for message_index, message in enumerate(input_value):
        if not isinstance(message, dict):
            continue
        role = message.get("role", "user")
        content = message.get("content")
        if not isinstance(content, list):
            continue
        for block_index, block in enumerate(content):
            if not isinstance(block, dict) or block.get("type") != "input_image":
                continue
            block_param = f"input[{message_index}].content[{block_index}]"
            if len(validated) >= limits.max_images:
                _invalid(
                    f"A request may contain at most {limits.max_images} images.",
                    f"{block_param}.type",
                    "too_many_images",
                )
            if role != "user":
                _invalid(
                    "Images are supported only in user messages.",
                    f"{block_param}.type",
                    "invalid_image_role",
                )
            unsupported_fields = set(block) - {"type", "image_url", "detail"}
            if unsupported_fields:
                field = sorted(unsupported_fields)[0]
                _invalid(
                    f"Image field '{field}' is not supported.",
                    f"{block_param}.{field}",
                    "unsupported_parameter",
                )
            detail = block.get("detail", "auto")
            if detail != "auto":
                _invalid(
                    "detail must be 'auto' when provided.",
                    f"{block_param}.detail",
                    "unsupported_value",
                )

            image_url_param = f"{block_param}.image_url"
            mime_type, image_format, encoded = _split_data_url(
                block.get("image_url"),
                image_url_param,
            )
            image_bytes = _decode_image(
                encoded,
                image_url_param,
                limits,
                limits.max_total_bytes - total_bytes,
            )
            width, height = _inspect_image(
                image_bytes,
                image_format,
                image_url_param,
                limits.max_pixels,
            )
            pixel_count = width * height
            if pixel_count > limits.max_total_pixels - total_pixels:
                _invalid(
                    f"Images must total at most {limits.max_total_pixels} pixels.",
                    image_url_param,
                    "image_total_too_many_pixels",
                )
            total_bytes += len(image_bytes)
            total_pixels += pixel_count
            validated.append(ValidatedImageInput(
                message_index=message_index,
                block_index=block_index,
                mime_type=mime_type,
                image_format=image_format,
                base64_data=encoded,
                byte_length=len(image_bytes),
                width=width,
                height=height,
                sha256=hashlib.sha256(image_bytes).hexdigest(),
                detail=detail,
            ))
    return validated
