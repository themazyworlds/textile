"""
Unit tests for Textile CLI strand call argument parsing.
"""

import unittest

from typer.testing import CliRunner

from textile.core.cli.app import app
from textile.core.orchestration.loom import loom


class TestCliExecution(unittest.TestCase):
    def setUp(self):
        loom._initialized = False
        loom.initialize()
        self.runner = CliRunner()

    def test_call_strand_positional_args(self):
        # hyprland_focus_workspace takes parameter 'workspace' (str)
        # Passing positional argument '8' should map to workspace='8'
        result = self.runner.invoke(app, ["call", "hyprland_focus_workspace", "8"])
        self.assertEqual(result.exit_code, 0)
        self.assertIn("ok", result.stdout)

    def test_call_strand_key_value_args(self):
        result = self.runner.invoke(app, ["call", "hyprland_focus_workspace", "workspace=2"])
        self.assertEqual(result.exit_code, 0)
        self.assertIn("ok", result.stdout)

    def test_call_strand_json_args(self):
        result = self.runner.invoke(app, ["call", "hyprland_focus_workspace", "--json", '{"workspace": "3"}'])
        self.assertEqual(result.exit_code, 0)
        self.assertIn("ok", result.stdout)


if __name__ == "__main__":
    unittest.main()
