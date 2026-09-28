import asyncio
import unittest

from textile.core.elastic import EventFrame, EventUrgency, ElasticEngine
from textile.core.tapestry import sensory_tapestry


class TestElasticEngine(unittest.TestCase):
    def setUp(self):
        self.elastic = ElasticEngine()

    def test_broadcast_and_exact_subscription(self):
        received = []

        def _cb(frame: EventFrame):
            received.append(frame)

        token = self.elastic.subscribe("system.heartbeat", _cb)
        try:
            # 1. Non-matching broadcast
            self.elastic.broadcast(
                topic="other.topic",
                summary="Ignored event",
                source="test",
            )
            self.assertEqual(len(received), 0)

            # 2. Matching broadcast
            frame = self.elastic.broadcast(
                topic="system.heartbeat",
                summary="Heartbeat pulse",
                source="test_node",
                urgency=EventUrgency.NOTICE,
                data={"cpu": 12.5},
            )
            self.assertEqual(len(received), 1)
            self.assertEqual(received[0].topic, "system.heartbeat")
            self.assertEqual(received[0].summary, "Heartbeat pulse")
            self.assertEqual(received[0].data["cpu"], 12.5)
            self.assertEqual(frame.id, received[0].id)
        finally:
            self.elastic.unsubscribe(token)

    def test_wildcard_pattern_subscription(self):
        received = []

        token = self.elastic.subscribe("timer.*", lambda f: received.append(f))
        try:
            self.elastic.broadcast("timer.started", "Timer started", "basics")
            self.elastic.broadcast("timer.expired", "Timer expired", "basics")
            self.elastic.broadcast("sensors.temp", "Temp normal", "sensors")

            self.assertEqual(len(received), 2)
            self.assertEqual(received[0].topic, "timer.started")
            self.assertEqual(received[1].topic, "timer.expired")
        finally:
            self.elastic.unsubscribe(token)

    def test_min_urgency_filtering(self):
        urgent_events = []

        token = self.elastic.subscribe(
            pattern="*",
            callback=lambda f: urgent_events.append(f),
            min_urgency=EventUrgency.ALERT,
        )
        try:
            # Low urgency (ambient & notice)
            self.elastic.broadcast("sys.info", "Low urgency info", urgency=EventUrgency.NOTICE)
            self.elastic.broadcast("sys.debug", "Ambient debug", urgency=EventUrgency.AMBIENT)
            self.assertEqual(len(urgent_events), 0)

            # High urgency (alert & flash)
            self.elastic.broadcast("sys.warning", "Alert warning", urgency=EventUrgency.ALERT)
            self.elastic.broadcast("sys.crash", "Flash emergency", urgency=EventUrgency.FLASH)

            self.assertEqual(len(urgent_events), 2)
            self.assertEqual(urgent_events[0].urgency, EventUrgency.ALERT)
            self.assertEqual(urgent_events[1].urgency, EventUrgency.FLASH)
        finally:
            self.elastic.unsubscribe(token)

    def test_retained_slot_and_tapestry_sync(self):
        self.elastic.broadcast(
            topic="test.slot_update",
            summary="State slot update",
            source="test_engine",
            retained_slot="test.custom_slot",
            retained_value={"active": True, "count": 42},
        )

        val = sensory_tapestry.get_slot("test.custom_slot")
        self.assertIsNotNone(val)
        self.assertTrue(val["active"])
        self.assertEqual(val["count"], 42)

    def test_async_event_stream(self):
        async def _test_stream():
            stream_gen = self.elastic.stream("stream.*")
            
            # Emit in background after starting stream
            async def _emitter():
                await asyncio.sleep(0.01)
                self.elastic.broadcast("stream.chunk_1", "Chunk 1")
                await asyncio.sleep(0.01)
                self.elastic.broadcast("stream.chunk_2", "Chunk 2")

            emit_task = asyncio.create_task(_emitter())
            frames = []
            
            async for f in stream_gen:
                frames.append(f)
                if len(frames) == 2:
                    break
            
            await emit_task
            self.assertEqual(len(frames), 2)
            self.assertEqual(frames[0].topic, "stream.chunk_1")
            self.assertEqual(frames[1].topic, "stream.chunk_2")

        asyncio.run(_test_stream())

    def test_cross_process_ipc_sync(self):
        import time

        # Create two simulated processes (engine_a and engine_b)
        engine_a = ElasticEngine(enable_ipc_poller=True)
        engine_a._pid = 11111  # Simulate Process A (e.g. Twill / Timer)

        engine_b = ElasticEngine(enable_ipc_poller=True)
        engine_b._pid = 22222  # Simulate Process B (e.g. Weave Voice Agent)

        received_by_b = []

        token = engine_b.subscribe("timer.expired", lambda f: received_by_b.append(f))
        try:
            # Engine A broadcasts a timer expiration
            engine_a.broadcast(
                topic="timer.expired",
                summary="Timer 'Tea' has finished (180s)",
                source="basics",
                urgency=EventUrgency.ALERT,
                data={"label": "Tea", "id": "tea_01"},
            )

            # Wait briefly for Engine B's background IPC thread to poll the event
            time.sleep(0.15)

            self.assertEqual(len(received_by_b), 1)
            self.assertEqual(received_by_b[0].topic, "timer.expired")
            self.assertEqual(received_by_b[0].data["label"], "Tea")
            self.assertEqual(received_by_b[0].data["id"], "tea_01")
        finally:
            engine_a.close()
            engine_b.close()


if __name__ == "__main__":
    unittest.main()
