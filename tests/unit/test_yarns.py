import os
import unittest
from typing import Literal

from pydantic import BaseModel, Field

from textile.core.base import Strand, Yarn, YarnManifest
from textile.core.loom import loom
from textile.core.skein import skein


class CustomPydanticModel(BaseModel):
    message: str = Field(..., description="Message string")
    priority: Literal["low", "high"] = Field("low", description="Priority")


class DummyYarn(Yarn):
    def __init__(self):
        super().__init__(manifest=YarnManifest(name="dummy", layer=50))

    def is_available(self) -> bool:
        return True

    def get_strands(self) -> list[Strand]:
        return [
            self.build_strand("normal_tool", "Normal tool", lambda args: "normal_ok"),
            self.build_strand("isolated_tool", "Isolated tool", lambda args: f"isolated_{args.get('x')}", isolated=True),
            self.build_strand("crashing_tool", "Crashing tool", lambda args: os._exit(11), isolated=True),
            self.build_strand(
                "typed_tool",
                "Typed tool",
                lambda args: "typed_ok",
                parameters={
                    "count": {"type": "integer", "description": "Count"},
                    "mode": {"type": "string", "enum": ["fast", "slow"], "description": "Mode"}
                },
                required=["count"]
            ),
            self.build_strand(
                "pydantic_tool",
                "Pydantic tool",
                lambda args: f"pydantic_{args.get('message')}_{args.get('priority')}",
                args_schema=CustomPydanticModel,
            )
        ]


