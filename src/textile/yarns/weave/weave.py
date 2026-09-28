"""
Weave - Voice & Perception Agent Subsystem powered by LiveKit Agents & Gemini 3 Live API.
Provides seamless real-time full-duplex voice companion bound to the Textile intelligence fabric.
"""

import asyncio
import contextlib
import json
import logging
import os
import re
import shutil
import sys
from collections.abc import AsyncGenerator, AsyncIterable
from pathlib import Path
from typing import Any

from livekit.agents import AgentServer, AutoSubscribe, JobContext, cli, mcp
from livekit.agents.voice import Agent, AgentSession
from livekit.plugins import google

from textile.core.elastic import EventFrame, EventUrgency, elastic
from textile.core.loom import loom
from textile.core.shuttle import shuttle

logger = logging.getLogger(__name__)

_basic_hyphenator: Any = None
with contextlib.suppress(Exception):
    from livekit.agents.tokenize import _basic_hyphenator

server = AgentServer()

MOOD_TAG_REGEX = re.compile(r"<mood:([a-zA-Z_-]+)>", re.IGNORECASE)


def extract_and_apply_mood_tags(content: str) -> None:
    """Extract and process semantic attunements from speech text using Loom Wefts."""
    if not content or not isinstance(content, str):
        return
    loom.process_stream(content)


class WeaveAgent(Agent):
    """Weave Voice Companion Agent with real-time streaming semantic token interception via Loom Wefts."""

    async def transcription_node(
        self, text: AsyncIterable[str | Any], model_settings: Any
    ) -> AsyncGenerator[str | Any, None]:
        buffer = ""
        async for delta in text:
            delta_text = getattr(delta, "text", None) or (delta if isinstance(delta, str) else str(delta))
            buffer += delta_text

            # Execute matching wefts and strip matched tags from buffer
            buffer = loom.process_stream(buffer)

            # Clean the current delta chunk
            clean_delta = loom.process_stream(delta_text)
            if clean_delta:
                if hasattr(delta, "text"):
                    setattr(delta, "text", clean_delta)
                    yield delta
                else:
                    yield clean_delta


