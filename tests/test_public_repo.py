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
            "sshelp/references/windows-ssh.md",
        ):
            self.assertTrue((ROOT / relative).is_file(), relative)

    def test_skill_examples_do_not_contain_local_machine_identity(self) -> None:
        paths = [
            ROOT / "sshelp" / "SKILL.md",
            ROOT / "sshelp" / "references" / "operations.md",
            ROOT / "sshelp" / "references" / "remote-files.md",
            ROOT / "sshelp" / "references" / "windows-ssh.md",
        ]
        text = "\n".join(path.read_text(encoding="utf-8") for path in paths)
        for private_value in ("10.83.226.157", "nitrazepam", "lenovo-lan", r"D:\Code\sshelp"):
            self.assertNotIn(private_value, text)

    def test_windows_ssh_guidance_preserves_platform_and_security_boundaries(self) -> None:
        text = (ROOT / "sshelp" / "references" / "windows-ssh.md").read_text(encoding="utf-8")
        for required in (
            "HostKeyAlias",
            "administrators_authorized_keys",
            "Missing file specification after redirection operator",
            "subprocess.communicate()",
            "SSHelp runtime commands are not Windows-remote compatible",
        ):
            self.assertIn(required, text)
        self.assertNotIn("StrictHostKeyChecking no", text)

    def test_generated_and_local_state_is_ignored(self) -> None:
        ignore = (ROOT / ".gitignore").read_text(encoding="utf-8")
        for value in ("/.local/", "**/.sshelp/", "**/.srd-tmp/", "__pycache__/"):
            self.assertIn(value, ignore)


if __name__ == "__main__":
    unittest.main()
