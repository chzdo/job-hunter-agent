import sys
import yaml
import argparse
from pathlib import Path
from rich.console import Console
from rich.table import Table
from rich.panel import Panel

from database import init_db, get_stats, get_jobs_by_status
from scraper import run_job_search
from scheduler import run_job_cycle, start_scheduler, load_config
from applier import PlaywrightApplier
from dashboard import serve_dashboard, generate_dashboard

console = Console()

def display_stats():
    stats = get_stats()
    table = Table(title="📊 Job Hunter Application Statistics", style="cyan")
    table.add_column("Status", style="bold yellow")
    table.add_column("Count", justify="right", style="bold green")

    for status, count in stats.items():
        table.add_row(status, str(count))

    console.print(table)

def display_jobs(status: str = "DISCOVERED", limit: int = 20):
    jobs = get_jobs_by_status(status, limit=limit)
    if not jobs:
        console.print(f"[yellow]No jobs found with status: {status}[/yellow]")
        return

    table = Table(title=f"📋 Latest {status} Jobs (Limit {limit})", style="blue")
    table.add_column("Platform", style="magenta", width=12)
    table.add_column("Title", style="bold white", width=30)
    table.add_column("Company", style="cyan", width=20)
    table.add_column("Location", style="green", width=15)
    table.add_column("URL", style="underline blue", width=40)

    for j in jobs:
        table.add_row(
            j.get("site", "N/A"),
            j.get("title", "N/A")[:28],
            j.get("company", "N/A")[:18],
            j.get("location", "N/A")[:13],
            j.get("job_url", "N/A")[:38]
        )

    console.print(table)

def main():
    parser = argparse.ArgumentParser(description="Job Hunter CLI")
    parser.add_argument("--stats", action="store_true", help="View current job database statistics")
    parser.add_argument("--list", choices=["DISCOVERED", "QUEUED", "APPLIED", "FAILED"], default=None, help="List jobs by status")
    parser.add_argument("--search-now", action="store_true", help="Execute an immediate job search across all platforms")
    parser.add_argument("--run-cycle", action="store_true", help="Execute one search and apply cycle immediately")
    parser.add_argument("--dry-run", action="store_true", help="Execute one cycle without submitting applications")
    parser.add_argument("--start", action="store_true", help="Start the 12-hour scheduler loop")
    parser.add_argument("--dashboard", action="store_true", help="Launch live web dashboard server at http://localhost:8080")
    parser.add_argument("--login", choices=["linkedin", "indeed"], default=None, help="Open browser to log into LinkedIn or Indeed once and save session")

    args = parser.parse_args()
    init_db()
    config = load_config()

    console.print(Panel.fit("[bold green]🤖 Multi-Platform Job Hunter & Auto-Apply Scheduler[/bold green]", subtitle="v1.0.0"))

    if args.dashboard:
        serve_dashboard(port=8080)
    elif args.login:
        applier = PlaywrightApplier(config)
        applier.login_interactive(args.login)
    elif args.stats:
        display_stats()
    elif args.list:
        display_jobs(args.list)
    elif args.search_now:
        console.print("[cyan]Running immediate search...[/cyan]")
        new_jobs = run_job_search(config)
        console.print(f"[bold green]Discovered {len(new_jobs)} new listings![/bold green]")
        display_stats()
    elif args.dry_run:
        run_job_cycle(config, dry_run=True)
        display_stats()
    elif args.run_cycle:
        run_job_cycle(config, dry_run=False)
        display_stats()
    elif args.start:
        start_scheduler(config, run_immediately=True)
    else:
        parser.print_help()

if __name__ == "__main__":
    main()
