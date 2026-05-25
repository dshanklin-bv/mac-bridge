"""
CLI entry point for tosh-nsfw.
"""

import argparse
import json
import logging
import sys

from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn

from . import __version__
from .scanner import scan_photos, scan_photos_with_logging, scan_single_path, THUMBNAIL_CACHE, delete_thumbnail
from .exporter import export_photos
from .tagger import tag_photos, get_tagged_count
from .reviewer import list_tagged, interactive_review, batch_delete
from .webapp import run_webapp

console = Console()
logger = logging.getLogger(__name__)


def setup_logging(verbose: bool = False) -> None:
    """Configure logging."""
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%H:%M:%S",
    )


def cmd_scan(args: argparse.Namespace) -> int:
    """Scan photos for NSFW content."""
    results = []

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        task = progress.add_task("Scanning photos...", total=None)

        def on_progress(scanned: int, total: int, uuid: str):
            desc = f"Scanned {scanned} photos"
            if total:
                desc += f" / {total}"
            progress.update(task, description=desc)

        # Use logging version to track what's been scanned
        for result in scan_photos_with_logging(
            limit=args.limit,
            threshold=args.threshold,
            rescan=args.rescan,
            progress_callback=on_progress,
        ):
            results.append(result)

    if args.json:
        print(json.dumps([r.to_dict() for r in results], indent=2))
    else:
        console.print(f"\n[bold]Found {len(results)} flagged photos[/bold]\n")
        for result in results:
            # Color by classification
            if result.classification == "nsfw":
                style = "red"
                icon = "[!]"
            elif result.classification == "suggestive":
                style = "yellow"
                icon = "[~]"
            else:
                style = "cyan"
                icon = "[?]"

            console.print(
                f"[{style}]{icon} {result.max_score:.0%} {result.classification}[/{style}] "
                f"{result.filename} ({result.uuid[:8]}...)"
            )
            for det in result.detections[:3]:
                console.print(f"    - {det.label}: {det.score:.0%} (severity {det.severity:.0%})")

    return 0


def cmd_export(args: argparse.Namespace) -> int:
    """Export NSFW photos to a folder."""
    results = []

    console.print(f"Scanning photos (threshold={args.threshold})...")

    for result in scan_photos(limit=args.limit, threshold=args.threshold):
        results.append(result)

    if not results:
        console.print("[yellow]No NSFW photos found.[/yellow]")
        return 0

    console.print(f"Found {len(results)} NSFW photos. Exporting...")

    exported = export_photos(results, args.output)
    console.print(f"[green]Exported {exported} photos to {args.output}[/green]")

    return 0


def cmd_tag(args: argparse.Namespace) -> int:
    """Tag NSFW photos in database."""
    results = []

    console.print(f"Scanning photos (threshold={args.threshold})...")

    for result in scan_photos(limit=args.limit, threshold=args.threshold):
        results.append(result)

    if not results:
        console.print("[yellow]No NSFW photos found.[/yellow]")
        return 0

    console.print(f"Found {len(results)} NSFW photos. Tagging...")

    tagged = tag_photos(results, dry_run=args.dry_run)

    if args.dry_run:
        console.print(f"[yellow]DRY RUN: Would tag {tagged} photos[/yellow]")
    else:
        console.print(f"[green]Tagged {tagged} photos[/green]")

    return 0


def cmd_review(args: argparse.Namespace) -> int:
    """Review tagged NSFW photos."""
    if args.list:
        list_tagged(min_score=args.min_score)
        return 0

    if args.batch_delete:
        batch_delete(min_score=args.min_score, dry_run=args.dry_run)
        return 0

    # Use web UI by default, --gui for tkinter
    if args.gui:
        interactive_review(min_score=args.min_score)
    else:
        run_webapp(port=args.port, open_browser_flag=not args.no_browser)
    return 0


def cmd_cleanup(args: argparse.Namespace) -> int:
    """Clean up orphaned thumbnails for deleted/lockboxed photos."""
    from .utils.db import get_cursor

    console.print("[bold]Cleaning up thumbnails...[/bold]\n")

    if not THUMBNAIL_CACHE.exists():
        console.print("No thumbnail cache found.")
        return 0

    # Get UUIDs of photos that have been deleted or lockboxed
    try:
        with get_cursor() as cur:
            cur.execute("""
                SELECT uuid FROM bronze.nsfw_scan_log
                WHERE review_action IN ('removed', 'lockboxed')
                   OR reviewed_at IS NOT NULL
            """)
            processed_uuids = {row[0] for row in cur.fetchall()}
    except Exception as e:
        console.print(f"[red]Database error: {e}[/red]")
        return 1

    # Find and delete orphaned thumbnails
    deleted = 0
    for thumb_file in THUMBNAIL_CACHE.glob("*.jpg"):
        uuid = thumb_file.stem
        if uuid in processed_uuids:
            if args.dry_run:
                console.print(f"[yellow]Would delete:[/yellow] {thumb_file.name}")
            else:
                thumb_file.unlink()
                console.print(f"[green]Deleted:[/green] {thumb_file.name}")
            deleted += 1

    if args.dry_run:
        console.print(f"\n[yellow]DRY RUN: Would delete {deleted} orphaned thumbnails[/yellow]")
    else:
        console.print(f"\n[green]Deleted {deleted} orphaned thumbnails[/green]")

    # Show remaining thumbnails
    remaining = len(list(THUMBNAIL_CACHE.glob("*.jpg")))
    console.print(f"Remaining thumbnails: {remaining}")

    return 0


