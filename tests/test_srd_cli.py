from __future__ import annotations

import argparse
import contextlib
import io
import subprocess
import sys
import unittest
from pathlib import Path
from unittest import mock


SCRIPTS = Path(__file__).resolve().parents[1] / "sshelp" / "scripts"
sys.path.insert(0, str(SCRIPTS))

import _diagnostics_common as diagnostics
import _remote_files_common as remote_files
import srd
import sshelp as cli


def ssh_args(**overrides: object) -> argparse.Namespace:
    values: dict[str, object] = {
        "host": "lab-server",
        "ssh_bin": "ssh",
        "ssh_config": None,
        "known_hosts": None,
        "identity_file": None,
        "connect_timeout": 8,
    }
    values.update(overrides)
    return argparse.Namespace(**values)


class EmbeddedHelperTests(unittest.TestCase):
    def test_remote_helpers_compile(self) -> None:
        compile(diagnostics.REMOTE_DIAGNOSTICS_HELPER, "diagnostics-helper", "exec")
        compile(remote_files.REMOTE_HELPER, "remote-files-helper", "exec")


class ExecTests(unittest.TestCase):
    @mock.patch("srd.subprocess.run")
    def test_short_command_uses_one_ssh_process_without_local_shell(self, mocked_run: mock.Mock) -> None:
        mocked_run.return_value = subprocess.CompletedProcess([], 0, b"main.py\n", b"")
        args = ssh_args(cwd="/home/user/project", timeout=30, max_output_bytes=1024 * 1024, command=["--", "git", "status", "--short"])
        result = cli.run_exec(args)
        self.assertEqual(result["exit_code"], 0)
        self.assertEqual(result["stdout"], "main.py\n")
        self.assertIs(mocked_run.call_args.kwargs["shell"], False)
        command = mocked_run.call_args.args[0]
        self.assertEqual(command[-2], "lab-server")
        self.assertIn("exec git status --short", command[-1])

    @mock.patch("srd.subprocess.run")
    def test_exec_quotes_awk_program_as_one_remote_argument(self, mocked_run: mock.Mock) -> None:
        mocked_run.return_value = subprocess.CompletedProcess([], 0, b"1 row\n", b"")
        program = "/^[0-9]/{print NR, $0}"
        args = ssh_args(
            cwd="/project",
            timeout=30,
            max_output_bytes=1024 * 1024,
            command=["--", "awk", program, "Instance/real_data/50_1.txt"],
        )
        cli.run_exec(args)
        self.assertIs(mocked_run.call_args.kwargs["shell"], False)
        remote = mocked_run.call_args.args[0][-1]
        self.assertEqual(
            remote,
            "cd -- /project && exec awk '/^[0-9]/{print NR, $0}' Instance/real_data/50_1.txt",
        )

    @mock.patch("srd.subprocess.run")
    def test_nonzero_remote_exit_is_a_normal_result(self, mocked_run: mock.Mock) -> None:
        mocked_run.return_value = subprocess.CompletedProcess([], 2, b"", b"bad option\n")
        args = ssh_args(cwd="/tmp", timeout=30, max_output_bytes=1024 * 1024, command=["false"])
        result = cli.run_exec(args)
        self.assertEqual(result["exit_code"], 2)
        self.assertEqual(result["stderr"], "bad option\n")


class HostInstallTests(unittest.TestCase):
    def test_install_requires_explicit_confirmation(self) -> None:
        args = ssh_args(yes=False, skip_ttyd=False, ttyd_version="1.7.7")
        with self.assertRaises(cli.SkillError) as raised:
            cli.run_host_install(args)
        self.assertEqual(raised.exception.code, "INSTALL_CONFIRMATION_REQUIRED")

    @mock.patch("sshelp.run_ssh")
    def test_install_uses_fixed_tools_and_pinned_official_ttyd(self, mocked_ssh: mock.Mock) -> None:
        mocked_ssh.return_value = subprocess.CompletedProcess(
            [],
            0,
            b"package_manager=apt\ntmux=tmux 3.4\npython=Python 3.12\nrg=ripgrep 14\nttyd_path=/home/u/.local/bin/ttyd\nttyd=ttyd 1.7.7\n",
            b"",
        )
        args = ssh_args(yes=True, skip_ttyd=False, ttyd_version="1.7.7")
        result = cli.run_host_install(args)
        remote = mocked_ssh.call_args.args[2]
        self.assertIn("sudo -n", remote)
        self.assertIn("tmux ripgrep python3", remote)
        self.assertIn("https://github.com/tsl0922/ttyd/releases/download/", remote)
        self.assertIn("$HOME/.local/bin/ttyd", remote)
        self.assertEqual(result["tools"]["ttyd_path"], "/home/u/.local/bin/ttyd")


