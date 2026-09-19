import threading
import unittest

from textile.core.tapestry import CoreTapestry, NoticeLevel, SensoryTapestry


class TestTapestry(unittest.TestCase):
    def test_core_task_ledger(self):
        core = CoreTapestry()
        
        # Start task
        rec = core.record_task_start("t1", "sensors_get_cpu_freqs", {"sensor": "cpu0"})
        self.assertEqual(rec.task_id, "t1")
        self.assertEqual(rec.strand_name, "sensors_get_cpu_freqs")
        self.assertEqual(len(core.get_active_tasks()), 1)

        # End task
        core.record_task_end("t1", success=True, duration_ms=12.5)
        self.assertEqual(len(core.get_active_tasks()), 0)
        history = core.get_task_history()
        self.assertEqual(len(history), 1)
        self.assertEqual(history[0]["strand_name"], "sensors_get_cpu_freqs")
        self.assertEqual(history[0]["duration_ms"], 12.5)
        self.assertTrue(history[0]["success"])

    def test_task_cancellation(self):
        core = CoreTapestry()
        core.record_task_start("task-123", "long_running_process", {})
        self.assertEqual(len(core.get_active_tasks()), 1)

        res = core.cancel_task("long_running_process")
        self.assertIn("Successfully cancelled", res)
        self.assertEqual(len(core.get_active_tasks()), 0)

        # Non-existent
        res_none = core.cancel_task("non_existent")
        self.assertIn("No active task matching", res_none)

    def test_sensory_blackboard_stitch_and_slots(self):
        sensory = SensoryTapestry()
        
        # Test slots
        sensory.set_slot("compositor.active_window", {"title": "Neovim", "class": "foot"})
        self.assertEqual(sensory.get_slot("compositor.active_window")["title"], "Neovim")
        self.assertIsNone(sensory.get_slot("nonexistent"))

        # Test stitch with different levels
        sensory.stitch(NoticeLevel.INFO, "battery", "Battery charged to 100%")
        sensory.stitch("WARNING", "bluetooth", "Headphones disconnected", {"mac": "00:11:22:33:44:55"})
        sensory.stitch("CRITICAL", "sensors", "High RAM usage over 80%", {"ram_percent": 88.5})

        notices = sensory.get_notices()
        self.assertEqual(len(notices), 3)

        crit_notices = sensory.get_notices(level="CRITICAL")
        self.assertEqual(len(crit_notices), 1)
        self.assertEqual(crit_notices[0]["source"], "sensors")
        self.assertIn("High RAM usage", crit_notices[0]["message"])
        self.assertEqual(crit_notices[0]["data"]["ram_percent"], 88.5)

        # Snapshot
        snap = sensory.get_state()
        self.assertIn("slots", snap)
        self.assertIn("recent_notices", snap)

    def test_concurrent_stitch_and_slots(self):
        sensory = SensoryTapestry()
        errors = []

        def worker(idx: int):
            try:
                for i in range(50):
                    sensory.set_slot(f"worker_{idx}", i)
                    sensory.stitch("INFO", f"worker_{idx}", f"Step {i}")
                    _ = sensory.get_state()
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=worker, args=(idx,)) for idx in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        self.assertEqual(len(errors), 0, f"Concurrent Tapestry operations caused errors: {errors}")


if __name__ == "__main__":
    unittest.main()
