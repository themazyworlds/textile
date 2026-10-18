"""
Unit tests for Textile CLI strand call argument parsing.
"""

import unittest
from unittest.mock import patch

from typer.testing import CliRunner

from textile.core.cli.quill import quill
from textile.core.orchestration.loom import loom


class TestCliExecution(unittest.TestCase):
    def setUp(self):
        loom._initialized = False
        loom.initialize()
        self.runner = CliRunner()

    def test_call_strand_positional_args(self):
        with patch.object(loom, "execute", return_value="ok"):
            result = self.runner.invoke(quill, ["call", "hyprland_focus_workspace", "8"])
            self.assertEqual(result.exit_code, 0)
            self.assertIn("ok", result.stdout)

    def test_call_strand_key_value_args(self):
        with patch.object(loom, "execute", return_value="ok"):
            result = self.runner.invoke(quill, ["call", "hyprland_focus_workspace", "workspace=2"])
            self.assertEqual(result.exit_code, 0)
            self.assertIn("ok", result.stdout)

    def test_call_strand_json_args(self):
        with patch.object(loom, "execute", return_value="ok"):
            result = self.runner.invoke(quill, ["call", "hyprland_focus_workspace", "--json", '{"workspace": "3"}'])
            self.assertEqual(result.exit_code, 0)
            self.assertIn("ok", result.stdout)

    def test_yarns_install_via_dulwich(self):
        from unittest.mock import MagicMock

        mock_repo = MagicMock()
        with patch("dulwich.porcelain.clone", return_value=mock_repo) as mock_clone:
            result = self.runner.invoke(quill, ["yarns", "install", "https://github.com/test/textile-yarn-dummy.git"])
            self.assertEqual(result.exit_code, 0)
            self.assertIn("Installed yarn", result.stdout)
            mock_clone.assert_called_once()
            mock_repo.close.assert_called_once()

    def test_yarns_install_dulwich_failure(self):
        with patch("dulwich.porcelain.clone", side_effect=RuntimeError("Dulwich network error")):
            result = self.runner.invoke(quill, ["yarns", "install", "https://github.com/test/textile-yarn-dummy.git"])
            self.assertEqual(result.exit_code, 0)
            self.assertIn("Error installing yarn", result.stdout)
            self.assertIn("Dulwich network error", result.stdout)


if __name__ == "__main__":
    unittest.main()
