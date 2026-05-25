"""
Interactive GUI review of tagged NSFW photos.
"""

import logging
import shutil
import subprocess
import tkinter as tk
from pathlib import Path
from tkinter import ttk, messagebox

from PIL import Image, ImageTk
from rich.console import Console
from rich.table import Table

from .tagger import get_tagged_photos, untag_photo, soft_delete_nsfw, mark_lockboxed
from .scanner import get_thumbnail_path, generate_thumbnail, delete_thumbnail
from .utils.db import get_cursor, DatabaseError
from .utils.photos import get_photo_by_uuid

logger = logging.getLogger(__name__)
console = Console()

# Server path prefix (photos synced to server)
SERVER_USER = "dshanklin"
SERVER_HOST = "rhea-dev"
SERVER_PHOTOS_ROOT = "/home/dshanklin/data/photos"
SERVER_LOCKBOX_ROOT = "/home/dshanklin/data/photos/lockbox"

# Local lockbox (on THIS Mac)
LOCAL_LOCKBOX = Path.home() / ".tosh" / "nsfw_lockbox"


def mark_reviewed(uuid: str, action: str) -> bool:
    """Mark a photo as reviewed in the scan log."""
    try:
        with get_cursor() as cur:
            # Upsert - insert if not exists, update if exists
            cur.execute("""
                INSERT INTO bronze.nsfw_scan_log (uuid, reviewed_at, review_action, flagged)
                VALUES (%s, NOW(), %s, TRUE)
                ON CONFLICT (uuid) DO UPDATE SET
                    reviewed_at = NOW(),
                    review_action = EXCLUDED.review_action
            """, (uuid, action))
            return True
    except DatabaseError as e:
        logger.warning(f"Could not mark reviewed: {e}")
        return False


def local_lockbox_photo(uuid: str, local_path: Path | str) -> bool:
    """
    Copy photo to local lockbox (on THIS Mac) and delete from iOS.

    Args:
        uuid: Photo UUID.
        local_path: Local path of the photo (in Photos library).

    Returns:
        True if successful, False otherwise.
    """
    local_path = Path(local_path) if local_path else None
    if not local_path or not local_path.exists():
        logger.warning(f"No local path for {uuid}, cannot lockbox")
        return False

    # 1. Copy to local lockbox
    LOCAL_LOCKBOX.mkdir(parents=True, exist_ok=True)
    lockbox_path = LOCAL_LOCKBOX / local_path.name

    try:
        shutil.copy2(local_path, lockbox_path)
        logger.info(f"Copied {uuid} to local lockbox: {lockbox_path}")
    except Exception as e:
        logger.error(f"Failed to copy to lockbox: {e}")
        return False

    # 2. Delete from iOS Photos using AppleScript
    try:
        applescript = f'''
        tell application "Photos"
            set targetPhoto to (media items whose id contains "{uuid}")
            if (count of targetPhoto) > 0 then
                delete targetPhoto
            end if
        end tell
        '''
        result = subprocess.run(
            ["osascript", "-e", applescript],
            capture_output=True,
            timeout=30,
        )
        if result.returncode == 0:
            logger.info(f"Deleted {uuid} from iOS Photos")
        else:
            logger.warning(f"Could not delete from iOS: {result.stderr.decode()}")
    except Exception as e:
        logger.warning(f"Failed to delete from iOS: {e}")

    # 3. Mark as lockboxed and reviewed
    mark_lockboxed(uuid, str(lockbox_path))
    mark_reviewed(uuid, "lockboxed")

    # 4. Delete thumbnail
    delete_thumbnail(uuid)
    return True


