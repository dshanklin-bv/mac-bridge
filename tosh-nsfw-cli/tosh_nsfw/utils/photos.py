"""
Apple Photos library access via osxphotos.
"""

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator

import osxphotos

logger = logging.getLogger(__name__)


@dataclass
class PhotoInfo:
    """Simplified photo info for NSFW scanning."""
    uuid: str
    path: Path | None
    filename: str
    date_created: str | None
    is_local: bool


_photos_db: osxphotos.PhotosDB | None = None


def _get_photos_db() -> osxphotos.PhotosDB:
    """Get Photos database (lazy singleton)."""
    global _photos_db
    if _photos_db is None:
        logger.info("Opening Photos library...")
        _photos_db = osxphotos.PhotosDB()
        logger.info(f"Opened library: {_photos_db.db_path}")
    return _photos_db


def get_local_photos(limit: int | None = None, skip_hidden: bool = True) -> Iterator[PhotoInfo]:
    """
    Iterate over photos that exist locally on disk.

    Args:
        limit: Maximum number of photos to return.
        skip_hidden: Skip photos in the Hidden album (default True).

    Yields:
        PhotoInfo objects for local photos.
    """
    db = _get_photos_db()
    count = 0

    for photo in db.photos(intrash=False):
        # Skip videos
        if photo.ismovie:
            continue

        # Skip hidden photos if requested
        if skip_hidden and photo.hidden:
            continue

        # Check if photo exists locally
        path = photo.path
        if not path or not Path(path).exists():
            continue

        yield PhotoInfo(
            uuid=photo.uuid,
            path=Path(path),
            filename=photo.filename or photo.uuid,
            date_created=photo.date.isoformat() if photo.date else None,
            is_local=True,
        )

        count += 1
        if limit and count >= limit:
            break


def get_photo_count() -> int:
    """Get total photo count in library (excluding trash)."""
    db = _get_photos_db()
    return len([p for p in db.photos(intrash=False) if not p.ismovie])


def get_local_photo_count() -> int:
    """Get count of photos available locally."""
    db = _get_photos_db()
    count = 0
    for photo in db.photos(intrash=False):
        if photo.ismovie:
            continue
        if photo.path and Path(photo.path).exists():
            count += 1
    return count


def get_photo_by_uuid(uuid: str) -> PhotoInfo | None:
    """
    Get a photo by UUID.

    Args:
        uuid: Photo UUID.

    Returns:
        PhotoInfo if found, None otherwise.
    """
    db = _get_photos_db()
    photos = db.photos(uuid=[uuid])

    if not photos:
        return None

    photo = photos[0]
    path = photo.path
    is_local = path and Path(path).exists()

    return PhotoInfo(
        uuid=photo.uuid,
        path=Path(path) if path else None,
        filename=photo.filename or photo.uuid,
        date_created=photo.date.isoformat() if photo.date else None,
        is_local=is_local,
    )
