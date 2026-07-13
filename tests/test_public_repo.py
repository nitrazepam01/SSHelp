from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class PublicRepositoryTests(unittest.TestCase):
    def test_public_repository_files_exist(self) -> None:
        for relative in (
            "README.md",
            "CONTRIBUTING.md",
            "SECURITY.md",
            ".gitignore",
            ".github/workflows/tests.yml",
            "sshelp/SKILL.md",
        ):
            self.assertTrue((ROOT / relative).is_file(), relative)

    def test_skill_examples_do_not_contain_local_machine_identity(self) -> None:
        paths = [
            ROOT / "sshelp" / "SKILL.md",
            ROOT / "sshelp" / "references" / "operations.md",
            ROOT / "sshelp" / "references" / "remote-files.md",
        ]
        text = "\n".join(path.read_text(encoding="utf-8") for path in paths)
        for private_value in ("10.83.226.157", "nitrazepam", "lenovo-lan", r"D:\Code\sshelp"):
            self.assertNotIn(private_value, text)

    def test_generated_and_local_state_is_ignored(self) -> None:
        ignore = (ROOT / ".gitignore").read_text(encoding="utf-8")
        for value in ("/.local/", "**/.sshelp/", "**/.srd-tmp/", "__pycache__/"):
            self.assertIn(value, ignore)


if __name__ == "__main__":
    unittest.main()
