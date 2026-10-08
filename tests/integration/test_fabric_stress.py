"""
High-Throughput Concurrent Stress & Thread Safety Suite for Textile Fabric.
Tests parallel Weft stream parsing, concurrent Loom strand execution,
and high-frequency Elastic event broadcasting under heavy thread load.
"""

import threading
from unittest import TestCase

from textile.core.execution.decorators import strand, weft
from textile.core.execution.yarn import Yarn
from textile.core.orchestration.loom import loom
from textile.core.orchestration.skein import skein
from textile.core.orchestration.stream import stream_engine
from textile.core.telemetry.blackboard import sensory_tapestry
from textile.core.telemetry.elastic import EventUrgency, elastic


class StressYarn(Yarn):
    """Synthetic Yarn designed for high-concurrency stress testing."""

    def __init__(self, name: str = "stress_yarn", layer: int = 50):
        super().__init__(name=name, layer=layer)
        self.counter = 0
        self._lock = threading.Lock()

    @strand(tier="observe")
    def stress_increment(self, amount: int = 1) -> str:
        with self._lock:
            self.counter += amount
            val = self.counter
        sensory_tapestry.set_slot("stress.counter", val)
        return f"Counter: {val}"

    @strand(tier="observe")
    def stress_query_state(self) -> dict:
        with self._lock:
            val = self.counter
        return {"counter": val, "tapestry_slot": sensory_tapestry.get_slot("stress.counter", 0)}

    @weft(pattern=r"<stress_mood:\s*([a-zA-Z_-]+)\s*>")
    def on_stress_mood(self, mood: str) -> None:
        sensory_tapestry.set_slot("stress.mood", mood.lower())


class TestFabricStress(TestCase):
    """Integration stress tests validating thread safety and multi-process concurrency."""

    @classmethod
    def setUpClass(cls):
        cls.yarn = StressYarn()
        skein.register_yarn(cls.yarn)
        loom.initialize()

    def test_concurrent_weft_stream_processing(self):
        """Stress test parallel Weft regex stream parsing across 10 threads x 50 iterations."""
        moods = ["excited", "thinking", "happy", "focused", "calm", "alert"]
        errors = []

        def _worker(thread_id: int):
            try:
                for i in range(50):
                    m = moods[(thread_id * 50 + i) % len(moods)]
                    text = f"Thread-{thread_id} step-{i} <stress_mood:{m}> payload data..."
                    cleaned = stream_engine.process_stream(text, loom.wefts)
                    if "<stress_mood:" in cleaned:
                        errors.append(f"Failed to strip tag in thread {thread_id}: {cleaned}")
            except (RuntimeError, ValueError, TypeError, KeyError) as e:
                errors.append(f"Thread {thread_id} crashed: {e}")

        threads = [threading.Thread(target=_worker, args=(t,)) for t in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10.0)

        self.assertEqual(errors, [], f"Stress test errors encountered: {errors}")
        self.assertIn(sensory_tapestry.get_slot("stress.mood"), moods)

    def test_concurrent_elastic_broadcasting(self):
        """Stress test high-frequency parallel Elastic event broadcasts."""
        events_sent = 0
        lock = threading.Lock()
        errors = []

        def _publisher(pub_id: int):
            nonlocal events_sent
            try:
                for i in range(100):
                    elastic.broadcast(
                        topic=f"stress.test.{pub_id}",
                        source=f"pub_{pub_id}",
                        summary=f"Stress event {i} from pub {pub_id}",
                        urgency=EventUrgency.AMBIENT,
                        data={"pub_id": pub_id, "iteration": i},
                        retained_slot=f"stress.slot_{pub_id}",
                        retained_value=i,
                    )
                    with lock:
                        events_sent += 1
            except (RuntimeError, ValueError, TypeError, KeyError) as e:
                errors.append(f"Publisher {pub_id} crashed: {e}")

        threads = [threading.Thread(target=_publisher, args=(p,)) for p in range(8)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=15.0)

        self.assertEqual(errors, [])
        self.assertEqual(events_sent, 800)

    def test_concurrent_loom_strand_execution(self):
        """Stress test parallel synchronous & asynchronous Loom strand dispatching."""
        errors = []

        def _executor(exec_id: int):
            try:
                for _ in range(20):
                    res = loom.execute_sync("stress_increment", {"amount": 1})
                    if not res.startswith("Counter:"):
                        errors.append(f"Unexpected strand output in exec {exec_id}: {res}")
            except (RuntimeError, ValueError, TypeError, KeyError) as e:
                errors.append(f"Executor {exec_id} crashed: {e}")

        threads = [threading.Thread(target=_executor, args=(e,)) for e in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=15.0)

        self.assertEqual(errors, [])
        state = loom.execute_sync("stress_query_state", {})
        self.assertIn("counter", state)
