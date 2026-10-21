import asyncio
import unittest

from textile.core.tapestry.elastic import ElasticEngine, EventFrame, EventUrgency


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

        token = self.elastic.subscribe("timer.*", received.append)
        try:
            self.elastic.broadcast("timer.started", "Timer started", "timer")
            self.elastic.broadcast("timer.expired", "Timer expired", "timer")
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
            callback=urgent_events.append,
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

        val = self.elastic.get_slot("test.custom_slot")
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

    def test_multi_subscriber_isolation(self):
        received_a = []
        received_b = []

        token_a = self.elastic.subscribe("timer.started", received_a.append)
        token_b = self.elastic.subscribe("timer.*", received_b.append)
        try:
            self.elastic.broadcast("timer.started", "Timer started", "timer")
            self.assertEqual(len(received_a), 1)
            self.assertEqual(len(received_b), 1)

            self.elastic.broadcast("timer.expired", "Timer expired", "timer")
            self.assertEqual(len(received_a), 1)
            self.assertEqual(len(received_b), 2)
        finally:
            self.elastic.unsubscribe(token_a)
            self.elastic.unsubscribe(token_b)


if __name__ == "__main__":
    unittest.main()