class RemoteDiscoveryTests(unittest.TestCase):
    @mock.patch("sshelp.run_remote_helper")
    def test_find_supports_recent_file_filter(self, mocked_remote: mock.Mock) -> None:
        mocked_remote.return_value = {"remote_root_real": "/project", "results": [{"path": "a.py"}], "truncated": False}
        args = ssh_args(area="remote", remote_action="find", root="/project", max_results=20, name=None, glob=["*.py"], modified_within_seconds=3600)
        result = cli.run_remote(args)
        self.assertEqual(result["results"][0]["path"], "a.py")
        self.assertEqual(mocked_remote.call_args.args[2], "find")
        self.assertEqual(mocked_remote.call_args.args[3]["modified_within_seconds"], 3600)


class DiagnosticTests(unittest.TestCase):
    @mock.patch("sshelp.run_remote_diagnostics")
    def test_process_inspect_is_derived_from_job_id(self, mocked_remote: mock.Mock) -> None:
        mocked_remote.return_value = {"ok": True, "job": {"job_id": "train-1", "pid": 123}, "process_tree": []}
        args = ssh_args(area="process", process_action="inspect", job_id="train-1")
        result = cli.run_diagnostic(args)
        self.assertEqual(result["job"]["pid"], 123)
        self.assertEqual(mocked_remote.call_args.args[2], "process_inspect")
        self.assertEqual(mocked_remote.call_args.args[3], {"job_id": "train-1"})

    @mock.patch.object(sys, "argv", ["srd.py", "process", "inspect", "--host", "lab", "--pid", "123"])
    def test_process_inspect_does_not_accept_arbitrary_pid(self) -> None:
        with self.assertRaises(cli.SkillError):
            cli.parse_args()


class UnifiedEntryTests(unittest.TestCase):
    def test_help_lists_the_complete_command_tree(self) -> None:
        cases = [
            (["sshelp.py", "--help"], ("host", "web", "file", "job")),
            (["sshelp.py", "host", "--help"], ("test", "install")),
            (["sshelp.py", "job", "--help"], ("start", "read", "status", "diagnose")),
            (["sshelp.py", "file", "--help"], ("checkout", "status", "diff", "commit", "abort")),
        ]
        for argv, expected in cases:
            with self.subTest(argv=argv), mock.patch.object(sys, "argv", argv):
                output = io.StringIO()
                with contextlib.redirect_stdout(output), self.assertRaises(SystemExit) as raised:
                    cli.parse_args()
                self.assertEqual(raised.exception.code, 0)
                for value in expected:
                    self.assertIn(value, output.getvalue())

    @mock.patch("sshelp.subprocess.call", return_value=0)
    def test_proven_job_actions_are_hidden_behind_sshelp(self, mocked_call: mock.Mock) -> None:
        result = cli.run_legacy_action(["job", "status", "--host", "lab", "--job-id", "a"])
        self.assertEqual(result, 0)
        command = mocked_call.call_args.args[0]
        self.assertTrue(command[1].endswith(str(Path("_compat") / "job_status.py")))
        self.assertEqual(command[2:], ["--host", "lab", "--job-id", "a"])
        self.assertIn(str(SCRIPTS), mocked_call.call_args.kwargs["env"]["PYTHONPATH"])

    def test_unknown_action_stays_in_the_native_parser(self) -> None:
        self.assertIsNone(cli.run_legacy_action(["job", "diagnose"]))

    def test_srd_name_remains_a_compatibility_alias(self) -> None:
        self.assertIs(srd.run_exec, cli.run_exec)


if __name__ == "__main__":
    unittest.main()