def cmd_status(args: argparse.Namespace) -> int:
    """Show NSFW tagging status."""
    from .utils.photos import get_local_photo_count
    from .utils.db import test_connection, get_cursor

    console.print("[bold]tosh-nsfw status[/bold]\n")

    # Database connection
    db_ok = test_connection()
    db_status = "[green]connected[/green]" if db_ok else "[red]disconnected[/red]"
    console.print(f"Database: {db_status}")

    if db_ok:
        tagged = get_tagged_count()
        console.print(f"Tagged NSFW: {tagged}")

        # Scan log stats
        try:
            with get_cursor() as cur:
                cur.execute("SELECT COUNT(*) FROM bronze.nsfw_scan_log")
                scanned_total = cur.fetchone()[0]
                cur.execute("SELECT COUNT(*) FROM bronze.nsfw_scan_log WHERE flagged = TRUE")
                scanned_flagged = cur.fetchone()[0]
                cur.execute("SELECT COUNT(*) FROM bronze.nsfw_scan_log WHERE reviewed_at IS NOT NULL")
                reviewed = cur.fetchone()[0]
            console.print(f"Scanned: {scanned_total} ({scanned_flagged} flagged, {reviewed} reviewed)")
        except Exception:
            pass

    # Photos library
    try:
        local_count = get_local_photo_count()
        console.print(f"Local photos: {local_count}")
    except Exception as e:
        console.print(f"Photos library: [red]error ({e})[/red]")

    return 0


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        prog="tosh-nsfw",
        description="NSFW photo detection for Apple Photos",
    )
    parser.add_argument(
        "--version", action="version", version=f"%(prog)s {__version__}"
    )
    parser.add_argument(
        "-v", "--verbose", action="store_true", help="Verbose output"
    )

    subparsers = parser.add_subparsers(dest="command", required=True)

    # scan command
    scan_parser = subparsers.add_parser("scan", help="Scan photos for NSFW content")
    scan_parser.add_argument(
        "--limit", "-n", type=int, help="Maximum photos to scan"
    )
    scan_parser.add_argument(
        "--threshold", "-t", type=float, default=0.75,
        help="Weighted score threshold (default: 0.75 = high confidence only)"
    )
    scan_parser.add_argument(
        "--json", action="store_true", help="Output as JSON"
    )
    scan_parser.add_argument(
        "--rescan", action="store_true", help="Re-scan already scanned photos"
    )
    scan_parser.set_defaults(func=cmd_scan)

    # export command
    export_parser = subparsers.add_parser("export", help="Export NSFW photos")
    export_parser.add_argument(
        "--output", "-o", required=True, help="Output directory"
    )
    export_parser.add_argument(
        "--limit", "-n", type=int, help="Maximum photos to scan"
    )
    export_parser.add_argument(
        "--threshold", "-t", type=float, default=0.75,
        help="Weighted score threshold (default: 0.75 = high confidence only)"
    )
    export_parser.set_defaults(func=cmd_export)

    # tag command
    tag_parser = subparsers.add_parser("tag", help="Tag NSFW photos in database")
    tag_parser.add_argument(
        "--limit", "-n", type=int, help="Maximum photos to scan"
    )
    tag_parser.add_argument(
        "--threshold", "-t", type=float, default=0.75,
        help="Weighted score threshold (default: 0.75 = high confidence only)"
    )
    tag_parser.add_argument(
        "--dry-run", action="store_true", help="Show what would be tagged"
    )
    tag_parser.set_defaults(func=cmd_tag)

    # review command
    review_parser = subparsers.add_parser("review", help="Review tagged photos")
    review_parser.add_argument(
        "--list", "-l", action="store_true", help="Just list tagged photos"
    )
    review_parser.add_argument(
        "--min-score", type=float, default=0.0,
        help="Minimum score filter (default: 0.0)"
    )
    review_parser.add_argument(
        "--batch-delete", action="store_true",
        help="Delete all photos above min-score"
    )
    review_parser.add_argument(
        "--dry-run", action="store_true", help="Show what would be deleted"
    )
    review_parser.add_argument(
        "--gui", action="store_true", help="Use tkinter GUI instead of web UI"
    )
    review_parser.add_argument(
        "--port", type=int, default=5050, help="Web UI port (default: 5050)"
    )
    review_parser.add_argument(
        "--no-browser", action="store_true", help="Don't auto-open browser"
    )
    review_parser.set_defaults(func=cmd_review)

    # status command
    status_parser = subparsers.add_parser("status", help="Show status")
    status_parser.set_defaults(func=cmd_status)

    # cleanup command
    cleanup_parser = subparsers.add_parser("cleanup", help="Clean up orphaned thumbnails")
    cleanup_parser.add_argument(
        "--dry-run", action="store_true", help="Show what would be deleted"
    )
    cleanup_parser.set_defaults(func=cmd_cleanup)

    args = parser.parse_args()
    setup_logging(args.verbose)

    try:
        return args.func(args)
    except KeyboardInterrupt:
        console.print("\n[yellow]Interrupted.[/yellow]")
        return 130
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        if args.verbose:
            import traceback
            traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
