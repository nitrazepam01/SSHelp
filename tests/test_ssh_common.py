from __future__ import annotations

import contextlib
import io
import os
import subprocess
import sys
import unittest
from pathlib import Path
from unittest import mock


SCRIPTS = Path(__file__).resolve().parents[1] / "sshelp" / "scripts"
sys.path.insert(0, str(SCRIPTS))

import _ssh_common as common


class ValidationTests(unittest.TestCase):
    def test_job_id_is_strict(self) -> None:
        self.assertEqual(common.validate_job_id("exp-01_ok"), "exp-01_ok")
        for value in ("", "-bad", "../../bad", "bad job", "x" * 65):
            with self.subTest(value=value), self.assertRaises(common.SkillError):
                common.validate_job_id(value)

    def test_new_names_keep_legacy_session_compatibility(self) -> None:
        self.assertEqual(common.session_name("exp-01"), "sshelp-exp-01")
        self.assertEqual(common.legacy_session_name("exp-01"), "srd-exp-01")

    def test_sshelp_environment_names_take_precedence(self) -> None:
        with mock.patch.dict(
            os.environ,
            {
                "SSHELP_SSH_CONFIG": "new-config",
                "SSH_RESEARCH_CONFIG": "old-config",
                "SSHELP_IDENTITY_FILE": "new-key",
            },
            clear=True,
        ):
            parser = common.JsonArgumentParser(add_help=False)
            common.add_ssh_arguments(parser)
            args = parser.parse_args([])
        self.assertEqual(args.ssh_config, "new-config")
        self.assertEqual(args.identity_file, "new-key")

    def test_host_cannot_be_an_ssh_option(self) -> None:
        with self.assertRaises(common.SkillError):
            common.validate_host("-oProxyCommand=bad")

    def test_remote_cwd_must_be_absolute(self) -> None:
        with self.assertRaises(common.SkillError):
            common.validate_cwd("relative/path")


class CommandTests(unittest.TestCase):
    def setUp(self) -> None:
        self.options = common.SSHOptions(
            ssh_bin="ssh",
            config=r"C:\Users\test\.ssh\config",
            known_hosts=r"C:\Users\test\.ssh\known_hosts",
            connect_timeout=8,
            identity_file=r"C:\Users\test\.ssh\id_ed25519",
        )

    def test_ssh_command_is_an_argument_list(self) -> None:
        command = common.build_ssh_command(
            self.options,
            "lab-server",
            "tmux list-sessions",
            tty=True,
        )
        self.assertEqual(command[0], "ssh")
        self.assertIn("BatchMode=yes", command)
        self.assertIn("IdentitiesOnly=yes", command)
        self.assertIn("-tt", command)
        self.assertEqual(command[-2:], ["lab-server", "tmux list-sessions"])

    @mock.patch("_ssh_common.subprocess.run")
    def test_run_ssh_never_uses_a_local_shell(self, mocked_run: mock.Mock) -> None:
        mocked_run.return_value = subprocess.CompletedProcess([], 0, b"ok", b"")
        common.run_ssh(self.options, "lab-server", "true")
        self.assertIs(mocked_run.call_args.kwargs["shell"], False)


class TerminalTextTests(unittest.TestCase):
    def test_incomplete_utf8_is_not_consumed(self) -> None:
        encoded = "中".encode("utf-8")
        text, consumed = common.decode_utf8_prefix(encoded[:2])
        self.assertEqual(text, "")
        self.assertEqual(consumed, 0)

    def test_ansi_and_progress_overwrite_are_normalized(self) -> None:
        raw = "\x1b[31mProgress 10%\x1b[0m\rProgress 20%\nerror\n"
        self.assertEqual(common.normalize_terminal_text(raw), "Progress 20%\nerror\n")

    def test_pane_status(self) -> None:
        status = common.parse_pane_status("1|2|9|123|python3\n")
        self.assertEqual(status["state"], "exited")
        self.assertEqual(status["exit_code"], 2)
        self.assertEqual(status["signal"], 9)


class JsonContractTests(unittest.TestCase):
    def test_cli_failure_is_structured_json(self) -> None:
        stream = io.StringIO()

        def fail() -> None:
            raise common.SkillError("EXPECTED", "expected failure")

        with contextlib.redirect_stdout(stream):
            code = common.cli_main(fail)
        self.assertEqual(code, 1)
        self.assertIn('"code": "EXPECTED"', stream.getvalue())

    def test_argument_failure_uses_skill_error(self) -> None:
        parser = common.JsonArgumentParser()
        parser.add_argument("--required", required=True)
        with self.assertRaises(common.SkillError) as raised:
            parser.parse_args([])
        self.assertEqual(raised.exception.code, "INVALID_ARGUMENTS")

    def test_authentication_failure_is_classified(self) -> None:
        result = subprocess.CompletedProcess(
            [], 255, b"", b"Permission denied (publickey,password)."
        )
        error = common.ssh_failure(result, "REMOTE_FAILED", "remote failed")
        self.assertEqual(error.code, "AUTH_FAILED")


if __name__ == "__main__":
    unittest.main()
