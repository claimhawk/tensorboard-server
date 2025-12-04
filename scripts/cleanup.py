# Copyright 2025 Tylt, Inc.
# SPDX-License-Identifier: MIT
"""
Interactive TensorBoard Log Cleanup Tool

A console GUI for managing TensorBoard logs across trainers.
Lists runs with metadata and allows selective deletion.

Usage:
    # Clean up lora-trainer logs
    modal run scripts/cleanup.py --trainer lora

    # Clean up router trainer logs
    modal run scripts/cleanup.py --trainer router

    # Clean up both
    modal run scripts/cleanup.py --trainer all
"""

import os
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import modal

app = modal.App("tensorboard-cleanup")

lora_volume = modal.Volume.from_name("claimhawk-lora-training", create_if_missing=False)
moe_volume = modal.Volume.from_name("moe-lora-data", create_if_missing=False)

image = modal.Image.debian_slim(python_version="3.11").pip_install("rich>=13.0.0")


@dataclass
class RunInfo:
    """Information about a training run's TensorBoard logs."""

    path: str
    dataset: str
    run_name: str
    size_mb: float
    modified: datetime
    event_count: int


def get_dir_size(path: Path) -> int:
    """Get total size of directory in bytes."""
    total = 0
    for entry in path.rglob("*"):
        if entry.is_file():
            total += entry.stat().st_size
    return total


def count_events(path: Path) -> int:
    """Count TensorBoard event files."""
    return len(list(path.rglob("events.out.tfevents.*")))


def scan_runs(base_path: str) -> list[RunInfo]:
    """Scan a log directory for training runs."""
    runs = []
    base = Path(base_path)

    if not base.exists():
        return runs

    # Structure: base/{dataset_name}/{run_name}/
    for dataset_dir in base.iterdir():
        if not dataset_dir.is_dir():
            continue
        for run_dir in dataset_dir.iterdir():
            if not run_dir.is_dir():
                continue

            size_bytes = get_dir_size(run_dir)
            event_count = count_events(run_dir)

            # Get modification time from most recent file
            mod_times = [f.stat().st_mtime for f in run_dir.rglob("*") if f.is_file()]
            modified = datetime.fromtimestamp(max(mod_times)) if mod_times else datetime.now()

            runs.append(
                RunInfo(
                    path=str(run_dir),
                    dataset=dataset_dir.name,
                    run_name=run_dir.name,
                    size_mb=size_bytes / (1024 * 1024),
                    modified=modified,
                    event_count=event_count,
                )
            )

    # Sort by modification time (oldest first)
    runs.sort(key=lambda r: r.modified)
    return runs


def display_runs(runs: list[RunInfo], trainer_name: str) -> list[int]:
    """Display runs in a table and prompt for selection."""
    from rich.console import Console
    from rich.prompt import Prompt
    from rich.table import Table

    console = Console()

    if not runs:
        console.print(f"[yellow]No runs found for {trainer_name}[/yellow]")
        return []

    # Build table
    table = Table(title=f"TensorBoard Logs - {trainer_name}")
    table.add_column("#", style="dim", width=4)
    table.add_column("Dataset", style="cyan")
    table.add_column("Run Name", style="green")
    table.add_column("Size", justify="right")
    table.add_column("Events", justify="right")
    table.add_column("Last Modified", style="magenta")

    for i, run in enumerate(runs):
        age = datetime.now() - run.modified
        if age.days > 7:
            age_style = "red"
        elif age.days > 1:
            age_style = "yellow"
        else:
            age_style = "green"

        table.add_row(
            str(i),
            run.dataset,
            run.run_name,
            f"{run.size_mb:.1f} MB",
            str(run.event_count),
            f"[{age_style}]{run.modified.strftime('%Y-%m-%d %H:%M')}[/{age_style}]",
        )

    console.print(table)
    console.print()

    # Calculate total size
    total_mb = sum(r.size_mb for r in runs)
    console.print(f"Total: {len(runs)} runs, {total_mb:.1f} MB")
    console.print()

    # Prompt for selection
    console.print("[bold]Select runs to delete:[/bold]")
    console.print("  - Enter numbers separated by spaces (e.g., '0 2 5')")
    console.print("  - Enter a range (e.g., '0-5')")
    console.print("  - Enter 'all' to select all")
    console.print("  - Enter 'old' to select runs older than 7 days")
    console.print("  - Press Enter to cancel")
    console.print()

    selection = Prompt.ask("Selection", default="")

    if not selection.strip():
        return []

    indices = []
    selection = selection.strip().lower()

    if selection == "all":
        indices = list(range(len(runs)))
    elif selection == "old":
        for i, run in enumerate(runs):
            if (datetime.now() - run.modified).days > 7:
                indices.append(i)
    else:
        # Parse numbers and ranges
        for part in selection.split():
            if "-" in part:
                try:
                    start, end = part.split("-")
                    indices.extend(range(int(start), int(end) + 1))
                except ValueError:
                    console.print(f"[red]Invalid range: {part}[/red]")
            else:
                try:
                    indices.append(int(part))
                except ValueError:
                    console.print(f"[red]Invalid number: {part}[/red]")

    # Filter valid indices
    valid_indices = [i for i in indices if 0 <= i < len(runs)]
    return valid_indices