@server.rtc_session(agent_name="weave")
async def entrypoint(ctx: JobContext):
    # Enrich log context with room identity
    ctx.log_context_fields = {"room": ctx.room.name}
    # main_loop = asyncio.get_running_loop()

    # Prewarm Loom, Shuttle proactivity, and tokenizers off the event loop before connecting audio session
    # loom.initialize()
    # shuttle.initialize()
    if _basic_hyphenator is not None:
        with contextlib.suppress(Exception):
            await asyncio.to_thread(_basic_hyphenator._get_hyphenator)

    await ctx.connect(auto_subscribe=AutoSubscribe.AUDIO_ONLY)

    model_name = os.getenv("TEXTILE_LIVE_MODEL", os.getenv("WEAVE_LIVE_MODEL", "gemini-3.8-live"))
    voice_name = os.getenv("TEXTILE_VOICE", os.getenv("WEAVE_VOICE", "Puck"))

    # LiveKit Google plugin automatically resolves GOOGLE_API_KEY from environment
    realtime_model = google.realtime.RealtimeModel(
        model=model_name,
        voice=voice_name,
    )

    # textile_env = dict(os.environ)
    # textile_env["TEXTILE_CALLER"] = "weave"

    # textile_cmd = shutil.which("textile") or sys.executable
    # textile_args = ["twill"] if shutil.which("textile") else ["-m", "textile.core.cli", "twill"]

    # textile_toolset = mcp.MCPToolset(
    #     id="textile",
    #     mcp_server=mcp.MCPServerStdio(
    #         command=textile_cmd,
    #         args=textile_args,
    #         env=textile_env,
    #         client_session_timeout_seconds=60.0,
    #     ),
    # )

    session = AgentSession(
        llm=realtime_model,
        turn_detection="realtime_llm",
    )

    # Event handlers connecting LiveKit voice stream to Textile Canvas UI asynchronously via Elastic
    # @session.on("agent_state_changed")
    # def on_agent_state_changed(ev):
    #     state = getattr(ev, "new_state", None)
    #     if state == "speaking":
    #         elastic.broadcast(
    #             topic="voice.state",
    #             source="weave",
    #             summary="Agent speaking",
    #             urgency=EventUrgency.NOTICE,
    #             data={"talking": True, "listening": False},
    #             retained_slot="canvas.is_talking",
    #             retained_value=True,
    #         )
    #     elif state == "thinking":
    #         elastic.broadcast(
    #             topic="voice.state",
    #             source="weave",
    #             summary="Agent thinking",
    #             urgency=EventUrgency.NOTICE,
    #             data={"talking": False},
    #             retained_slot="canvas.is_talking",
    #             retained_value=False,
    #         )
    #     elif state == "listening":
    #         elastic.broadcast(
    #             topic="voice.state",
    #             source="weave",
    #             summary="Agent listening",
    #             urgency=EventUrgency.NOTICE,
    #             data={"listening": True, "talking": False},
    #             retained_slot="canvas.is_listening",
    #             retained_value=True,
    #         )
    #     elif state in ("idle", "initializing", None):
    #         elastic.broadcast(
    #             topic="voice.state",
    #             source="weave",
    #             summary="Agent idle",
    #             urgency=EventUrgency.NOTICE,
    #             data={"talking": False},
    #             retained_slot="canvas.is_talking",
    #             retained_value=False,
    #         )

    # @session.on("user_state_changed")
    # def on_user_state_changed(ev):
    #     state = getattr(ev, "new_state", None)
    #     if state == "speaking":
    #         elastic.broadcast(
    #             topic="voice.state",
    #             source="weave",
    #             summary="User speaking",
    #             urgency=EventUrgency.NOTICE,
    #             data={"listening": True, "talking": False},
    #             retained_slot="canvas.is_listening",
    #             retained_value=True,
    #         )

    # @session.on("conversation_item_added")
    # def on_conversation_item_added(ev):
    #     item = getattr(ev, "item", None)
    #     if item is not None:
    #         content = getattr(item, "content", None)
    #         if isinstance(content, str):
    #             extract_and_apply_mood_tags(content)
    #         elif isinstance(content, list):
    #             for part in content:
    #                 text_val = getattr(part, "text", None) or (part if isinstance(part, str) else "")
    #                 extract_and_apply_mood_tags(text_val)

    # def on_elastic_event(frame: EventFrame) -> None:
    #     # Ignore ambient events and self-emitted voice events to prevent loops
    #     if frame.urgency == EventUrgency.AMBIENT or frame.source in ("weave", "voice"):
    #         return
    #
    #     is_timer_expired = frame.topic == "timer.expired"
    #     is_flash = frame.urgency == EventUrgency.FLASH
    #     is_spark = frame.topic == "shuttle.spark"
    #     is_alert = frame.urgency == EventUrgency.ALERT
    #
    #     # Only speak spontaneously on timer expirations, proactive sparks, alerts, or flash emergencies
    #     if not (is_timer_expired or is_spark or is_alert or is_flash):
    #         return
    #
    #     # Quiet mode suppresses idle curiosity sparks, but intentional timers and flash alerts always speak
    #     if shuttle.is_quiet() and not (is_flash or is_timer_expired):
    #         return
    #
    #     if is_spark:
    #         summary = frame.summary or frame.data.get("reason", "Desktop event")
    #         raw_ctx = frame.data.get("raw_data", {})
    #     else:
    #         summary = frame.summary
    #         raw_ctx = frame.data
    #
    #     prompt_text = f"[System Alert: {summary}]"
    #     instruction_text = (
    #         f"You are speaking spontaneously to the user based on real-time desktop intelligence. "
    #         f"Event: '{summary}'. Context: {json.dumps(raw_ctx) if isinstance(raw_ctx, (dict, list)) else raw_ctx}. "
    #         f"{'This is a critical flash emergency—be immediate, clear, and direct.' if is_flash else 'Announce this naturally, succinctly, and helpfully in 1-2 spoken sentences.'}"
    #     )
    #
    #     def _trigger_reply():
    #         # If user or agent is actively speaking, avoid turn collision on non-critical events
    #         if getattr(session, "user_state", None) == "speaking" or getattr(session, "agent_state", None) == "speaking":
    #             if not is_flash:
    #                 logger.debug("Suppressing spontaneous reply while voice turn is active")
    #                 return
    #         try:
    #             session.generate_reply(
    #                 user_input=prompt_text,
    #                 instructions=instruction_text,
    #             )
    #         except Exception as e:
    #             logger.warning("Spontaneous reply skipped or postponed: %s", e)
    #
    #     # Safely schedule on the LiveKit main asyncio loop from any thread
    #     main_loop.call_soon_threadsafe(_trigger_reply)
    #
    # elastic_token = elastic.subscribe("*", on_elastic_event)

    base_persona = "You are a helpful voice assistant. Keep answers brief and conversational."

    agent = Agent(
        instructions=base_persona,
    )

    await session.start(room=ctx.room, agent=agent)
    await session.generate_reply(
        instructions="Say a brief, confident hello."
    )


def run_voice_agent(
    mode: str = "console",
    model: str = "gemini-3.8-live",
    voice: str = "Puck",
    text_mode: bool = False,
):
    """Entry point to run Weave Voice Agent using LiveKit CLI (lk)."""
    os.environ["TEXTILE_LIVE_MODEL"] = model
    os.environ["TEXTILE_VOICE"] = voice
    os.environ["WEAVE_LIVE_MODEL"] = model
    os.environ["WEAVE_VOICE"] = voice

    if mode == "start":
        sys.argv = ["textile-weave", "start"]
        cli.run_app(server)
        return

    script_path = str(Path(__file__).resolve())
    lk_bin = shutil.which("lk")

    if not lk_bin:
        raise RuntimeError(
            "LiveKit CLI ('lk') is required to run Weave in interactive console/dev mode.\n"
            "Install it via:\n"
            "  curl -sSL https://get.livekit.io/cli | bash\n"
            "Then authenticate with your LiveKit Cloud project:\n"
            "  lk cloud auth\n"
        )

    if mode == "console":
        cmd = [lk_bin, "agent", "console", script_path]
        if text_mode:
            cmd.append("--text")
        os.execvpe(lk_bin, cmd, os.environ)
    elif mode == "dev":
        cmd = [lk_bin, "agent", "dev", script_path]
        os.execvpe(lk_bin, cmd, os.environ)


if __name__ == "__main__":
    cli.run_app(server)
