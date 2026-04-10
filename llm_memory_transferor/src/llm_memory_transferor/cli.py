"""mwiki CLI - Portable Personal Memory Layer command-line interface."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

import click
from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.table import Table

console = Console()

# Default wiki directory: ./wiki relative to cwd
DEFAULT_WIKI = Path.cwd() / "wiki"

SUPPORTED_PLATFORMS = ["chatgpt", "claude", "deepseek", "kimi", "generic"]


def _get_wiki(wiki_path: str | None) -> "L2Wiki":
    from .layers.l2_wiki import L2Wiki
    path = Path(wiki_path) if wiki_path else DEFAULT_WIKI
    return L2Wiki(path)


def _get_llm(
    model: str | None,
    backend: str | None = None,
    api_key: str | None = None,
    base_url: str | None = None,
) -> "LLMClient":
    from .utils.llm_client import LLMClient, _detect_backend
    resolved_backend = backend or _detect_backend()
    return LLMClient(api_key=api_key, model=model, backend=resolved_backend, base_url=base_url)


@click.group()
@click.version_option("0.1.0", prog_name="mwiki")
def cli() -> None:
    """Portable Personal Memory Layer - migrate and maintain LLM memory across platforms."""


# ---------------------------------------------------------------------------
# mwiki scan
# ---------------------------------------------------------------------------

@cli.command()
@click.argument("history_files", nargs=-1, type=click.Path(exists=True), required=True)
@click.option("--platform", "-p", default="unknown", help="Source platform name.")
@click.option("--memory-file", "-m", multiple=True, type=click.Path(exists=True),
              help="Platform memory/profile export files (L1 signals). Repeatable.")
@click.option("--wiki", "-w", default=None, help="Wiki directory path (default: ./wiki).")
@click.option("--model", default=None, help="Model ID to use (overrides backend default).")
@click.option("--backend", default=None,
              type=click.Choice(["anthropic", "openai", "openai_compat"]),
              help="LLM backend. Auto-detected from env vars if omitted.")
@click.option("--api-key", default=None, envvar="MWIKI_API_KEY",
              help="API key (overrides ANTHROPIC_API_KEY / OPENAI_API_KEY).")
@click.option("--base-url", default=None, envvar="OPENAI_BASE_URL",
              help="Base URL for openai_compat backend (e.g. http://localhost:11434/v1).")
def scan(
    history_files: tuple,
    platform: str,
    memory_file: tuple,
    wiki: Optional[str],
    model: Optional[str],
    backend: Optional[str],
    api_key: Optional[str],
    base_url: Optional[str],
) -> None:
    """
    SCENARIO 1: Scan A-platform history and build initial memory wiki.

    Reads chat history files (JSON/JSONL/MD/TXT) and optional platform memory
    exports, then builds a structured L2 Managed MWiki.

    Example:
      mwiki scan chatgpt_export.json -p chatgpt -m saved_memory.json
    """
    from .layers.l0_raw import L0RawLayer
    from .layers.l1_signals import L1SignalLayer
    from .processors.memory_builder import MemoryBuilder

    l2 = _get_wiki(wiki)
    llm = _get_llm(model, backend=backend, api_key=api_key, base_url=base_url)

    console.print(Panel.fit(
        "[bold blue]mwiki scan[/bold blue] - Building initial memory wiki",
        border_style="blue",
    ))

    # Load L0 raw history
    l0 = L0RawLayer(l2.wiki_dir / "_raw_index")
    all_convs = []
    with Progress(SpinnerColumn(), TextColumn("{task.description}"), console=console) as prog:
        task = prog.add_task("Loading chat history...", total=None)
        for hf in history_files:
            path = Path(hf)
            try:
                convs = l0.ingest_file(path)
                all_convs.extend(convs)
                prog.console.print(f"  Loaded [green]{len(convs)}[/green] conversations from {path.name}")
            except Exception as e:
                prog.console.print(f"  [yellow]Warning:[/yellow] Could not parse {path.name}: {e}")
        prog.update(task, description=f"Loaded {len(all_convs)} total conversations.")

    if not all_convs:
        console.print("[red]No conversations found in the provided files.[/red]")
        raise SystemExit(1)

    # Load L1 signals
    l1 = L1SignalLayer()
    for mf in memory_file:
        path = Path(mf)
        sigs = l1.load_file(path, platform=platform)
        console.print(f"  Loaded [green]{len(sigs)}[/green] memory signals from {path.name}")

    # Build
    builder = MemoryBuilder(llm=llm, wiki=l2)

    with Progress(SpinnerColumn(), TextColumn("{task.description}"), console=console) as prog:
        task = prog.add_task("Building memory...", total=None)

        def on_progress(msg: str) -> None:
            prog.update(task, description=msg)

        results = builder.build(all_convs, l1, on_progress=on_progress)

    # Show results
    table = Table(title="Build Results", show_header=True)
    table.add_column("Memory Type", style="cyan")
    table.add_column("Objects", justify="right", style="green")
    table.add_column("Source episodes", justify="right", style="dim")
    total_processed = results.get("episodes", 0) + results.get("skipped_noise", 0)
    table.add_row(
        "Episodes (memory-relevant)",
        str(results.get("episodes", 0)),
        f"{results.get('topics_identified', 0)} unique topics · {results.get('skipped_noise', 0)}/{total_processed} skipped as noise",
    )
    table.add_row(
        "Profile",
        "1" if results.get("profile") else "0",
        str(results.get("episodes_to_profile", 0)),
    )
    table.add_row(
        "Preferences",
        "1" if results.get("preferences") else "0",
        str(results.get("episodes_to_preferences", 0)),
    )
    table.add_row(
        "Projects",
        str(results.get("projects", 0)),
        str(results.get("episodes_to_projects", 0)),
    )
    table.add_row(
        "Workflows",
        str(results.get("workflows", 0)),
        str(results.get("episodes_to_workflows", 0)),
    )
    console.print(table)
    console.print(f"\n[bold]Wiki stored at:[/bold] {l2.wiki_dir}")


# ---------------------------------------------------------------------------
# mwiki update
# ---------------------------------------------------------------------------

@cli.command()
@click.argument("conversation_file", type=click.Path(exists=True))
@click.option("--platform", "-p", default="unknown", help="Source platform name.")
@click.option("--memory-file", "-m", multiple=True, type=click.Path(exists=True),
              help="Latest platform memory export (L1 signals).")
@click.option("--wiki", "-w", default=None, help="Wiki directory path.")
@click.option("--model", default=None, help="Model ID to use (overrides backend default).")
@click.option("--backend", default=None,
              type=click.Choice(["anthropic", "openai", "openai_compat"]),
              help="LLM backend. Auto-detected from env vars if omitted.")
@click.option("--api-key", default=None, envvar="MWIKI_API_KEY",
              help="API key (overrides ANTHROPIC_API_KEY / OPENAI_API_KEY).")
@click.option("--base-url", default=None, envvar="OPENAI_BASE_URL",
              help="Base URL for openai_compat backend (e.g. http://localhost:11434/v1).")
def update(
    conversation_file: str,
    platform: str,
    memory_file: tuple,
    wiki: Optional[str],
    model: Optional[str],
    backend: Optional[str],
    api_key: Optional[str],
    base_url: Optional[str],
) -> None:
    """
    SCENARIO 2: Update memory wiki from a new conversation.

    Only processes what changed - no full rescan needed.

    Example:
      mwiki update latest_chat.txt -p claude
    """
    from .layers.l1_signals import L1SignalLayer
    from .layers.l3_schema import L3Schema
    from .processors.memory_updater import MemoryUpdater

    l2 = _get_wiki(wiki)
    llm = _get_llm(model, backend=backend, api_key=api_key, base_url=base_url)

    path = Path(conversation_file)
    text = path.read_text(encoding="utf-8")

    l1 = L1SignalLayer()
    for mf in memory_file:
        l1.load_file(Path(mf), platform=platform)

    updater = MemoryUpdater(llm=llm, wiki=l2, schema=L3Schema())

    with Progress(SpinnerColumn(), TextColumn("{task.description}"), console=console) as prog:
        task = prog.add_task("Analyzing conversation...", total=None)

        def on_progress(msg: str) -> None:
            prog.update(task, description=msg)

        results = updater.update(
            text,
            l1_layer=l1 if memory_file else None,
            platform=platform,
            on_progress=on_progress,
        )

    status = results.get("status", "unknown")
    if status == "noise":
        console.print("[yellow]No memory-worthy content detected. No updates made.[/yellow]")
    elif status == "updated":
        console.print("[green]Memory updated successfully.[/green]")
        if results.get("profile_updated"):
            console.print("  - Profile updated")
        if results.get("preferences_updated"):
            console.print("  - Preferences updated")
        if results.get("projects_updated"):
            console.print(f"  - Projects updated: {', '.join(results['projects_updated'])}")
        if results.get("workflows_updated"):
            console.print("  - Workflows updated")
        if results.get("episode_created"):
            console.print(f"  - Episode created: {results['episode_created']}")
    else:
        console.print(f"[yellow]Status: {status}[/yellow]")


# ---------------------------------------------------------------------------
# mwiki export
# ---------------------------------------------------------------------------

@cli.command()
@click.option("--target", "-t", default="generic",
              type=click.Choice(SUPPORTED_PLATFORMS),
              help="Target platform.")
@click.option("--output", "-o", default=None, help="Output file path (without .zip extension).")
@click.option("--no-zip", is_flag=True, default=False, help="Output as directory instead of zip.")
@click.option("--wiki", "-w", default=None, help="Wiki directory path.")
@click.option(
    "--include-persistent", default="profile,preferences,projects,workflows",
    help="Comma-separated persistent memory sections to include. "
         "Options: profile, preferences, projects, workflows. "
         "Default: all four.",
)
@click.option(
    "--episode-ids", default=None,
    help="Comma-separated episode IDs to include. Omit to include all episodes.",
)
def export(
    target: str,
    output: Optional[str],
    no_zip: bool,
    wiki: Optional[str],
    include_persistent: str,
    episode_ids: Optional[str],
) -> None:
    """
    Export memory package for migration to a target platform.

    The package contains only episodic memories and persistent memories.
    Use --include-persistent and --episode-ids to control what is included.

    Examples:
      mwiki export --target claude
      mwiki export --target claude --include-persistent profile,projects
      mwiki export --target claude --episode-ids abc12345,def67890
    """
    from .exporters.package_exporter import PackageExporter

    l2 = _get_wiki(wiki)

    persistent_sections = [s.strip() for s in include_persistent.split(",") if s.strip()]
    selected_episode_ids = (
        [eid.strip() for eid in episode_ids.split(",") if eid.strip()]
        if episode_ids else None
    )

    if not output:
        output = f"memory_package_{target}"
    output_path = Path(output)

    exporter = PackageExporter(wiki=l2)
    with console.status("Exporting memory package..."):
        result_path = exporter.export(
            output_path=output_path,
            target_platform=target,
            zip_output=not no_zip,
            include_persistent=persistent_sections,
            include_episode_ids=selected_episode_ids,
        )

    console.print(f"[green]Memory package exported:[/green] {result_path}")
    console.print(f"  Persistent sections: {', '.join(persistent_sections)}")
    if selected_episode_ids:
        console.print(f"  Episodes: {len(selected_episode_ids)} selected")
    else:
        console.print("  Episodes: all")
    console.print(f"\nTo use in {target}:")
    console.print("  1. Open [bold]minimal_bootstrap_prompt.txt[/bold] from the package")
    console.print("  2. Paste it as the system prompt / custom instructions in the new platform")
    console.print("  3. Start chatting - the model will recognize your context immediately")


# ---------------------------------------------------------------------------
# mwiki show
# ---------------------------------------------------------------------------

@cli.command()
@click.argument("section", default="all",
                type=click.Choice(["all", "profile", "preferences", "projects", "workflows",
                                   "episodes", "index", "changelog"]))
@click.option("--wiki", "-w", default=None, help="Wiki directory path.")
def show(section: str, wiki: Optional[str]) -> None:
    """
    Show current memory wiki contents.

    SECTION: all | profile | preferences | projects | workflows | episodes | index | changelog
    """
    l2 = _get_wiki(wiki)

    if section in ("all", "index"):
        index = l2.get_index()
        table = Table(title="Memory Wiki Index", show_header=True)
        table.add_column("Key", style="cyan")
        table.add_column("Value")
        for k, v in index.items():
            table.add_row(k, str(v))
        console.print(table)

    if section in ("all", "profile"):
        profile = l2.load_profile()
        if profile:
            console.print(Panel(profile.to_markdown(), title="Profile", border_style="green"))
        else:
            console.print("[yellow]No profile found.[/yellow]")

    if section in ("all", "preferences"):
        prefs = l2.load_preferences()
        if prefs:
            console.print(Panel(prefs.to_markdown(), title="Preferences", border_style="blue"))
        else:
            console.print("[yellow]No preferences found.[/yellow]")

    if section in ("all", "projects"):
        projects = l2.list_projects()
        if projects:
            for p in projects:
                style = "green" if p.is_active else "dim"
                console.print(Panel(p.to_markdown(), title=f"Project: {p.project_name}",
                                    border_style=style))
        else:
            console.print("[yellow]No projects found.[/yellow]")

    if section in ("all", "workflows"):
        workflows = l2.load_workflows()
        if workflows:
            for w in workflows:
                console.print(Panel(w.to_markdown(), title=f"Workflow: {w.workflow_name}",
                                    border_style="magenta"))
        else:
            console.print("[yellow]No workflows found.[/yellow]")

    if section in ("all", "episodes"):
        episodes = l2.list_episodes()
        if episodes:
            table = Table(title="Episodes", show_header=True)
            table.add_column("ID", style="dim")
            table.add_column("Topic")
            table.add_column("Project")
            table.add_column("Created")
            for ep in episodes[-20:]:
                table.add_row(
                    ep.episode_id,
                    ep.topic[:50],
                    ep.related_project[:20] if ep.related_project else "-",
                    ep.created_at.date().isoformat(),
                )
            console.print(table)
        else:
            console.print("[yellow]No episodes found.[/yellow]")

    if section == "changelog":
        changes = l2.change_history(limit=30)
        table = Table(title="Change Log (last 30)", show_header=True)
        table.add_column("Timestamp", style="dim")
        table.add_column("Type")
        table.add_column("Action")
        table.add_column("ID")
        for c in changes:
            table.add_row(
                c.get("timestamp", "")[:19],
                c.get("entity_type", ""),
                c.get("action", ""),
                str(c.get("entity_id", ""))[:30],
            )
        console.print(table)


# ---------------------------------------------------------------------------
# mwiki bootstrap
# ---------------------------------------------------------------------------

@cli.command()
@click.option("--target", "-t", default="generic",
              type=click.Choice(SUPPORTED_PLATFORMS),
              help="Target platform for bootstrap format.")
@click.option("--max-tokens", default=None, type=int, help="Maximum token budget.")
@click.option("--wiki", "-w", default=None, help="Wiki directory path.")
def bootstrap(target: str, max_tokens: Optional[int], wiki: Optional[str]) -> None:
    """
    Print minimal bootstrap prompt for a target platform.

    Copy-paste this into the target platform's system prompt / custom instructions.

    Example:
      mwiki bootstrap --target claude
    """
    from .exporters.bootstrap_generator import BootstrapGenerator

    l2 = _get_wiki(wiki)
    gen = BootstrapGenerator(wiki=l2)
    result = gen.generate(target_platform=target, max_tokens=max_tokens)

    console.print(Panel(
        result,
        title=f"Bootstrap Prompt for [bold]{target}[/bold]",
        border_style="cyan",
        subtitle=f"{len(result)} chars",
    ))


# ---------------------------------------------------------------------------
# mwiki edit
# ---------------------------------------------------------------------------

@cli.command()
@click.argument("section", type=click.Choice(["profile", "preferences", "project"]))
@click.option("--project-name", "-n", default=None, help="Project name (for 'project' section).")
@click.option("--wiki", "-w", default=None, help="Wiki directory path.")
def edit(section: str, project_name: Optional[str], wiki: Optional[str]) -> None:
    """
    Open memory section in your default editor for manual editing.

    Changes to the markdown file are parsed back into the JSON store.
    """
    import subprocess
    import sys

    l2 = _get_wiki(wiki)
    editor = os.environ.get("EDITOR", "vi")

    if section == "profile":
        md_path = l2.wiki_dir / "profile.md"
        if not md_path.exists():
            console.print("[yellow]No profile yet. Run 'mwiki scan' first.[/yellow]")
            return
        subprocess.run([editor, str(md_path)], check=False)
        console.print("[green]Profile markdown updated.[/green] (JSON will sync on next operation)")

    elif section == "preferences":
        md_path = l2.wiki_dir / "preferences.md"
        if not md_path.exists():
            console.print("[yellow]No preferences yet. Run 'mwiki scan' first.[/yellow]")
            return
        subprocess.run([editor, str(md_path)], check=False)
        console.print("[green]Preferences markdown updated.[/green]")

    elif section == "project":
        if not project_name:
            projects = l2.list_projects()
            if not projects:
                console.print("[yellow]No projects found.[/yellow]")
                return
            console.print("Available projects:")
            for p in projects:
                console.print(f"  - {p.project_name}")
            return
        safe = project_name.lower().replace(" ", "_")[:64]
        md_path = l2.wiki_dir / "projects" / f"{safe}.md"
        if not md_path.exists():
            console.print(f"[yellow]Project '{project_name}' not found.[/yellow]")
            return
        subprocess.run([editor, str(md_path)], check=False)
        console.print(f"[green]Project '{project_name}' markdown updated.[/green]")


# ---------------------------------------------------------------------------
# mwiki delete
# ---------------------------------------------------------------------------

@cli.command()
@click.argument("section", type=click.Choice(["profile", "preferences", "project", "episode",
                                               "workflow"]))
@click.option("--name", "-n", default=None, help="Name/ID of the item to delete.")
@click.option("--wiki", "-w", default=None, help="Wiki directory path.")
@click.option("--yes", "-y", is_flag=True, default=False, help="Skip confirmation prompt.")
def delete(section: str, name: Optional[str], wiki: Optional[str], yes: bool) -> None:
    """Delete a memory entry from the wiki."""
    l2 = _get_wiki(wiki)

    def confirm(msg: str) -> bool:
        if yes:
            return True
        return click.confirm(msg)

    if section == "profile":
        path = l2.wiki_dir / "profile.json"
        if not path.exists():
            console.print("[yellow]No profile to delete.[/yellow]")
            return
        if confirm("Delete profile permanently?"):
            path.unlink()
            md = l2.wiki_dir / "profile.md"
            if md.exists():
                md.unlink()
            console.print("[green]Profile deleted.[/green]")

    elif section == "preferences":
        path = l2.wiki_dir / "preferences.json"
        if not path.exists():
            console.print("[yellow]No preferences to delete.[/yellow]")
            return
        if confirm("Delete preferences permanently?"):
            path.unlink()
            md = l2.wiki_dir / "preferences.md"
            if md.exists():
                md.unlink()
            console.print("[green]Preferences deleted.[/green]")

    elif section == "project":
        if not name:
            console.print("[red]--name required for project deletion.[/red]")
            return
        safe = name.lower().replace(" ", "_")[:64]
        json_path = l2.wiki_dir / "projects" / f"{safe}.json"
        if not json_path.exists():
            console.print(f"[yellow]Project '{name}' not found.[/yellow]")
            return
        if confirm(f"Delete project '{name}' permanently?"):
            json_path.unlink()
            md = json_path.with_suffix(".md")
            if md.exists():
                md.unlink()
            console.print(f"[green]Project '{name}' deleted.[/green]")

    elif section == "episode":
        if not name:
            console.print("[red]--name (episode ID) required.[/red]")
            return
        json_path = l2.wiki_dir / "episodes" / f"{name}.json"
        if not json_path.exists():
            console.print(f"[yellow]Episode '{name}' not found.[/yellow]")
            return
        if confirm(f"Delete episode '{name}'?"):
            json_path.unlink()
            md = json_path.with_suffix(".md")
            if md.exists():
                md.unlink()
            console.print(f"[green]Episode '{name}' deleted.[/green]")

    elif section == "workflow":
        if not name:
            console.print("[red]--name required for workflow deletion.[/red]")
            return
        workflows = l2.load_workflows()
        filtered = [w for w in workflows if w.workflow_name != name]
        if len(filtered) == len(workflows):
            console.print(f"[yellow]Workflow '{name}' not found.[/yellow]")
            return
        if confirm(f"Delete workflow '{name}'?"):
            l2.save_workflows(filtered)
            console.print(f"[green]Workflow '{name}' deleted.[/green]")

    l2.rebuild_index()


if __name__ == "__main__":
    cli()
