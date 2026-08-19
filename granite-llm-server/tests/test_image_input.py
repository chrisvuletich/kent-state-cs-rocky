from __future__ import annotations

import base64
import hashlib
import unittest
from io import BytesIO
from unittest.mock import patch

from PIL import Image

from app.image_input import validate_internal_image_block
from app.request_parser import (
    MAX_IMAGE_BYTES,
    MAX_IMAGE_PIXELS,
    MAX_IMAGE_TOTAL_BYTES,
    MAX_IMAGE_TOTAL_PIXELS,
    extract_messages,
)


def image_bytes(image_format="PNG", size=(2, 3), *, animated=False):
    output = BytesIO()
    image = Image.new("RGB", size, (30, 60, 90))
    arguments = {}
    if animated:
        arguments = {
            "save_all": True,
            "append_images": [Image.new("RGB", size, (90, 60, 30))],
            "duration": 100,
            "loop": 0,
        }
    image.save(output, format=image_format, **arguments)
    return output.getvalue()


def internal_block(data=None, mime_type="image/png", size=(2, 3)):
    data = data if data is not None else image_bytes("PNG", size)
    return {
        "type": "input_image",
        "mime_type": mime_type,
        "image_base64": base64.b64encode(data).decode("ascii"),
        "detail": "auto",
        "byte_length": len(data),
        "width": size[0],
        "height": size[1],
        "sha256": hashlib.sha256(data).hexdigest(),
    }


class GraniteImageInputTests(unittest.TestCase):
    def validate(self, block):
        return validate_internal_image_block(
            block,
            max_image_bytes=MAX_IMAGE_BYTES,
            remaining_bytes=MAX_IMAGE_TOTAL_BYTES,
            max_pixels=MAX_IMAGE_PIXELS,
            remaining_pixels=MAX_IMAGE_TOTAL_PIXELS,
        )

    def test_validated_internal_image_reaches_ollama_images_array(self):
        block = internal_block()
        messages = extract_messages({
            "input": [{
                "role": "user",
                "content": [
                    {"type": "input_text", "text": "Describe it."},
                    block,
                ],
            }],
        }, allow_images=True)

        self.assertEqual(messages, [{
            "role": "user",
            "content": "Describe it.",
            "images": [block["image_base64"]],
        }])

    def test_image_blocks_are_rejected_when_rollout_is_disabled(self):
        with self.assertRaisesRegex(ValueError, "not enabled"):
            extract_messages({
                "input": [{
                    "role": "user",
                    "content": [internal_block()],
                }],
            }, allow_images=False)

    def test_assistant_output_text_history_is_preserved(self):
        messages = extract_messages({
            "input": [{
                "role": "assistant",
                "content": [{"type": "output_text", "text": "Earlier reply"}],
            }],
        })

        self.assertEqual(messages, [{
            "role": "assistant",
            "content": "Earlier reply",
        }])

    def test_interleaved_text_and_images_preserve_provider_message_order(self):
        first = internal_block(size=(2, 3))
        second = internal_block(size=(3, 2))

        messages = extract_messages({
            "input": [{
                "role": "user",
                "content": [
                    {"type": "input_text", "text": "Before."},
                    first,
                    {"type": "input_text", "text": "Between."},
                    second,
                    {"type": "input_text", "text": "After."},
                ],
            }],
        }, allow_images=True)

        self.assertEqual(messages, [
            {"role": "user", "content": "Before."},
            {"role": "user", "content": "", "images": [first["image_base64"]]},
            {"role": "user", "content": "Between."},
            {"role": "user", "content": "", "images": [second["image_base64"]]},
            {"role": "user", "content": "After."},
        ])

    def test_tampered_internal_metadata_and_data_fail_closed(self):
        valid = internal_block()
        cases = []
        for field, value in (
            ("sha256", "0" * 64),
            ("byte_length", valid["byte_length"] + 1),
            ("width", valid["width"] + 1),
            ("mime_type", "image/jpeg"),
            ("image_base64", "%%%%"),
        ):
            candidate = dict(valid)
            candidate[field] = value
            cases.append(candidate)
        extra = dict(valid)
        extra["private"] = "must fail"
        cases.append(extra)

        for candidate in cases:
            with self.subTest(candidate=candidate), self.assertRaises(ValueError):
                self.validate(candidate)

    def test_animation_and_pixel_or_byte_overages_fail_closed(self):
        animated = image_bytes("WEBP", animated=True)
        animated_block = internal_block(animated, "image/webp")
        with self.assertRaisesRegex(ValueError, "Animated"):
            self.validate(animated_block)

        valid = internal_block()
        with self.assertRaisesRegex(ValueError, "byte limit"):
            validate_internal_image_block(
                valid,
                max_image_bytes=valid["byte_length"] - 1,
                remaining_bytes=MAX_IMAGE_TOTAL_BYTES,
                max_pixels=MAX_IMAGE_PIXELS,
                remaining_pixels=MAX_IMAGE_TOTAL_PIXELS,
            )
        with self.assertRaisesRegex(ValueError, "pixel limit"):
            validate_internal_image_block(
                valid,
                max_image_bytes=MAX_IMAGE_BYTES,
                remaining_bytes=MAX_IMAGE_TOTAL_BYTES,
                max_pixels=5,
                remaining_pixels=MAX_IMAGE_TOTAL_PIXELS,
            )

        with self.assertRaisesRegex(ValueError, "request pixel limit"):
            validate_internal_image_block(
                valid,
                max_image_bytes=MAX_IMAGE_BYTES,
                remaining_bytes=MAX_IMAGE_TOTAL_BYTES,
                max_pixels=MAX_IMAGE_PIXELS,
                remaining_pixels=5,
            )

    def test_request_wide_pixel_budget_is_enforced_across_images(self):
        block = internal_block()
        payload = {
            "input": [{
                "role": "user",
                "content": [block, block],
            }],
        }
        with (
            patch("app.request_parser.MAX_IMAGE_TOTAL_PIXELS", 11),
            self.assertRaisesRegex(ValueError, "request pixel limit"),
        ):
            extract_messages(payload, allow_images=True)


if __name__ == "__main__":
    unittest.main()
