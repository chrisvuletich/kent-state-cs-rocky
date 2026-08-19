from __future__ import annotations

import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
DOCS_ROOT = ROOT / "rocky-interface" / "static"
DEVELOPER_DOCS = DOCS_ROOT / "docs" / "developer"
REGISTRY = (
    ROOT / "rocky-interface" / "src" / "lib" / "documentation" / "registry.ts"
)


class StudentApiDocumentationTests(unittest.TestCase):
    def read_doc(self, filename: str) -> str:
        return (DEVELOPER_DOCS / filename).read_text(encoding="utf-8")

    def test_every_registered_markdown_document_exists(self):
        registry = REGISTRY.read_text(encoding="utf-8")
        paths = re.findall(r"path:\s*'(/docs/[^']+\.md)'", registry)

        self.assertTrue(paths)
        missing = [path for path in paths if not (DOCS_ROOT / path.lstrip("/")).is_file()]
        self.assertEqual(missing, [])

    def test_api_reference_advertises_runtime_capabilities_without_stale_claims(self):
        reference = self.read_doc("api-reference.md")

        for required in (
            '"supports_streaming": true',
            '"supports_image_input": true',
            '"type": "input_image"',
            "response.output_text.delta",
            "response.completed",
            "terminal `error` event",
        ):
            with self.subTest(required=required):
                self.assertIn(required, reference)

        for stale in (
            "Streaming is not currently supported",
            "Rocky currently accepts text only",
            "images, structured output, and\nstreaming are not part",
        ):
            with self.subTest(stale=stale):
                self.assertNotIn(stale, reference)

    def test_advanced_guides_are_registered_and_cover_failure_semantics(self):
        registry = REGISTRY.read_text(encoding="utf-8")
        streaming = self.read_doc("streaming-example.md")
        images = self.read_doc("image-input-example.md")
        errors = self.read_doc("errors.md")

        self.assertIn("/docs/developer/streaming-example.md", registry)
        self.assertIn("/docs/developer/image-input-example.md", registry)
        self.assertIn("supports_streaming", streaming)
        self.assertIn("closed connection", streaming)
        self.assertIn("TextDecoder", streaming)
        self.assertIn("supports_image_input", images)
        self.assertIn("university safety", images)
        self.assertIn("unsupported_image_source", errors)
        self.assertIn("image_total_too_many_pixels", errors)
        self.assertIn("HTTP status cannot be changed", errors)

    def test_python_examples_are_syntactically_valid(self):
        for filename in ("streaming-example.md", "image-input-example.md"):
            examples = re.findall(
                r"```python\n(.*?)```",
                self.read_doc(filename),
                flags=re.DOTALL,
            )
            self.assertTrue(examples, filename)
            for index, example in enumerate(examples):
                with self.subTest(filename=filename, example=index):
                    compile(example, f"{filename}:{index}", "exec")


if __name__ == "__main__":
    unittest.main()
