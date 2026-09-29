"""
Weave - Voice & Perception Agent Subsystem powered by LiveKit Agents & Gemini 3 Live API.
Provides seamless real-time full-duplex voice companion bound to the Textile intelligence fabric.
"""

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

from textile.core.elastic import EventUrgency, elastic
from textile.core.loom import loom

logger = logging.getLogger(__name__)

# --- Model & Voice ---
LIVE_MODEL = "gemini-3.8-live"
VOICE = "Puck"

server = AgentServer()


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

    await ctx.connect(auto_subscribe=AutoSubscribe.AUDIO_ONLY)

    realtime_model = google.realtime.RealtimeModel(
        model=LIVE_MODEL,
        voice=VOICE,
    )

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
    text_mode: bool = False,
):
    """Entry point to run Weave Voice Agent using LiveKit CLI (lk)."""
    if mode == "start":
        sys.argv = ["textile-weave", "start"]
        cli.run_app(server)
        return

    script_path = str(Path(__file__).resolve())
    lk_bin = shutil.which("lk")

    if not lk_bin:
        print(
            "Notice: LiveKit CLI ('lk') wasn't found on your PATH.\n"
            "To run Weave in interactive console/dev mode, you can install it anytime:\n"
            "  curl -sSL https://get.livekit.io/cli | bash && lk cloud auth"
        )
        return

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
