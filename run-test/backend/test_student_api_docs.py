from __future__ import annotations

import re
import shutil
import subprocess
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
DOCS_ROOT = ROOT / "rocky-interface" / "static"
DEVELOPER_DOCS = DOCS_ROOT / "docs" / "developer"
REGISTRY = (
    ROOT / "rocky-interface" / "src" / "lib" / "documentation" / "registry.ts"
)
STATIC_ROOT = ROOT / "rocky-interface" / "static"


def documentation_files() -> list[Path]:
    files = list(ROOT.glob("*.md"))
    for directory in (
        "api-rocky",
        "granite-llm-server",
        "rocky-backend",
        "deploy",
        "run-test",
    ):
        files.extend((ROOT / directory).glob("*.md"))
    files.extend((ROOT / "rocky-interface").glob("*.md"))
    files.extend((STATIC_ROOT / "docs").rglob("*.md"))
    return sorted(set(files))


class StudentApiDocumentationTests(unittest.TestCase):
    def read_doc(self, filename: str) -> str:
        return (DEVELOPER_DOCS / filename).read_text(encoding="utf-8")

    def test_every_registered_markdown_document_exists(self):
        registry = REGISTRY.read_text(encoding="utf-8")
        paths = re.findall(r"path:\s*'(/docs/[^']+\.md)'", registry)

        self.assertTrue(paths)
        missing = [path for path in paths if not (DOCS_ROOT / path.lstrip("/")).is_file()]
        self.assertEqual(missing, [])

    def test_local_markdown_links_and_images_resolve(self):
        missing: list[str] = []
        link_pattern = re.compile(r"!?\[[^\]]*\]\(([^)]+)\)")

        for document in documentation_files():
            for raw_target in link_pattern.findall(document.read_text(encoding="utf-8")):
                target = raw_target.strip().strip("<>").split("#", 1)[0]
                if not target or target.startswith(("http://", "https://", "mailto:", "/?")):
                    continue
                resolved = (
                    STATIC_ROOT / target.lstrip("/")
                    if target.startswith("/")
                    else document.parent / target
                )
                if not resolved.exists():
                    missing.append(f"{document.relative_to(ROOT)} -> {raw_target}")

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

    def test_public_error_and_limit_guidance_matches_runtime_contract(self):
        reference = self.read_doc("api-reference.md")
        errors = self.read_doc("errors.md")

        self.assertIn("metadata.max_output_tokens", reference)
        self.assertNotIn("Maximum generated tokens from 1 through 2048", reference)
        self.assertIn("rate_limit_identity_unavailable", errors)
        self.assertIn("ingress-level `413` or `429`", reference)
        self.assertIn("ingress-level `413` or `429`", errors)

    def test_python_examples_are_syntactically_valid(self):
        for path in sorted(DEVELOPER_DOCS.glob("*.md")):
            examples = re.findall(
                r"```python\n(.*?)```",
                path.read_text(encoding="utf-8"),
                flags=re.DOTALL,
            )
            for index, example in enumerate(examples):
                with self.subTest(filename=path.name, example=index):
                    compile(example, f"{path.name}:{index}", "exec")

    def test_javascript_examples_are_syntactically_valid(self):
        node = shutil.which("node")
        self.assertIsNotNone(node, "Node.js is required to validate student JavaScript examples")

        for path in sorted(DEVELOPER_DOCS.glob("*.md")):
            examples = re.findall(
                r"```javascript\n(.*?)```",
                path.read_text(encoding="utf-8"),
                flags=re.DOTALL,
            )
            for index, example in enumerate(examples):
                with self.subTest(filename=path.name, example=index):
                    result = subprocess.run(
                        [node, "--check", "--input-type=module"],
                        input=example,
                        text=True,
                        capture_output=True,
                        check=False,
                    )
                    self.assertEqual(result.returncode, 0, result.stderr)

    def test_api_key_guide_uses_current_control_labels(self):
        guide = self.read_doc("api-keys.md")
        component = (
            ROOT
            / "rocky-interface"
            / "src"
            / "lib"
            / "components"
            / "cards"
            / "CourseKeySlotCard.svelte"
        ).read_text(encoding="utf-8")

        for label in ("Generate Key", "Regenerate Key"):
            with self.subTest(label=label):
                self.assertIn(label, guide)
                self.assertIn(label, component)
        self.assertNotIn("Generate API Key", guide)

    def test_admin_guide_matches_current_summary_metrics(self):
        guide = (
            STATIC_ROOT / "docs" / "administration" / "admin-dashboard.md"
        ).read_text(encoding="utf-8")
        component = (
            ROOT
            / "rocky-interface"
            / "src"
            / "lib"
            / "components"
            / "views"
            / "AdminPanel.svelte"
        ).read_text(encoding="utf-8")

        for label in ("Total Users", "Active Users", "Total Courses", "API Keys Issued"):
            with self.subTest(label=label):
                self.assertIn(label, guide)
                self.assertIn(label, component)
        self.assertNotIn("Requests Today", guide)
        self.assertIn("Top Courses — Last 30 Days", guide)

    def test_deployment_guide_documents_templates_without_local_account_paths(self):
        guide = (ROOT / "deploy" / "README.md").read_text(encoding="utf-8")
        service_templates = "\n".join(
            path.read_text(encoding="utf-8")
            for path in sorted((ROOT / "deploy" / "systemd").glob("*.service.example"))
        )
        placeholders = set(re.findall(r"\{\{[A-Z0-9_]+\}\}", service_templates))

        for placeholder in sorted(placeholders):
            with self.subTest(placeholder=placeholder):
                self.assertIn(placeholder, guide)
        self.assertNotIn("/home/bboggia", guide)
        self.assertNotIn("bboggia:bboggia", guide)


if __name__ == "__main__":
    unittest.main()
