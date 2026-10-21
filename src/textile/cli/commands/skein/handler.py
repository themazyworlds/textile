"""
Skein Command Handler.
Manages Skein layer hierarchy, policy engine, and yarn activation toggling.
"""

lazy from rich.tree import Tree

from textile.cli.ui import Column, console, print_table
lazy from textile.core.camshaft import camshaft
lazy from textile.core.skein.mesh import skein


def handle_skein_enable(yarn_target: str) -> None:
    """Enable capability yarn in Skein."""
    camshaft.set_yarn_enabled(yarn_target, True)
    console.print(f"  [bold green]✓[/bold green] Enabled yarn [bold white]{yarn_target}[/bold white].")


def handle_skein_disable(yarn_target: str) -> None:
    """Disable capability yarn in Skein."""
    camshaft.set_yarn_enabled(yarn_target, False)
    console.print(f"  [bold yellow]✓[/bold yellow] Disabled yarn [bold white]{yarn_target}[/bold white].")


def handle_skein_toggle(yarn_target: str) -> None:
    """Toggle activation state of a capability yarn in Skein."""
    state = camshaft.toggle_yarn(yarn_target)
    state_str = "[bold green]enabled[/bold green]" if state else "[bold yellow]disabled[/bold yellow]"
    console.print(f"  [bold white]✓[/bold white] Toggled yarn [bold white]{yarn_target}[/bold white] to {state_str}.")


def render_skein_tree() -> None:
    """Render Skein layer hierarchy as an interactive Rich tree."""
    layers_map: dict[int, list[tuple[str, bool, int]]] = {}
    for name, yarn in skein.get_all_yarns().items():
        is_en = skein.is_enabled(name)
        strands_count = len(yarn.get_strands())
        layers_map.setdefault(yarn.layer, []).append((name, is_en, strands_count))

    tree = Tree(
        "[bold bright_cyan]Skein Runtime Hierarchy[/bold bright_cyan]",
        guide_style="dim cyan",
    )
    for layer_num in sorted(layers_map.keys(), reverse=True):
        layer_branch = tree.add(f"[bold magenta]Layer {layer_num}[/bold magenta]")
        for y_name, is_en, s_count in sorted(layers_map[layer_num], key=lambda x: x[0]):
            status_str = "[bold green]ACTIVE[/bold green]" if is_en else "[bold red]DISABLED[/bold red]"
            layer_branch.add(f"[bold white]{y_name}[/bold white] [{status_str}] [dim]({s_count} strands)[/dim]")
    console.print(tree)


def render_skein_table() -> None:
    """Render table of all yarns in Skein with layer and status."""
    rows = []
    for name, yarn in sorted(skein.get_all_yarns().items(), key=lambda x: (-x[1].layer, x[1].name)):
        is_en = skein.is_enabled(name)
        en_str = "[green]YES[/green]" if is_en else "[red]NO[/red]"
        desc = (yarn.description or "").splitlines()[0].strip() if yarn.description else ""
        strands_count = str(len(yarn.get_strands()))
        rows.append((yarn.name, str(yarn.layer), en_str, strands_count, desc))

    print_table(
        header_title="Skein",
        columns=[
            Column("Yarn", style="bold cyan", no_wrap=True),
            Column("Layer", style="dim", justify="center", no_wrap=True),
            Column("Enabled", justify="center", no_wrap=True),
            Column("Strands", justify="right", no_wrap=True),
            Column("Description", style="dim"),
        ],
        rows=rows,
    )
