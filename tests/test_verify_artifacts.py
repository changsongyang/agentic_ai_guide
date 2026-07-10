from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest import mock


try:
    from tools import verify_artifacts as verifier
except ImportError:
    verifier = None


class ArtifactVerifierTests(unittest.TestCase):
    def require_verifier(self):
        self.assertIsNotNone(verifier, "tools/verify_artifacts.py must be importable")
        return verifier

    def test_html_requires_exact_title_and_all_mermaid_svg_figures(self):
        module = self.require_verifier()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "book.html"
            path.write_text(
                "<!doctype html><html><head><title>智能体 AI 权威指南</title></head>"
                '<body><figure class="diagram"><svg></svg></figure></body></html>',
                encoding="utf-8",
            )
            module.verify_html(
                path,
                "智能体 AI 权威指南",
                expected_mermaid_count=1,
            )

            for invalid in (
                path.read_text(encoding="utf-8").replace("权威指南", "错误标题", 1),
                path.read_text(encoding="utf-8").replace("<svg></svg>", "source fallback"),
                path.read_text(encoding="utf-8").replace(
                    "</body>", '<pre class="diagram-fallback">graph TD</pre></body>'
                ),
                path.read_text(encoding="utf-8").replace("</body>", "MERMAIDZZ0ZZ</body>"),
            ):
                path.write_text(invalid, encoding="utf-8")
                with self.assertRaises(module.ArtifactVerificationError):
                    module.verify_html(
                        path,
                        "智能体 AI 权威指南",
                        expected_mermaid_count=1,
                    )

    def test_summary_mermaid_count_only_uses_published_chapters(self):
        module = self.require_verifier()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "SUMMARY.md").write_text(
                "* [A](a.md)\n* [A again](a.md)\n", encoding="utf-8"
            )
            (root / "a.md").write_text(
                "```mermaid\ngraph TD\n```\n", encoding="utf-8"
            )
            (root / "unused.md").write_text(
                "```mermaid\ngraph LR\n```\n", encoding="utf-8"
            )
            self.assertEqual(module.count_summary_mermaid_blocks(root), 1)

    def test_pdf_requires_signature_and_expected_title(self):
        module = self.require_verifier()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "book.pdf"
            path.write_bytes(b"%PDF-1.7\nplaceholder")
            with (
                mock.patch.object(module.shutil, "which", return_value="/usr/bin/tool"),
                mock.patch.object(
                    module,
                    "command_output",
                    return_value="Title: 智能体 AI 权威指南\n",
                ),
            ):
                module.verify_pdf(path, "智能体 AI 权威指南")

            path.write_bytes(b"not a PDF")
            with self.assertRaises(module.ArtifactVerificationError):
                module.verify_pdf(path, "智能体 AI 权威指南")

    def test_checksums_cover_all_artifacts_and_detect_tampering(self):
        module = self.require_verifier()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            pdf = root / "book.pdf"
            html = root / "book.html"
            manifest = root / "SHA256SUMS"
            pdf.write_bytes(b"pdf")
            html.write_bytes(b"html")
            module.write_checksums([pdf, html], manifest)
            module.verify_checksums(manifest)
            self.assertEqual(len(manifest.read_text(encoding="utf-8").splitlines()), 2)

            html.write_bytes(b"changed")
            with self.assertRaises(module.ArtifactVerificationError):
                module.verify_checksums(manifest)


if __name__ == "__main__":
    unittest.main()