def delete_from_ios(uuid: str) -> bool:
    """Delete photo from iOS Photos using multiple fallback methods."""

    # Method 1: Try photoscript (more reliable)
    try:
        from photoscript import PhotosLibrary
        lib = PhotosLibrary()
        photos = list(lib.photos(uuid=[uuid]))
        if photos:
            photo = photos[0]
            photo.delete()
            logger.info(f"Deleted {uuid} from iOS Photos (photoscript)")
            mark_reviewed(uuid, "removed")
            delete_thumbnail(uuid)
            return True
    except Exception as e:
        logger.warning(f"photoscript delete failed for {uuid}: {e}")

    # Method 2: Fall back to AppleScript
    try:
        applescript = f'''
        tell application "Photos"
            set targetPhoto to (media items whose id contains "{uuid}")
            if (count of targetPhoto) > 0 then
                delete targetPhoto
            end if
        end tell
        '''
        result = subprocess.run(
            ["osascript", "-e", applescript],
            capture_output=True,
            timeout=30,
        )
        if result.returncode == 0:
            logger.info(f"Deleted {uuid} from iOS Photos (AppleScript)")
            mark_reviewed(uuid, "removed")
            delete_thumbnail(uuid)
            return True
        else:
            logger.warning(f"AppleScript delete failed: {result.stderr.decode()}")
    except Exception as e:
        logger.warning(f"AppleScript delete failed for {uuid}: {e}")

    # Both methods failed
    logger.error(f"All deletion methods failed for {uuid}")
    return False


def lockbox_photo(uuid: str, server_path: str) -> bool:
    """
    Move photo to lockbox on server and delete from iOS.

    Args:
        uuid: Photo UUID.
        server_path: Current server path of the photo.

    Returns:
        True if successful, False otherwise.
    """
    if not server_path:
        logger.warning(f"No server path for {uuid}, cannot lockbox")
        return False

    # 1. Move to lockbox on server
    filename = Path(server_path).name
    lockbox_path = f"{SERVER_LOCKBOX_ROOT}/{filename}"

    try:
        # Create lockbox dir and move file on server
        move_cmd = f"mkdir -p {SERVER_LOCKBOX_ROOT} && mv '{server_path}' '{lockbox_path}'"
        result = subprocess.run(
            ["ssh", SERVER_HOST, move_cmd],
            capture_output=True,
            timeout=30,
        )
        if result.returncode != 0:
            logger.error(f"Failed to move to lockbox: {result.stderr.decode()}")
            return False

        logger.info(f"Moved {uuid} to lockbox: {lockbox_path}")

    except Exception as e:
        logger.error(f"Failed to lockbox {uuid}: {e}")
        return False

    # 2. Delete from iOS Photos using AppleScript
    try:
        applescript = f'''
        tell application "Photos"
            set targetPhoto to (media items whose id contains "{uuid}")
            if (count of targetPhoto) > 0 then
                delete targetPhoto
            end if
        end tell
        '''
        result = subprocess.run(
            ["osascript", "-e", applescript],
            capture_output=True,
            timeout=30,
        )
        if result.returncode == 0:
            logger.info(f"Deleted {uuid} from iOS Photos")
        else:
            logger.warning(f"Could not delete from iOS: {result.stderr.decode()}")

    except Exception as e:
        logger.warning(f"Failed to delete from iOS: {e}")

    # 3. Update nsfw_photos table: mark as lockboxed
    return mark_lockboxed(uuid, lockbox_path)


def _fetch_server_image(server_path: str, local_cache: Path) -> Path | None:
    """Fetch image from server via scp."""
    if not server_path:
        return None

    cache_file = local_cache / Path(server_path).name
    if cache_file.exists():
        return cache_file

    local_cache.mkdir(parents=True, exist_ok=True)

    try:
        result = subprocess.run(
            ["scp", f"{SERVER_HOST}:{server_path}", str(cache_file)],
            capture_output=True,
            timeout=30,
        )
        if result.returncode == 0:
            return cache_file
    except Exception as e:
        logger.warning(f"Failed to fetch {server_path}: {e}")

    return None


