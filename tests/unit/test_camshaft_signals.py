"""
Unit tests for Textile Camshaft in-process Blinker signal bus.
Verifies decoupled signal dispatching, request helpers, and reactive events.
"""

import unittest

import blinker

from textile.core.camshaft import (
    camshaft,
    ensure_bootstrapped,
)
from textile.core.tapestry.intra import core_tapestry


class TestCamshaftSignals(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        ensure_bootstrapped()

    def test_request_list_strands_signal(self):
        strands = camshaft.get_all_strands()
        self.assertIsInstance(strands, list)
        self.assertGreater(len(strands), 0)
        strand_names = [s.name for s in strands]
        self.assertIn("textile_get_state", strand_names)

    def test_request_get_strand_signal(self):
        strand = camshaft.get_strand("textile_get_state")
        self.assertIsNotNone(strand)
        self.assertEqual(strand.name, "textile_get_state")

    def test_request_list_yarns_signal(self):
        yarns = camshaft.get_all_yarns()
        self.assertIsInstance(yarns, dict)
        self.assertIn("core", yarns)

    async def test_request_execute_strand_signal(self):
        result = await camshaft.execute_strand("textile_get_engine_state", {})
        self.assertIn("active_tasks", result)

    def test_reactive_yarn_toggle_signal(self):
        # Listen for reactive yarn_status_changed broadcast
        received_events = []

        def _on_yarn_changed(_sender, **kwargs):
            received_events.append(kwargs)

        camshaft.connect("yarn_status_changed", _on_yarn_changed, weak=False)
        target_yarn = "hyprland"
        try:
            # Toggle hyprland yarn
            orig_state = camshaft.is_yarn_enabled(target_yarn)
            state = camshaft.toggle_yarn(target_yarn)
            self.assertEqual(state, not orig_state)
            self.assertGreater(len(received_events), 0)
            self.assertEqual(received_events[-1].get("yarn_name"), target_yarn)
        finally:
            # Restore state
            if camshaft.is_yarn_enabled(target_yarn) != orig_state:
                camshaft.toggle_yarn(target_yarn)
            camshaft.disconnect("yarn_status_changed", _on_yarn_changed)

    def test_request_empty_signal_returns_none(self):
        dummy_signal = blinker.Signal("dummy:unregistered")
        result = camshaft.request(dummy_signal)
        self.assertIsNone(result)

    async def test_string_signal_dispatch(self):
        res = await camshaft.request_async("strand:execute_input", name="textile_get_engine_state", args={})
        self.assertIn("active_tasks", res)

    async def test_strand_execute_input_and_strand_executed_broadcast(self):
        executed_events = []

        def _on_executed(_sender, **kwargs):
            executed_events.append(kwargs)

        camshaft.connect("strand_executed", _on_executed, weak=False)
        try:
            res = await camshaft.execute_strand("textile_get_engine_state", {})
            self.assertIn("active_tasks", res)
            self.assertGreater(len(executed_events), 0)
            self.assertEqual(executed_events[-1].get("strand_name"), "textile_get_engine_state")
            self.assertTrue(executed_events[-1].get("success"))
        finally:
            camshaft.disconnect("strand_executed", _on_executed)

    def test_blackboard_slot_input_and_broadcast(self):
        slot_events = []

        def _on_slot_updated(_sender, **kwargs):
            slot_events.append(kwargs)

        camshaft.connect("blackboard_slot_updated", _on_slot_updated, weak=False)
        try:
            camshaft.set_blackboard_slot("test.reactive_slot", {"count": 42})
            val = camshaft.get_blackboard_slot("test.reactive_slot")
            self.assertEqual(val, {"count": 42})
            self.assertGreater(len(slot_events), 0)
            self.assertEqual(slot_events[-1].get("key"), "test.reactive_slot")
            self.assertEqual(slot_events[-1].get("value"), {"count": 42})
        finally:
            camshaft.disconnect("blackboard_slot_updated", _on_slot_updated)

    def test_telemetry_get_engine_state(self):
        state = camshaft.get_engine_state()
        self.assertIsInstance(state, dict)
        self.assertIn("active_tasks", state)
        self.assertIn("task_history", state)

    def test_telemetry_get_sensory_state(self):
        state = camshaft.get_sensory_state()
        self.assertIsInstance(state, dict)
        self.assertIn("slots", state)
        self.assertIn("recent_notices", state)

    def test_telemetry_blackboard_slots(self):
        camshaft.set_blackboard_slot("test.key", {"val": 123})
        res = camshaft.get_blackboard_slot("test.key")
        self.assertEqual(res, {"val": 123})
        self.assertIsNone(camshaft.get_blackboard_slot("nonexistent.key"))
        self.assertEqual(camshaft.get_blackboard_slot("nonexistent.key", default="fallback"), "fallback")

    def test_telemetry_cancel_nonexistent_task(self):
        msg = camshaft.cancel_task("nonexistent_task_id_999")
        self.assertIn("No active task matching", msg)

    async def test_telemetry_subscription_records_strand_execution(self):
        core_tapestry.clear()
        result = await camshaft.execute_strand("textile_get_engine_state", {})
        self.assertIn("active_tasks", result)

        history = camshaft.get_task_history()
        self.assertGreaterEqual(len(history), 1)
        latest_task = history[0]
        self.assertEqual(latest_task["strand_name"], "textile_get_engine_state")
        self.assertTrue(latest_task["success"])
        self.assertIsNotNone(latest_task["duration_ms"])

    def test_unified_camshaft_decorator_subscription(self):
        received_broadcasts = []

        @camshaft.on("strand_executed")
        def _handle_executed(_sender, **kwargs):
            received_broadcasts.append(kwargs)

        try:
            camshaft.emit("strand_executed", strand_name="unit.test", success=True)
            self.assertGreaterEqual(len(received_broadcasts), 1)
            self.assertEqual(received_broadcasts[-1].get("strand_name"), "unit.test")
            self.assertTrue(received_broadcasts[-1].get("success"))
        finally:
            camshaft.disconnect("strand_executed", _handle_executed)

    def test_unified_camshaft_signals_attribute_and_emit(self):
        received_custom = []

        @camshaft.on(camshaft.signals.stitch_notice)
        def _handle_notice(_sender, **kwargs):
            received_custom.append(kwargs)

        try:
            camshaft.emit("stitch_notice", level="INFO", source="test", message="Test notice emission")
            self.assertGreaterEqual(len(received_custom), 1)
            self.assertEqual(received_custom[-1].get("message"), "Test notice emission")
        finally:
            camshaft.disconnect(camshaft.signals.stitch_notice, _handle_notice)

    def test_unified_camshaft_connect_and_disconnect(self):
        calls = []

        def _listener(_sender, **kwargs):
            calls.append(kwargs)

        camshaft.connect("strand_executed", _listener)
        camshaft.emit("strand_executed", task_id="t1", strand_name="dummy", duration_ms=10.0, success=True)
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0]["task_id"], "t1")

        camshaft.disconnect("strand_executed", _listener)
        camshaft.emit("strand_executed", task_id="t2", strand_name="dummy", duration_ms=5.0, success=True)
        self.assertEqual(len(calls), 1)

    def test_security_mixin_camshaft_methods(self):
        policy = camshaft.get_tier_policy("mutate")
        self.assertTrue(policy.requires_2fa)
        self.assertTrue(policy.requires_sandbox)

        secret = camshaft.get_totp_secret()
        self.assertGreaterEqual(len(secret), 16)

        uri = camshaft.get_totp_uri(secret)
        self.assertIn("otpauth://totp/Textile", uri)

        # Observe tier passes without OTP
        ok, err = camshaft.check_security_policy("observe", "sensors_get_telemetry")
        self.assertTrue(ok)
        self.assertIsNone(err)

        # Clear TOTP state through camshaft
        camshaft.clear_totp()

    async def test_native_error_handling_without_exceptions(self):
        # Unknown strand returns Error notice without throwing exception
        res_not_found = await camshaft.execute_strand("non_existent_strand_xyz", {})
        self.assertTrue(res_not_found.startswith("Error:"))
        self.assertIn("non_existent_strand_xyz", res_not_found)

    def test_discovery_mixin_signals_and_methods(self):
        # Test search paths
        paths = camshaft.get_yarn_search_paths()
        self.assertIsInstance(paths, list)
        self.assertGreater(len(paths), 0)

        # Test reading strand index
        index = camshaft.read_strand_index()
        self.assertIsInstance(index, dict)

        # Test reading probe cache
        cache = camshaft.read_probe_cache()
        self.assertIsInstance(cache, dict)

        # Verify real domain signals are in camshaft.signals
        self.assertTrue(hasattr(camshaft.signals, "strand_execute_input"))
        self.assertTrue(hasattr(camshaft.signals, "strand_execution_started"))
        self.assertTrue(hasattr(camshaft.signals, "strand_executed"))
        self.assertTrue(hasattr(camshaft.signals, "yarn_toggle_input"))
        self.assertTrue(hasattr(camshaft.signals, "yarn_status_changed"))
        self.assertTrue(hasattr(camshaft.signals, "blackboard_slot_input"))
        self.assertTrue(hasattr(camshaft.signals, "blackboard_slot_updated"))
        self.assertTrue(hasattr(camshaft.signals, "stitch_notice"))


if __name__ == "__main__":
    unittest.main()
