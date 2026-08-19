from __future__ import annotations

import base64
import importlib.util
import json
import sys
import unittest
from io import BytesIO
from pathlib import Path

from PIL import Image


ROOT = Path(__file__).resolve().parents[2]
API_ROCKY_DIR = ROOT / "api-rocky"
MODULE_PATH = API_ROCKY_DIR / "image_input.py"
FIXTURE_PATH = ROOT / "run-test" / "fixtures" / "responses_image_input.json"

spec = importlib.util.spec_from_file_location("rocky_image_input_tests", MODULE_PATH)
if spec is None or spec.loader is None:
    raise RuntimeError("Unable to load Rocky image-input validation.")
image_input = importlib.util.module_from_spec(spec)
sys.path.insert(0, str(API_ROCKY_DIR))
try:
    sys.modules[spec.name] = image_input
    spec.loader.exec_module(image_input)
finally:
    sys.path.remove(str(API_ROCKY_DIR))


def encoded_image(image_format="PNG", size=(2, 3), *, save_all=False):
    output = BytesIO()
    first = Image.new("RGB", size, (20, 40, 60))
    save_arguments = {}
    if save_all:
        save_arguments = {
            "save_all": True,
            "append_images": [Image.new("RGB", size, (80, 100, 120))],
            "duration": 100,
            "loop": 0,
        }
    first.save(output, format=image_format, **save_arguments)
    return output.getvalue()


def image_block(image_bytes, mime_type="image/png", **extra):
    encoded = base64.b64encode(image_bytes).decode("ascii")
    return {
        "type": "input_image",
        "image_url": f"data:{mime_type};base64,{encoded}",
        **extra,
    }


def request_input(*blocks, role="user"):
    return [{"role": role, "content": list(blocks)}]


class ImageInputValidationTests(unittest.TestCase):
    def limits(self, **overrides):
        values = {
            "max_images": 4,
            "max_image_bytes": 4 * 1024 * 1024,
            "max_total_bytes": 6 * 1024 * 1024,
            "max_pixels": 20_000_000,
            "max_total_pixels": 40_000_000,
        }
        values.update(overrides)
        return image_input.ImageInputLimits(**values)

    def test_frozen_fixture_is_verified_and_normalized(self):
        payload = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))

        images = image_input.validate_image_inputs(payload["input"], self.limits())

        self.assertEqual(len(images), 1)
        validated = images[0]
        self.assertEqual((validated.mime_type, validated.width, validated.height), (
            "image/png", 1, 1,
        ))
        self.assertEqual(validated.detail, "auto")
        self.assertEqual(len(validated.sha256), 64)
        internal = validated.internal_block()
        self.assertNotIn("image_url", internal)
        self.assertEqual(base64.b64decode(internal["image_base64"]),
                         base64.b64decode(validated.base64_data))
        self.assertNotIn("image_base64", validated.telemetry_record())

    def test_accepts_verified_jpeg_png_and_static_webp(self):
        cases = (
            ("JPEG", "image/jpeg"),
            ("PNG", "image/png"),
            ("WEBP", "image/webp"),
        )
        for image_format, mime_type in cases:
            with self.subTest(image_format=image_format):
                images = image_input.validate_image_inputs(
                    request_input(image_block(
                        encoded_image(image_format),
                        mime_type,
                        detail="auto",
                    )),
                    self.limits(),
                )
                self.assertEqual(images[0].image_format, image_format)
                self.assertEqual((images[0].width, images[0].height), (2, 3))

    def test_rejects_remote_urls_bad_base64_corruption_and_type_mismatch(self):
        png = encoded_image("PNG")
        cases = (
            (
                {"type": "input_image", "image_url": "https://example.test/a.png"},
                "unsupported_image_source",
            ),
            (
                {"type": "input_image", "image_url": "data:image/png;base64,%%%%"},
                "invalid_image",
            ),
            (image_block(b"not an image"), "invalid_image"),
            (image_block(png, "image/jpeg"), "image_type_mismatch"),
        )
        for block, code in cases:
            with (
                self.subTest(code=code),
                self.assertRaises(image_input.ImageInputValidationError) as raised,
            ):
                image_input.validate_image_inputs(request_input(block), self.limits())
            self.assertEqual(raised.exception.code, code)
            self.assertIn("input[0].content[0].image_url", raised.exception.param)

    def test_rejects_unsupported_fields_detail_roles_and_animation(self):
        png = encoded_image("PNG")
        animated_webp = encoded_image("WEBP", save_all=True)
        cases = (
            (request_input(image_block(png), role="assistant"), "invalid_image_role"),
            (request_input(image_block(png, file_id="file_123")), "unsupported_parameter"),
            (request_input(image_block(png, detail="high")), "unsupported_value"),
            (
                request_input(image_block(animated_webp, "image/webp")),
                "animated_image_not_supported",
            ),
        )
        for input_value, code in cases:
            with (
                self.subTest(code=code),
                self.assertRaises(image_input.ImageInputValidationError) as raised,
            ):
                image_input.validate_image_inputs(input_value, self.limits())
            self.assertEqual(raised.exception.code, code)

    def test_enforces_count_per_image_total_byte_and_pixel_budgets(self):
        small = encoded_image("PNG", (2, 2))
        large_pixels = encoded_image("PNG", (3, 3))
        cases = (
            (
                request_input(image_block(small), image_block(small)),
                self.limits(max_images=1),
                "too_many_images",
            ),
            (
                request_input(image_block(small)),
                self.limits(max_image_bytes=len(small) - 1),
                "image_too_large",
            ),
            (
                request_input(image_block(small), image_block(small)),
                self.limits(max_total_bytes=(2 * len(small)) - 1),
                "image_total_too_large",
            ),
            (
                request_input(image_block(large_pixels)),
                self.limits(max_pixels=8),
                "image_too_many_pixels",
            ),
            (
                request_input(image_block(small), image_block(small)),
                self.limits(max_total_pixels=7),
                "image_total_too_many_pixels",
            ),
        )
        for input_value, limits, code in cases:
            with (
                self.subTest(code=code),
                self.assertRaises(image_input.ImageInputValidationError) as raised,
            ):
                image_input.validate_image_inputs(input_value, limits)
            self.assertEqual(raised.exception.code, code)


if __name__ == "__main__":
    unittest.main()