def list_tagged(min_score: float = 0.0) -> None:
    """
    List all tagged NSFW photos in a table.

    Args:
        min_score: Minimum NSFW score filter.
    """
    photos = get_tagged_photos(min_score=min_score)

    if not photos:
        console.print("[yellow]No tagged NSFW photos found.[/yellow]")
        return

    table = Table(title=f"Tagged NSFW Photos ({len(photos)} total)")
    table.add_column("UUID", style="dim")
    table.add_column("Filename")
    table.add_column("Score", justify="right")
    table.add_column("Detected At")

    for photo in photos:
        score = photo.get("nsfw_score", 0)
        score_style = "red" if score >= 0.8 else "yellow" if score >= 0.6 else "green"

        detected_at = photo.get("nsfw_detected_at")
        detected_str = detected_at.strftime("%Y-%m-%d %H:%M") if detected_at else "-"

        table.add_row(
            photo["uuid"][:8] + "...",
            photo.get("filename", "-"),
            f"[{score_style}]{score:.2%}[/{score_style}]",
            detected_str,
        )

    console.print(table)


class ReviewerGUI:
    """GUI for reviewing tagged NSFW photos."""

    def __init__(self, photos: list[dict]):
        self.photos = photos
        self.current_index = 0
        self.stats = {"reviewed": 0, "approved": 0, "removed": 0, "lockboxed": 0, "skipped": 0}
        self.cache_dir = Path("/tmp/tosh_nsfw_review_cache")

        self.root = tk.Tk()
        self.root.title("NSFW Photo Review")
        self.root.geometry("900x700")
        self.root.configure(bg="#1e1e1e")

        self._setup_ui()
        self._load_current_photo()

    def _setup_ui(self):
        """Setup the GUI layout."""
        # Main container
        main_frame = ttk.Frame(self.root, padding=10)
        main_frame.pack(fill=tk.BOTH, expand=True)

        # Style
        style = ttk.Style()
        style.configure("TFrame", background="#1e1e1e")
        style.configure("TLabel", background="#1e1e1e", foreground="white")
        style.configure("Header.TLabel", font=("Helvetica", 14, "bold"))
        style.configure("Score.TLabel", font=("Helvetica", 24, "bold"))

        # Header with progress
        header_frame = ttk.Frame(main_frame)
        header_frame.pack(fill=tk.X, pady=(0, 10))

        self.progress_label = ttk.Label(
            header_frame, text="", style="Header.TLabel"
        )
        self.progress_label.pack(side=tk.LEFT)

        self.score_label = ttk.Label(
            header_frame, text="", style="Score.TLabel", foreground="#ff4444"
        )
        self.score_label.pack(side=tk.RIGHT)

        # Image display
        self.image_frame = ttk.Frame(main_frame)
        self.image_frame.pack(fill=tk.BOTH, expand=True, pady=10)

        self.image_label = ttk.Label(self.image_frame, text="Loading...")
        self.image_label.pack(expand=True)

        # Info panel
        info_frame = ttk.Frame(main_frame)
        info_frame.pack(fill=tk.X, pady=10)

        self.filename_label = ttk.Label(info_frame, text="")
        self.filename_label.pack(anchor=tk.W)

        self.uuid_label = ttk.Label(info_frame, text="", foreground="#888888")
        self.uuid_label.pack(anchor=tk.W)

        self.path_label = ttk.Label(info_frame, text="", foreground="#888888")
        self.path_label.pack(anchor=tk.W)

        # Button panel
        button_frame = ttk.Frame(main_frame)
        button_frame.pack(fill=tk.X, pady=10)

        # Thumbs Up button (green) - approve/keep, mark as reviewed
        self.approve_btn = tk.Button(
            button_frame,
            text="👍 Keep (K)",
            command=self._on_approve,
            bg="#44aa44",
            fg="white",
            font=("Helvetica", 14),
            width=14,
            height=2,
        )
        self.approve_btn.pack(side=tk.LEFT, padx=5)

        # Thumbs Down button (red) - remove from iOS
        self.remove_btn = tk.Button(
            button_frame,
            text="👎 Remove (R)",
            command=self._on_remove,
            bg="#cc4444",
            fg="white",
            font=("Helvetica", 14),
            width=14,
            height=2,
        )
        self.remove_btn.pack(side=tk.LEFT, padx=5)

        # Lockbox button (purple) - copy to local lockbox, remove from iOS
        self.lockbox_btn = tk.Button(
            button_frame,
            text="📦 Lockbox (L)",
            command=self._on_lockbox,
            bg="#8844cc",
            fg="white",
            font=("Helvetica", 14),
            width=14,
            height=2,
        )
        self.lockbox_btn.pack(side=tk.LEFT, padx=5)

        # Quit button
        self.quit_btn = tk.Button(
            button_frame,
            text="Quit (Q)",
            command=self._on_quit,
            bg="#444444",
            fg="white",
            font=("Helvetica", 12),
            width=10,
            height=2,
        )
        self.quit_btn.pack(side=tk.RIGHT, padx=5)

        # Skip button (gray)
        self.skip_btn = tk.Button(
            button_frame,
            text="Skip (S)",
            command=self._on_skip,
            bg="#666666",
            fg="white",
            font=("Helvetica", 12),
            width=10,
            height=2,
        )
        self.skip_btn.pack(side=tk.RIGHT, padx=5)

        # Keyboard bindings
        self.root.bind("k", lambda e: self._on_approve())
        self.root.bind("r", lambda e: self._on_remove())
        self.root.bind("l", lambda e: self._on_lockbox())
        self.root.bind("s", lambda e: self._on_skip())
        self.root.bind("q", lambda e: self._on_quit())
        self.root.bind("<Escape>", lambda e: self._on_quit())
        self.root.bind("<Right>", lambda e: self._on_skip())
        self.root.bind("<Left>", lambda e: self._go_back())

    def _load_current_photo(self):
        """Load and display the current photo."""
        if self.current_index >= len(self.photos):
            self._show_complete()
            return

        photo = self.photos[self.current_index]
        uuid = photo["uuid"]
        filename = photo.get("filename", "unknown")
        score = photo.get("nsfw_score", 0)
        server_path = photo.get("server_path", "")

        # Update labels
        self.progress_label.config(
            text=f"Photo {self.current_index + 1} of {len(self.photos)}"
        )
        self.score_label.config(text=f"{score:.0%}")
        self.filename_label.config(text=f"File: {filename}")
        self.uuid_label.config(text=f"UUID: {uuid}")
        self.path_label.config(text=f"Path: {server_path or 'N/A'}")

        # Load image
        self._load_image(server_path, uuid)

    def _load_image(self, server_path: str, uuid: str):
        """Load image from cached thumbnail, local Photos library, or server."""
        self.image_label.config(text="Loading image...")
        self.root.update()

        image_path = None

        # Try cached thumbnail first (fastest)
        thumb_path = get_thumbnail_path(uuid)
        if thumb_path:
            image_path = thumb_path
        else:
            # Try local path and generate thumbnail
            photo_info = get_photo_by_uuid(uuid)
            if photo_info and photo_info.path and photo_info.path.exists():
                image_path = photo_info.path
                # Generate thumbnail for next time
                generate_thumbnail(uuid, photo_info.path)
            # Fall back to server fetch
            elif server_path:
                image_path = _fetch_server_image(server_path, self.cache_dir)

        if image_path and Path(image_path).exists():
            try:
                img = Image.open(image_path)
                # Only resize if not already a thumbnail
                if not thumb_path:
                    img.thumbnail((800, 500), Image.Resampling.LANCZOS)
                photo_img = ImageTk.PhotoImage(img)
                self.image_label.config(image=photo_img, text="")
                self.image_label.image = photo_img  # Keep reference
            except Exception as e:
                self.image_label.config(text=f"Failed to load image: {e}")
        else:
            self.image_label.config(text="Image not available\n(not downloaded locally)")

    def _on_approve(self):
        """Handle approve/keep action (thumbs up) - mark as reviewed, keep photo."""
        photo = self.photos[self.current_index]
        mark_reviewed(photo["uuid"], "approved")
        self.stats["approved"] += 1
        self._next()

    def _on_remove(self):
        """Handle remove action (thumbs down) - delete from iOS only."""
        photo = self.photos[self.current_index]
        if delete_from_ios(photo["uuid"]):
            self.stats["removed"] += 1
        self._next()

    def _on_lockbox(self):
        """Handle lockbox action - copy to local lockbox, remove from iOS."""
        photo = self.photos[self.current_index]
        # Look up the local path from Photos library
        photo_info = get_photo_by_uuid(photo["uuid"])
        if photo_info and photo_info.path:
            if local_lockbox_photo(photo["uuid"], photo_info.path):
                self.stats["lockboxed"] += 1
        else:
            logger.warning(f"Photo {photo['uuid']} not found locally, cannot lockbox")
        self._next()

    def _on_skip(self):
        """Handle skip action."""
        self.stats["skipped"] += 1
        self._next()

    def _go_back(self):
        """Go to previous photo."""
        if self.current_index > 0:
            self.current_index -= 1
            self._load_current_photo()

    def _next(self):
        """Move to next photo."""
        self.stats["reviewed"] += 1
        self.current_index += 1
        self._load_current_photo()

    def _on_quit(self):
        """Handle quit action."""
        if messagebox.askyesno("Quit", "Are you sure you want to quit?"):
            self.root.quit()

    def _show_complete(self):
        """Show completion message."""
        self.image_label.config(
            text=f"Review Complete!\n\n"
            f"Reviewed: {self.stats['reviewed']}\n"
            f"👍 Approved: {self.stats['approved']}\n"
            f"👎 Removed: {self.stats['removed']}\n"
            f"📦 Lockboxed: {self.stats['lockboxed']}\n"
            f"Skipped: {self.stats['skipped']}"
        )
        self.approve_btn.config(state=tk.DISABLED)
        self.remove_btn.config(state=tk.DISABLED)
        self.lockbox_btn.config(state=tk.DISABLED)
        self.skip_btn.config(state=tk.DISABLED)
        self.progress_label.config(text="Complete!")
        self.score_label.config(text="")

    def run(self) -> dict:
        """Run the GUI and return stats."""
        self.root.mainloop()
        return self.stats


