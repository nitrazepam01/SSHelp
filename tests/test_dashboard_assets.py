from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ASSET = ROOT / "sshelp" / "assets" / "dashboard.html"
OPEN_SCRIPT = ROOT / "sshelp" / "scripts" / "_compat" / "Open-MultiJobDashboard.ps1"
CLOSE_SCRIPT = ROOT / "sshelp" / "scripts" / "_compat" / "Close-MultiJobDashboard.ps1"
UNIFIED_SCRIPT = ROOT / "sshelp" / "scripts" / "SSHelp.ps1"
OPERATIONS_REFERENCE = ROOT / "sshelp" / "references" / "operations.md"


class DashboardAssetTests(unittest.TestCase):
    def test_template_is_local_and_dynamic(self) -> None:
        html = ASSET.read_text(encoding="utf-8")
        self.assertIn("__DASHBOARD_CONFIG__", html)
        self.assertIn("terminal-grid", html)
        self.assertIn("127.0.0.1:*", html)
        self.assertNotIn("https://", html)
        self.assertNotIn("linear-gradient", html)

    def test_scripts_bind_only_to_loopback(self) -> None:
        open_script = OPEN_SCRIPT.read_text(encoding="utf-8")
        close_script = CLOSE_SCRIPT.read_text(encoding="utf-8")
        self.assertIn('"--bind", "127.0.0.1"', open_script)
        self.assertIn("Open-JobWeb.ps1", open_script)
        self.assertIn("Close-JobWeb.ps1", close_script)
        self.assertNotIn("0.0.0.0", open_script)

    def test_ttyd_runbook_keeps_validated_safety_rules(self) -> None:
        runbook = OPERATIONS_REFERENCE.read_text(encoding="utf-8")
        self.assertIn("env -u TMUX", runbook)
        self.assertIn("Reconnecting...", runbook)
        self.assertIn("127.0.0.1", runbook)
        self.assertIn("dashboard-open", runbook)

    def test_unified_powershell_entry_exposes_all_observer_modes(self) -> None:
        script = UNIFIED_SCRIPT.read_text(encoding="utf-8")
        for action in ("terminal", "web-open", "web-close", "dashboard-open", "dashboard-close"):
            self.assertIn(action, script)
        self.assertIn("Open-MultiJobDashboard.ps1", script)
        self.assertIn("SSHELP_WORK_ROOT", script)
        self.assertIn('Join-Path (Get-Location) ".sshelp"', script)


if __name__ == "__main__":
    unittest.main()
