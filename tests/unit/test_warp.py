import unittest
from textile.core.warp import WarpEvent, warp


class TestWarp(unittest.TestCase):
    def test_pub_sub(self):
        received = []
        def _cb(data=None):
            received.append(data)

        warp.subscribe(WarpEvent.USER_INPUT_PROMPT, _cb)
        warp.publish(WarpEvent.USER_INPUT_PROMPT, "test_payload")
        self.assertEqual(len(received), 1)
        self.assertEqual(received[0], "test_payload")


if __name__ == "__main__":
    unittest.main()