def interactive_review(min_score: float = 0.0) -> dict:
    """
    Launch GUI to review tagged NSFW photos.

    Args:
        min_score: Minimum NSFW score filter.

    Returns:
        Summary dict with counts of actions taken.
    """
    photos = get_tagged_photos(min_score=min_score)

    if not photos:
        console.print("[yellow]No tagged NSFW photos to review.[/yellow]")
        return {"reviewed": 0, "approved": 0, "removed": 0, "lockboxed": 0, "skipped": 0}

    console.print(f"Launching GUI for {len(photos)} photos...")

    gui = ReviewerGUI(photos)
    stats = gui.run()

    console.print("\n[bold green]Review complete![/bold green]")
    console.print(f"  Reviewed:  {stats['reviewed']}")
    console.print(f"  👍 Approved: {stats['approved']}")
    console.print(f"  👎 Removed:  {stats['removed']}")
    console.print(f"  📦 Lockboxed: {stats['lockboxed']}")
    console.print(f"  Skipped:   {stats['skipped']}")

    return stats


def batch_delete(min_score: float = 0.9, dry_run: bool = True) -> int:
    """
    Batch delete photos above a score threshold.

    Args:
        min_score: Minimum score to delete.
        dry_run: If True, only show what would be deleted.

    Returns:
        Number of photos deleted.
    """
    photos = get_tagged_photos(min_score=min_score)

    if not photos:
        console.print(f"[yellow]No photos with score >= {min_score:.0%}[/yellow]")
        return 0

    if dry_run:
        console.print(f"[bold]DRY RUN: Would delete {len(photos)} photos[/bold]")
        for photo in photos[:10]:
            console.print(f"  {photo['uuid'][:8]}... score={photo['nsfw_score']:.2%}")
        if len(photos) > 10:
            console.print(f"  ... and {len(photos) - 10} more")
        return 0

    deleted = 0
    for photo in photos:
        if soft_delete_nsfw(photo["uuid"]):
            deleted += 1

    console.print(f"[green]Deleted {deleted} photos[/green]")
    return deleted