class TestYarnArchitecture(unittest.TestCase):
    def setUp(self):
        loom._initialized = False
        loom.initialize()

    def test_yarns_loaded(self):
        self.assertGreater(len(loom.active_yarns), 0, "No active yarns loaded.")
        self.assertGreater(len(loom._strand_to_yarn), 0, "No strands registered.")

    def test_process_isolation_and_crash_recovery(self):
        dummy = DummyYarn()
        # 1. Normal strand execution
        self.assertEqual(dummy.execute_sync("normal_tool", {}), "normal_ok")

        # 2. Isolated process execution
        res = dummy.execute_sync("isolated_tool", {"x": "val"})
        self.assertEqual(res, "isolated_val")

        # 3. Crash recovery: child os._exit(11) must NOT crash host parent
        crash_res = dummy.execute_sync("crashing_tool", {})
        self.assertIn("crashed", crash_res)
        self.assertIn("Host process preserved", crash_res)

    def test_strict_parameter_validation(self):
        dummy = DummyYarn()

        # Missing required parameter 'count'
        missing_res = dummy.execute_sync("typed_tool", {})
        self.assertIn("Validation Hint", missing_res)
        self.assertIn("missing in action", missing_res)

        # Invalid enum choice
        enum_res = dummy.execute_sync("typed_tool", {"count": 5, "mode": "invalid_mode"})
        self.assertIn("Validation Hint", enum_res)
        self.assertIn("Available options", enum_res)

        # Successful typed call
        valid_res = dummy.execute_sync("typed_tool", {"count": 5, "mode": "fast"})
        self.assertEqual(valid_res, "typed_ok")

    def test_pydantic_schema_validation(self):
        dummy = DummyYarn()
        # Missing message
        res = dummy.execute_sync("pydantic_tool", {})
        self.assertIn("Validation Hint", res)
        self.assertIn("missing in action", res)

        # Invalid priority enum
        res2 = dummy.execute_sync("pydantic_tool", {"message": "hello", "priority": "invalid"})
        self.assertIn("Validation Hint", res2)
        self.assertIn("Available options", res2)

        # Valid call
        res3 = dummy.execute_sync("pydantic_tool", {"message": "hello", "priority": "high"})
        self.assertEqual(res3, "pydantic_hello_high")

        # Test MCP schema conversion
        p_strand = next(s for s in dummy.get_strands() if s.name == "pydantic_tool")
        mcp_def = p_strand.to_mcp_definition()
        self.assertIn("properties", mcp_def["inputSchema"])
        self.assertIn("message", mcp_def["inputSchema"]["properties"])

    def test_capability_based_overrides(self):
        class LowCapYarn(Yarn):
            def __init__(self):
                super().__init__(manifest=YarnManifest(name="low_cap_yarn", layer=10))

            def is_available(self): return True
            def get_strands(self):
                return [self.build_strand("low_app", "Low App", lambda args: "low_out", capability="test.launcher")]

        class HighCapYarn(Yarn):
            def __init__(self):
                super().__init__(manifest=YarnManifest(name="high_cap_yarn", layer=100))

            def is_available(self): return True
            def get_strands(self):
                return [self.build_strand("high_app", "High App", lambda args: "high_out", capability="test.launcher")]

        p_low = LowCapYarn()
        p_high = HighCapYarn()
        skein.register_yarn(p_low)
        skein.register_yarn(p_high)
        loom._rebuild_active()

        low_strand = p_low.get_strands()[0]
        high_strand = p_high.get_strands()[0]

        is_over, active_p, cap = loom.get_strand_override_status(low_strand, p_low)
        self.assertTrue(is_over)
        self.assertEqual(active_p, "high_cap_yarn")
        self.assertEqual(cap, "test.launcher")

        is_over_high, _active_p_high, _ = loom.get_strand_override_status(high_strand, p_high)
        self.assertFalse(is_over_high)

        # Execution of overridden low_app strand should route to high_cap_yarn
        res = loom.execute_sync("low_app", {})
        self.assertEqual(res, "high_out")

    def test_name_collision_without_capability_not_overridden(self):
        class YarnNoCapA(Yarn):
            def __init__(self):
                super().__init__(manifest=YarnManifest(name="nocap_a", layer=10))

            def is_available(self): return True
            def get_strands(self):
                return [self.build_strand("same_name", "Same Name A", lambda args: "a")]

        class YarnNoCapB(Yarn):
            def __init__(self):
                super().__init__(manifest=YarnManifest(name="nocap_b", layer=100))

            def is_available(self): return True
            def get_strands(self):
                return [self.build_strand("same_name", "Same Name B", lambda args: "b")]

        pa = YarnNoCapA()
        pb = YarnNoCapB()
        skein.register_yarn(pa)
        skein.register_yarn(pb)
        loom._rebuild_active()

        strand_a = pa.get_strands()[0]
        is_over_a, _, _ = loom.get_strand_override_status(strand_a, pa)
        self.assertFalse(is_over_a, "Strands without capability contracts must never be flagged as overridden.")

    def test_canvas_yarn_and_mood(self):
        from textile.yarns.canvas.canvas import Canvas
        canvas = Canvas()
        self.assertEqual(canvas.name, "canvas")
        self.assertEqual(canvas.layer, 100)
        strands = canvas.get_strands()
        strand_names = [s.name for s in strands]
        self.assertIn("canvas_launch", strand_names)
        self.assertIn("canvas_close", strand_names)
        self.assertIn("canvas_set_mood", strand_names)
        self.assertIn("canvas_set_expression", strand_names)
        self.assertIn("canvas_set_talking", strand_names)
        self.assertIn("canvas_set_listening", strand_names)
        self.assertIn("canvas_get_state", strand_names)

        # Test mood strand execution updates tapestry
        res = canvas.execute_sync("canvas_set_mood", {"mood": "excited"})
        self.assertIn("excited", res)
        st_raw = canvas.execute_sync("canvas_get_state", {})
        import json
        json.loads(st_raw) if isinstance(st_raw, str) else st_raw

    def test_capability_tiers_and_auto_isolation(self):
        from textile.core.base import strand

        class TierTestYarn(Yarn):
            def __init__(self):
                super().__init__(manifest=YarnManifest(name="tier_test", layer=50))

            def is_available(self): return True

            @strand(description="Read telemetry", tier="observe")
            def read_stat(self) -> str:
                return "stat_ok"

            @strand(description="Elevated command execution", tier="privileged")
            def admin_task(self) -> str:
                return "admin_ok"

            @strand(description="Custom command runner", tier="system_exec")
            def exec_task(self) -> str:
                return "exec_ok"

        yarn = TierTestYarn()
        strands = {s.name: s for s in yarn.get_strands()}

        self.assertEqual(strands["read_stat"].tier, "observe")
        self.assertFalse(strands["read_stat"].isolated)

        self.assertEqual(strands["admin_task"].tier, "privileged")
        self.assertTrue(strands["admin_task"].isolated)

        self.assertEqual(strands["exec_task"].tier, "system_exec")
        self.assertTrue(strands["exec_task"].isolated)

    def test_weft_attunements_and_pydantic_coercion(self):
        from textile.core.base import weft

        events_received = []

        class WeftTestYarn(Yarn):
            def __init__(self):
                super().__init__(manifest=YarnManifest(name="weft_test", layer=50))

            def is_available(self): return True

            @weft(pattern=r"<target:(?P<name>[a-zA-Z0-9_-]+),(?P<count>\d+)>")
            def on_target(self, name: str, count: int):
                events_received.append(("target", name, count))

            @weft(pattern=r"<coord:(-?\d+(?:\.\d+)?),(-?\d+(?:\.\d+)?)>")
            def on_coord(self, x: float, y: float):
                events_received.append(("coord", x, y))

        y = WeftTestYarn()
        wefts = y.get_wefts()
        self.assertEqual(len(wefts), 2)
        skein.register_yarn(y)
        loom._rebuild_active()

        # Process a stream containing both wefts
        raw_stream = "Tracking <target:alpha_1,42> in sector <coord:12.5,-8.75> immediately!"
        clean_stream = loom.process_stream(raw_stream)

        self.assertEqual(clean_stream, "Tracking  in sector  immediately!")
        self.assertEqual(len(events_received), 2)
        # Verify Pydantic coercion to int and float
        self.assertEqual(events_received[0], ("target", "alpha_1", 42))
        self.assertEqual(events_received[1], ("coord", 12.5, -8.75))

    def test_weave_mood_tag_parsing(self):
        import time

        from textile.core.loom import loom
        from textile.core.skein import skein
        from textile.core.tapestry import sensory_tapestry
        from textile.yarns.canvas.canvas import Canvas
        from textile.yarns.weave.weave import extract_and_apply_mood_tags

        canvas = Canvas()
        canvas.is_available = lambda: True
        skein.register_yarn(canvas)
        loom._rebuild_active()

        # Simulate Gemini returning speech text with inline semantic mood tags
        gemini_speech = "<mood:curious> Let me check that system log for you... <mood:thinking> analyzing now... <mood:happy> everything looks clean!"
        extract_and_apply_mood_tags(gemini_speech)
        time.sleep(0.1)

        # The final tag should be applied to canvas slot in tapestry
        self.assertEqual(sensory_tapestry.get_slot("canvas.mood"), "happy")

    def test_weave_streaming_transcription_node(self):
        import asyncio
        import time

        from textile.core.loom import loom
        from textile.core.skein import skein
        from textile.core.tapestry import sensory_tapestry
        from textile.yarns.canvas.canvas import Canvas
        from textile.yarns.weave.weave import WeaveAgent

        canvas = Canvas()
        canvas.is_available = lambda: True
        skein.register_yarn(canvas)
        loom._rebuild_active()

        agent = WeaveAgent(instructions="test instructions")

        async def _test():
            async def token_stream():
                yield "<mood:curious>"
                yield " What shall"
                yield " we investigate"
                yield " next?"

            output_tokens = []
            async for token in agent.transcription_node(token_stream(), None):
                output_tokens.append(token)

            return "".join(output_tokens)

        loop = asyncio.new_event_loop()
        clean_text = loop.run_until_complete(_test())
        loop.close()
        time.sleep(0.1)

        # Verify tag was intercepted and stripped from visible stream
        self.assertEqual(sensory_tapestry.get_slot("canvas.mood"), "curious")
        self.assertEqual(clean_text, " What shall we investigate next?")

    def test_packagekit_pure_dbus_yarn(self):
        from dbus_fast import Variant

        from textile.yarns.packagekit.packagekit import (
            PackageKit,
            parse_package_id,
            unwrap_variant,
        )

        pk = PackageKit()
        self.assertEqual(pk.name, "packagekit")
        self.assertEqual(pk.layer, 10)
        strands = [s.name for s in pk.get_strands()]
        self.assertIn("packagekit_search", strands)
        self.assertIn("packagekit_install", strands)
        self.assertIn("packagekit_remove", strands)
        self.assertIn("packagekit_get_details", strands)
        self.assertIn("packagekit_check_updates", strands)
        self.assertIn("packagekit_what_provides", strands)
        self.assertIn("packagekit_refresh_cache", strands)

        # Test package ID parser
        parsed = parse_package_id("neovim;0.12.5-1;x86_64;installed")
        self.assertEqual(parsed["name"], "neovim")
        self.assertEqual(parsed["version"], "0.12.5-1")
        self.assertEqual(parsed["arch"], "x86_64")
        self.assertEqual(parsed["repository"], "installed")

        # Test Variant unboxer
        v = Variant("s", "test_val")
        self.assertEqual(unwrap_variant(v), "test_val")
        d = {"key": Variant("i", 42), "nested": [Variant("s", "foo")]}
        unwrapped = unwrap_variant(d)
        self.assertEqual(unwrapped, {"key": 42, "nested": ["foo"]})

    def test_clipboard_yarn(self):
        from textile.yarns.clipboard.clipboard import Clipboard
        cb = Clipboard()
        self.assertEqual(cb.name, "clipboard")
        self.assertEqual(cb.layer, 50)
        strands = [s.name for s in cb.get_strands()]
        self.assertIn("clipboard_get", strands)
        self.assertIn("clipboard_set", strands)
        self.assertIn("clipboard_clear", strands)

        # Test live pyxclip clipboard set and get
        if cb.is_available():
            set_res = cb.execute_sync("clipboard_set", {"text": "Textile Pyxclip Test"})
            if "copied" in set_res:
                self.assertIn("copied", set_res)
                get_res = cb.execute_sync("clipboard_get", {})
                self.assertEqual(get_res, "Textile Pyxclip Test")

    def test_toml_manifest_pydantic_validation(self):
        import tempfile
        from pathlib import Path
        from textile.core.base import YarnManifest

        # Test valid TOML manifest
        with tempfile.NamedTemporaryFile("w", suffix=".toml", delete=False) as f:
            f.write('[yarn]\nname = "test_manifest"\nversion = "1.0.0"\nmanifest_version = 1\nlayer = 50\n')
            temp_path = Path(f.name)
        try:
            m = YarnManifest.from_toml(temp_path)
            self.assertEqual(m.name, "test_manifest")
            self.assertEqual(m.manifest_version, 1)
        finally:
            temp_path.unlink()

        # Test malformed TOML manifest (e.g. invalid layer type)
        with tempfile.NamedTemporaryFile("w", suffix=".toml", delete=False) as f:
            f.write('[yarn]\nname = "invalid"\nlayer = "invalid_int_string"\n')
            temp_path2 = Path(f.name)
        try:
            with self.assertRaises(ValueError) as ctx:
                YarnManifest.from_toml(temp_path2)
            self.assertIn("Validation Hint:", str(ctx.exception))
        finally:
            temp_path2.unlink()


if __name__ == "__main__":
    unittest.main()


