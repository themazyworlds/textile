"""
Tapestry Command Handler.
Inspects active and historic execution tasks and sensory blackboard context.
"""

lazy import orjson

from textile.cli.ui import Column, print_table
lazy from textile.core.tapestry.intra import intra_mesh as core_tapestry
lazy from textile.core.tapestry.sensory import sensory_mesh as sensory_tapestry


def handle_tapestry(json_output: bool = False) -> None:
    """Inspect engine task ledger and sensory blackboard."""
    if json_output:
        payload = {
            "engine": core_tapestry.get_engine_state(),
            "sensory": sensory_tapestry.get_state(),
        }
        print(orjson.dumps(payload, option=orjson.OPT_INDENT_2).decode())
        return

    active = core_tapestry.get_active_tasks()
    history = core_tapestry.get_task_history(limit=15)

    rows = []
    for t in active:
        rows.append((t["task_id"][:8], t["strand_name"], str(t.get("tier", "-")), "[bold green]RUNNING[/bold green]"))
    for t in reversed(history):
        status_str = "[green]SUCCESS[/green]" if t.get("success") else "[red]FAILED[/red]"
        rows.append((t["task_id"][:8], t["strand_name"], str(t.get("tier", "-")), status_str))

    print_table(
        header_title="Tapestry",
        subtitle=f"{len(active)} active tasks",
        columns=[
            Column("Task ID", style="bold yellow", width=10),
            Column("Strand", style="bold white", width=28),
            Column("Tier", width=12),
            Column("Status", width=12),
        ],
        rows=rows,
    )
