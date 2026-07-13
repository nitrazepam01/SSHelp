from __future__ import annotations

import argparse
import subprocess
import sys
import unittest
from pathlib import Path
from unittest import mock


SCRIPTS = Path(__file__).resolve().parents[1] / "sshelp" / "scripts"
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(SCRIPTS / "_compat"))

import job_attach
import job_read
import job_start
import job_status
import job_web_start


def base_args(**overrides: object) -> argparse.Namespace:
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


class JobStartTests(unittest.TestCase):
    @mock.patch("job_start.run_ssh")
    @mock.patch("job_start.parse_args")
    def test_start_builds_a_prefixed_tmux_task(
        self, mocked_args: mock.Mock, mocked_ssh: mock.Mock
    ) -> None:
        mocked_args.return_value = base_args(
            cwd="/home/user/project",
            job_id="test-job",
            command=["--", "python3", "-u", "train.py"],
        )
        mocked_ssh.return_value = subprocess.CompletedProcess([], 0, b"", b"")
        result = job_start.run()
        self.assertEqual(result["session"], "sshelp-test-job")
        remote_script = mocked_ssh.call_args.args[2]
        self.assertIn('session=sshelp-test-job', remote_script)
        self.assertIn('$HOME/.sshelp/jobs', remote_script)
        self.assertIn("set-window-option", remote_script)
        self.assertIn("remain-on-exit on", remote_script)
        self.assertIn("pipe-pane", remote_script)


class JobReadTests(unittest.TestCase):
    @mock.patch("job_read.run_ssh")
    @mock.patch("job_read.parse_args")
    def test_read_returns_new_offset_and_normalized_output(
        self, mocked_args: mock.Mock, mocked_ssh: mock.Mock
    ) -> None:
        mocked_args.return_value = base_args(
            job_id="test-job", offset=10, max_bytes=1024, raw_ansi=False
        )
        payload = "\x1b[32m训练\x1b[0m\r完成\n".encode("utf-8")
        mocked_ssh.return_value = subprocess.CompletedProcess(
            [], 0, b"SRD1 100 10 0\n" + payload, b""
        )
        result = job_read.run()
        self.assertEqual(result["new_offset"], 10 + len(payload))
        self.assertEqual(result["output"], "完成\n")


class JobStatusTests(unittest.TestCase):
    @mock.patch("job_status.run_ssh")
    @mock.patch("job_status.parse_args")
    def test_missing_session_is_a_state(self, mocked_args: mock.Mock, mocked_ssh: mock.Mock) -> None:
        mocked_args.return_value = base_args(job_id="test-job")
        mocked_ssh.return_value = subprocess.CompletedProcess([], 44, b"", b"")
        result = job_status.run()
        self.assertEqual(result["state"], "missing")


class ObserverTests(unittest.TestCase):
    @mock.patch("job_attach.subprocess.call")
    @mock.patch("job_attach.parse_args")
    def test_terminal_attach_is_read_only_by_default(
        self, mocked_args: mock.Mock, mocked_call: mock.Mock
    ) -> None:
        mocked_args.return_value = base_args(job_id="test-job", interactive=False)
        mocked_call.return_value = 0
        self.assertEqual(job_attach.main(), 0)
        command = mocked_call.call_args.args[0]
        self.assertIn("attach-session -r", command[-1])
        self.assertIs(mocked_call.call_args.kwargs["shell"], False)

    @mock.patch("job_web_start.run_ssh")
    @mock.patch("job_web_start.parse_args")
    def test_web_observer_is_loopback_and_read_only(
        self, mocked_args: mock.Mock, mocked_ssh: mock.Mock
    ) -> None:
        mocked_args.return_value = base_args(
            job_id="test-job", local_port=7681, remote_port=7682
        )
        mocked_ssh.return_value = subprocess.CompletedProcess([], 0, b"", b"")
        result = job_web_start.run()
        remote_script = mocked_ssh.call_args.args[2]
        self.assertIn("target=sshelp-test-job", remote_script)
        self.assertIn("srd-test-job", remote_script)
        self.assertIn("$ttyd_bin -i 127.0.0.1", remote_script)
        self.assertIn("env -u TMUX tmux attach-session -r", remote_script)
        self.assertIn("python3", remote_script)
        self.assertNotIn(" -W ", remote_script)
        self.assertIn("127.0.0.1:7681:127.0.0.1:7682", result["tunnel_argv"])
        self.assertEqual(result["browser_url"], "http://127.0.0.1:7681")


if __name__ == "__main__":
    unittest.main()
