from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import check_project_rules as rules


ROOT = Path(__file__).resolve().parents[1]


def check_python(testcase: unittest.TestCase, root: Path) -> list[str]:
    testcase.assertTrue(
        hasattr(rules, "check_python_fences"),
        "check_project_rules.py must define check_python_fences()",
    )
    return rules.check_python_fences(root)


class PythonFenceTests(unittest.TestCase):
    def write_markdown(self, directory: str, text: str) -> Path:
        path = Path(directory) / "example.md"
        path.write_text(text, encoding="utf-8")
        return path

    def test_valid_python_fence_passes_ast_validation(self):
        with tempfile.TemporaryDirectory() as directory:
            self.write_markdown(directory, "```python\nprint('ok')\n```\n")
            self.assertEqual(check_python(self, Path(directory)), [])

    def test_syntax_error_is_reported(self):
        with tempfile.TemporaryDirectory() as directory:
            self.write_markdown(directory, "```python\nfrom <framework> import Client\n```\n")
            issues = check_python(self, Path(directory))
            self.assertTrue(any("angle-bracket placeholder" in issue for issue in issues), issues)
            self.assertTrue(any("invalid Python syntax" in issue for issue in issues), issues)

    def test_angle_bracket_configuration_placeholder_is_reported(self):
        with tempfile.TemporaryDirectory() as directory:
            self.write_markdown(directory, '```python\nmodel = "<MODEL>"\n```\n')
            issues = check_python(self, Path(directory))
            self.assertTrue(any("angle-bracket placeholder" in issue for issue in issues), issues)

    def test_balanced_xml_tags_inside_a_string_are_not_placeholders(self):
        with tempfile.TemporaryDirectory() as directory:
            self.write_markdown(
                directory,
                '```python\nprompt = "<thinking>plan</thinking><answer>ok</answer>"\n```\n',
            )
            self.assertEqual(check_python(self, Path(directory)), [])

    def test_explicit_non_runnable_pseudocode_is_the_only_exception(self):
        with tempfile.TemporaryDirectory() as directory:
            self.write_markdown(
                directory,
                "以下为伪代码，不可直接运行。\n\n"
                "```python non-runnable\nfrom <framework> import Client\n```\n",
            )
            self.assertEqual(check_python(self, Path(directory)), [])

            self.write_markdown(
                directory,
                "```python non-runnable\nfrom <framework> import Client\n```\n",
            )
            issues = check_python(self, Path(directory))
            self.assertTrue(any("must be introduced as pseudocode" in issue for issue in issues), issues)

    def test_every_repository_python_fence_is_parseable_or_explicit_pseudocode(self):
        self.assertEqual(check_python(self, ROOT), [])

    def test_main_checker_enforces_python_fences(self):
        source = (ROOT / "check_project_rules.py").read_text(encoding="utf-8")
        self.assertIn("issues.extend(check_python_fences())", source)


if __name__ == "__main__":
    unittest.main()
