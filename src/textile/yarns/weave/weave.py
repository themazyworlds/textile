"""
Weave - Voice & Perception Agent Subsystem powered by LiveKit Agents & Gemini 3 Live API.
Provides seamless real-time full-duplex voice companion bound to the Textile intelligence fabric.
"""

import asyncio
import contextlib
import json
import logging
import os
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


def extract_and_apply_mood_tags(content: str) -> None:
    """Extract and process semantic attunements from speech text using Loom Wefts."""
    if not content or not isinstance(content, str):
        return
    loom.process_stream(content)


class WeaveAgent(Agent):
    """Voice companion agent with real-time streaming semantic token interception via Loom Wefts."""

    async def transcription_node(
        self, text: AsyncIterable[str | Any], model_settings: Any
    ) -> AsyncGenerator[str | Any, None]:
        async for delta in text:
            delta_text = getattr(delta, "text", None) or (delta if isinstance(delta, str) else str(delta))
            clean_delta = loom.process_stream(delta_text)
            if clean_delta:
                if hasattr(delta, "text"):
                    setattr(delta, "text", clean_delta)
                    yield delta
                else:
                    yield clean_delta


@server.rtc_session(agent_name="weave")
async def entrypoint(ctx: JobContext):
    ctx.log_context_fields = {"room": ctx.room.name}
    main_loop = asyncio.get_running_loop()

    # Prewarm Loom, Shuttle, and tokenizers
    loom.initialize()
    shuttle.initialize()
    if _basic_hyphenator is not None:
        with contextlib.suppress(Exception):
            await asyncio.to_thread(_basic_hyphenator._get_hyphenator)

    await ctx.connect(auto_subscribe=AutoSubscribe.AUDIO_ONLY)

    model_name = os.getenv("TEXTILE_LIVE_MODEL", os.getenv("WEAVE_LIVE_MODEL", "gemini-3.8-live"))
    voice_name = os.getenv("TEXTILE_VOICE", os.getenv("WEAVE_VOICE", "Puck"))

    realtime_model = google.realtime.RealtimeModel(
        model=model_name,
        voice=voice_name,
    )

    # MCP Toolset connecting Weave to Twill / Loom Strands
    textile_env = dict(os.environ)
    textile_env["TEXTILE_CALLER"] = "weave"
    textile_cmd = shutil.which("textile") or sys.executable
    textile_args = ["twill"] if shutil.which("textile") else ["-m", "textile.core.cli", "twill"]

    textile_toolset = mcp.MCPToolset(
        id="textile",
        mcp_server=mcp.MCPServerStdio(
            command=textile_cmd,
            args=textile_args,
            env=textile_env,
            client_session_timeout_seconds=60.0,
        ),
    )

    session = AgentSession(
        llm=realtime_model,
        turn_detection="realtime_llm",
    )

    # Broadcast voice speaking/listening states to Canvas UI via Elastic
    @session.on("agent_state_changed")
    def on_agent_state_changed(ev):
        state = getattr(ev, "new_state", None)
        talking = state == "speaking"
        listening = state == "listening"
        elastic.broadcast(
            topic="voice.state",
            source="weave",
            summary=f"Agent {state}",
            urgency=EventUrgency.AMBIENT,
            data={"talking": talking, "listening": listening},
            retained_slot="canvas.is_talking",
            retained_value=talking,
        )

    @session.on("user_state_changed")
    def on_user_state_changed(ev):
        state = getattr(ev, "new_state", None)
        if state == "speaking":
            elastic.broadcast(
                topic="voice.state",
                source="weave",
                summary="User speaking",
                urgency=EventUrgency.AMBIENT,
                data={"listening": True, "talking": False},
                retained_slot="canvas.is_listening",
                retained_value=True,
            )

    # Fallback weft token extraction from whole conversation messages
    @session.on("conversation_item_added")
    def on_conversation_item_added(ev):
        item = getattr(ev, "item", None)
        if item is not None:
            content = getattr(item, "content", None)
            if isinstance(content, str):
                loom.process_stream(content)
            elif isinstance(content, list):
                for part in content:
                    txt = getattr(part, "text", None) or (part if isinstance(part, str) else "")
                    if txt:
                        loom.process_stream(txt)

    # Spontaneous speech listener for system timers, alerts, and proactive sparks
    def on_elastic_event(frame: EventFrame) -> None:
        if frame.urgency == EventUrgency.AMBIENT or frame.source == "weave":
            return

        is_timer = frame.topic == "timer.expired"
        is_spark = frame.topic == "shuttle.spark"
        is_flash = frame.urgency == EventUrgency.FLASH
        is_alert = frame.urgency == EventUrgency.ALERT

        if not (is_timer or is_spark or is_alert or is_flash):
            return

        if shuttle.is_quiet() and not (is_flash or is_timer):
            return

        summary = frame.summary or "System notification"
        ctx_data = frame.data

        prompt_text = f"[System Alert: {summary}]"
        instruction_text = (
            f"Announce this desktop event succinctly in 1-2 spoken sentences: '{summary}'. "
            f"Context: {json.dumps(ctx_data) if isinstance(ctx_data, (dict, list)) else ctx_data}."
        )

        def _trigger_reply():
            user_state = getattr(session, "user_state", None)
            agent_state = getattr(session, "agent_state", None)
            if user_state == "speaking" or agent_state in ("speaking", "thinking"):
                if not is_flash:
                    logger.debug("Suppressing spontaneous reply during active voice turn (agent: %s, user: %s)", agent_state, user_state)
                    return
            try:
                session.generate_reply(
                    user_input=prompt_text,
                    instructions=instruction_text,
                )
            except Exception as e:
                logger.warning("Spontaneous reply postponed: %s", e)

        main_loop.call_soon_threadsafe(_trigger_reply)

    elastic.subscribe("*", on_elastic_event)

    instructions = (
        "You are Weave, a sovereign Linux desktop companion powered by the Textile intelligence fabric.\n"
        "Execute available strands immediately and succinctly report results back in natural spoken voice.\n"
        "Keep responses brief, conversational, and helpful.\n\n"
        f"{loom.get_fabric_instructions()}"
    )

    agent = WeaveAgent(
        instructions=instructions,
        tools=[textile_toolset],
    )

    await session.start(room=ctx.room, agent=agent)
    await session.generate_reply(
        instructions="Say a brief, confident hello stating that desktop systems and voice weave are online."
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