def confirm_and_delete(runs: list[RunInfo], indices: list[int]) -> int:
    """Confirm deletion and remove selected runs."""
    import shutil

    from rich.console import Console
    from rich.prompt import Confirm

    console = Console()

    if not indices:
        console.print("[yellow]No runs selected[/yellow]")
        return 0

    selected = [runs[i] for i in indices]
    total_mb = sum(r.size_mb for r in selected)

    console.print()
    console.print("[bold red]The following runs will be PERMANENTLY deleted:[/bold red]")
    for run in selected:
        console.print(f"  - {run.dataset}/{run.run_name} ({run.size_mb:.1f} MB)")
    console.print(f"\nTotal: {len(selected)} runs, {total_mb:.1f} MB")
    console.print()

    if not Confirm.ask("Are you sure?", default=False):
        console.print("[yellow]Cancelled[/yellow]")
        return 0

    deleted = 0
    for run in selected:
        try:
            shutil.rmtree(run.path)
            console.print(f"[green]Deleted: {run.dataset}/{run.run_name}[/green]")
            deleted += 1
        except Exception as e:
            console.print(f"[red]Failed to delete {run.path}: {e}[/red]")

    return deleted


@app.function(
    image=image,
    volumes={
        "/volume": lora_volume,
        "/moe-data": moe_volume,
    },
)
def cleanup_interactive(trainer: str = "all"):
    """Interactive cleanup of TensorBoard logs."""
    from rich.console import Console

    console = Console()
    console.print("[bold]TensorBoard Log Cleanup Tool[/bold]")
    console.print()

    total_deleted = 0

    if trainer in ("lora", "all"):
        console.print("[bold cyan]== LoRA Trainer Logs ==[/bold cyan]")
        runs = scan_runs("/volume/tensorboard")
        indices = display_runs(runs, "LoRA Trainer")
        if indices:
            total_deleted += confirm_and_delete(runs, indices)
            # Commit volume changes
            lora_volume.commit()
        console.print()

    if trainer in ("router", "all"):
        console.print("[bold cyan]== Router Trainer Logs ==[/bold cyan]")
        runs = scan_runs("/moe-data/tb_logs")
        indices = display_runs(runs, "Router Trainer")
        if indices:
            total_deleted += confirm_and_delete(runs, indices)
            # Commit volume changes
            moe_volume.commit()
        console.print()

    if total_deleted > 0:
        console.print(f"[bold green]Cleanup complete: {total_deleted} runs deleted[/bold green]")
    else:
        console.print("[yellow]No runs were deleted[/yellow]")


@app.local_entrypoint()
def main(trainer: str = "all"):
    """
    Clean up old TensorBoard logs.

    Args:
        trainer: Which trainer's logs to clean ('lora', 'router', or 'all')
    """
    if trainer not in ("lora", "router", "all"):
        print(f"Invalid trainer: {trainer}. Use 'lora', 'router', or 'all'")
        return

    cleanup_interactive.remote(trainer)
