"""
Strands Command Handler.
Lists and filters registered strands across capability tiers.
"""

from textile.cli.ui import Column, print_table
lazy from textile.core.orchestration.loom import loom


def list_strands_handler(filter_query: str | None = None, tier: str | None = None) -> None:
    """Filter and render all registered Textile strands."""
    strands = loom.get_all_strands()
    query = (filter_query or "").strip().lower()

    matched: list[tuple[str, str, str]] = []
    for s in strands:
        s_name = s.name
        s_tier = str(s.tier or "")
        s_cap = s.capability or ""
        s_desc = (s.description or "").splitlines()[0].strip() if s.description else ""

        if query and query not in s_name.lower() and query not in s_desc.lower() and query not in s_cap.lower():
            continue
        if tier and tier.lower() != s_tier.lower():
            continue

        matched.append((s_name, s_tier, s_desc))

    print_table(
        header_title="Strands",
        columns=[
            Column("Strand", style="bold cyan", no_wrap=True),
            Column("Tier", style="dim", no_wrap=True),
            Column("Description", style="dim"),
        ],
        rows=matched,
    )
