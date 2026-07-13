from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


SCRIPTS = Path(__file__).resolve().parents[1] / "sshelp" / "scripts"
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(SCRIPTS / "_compat"))

import _remote_files_common as common
import file_commit
import file_diff


def manifest(checkout_id: str, base_hash: str) -> dict[str, object]:
    return {
        "schema_version": 1,
        "state": "ready",
        "checkout_id": checkout_id,
        "host": "lab-server",
        "remote_root": "/home/user/project",
        "ssh": {
            "ssh_bin": "ssh",
            "sftp_bin": "sftp",
            "config": None,
            "known_hosts": None,
            "identity_file": None,
            "connect_timeout": 8,
        },
        "files": [
            {
                "relative_path": "src/main.py",
                "remote_absolute_path": "/home/user/project/src/main.py",
                "base_sha256": base_hash,
                "size": 12,
                "mode": "0644",
                "mtime_ns": 1,
            }
        ],
    }


class PathSafetyTests(unittest.TestCase):
    def test_relative_paths_are_strict(self) -> None:
        self.assertEqual(common.validate_relative_path("src/main.py"), "src/main.py")
        for value in ("../main.py", "/etc/passwd", r"src\main.py", ".env", "secret.pem", "bad:name.py"):
            with self.subTest(value=value), self.assertRaises(common.SkillError):
                common.validate_relative_path(value)

    def test_checkout_id_cannot_select_an_arbitrary_directory(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            with self.assertRaises(common.SkillError):
                common.checkout_directory(Path(temporary), "../other")


class LocalTransactionTests(unittest.TestCase):
    def test_default_checkout_lives_under_the_current_project(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            previous = Path.cwd()
            try:
                os.chdir(temporary)
                with mock.patch.dict(
                    os.environ,
                    {"SSHELP_WORK_ROOT": "", "SSHELP_CHECKOUT_ROOT": "", "SSH_RESEARCH_CHECKOUT_ROOT": ""},
                    clear=False,
                ):
                    self.assertEqual(common.default_checkout_root(), Path(temporary) / ".sshelp" / "checkouts")
            finally:
                os.chdir(previous)

    @mock.patch("_remote_files_common.os.name", "nt")
    def test_windows_checkout_inherits_the_workspace_acl(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            checkout_id, directory = common.create_checkout_directory(Path(temporary))
            self.assertTrue(common.CHECKOUT_ID_RE.fullmatch(checkout_id))
            marker = directory / "work" / "editable.txt"
            marker.write_text("editable", encoding="utf-8")
            self.assertEqual(marker.read_text(encoding="utf-8"), "editable")

    def test_status_detects_modified_added_and_deleted_files(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            (directory / "base" / "src").mkdir(parents=True)
            (directory / "work" / "src").mkdir(parents=True)
            original = directory / "base" / "src" / "main.py"
            original.write_text("old\n", encoding="utf-8")
            base_hash = common.hash_file(original)
            (directory / "work" / "src" / "main.py").write_text("new\n", encoding="utf-8")
            (directory / "work" / "src" / "added.py").write_text("added\n", encoding="utf-8")
            values = common.classify_local_changes(directory, manifest("deadbeef", base_hash))
            states = {item["path"]: item["state"] for item in values}
            self.assertEqual(states["src/main.py"], "modified-local")
            self.assertEqual(states["src/added.py"], "added-local")

    @mock.patch("file_diff.parse_args")
    def test_diff_uses_the_immutable_base_copy(self, mocked_args: mock.Mock) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            checkout_id = "deadbeef"
            directory = root / checkout_id
            (directory / "base" / "src").mkdir(parents=True)
            (directory / "work" / "src").mkdir(parents=True)
            base = directory / "base" / "src" / "main.py"
            base.write_text("old\n", encoding="utf-8")
            (directory / "work" / "src" / "main.py").write_text("new\n", encoding="utf-8")
            common.write_manifest(directory, manifest(checkout_id, common.hash_file(base)))
            mocked_args.return_value = argparse.Namespace(checkout=checkout_id, checkout_root=root)
            result = file_diff.run()
            self.assertIn("-old", result["files"][0]["diff"])
            self.assertIn("+new", result["files"][0]["diff"])


class TransferTests(unittest.TestCase):
    @mock.patch("_remote_files_common.subprocess.run")
    def test_sftp_batches_files_without_a_local_shell(self, mocked_run: mock.Mock) -> None:
        mocked_run.return_value = subprocess.CompletedProcess([], 0, b"", b"")
        options = common.SSHOptions("ssh", None, None, 8, None)
        common.run_sftp_batch(options, "sftp", "lab-server", ['get "/a" "D:/a"', 'get "/b" "D:/b"'])
        self.assertIs(mocked_run.call_args.kwargs["shell"], False)
        self.assertEqual(mocked_run.call_args.args[0][-3:], ["-b", "-", "lab-server"])
        body = mocked_run.call_args.kwargs["input"].decode("utf-8")
        self.assertIn('get "/a"', body)
        self.assertIn('get "/b"', body)

    @mock.patch("file_commit.run_remote_helper")
    @mock.patch("file_commit.run_sftp_batch")
    @mock.patch("file_commit.parse_args")
    def test_commit_rechecks_then_uploads_a_same_directory_temp(
        self,
        mocked_args: mock.Mock,
        mocked_sftp: mock.Mock,
        mocked_remote: mock.Mock,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            checkout_id = "deadbeef"
            directory = root / checkout_id
            (directory / "base" / "src").mkdir(parents=True)
            (directory / "work" / "src").mkdir(parents=True)
            base = directory / "base" / "src" / "main.py"
            base.write_text("old\n", encoding="utf-8")
            base_hash = common.hash_file(base)
            work = directory / "work" / "src" / "main.py"
            work.write_text("new\n", encoding="utf-8")
            new_hash = common.hash_file(work)
            common.write_manifest(directory, manifest(checkout_id, base_hash))
            mocked_args.return_value = argparse.Namespace(checkout=checkout_id, checkout_root=root, new_file_mode="0644", keep_local=True)
            mocked_remote.side_effect = [
                {"files": [{"relative_path": "src/main.py", "state": "regular", "sha256": base_hash}]},
                {"committed": [{"path": "src/main.py", "old_sha256": base_hash, "new_sha256": new_hash, "kind": "modified"}]},
            ]
            result = file_commit.run()
            batch = mocked_sftp.call_args.args[3]
            self.assertIn("/src/.main.py.sshelp-deadbeef.tmp", batch[0])
            commit_payload = mocked_remote.call_args_list[1].args[3]
            self.assertEqual(commit_payload["files"][0]["base_sha256"], base_hash)
            self.assertEqual(result["committed"][0]["new_sha256"], new_hash)


if __name__ == "__main__":
    unittest.main()
