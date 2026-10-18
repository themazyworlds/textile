"""
Yarns Command Handler.
Manages installed capability yarns, repository cloning, inspection, and discovery search paths.
"""

import contextlib
import inspect
import io
import shutil
from pathlib import Path

lazy from dulwich import errors, porcelain

from textile.core.cli.ui import Column, console, print_table
lazy from textile.core.orchestration.skein import skein


def handle_yarn_paths() -> None:
    """Print all discovered yarn search paths in order of layer priority."""
    console.print("\n  [bold cyan]Textile Yarn Discovery Search Paths (in priority order):[/bold cyan]\n")
    for i, p in enumerate(skein.get_search_paths(), 1):
        exists_str = "[green]exists[/green]" if p.exists() else "[dim]not found[/dim]"
        console.print(f"  [bold yellow]{i}.[/bold yellow] {p} ({exists_str})")
    console.print()


def handle_yarn_info(target: str) -> None:
    """Inspect detailed metadata, source location, and strands for an installed yarn."""
    yarn = skein.all_yarns.get(target)
    if not yarn:
        console.print(f"  [bold red]Error:[/bold red] Yarn '[bold white]{target}[/bold white]' is not installed.")
        return

    source_path = "built-in / dynamic"
    with contextlib.suppress(TypeError, OSError):
        source_path = str(inspect.getfile(yarn.__class__))

    strands = yarn.get_strands()
    desc = (yarn.description or "").strip()
    deps = ", ".join(yarn.get_dependencies()) if yarn.get_dependencies() else "[dim]none[/dim]"

    console.print(f"\n  [bold bright_cyan]Yarn Info:[/bold bright_cyan] [bold white]{yarn.name}[/bold white]\n")
    console.print(f"  [bold cyan]Class:[/bold cyan]        {yarn.__class__.__name__}")
    console.print(f"  [bold cyan]Layer:[/bold cyan]        {yarn.layer}")
    console.print(f"  [bold cyan]Version:[/bold cyan]      {yarn.version}")
    console.print(f"  [bold cyan]Tailor:[/bold cyan]       {yarn.tailor}")
    console.print(f"  [bold cyan]Source:[/bold cyan]       {source_path}")
    console.print(f"  [bold cyan]Dependencies:[/bold cyan] {deps}")
    console.print(f"  [bold cyan]Description:[/bold cyan]  {desc}\n")

    if strands:
        rows = []
        for s in sorted(strands, key=lambda x: x.name):
            s_desc = (s.description or "").splitlines()[0].strip() if s.description else ""
            rows.append((s.name, s.tier, s_desc))
        print_table(
            header_title="Strands",
            subtitle=f"{len(strands)} registered",
            columns=[
                Column("Strand", style="bold cyan"),
                Column("Tier", justify="center", style="yellow"),
                Column("Description", style="dim"),
            ],
            rows=rows,
        )


def handle_yarn_install(target: str, user_yarns: Path) -> None:
    """Install capability yarn from local path or remote Git repository via Dulwich."""
    user_yarns.mkdir(parents=True, exist_ok=True)
    target_path = Path(target).expanduser().resolve()
    if target_path.exists() and target_path.is_dir():
        dest = user_yarns / target_path.name
        shutil.copytree(target_path, dest, dirs_exist_ok=True)
        console.print(f"  [bold green]✓[/bold green] Installed yarn from [bold white]{target}[/bold white]")
        console.print(f"    Destination: {dest}")
    else:
        repo_url = target if target.startswith(("http://", "https://", "git@")) else f"https://github.com/{target}.git"
        raw_name = target.rstrip("/").split("/")[-1].replace(".git", "")
        repo_name = raw_name.replace("textile-yarn-", "").replace("textile-", "")
        dest = user_yarns / repo_name

        cloned = False
        err_msg = ""
        err_stream = io.BytesIO()
        try:
            repo = porcelain.clone(repo_url, str(dest), depth=1, errstream=err_stream)
            repo.close()
            cloned = True
        except (errors.GitProtocolError, OSError, ValueError, KeyError, RuntimeError) as e:
            err_msg = err_stream.getvalue().decode(errors="replace").strip() or str(e)

        if not cloned:
            console.print(f"  [bold red]Error installing yarn:[/bold red] {err_msg}")
            return

        console.print(
            f"  [bold green]✓[/bold green] Installed yarn [bold white]{repo_name}[/bold white] from {repo_url}"
        )
        console.print(f"    Destination: {dest}")

    skein._initialized = False
    skein.initialize()


def handle_yarn_remove(target: str, user_yarns: Path) -> None:
    """Remove installed user yarn directory."""
    dest = user_yarns / target
    if dest.exists():
        shutil.rmtree(dest)
        console.print(f"  [bold yellow]✓[/bold yellow] Removed yarn [bold white]{target}[/bold white] from {dest}")
    else:
        console.print(f"  [bold red]Error:[/bold red] Yarn '{target}' not found in {user_yarns}.")


def render_yarns_list_table() -> None:
    """Render all discovered and installed capability yarns."""
    rows = []
    for name, yarn in sorted(skein.all_yarns.items()):
        desc = (yarn.description or "").splitlines()[0].strip() if yarn.description else ""
        rows.append(
            (
                name,
                str(yarn.layer),
                yarn.tailor or "textile",
                yarn.version,
                str(len(yarn.get_strands())),
                desc,
            )
        )

    print_table(
        header_title="Installed Yarns",
        columns=[
            Column("Yarn", style="bold cyan", no_wrap=True),
            Column("Layer", style="dim", justify="center", no_wrap=True),
            Column("Tailor", no_wrap=True),
            Column("Version", style="green", no_wrap=True),
            Column("Strands", justify="right", no_wrap=True),
            Column("Description", style="dim"),
        ],
        rows=rows,
    )
