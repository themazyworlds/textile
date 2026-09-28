import time
import unittest

from textile.core.shuttle import ShuttleEngine
from textile.core.tapestry import sensory_tapestry
from textile.core.warp import WarpEvent, warp


class TestShuttleEngine(unittest.TestCase):
    def setUp(self):
        self.engines: list[ShuttleEngine] = []
        # Reset tapestry slots
        sensory_tapestry.set_slot("shuttle.enabled", True)
        sensory_tapestry.set_slot("shuttle.quiet", False)
        sensory_tapestry.set_slot("shuttle.quiet_until", None)
        sensory_tapestry.set_slot("shuttle.curiosity_level", 0.0)
        sensory_tapestry.set_slot("shuttle.inner_monologue", [])
        sensory_tapestry.set_slot("shuttle.last_spark", None)

    def tearDown(self):
        for eng in self.engines:
            eng.close()

    def _create_engine(self, **kwargs) -> ShuttleEngine:
        eng = ShuttleEngine(**kwargs)
        eng.initialize()
        self.engines.append(eng)
        return eng

    def test_initialization_and_slots(self):
        engine = self._create_engine()
        self.assertTrue(engine.is_enabled())
        self.assertFalse(engine.is_quiet())
        self.assertEqual(engine.curiosity_level, 0.0)

    def test_flash_spark_on_critical_event(self):
        engine = self._create_engine(spark_threshold=0.8)

        sparks = []

        def _on_spark(data):
            sparks.append(data)

        cb = warp.subscribe(WarpEvent.SHUTTLE_SPARK, _on_spark)
        try:
            res = engine.feed_event(
                source="journal.coredump",
                event_type="crash",
                data={"process": "hyprland", "pid": 1234},
                urgency=1.0,
                summary="Process hyprland crashed with SIGSEGV",
            )
            self.assertIsNotNone(res)
            self.assertTrue(res["is_flash"])
            self.assertEqual(res["urgency"], 1.0)
            self.assertIn("Process hyprland crashed", res["reason"])
            self.assertEqual(len(sparks), 1)
            self.assertEqual(sparks[0]["source"], "journal.coredump")
        finally:
            warp.unsubscribe(WarpEvent.SHUTTLE_SPARK, cb)

    def test_tension_compounding_and_resonance_spark(self):
        engine = self._create_engine(spark_threshold=0.6)

        sparks = []

        def _on_spark(data):
            sparks.append(data)

        cb = warp.subscribe(WarpEvent.SHUTTLE_SPARK, _on_spark)
        try:
            # Event 1 (urgency 0.25) -> tension 0.25
            r1 = engine.feed_event(
                source="sensors.cpu",
                event_type="telemetry",
                data={"temp": 65},
                urgency=0.25,
                summary="CPU temperature rise",
            )
            self.assertIsNone(r1)
            self.assertEqual(len(sparks), 0)

            # Event 2 (urgency 0.25) -> tension 0.50
            r2 = engine.feed_event(
                source="sensors.cpu",
                event_type="telemetry",
                data={"temp": 70},
                urgency=0.25,
                summary="CPU temperature rise higher",
            )
            self.assertIsNone(r2)
            self.assertEqual(len(sparks), 0)

            # Event 3 (urgency 0.25) -> tension 0.75 >= threshold 0.6 -> Resonance spark!
            r3 = engine.feed_event(
                source="sensors.cpu",
                event_type="telemetry",
                data={"temp": 80},
                urgency=0.25,
                summary="CPU temperature reached 80C",
            )
            self.assertIsNotNone(r3)
            self.assertFalse(r3["is_flash"])
            self.assertGreaterEqual(r3["urgency"], 0.6)
            self.assertEqual(len(sparks), 1)
        finally:
            warp.unsubscribe(WarpEvent.SHUTTLE_SPARK, cb)

    def test_tension_decay_on_tick(self):
        engine = self._create_engine(decay_rate=0.1)

        engine.feed_event(
            source="test_source",
            event_type="test",
            data={},
            urgency=0.5,
        )
        state = engine.get_state()
        self.assertAlmostEqual(state["tension_map"].get("test_source", 0.0), 0.5, places=2)

        # Tick 2 seconds -> decay 0.2 -> tension becomes 0.3
        engine.tick(delta_seconds=2.0)
        state_after = engine.get_state()
        self.assertAlmostEqual(state_after["tension_map"].get("test_source", 0.0), 0.3, places=2)

        # Tick 4 seconds -> decay 0.4 -> drops below 0.01 -> removed
        engine.tick(delta_seconds=4.0)
        state_final = engine.get_state()
        self.assertNotIn("test_source", state_final["tension_map"])

    def test_curiosity_drift_on_idle(self):
        engine = self._create_engine(
            spark_threshold=0.5,
            curiosity_drift_rate=0.1,
            idle_timeout_seconds=5.0,
        )

        # Simulate last event was 10 seconds ago
        engine._last_event_time = time.time() - 10.0
        engine._last_spark_time = time.time() - 100.0

        # Tick 3 seconds -> curiosity drifts by 0.3
        res = engine.tick(delta_seconds=3.0)
        self.assertIsNone(res)  # curiosity at 0.3 < 0.5
        self.assertAlmostEqual(engine.curiosity_level, 0.3, places=2)

        # Tick 3 more seconds -> curiosity drifts to 0.6 >= 0.5 -> fires idle curiosity spark
        res_spark = engine.tick(delta_seconds=3.0)
        self.assertIsNotNone(res_spark)
        self.assertEqual(res_spark["source"], "idle_curiosity")
        self.assertIn("Curiosity drift peak", res_spark["reason"])

    def test_governor_quiet_mode_and_unmute(self):
        engine = self._create_engine()

        quiet_events = []

        def _on_quiet(data):
            quiet_events.append(data)

        cb = warp.subscribe(WarpEvent.SHUTTLE_QUIET_CHANGED, _on_quiet)
        try:
            # 1. Timed quiet mode
            msg = engine.set_quiet(duration_seconds=300)
            self.assertIn("5.0 minutes", msg)
            self.assertTrue(engine.is_quiet())
            self.assertEqual(len(quiet_events), 1)
            self.assertTrue(quiet_events[0]["quiet"])

            # 2. Normal resonance spark suppressed
            sparks = []

            def _on_spark(data):
                sparks.append(data)

            cb_spark = warp.subscribe(WarpEvent.SHUTTLE_SPARK, _on_spark)
            try:
                # Accumulate tension to threshold
                engine.feed_event(source="app.notice", event_type="notice", data={}, urgency=0.9)
                # Should not be published to Warp because quiet mode is active
                self.assertEqual(len(sparks), 0)

                # 3. Flash alert still fires even in quiet mode
                engine.feed_event(
                    source="system.kernel",
                    event_type="panic",
                    data={},
                    urgency=1.0,
                    summary="Kernel critical panic",
                )
                self.assertEqual(len(sparks), 1)
                self.assertTrue(sparks[0]["is_flash"])
            finally:
                warp.unsubscribe(WarpEvent.SHUTTLE_SPARK, cb_spark)

            # 4. Unmute
            unmute_msg = engine.unmute()
            self.assertIn("unmuted", unmute_msg)
            self.assertFalse(engine.is_quiet())
            self.assertEqual(len(quiet_events), 2)
            self.assertFalse(quiet_events[1]["quiet"])
        finally:
            warp.unsubscribe(WarpEvent.SHUTTLE_QUIET_CHANGED, cb)

    def test_quiet_mode_auto_expiration(self):
        engine = self._create_engine()

        # Set quiet mode for a past timestamp
        sensory_tapestry.set_slot("shuttle.quiet", False)
        sensory_tapestry.set_slot("shuttle.quiet_until", time.time() - 1.0)

        # Checking is_quiet should detect expiration and clear it
        self.assertFalse(engine.is_quiet())
        self.assertIsNone(sensory_tapestry.get_slot("shuttle.quiet_until"))

    def test_monologue_history_capping(self):
        engine = self._create_engine()

        for i in range(25):
            engine.feed_event(
                source=f"src_{i}",
                event_type="tick",
                data={},
                urgency=0.01,
                summary=f"Thought number {i}",
            )

        state = engine.get_state()
        self.assertEqual(len(state["inner_monologue"]), 20)
        self.assertIn("Thought number 24", state["inner_monologue"][-1])
        self.assertIn("Thought number 5", state["inner_monologue"][0])


if __name__ == "__main__":
    unittest.main()
