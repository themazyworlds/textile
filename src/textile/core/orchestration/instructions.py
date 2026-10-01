"""
Textile Fabric Instruction Builder and MCP Definition Generator.
Synthesizes system prompt directives, security governance, and MCP tool definitions.
"""

from typing import Any

from textile.core.execution.strands import Strand
from textile.core.execution.yarn import Yarn

__all__ = ["FabricInstructions", "fabric_instructions"]


class FabricInstructions:
    """Formatter and synthesizer for active Textile fabric prompt instructions and MCP definitions."""

    def get_mcp_definitions(self, active_strands: list[Strand]) -> list[dict[str, Any]]:
        """Return MCP tool definitions for active strands."""
        return [strand.to_mcp_definition() for strand in active_strands]

    def build_instructions(self, active_yarns: dict[str, Yarn]) -> str:
        """Deliver active strand tools, weft stream attunements, and security governance prompt text."""
        weft_docs: list[str] = []
        strand_docs: list[str] = []

        for name, yarn in active_yarns.items():
            pub_tag = f"[{yarn.publisher}/{name}]" if getattr(yarn, "publisher", None) else f"[{name}]"
            for weft in yarn.get_wefts():
                if weft.description:
                    weft_docs.append(f"- `{weft.name}` {pub_tag}: {weft.description}")
            for s in yarn.get_strands():
                if s.description:
                    strand_docs.append(f"- `{s.name}` {pub_tag}: {s.description}")

        active_yarn_names = list(active_yarns.keys())
        desktop_control_directive = (
            "## Direct Desktop Control & Automation Directive\n"
            "You are DIRECTLY empowered and connected to the Linux desktop automation engine via Textile tools.\n"
            "Whenever the user asks you to perform desktop actions (such as switching workspaces,\n"
            "focusing/moving windows, launching applications, adjusting night light,\n"
            "checking hardware telemetry, or executing process actions),\n"
            "YOU MUST IMMEDIATELY INVOKE THE CORRESPONDING TOOL (e.g., `hyprland_focus_workspace(workspace='7')`).\n"
            "NEVER claim that you lack the capability, direct access, or tools to control the desktop.\n\n"
        )
        security_governance = (
            "## Textile Sovereign Security & Capability Governance Model\n"
            "Security is governed by Capability Tiers and Visual OTP Confirmation:\n"
            "- Capability Tiers:\n"
            "  * OBSERVE: Read-only telemetry, status, and sensors (runs freely).\n"
            "  * INTERACT: Non-destructive desktop UI, notifications, window focus (runs freely).\n"
            "  * MUTATE: State-mutating file operations and process modifications (requires Visual OTP).\n"
            "  * PRIVILEGED: High-impact system operations (pkexec, package installations) (requires Visual OTP).\n"
            "  * SYSTEM_EXEC: Lifecycle session operations (UWSM stop, system reboot) (requires Visual OTP).\n"
            "- Visual OTP Confirmation:\n"
            "  * State-mutating actions display a single-use 4-digit OTP code on the user's screen.\n"
            "  * Confirm by providing the 4-digit code in the execution call.\n\n"
        )
        header = (
            "Textile Linux Desktop Automation & Intelligence Fabric Active.\n"
            f"Active Capability Yarns: {', '.join(active_yarn_names)}.\n\n"
            f"{desktop_control_directive}"
            f"{security_governance}"
        )
        if strand_docs:
            header += "## Available Desktop Strands (Tools)\n" + "\n".join(strand_docs) + "\n\n"
        if weft_docs:
            header += (
                "## Real-Time Streaming Semantic Attunements\n"
                "You are strongly encouraged to emit inline semantic tags during speech "
                "for real-time desktop attunement:\n" + "\n".join(weft_docs) + "\n"
            )
        return header


fabric_instructions = FabricInstructions()
