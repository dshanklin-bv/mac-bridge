"""
NSFW photo scanner using Ojo's NSFWDetector.
Handles all image formats and provides context-aware scoring.
"""

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterator

# Register HEIC support BEFORE importing PIL
try:
    from pillow_heif import register_heif_opener
    register_heif_opener()
except ImportError:
    pass

from PIL import Image

from .utils.db import get_cursor, DatabaseError
from .utils.photos import PhotoInfo, get_local_photos

# Thumbnail cache directory
THUMBNAIL_CACHE = Path.home() / ".tosh" / "nsfw_thumbnails"
THUMBNAIL_SIZE = (800, 600)

logger = logging.getLogger(__name__)

# Lazy-loaded Ojo components
_detector = None
_model_manager = None


@dataclass
class Detection:
    """Single NSFW detection result."""
    label: str
    score: float
    severity: float
    box: list[int] = field(default_factory=list)


@dataclass
class ScanResult:
    """NSFW scan result for a photo."""
    uuid: str
    path: Path
    filename: str
    date_created: str | None
    max_score: float
    classification: str
    detections: list[Detection]
    is_nsfw: bool
    context: str | None = None

    def to_dict(self) -> dict:
        return {
            "uuid": self.uuid,
            "path": str(self.path),
            "filename": self.filename,
            "date_created": self.date_created,
            "max_score": round(self.max_score, 4),
            "classification": self.classification,
            "is_nsfw": self.is_nsfw,
            "context": self.context,
            "detections": [
                {"label": d.label, "score": round(d.score, 4), "severity": round(d.severity, 2)}
                for d in self.detections
            ],
        }


def _get_detector():
    """Get Ojo NSFWDetector (lazy singleton)."""
    global _detector, _model_manager
    if _detector is None:
        logger.info("Loading Ojo NSFW detector...")
        from ojo.plugins.impl.tier1.nsfw_detection import NSFWDetector
        from ojo.models import get_model_manager

        _model_manager = get_model_manager()
        _detector = NSFWDetector()
        _detector.set_models(_model_manager)
        _detector.load_models()
        logger.info("Ojo NSFW detector loaded.")
    return _detector


def _load_image(path: Path) -> Image.Image | None:
    """Load image and convert to RGB, handling HEIC and other formats."""
    try:
        img = Image.open(path)
        if img.mode != 'RGB':
            img = img.convert('RGB')
        return img
    except Exception as e:
        logger.warning(f"Failed to load image {path}: {e}")
        return None


def scan_photo(photo: PhotoInfo, threshold: float = 0.3) -> ScanResult | None:
    """Scan a single photo for NSFW content using Ojo."""
    if not photo.path or not photo.path.exists():
        return None

    # Load image
    img = _load_image(photo.path)
    if img is None:
        return None

    detector = _get_detector()

    try:
        result = detector.process(img, photo_id=0)
    except Exception as e:
        logger.warning(f"Failed to scan {photo.uuid}: {e}")
        return None
    finally:
        img.close()

    # Parse Ojo result
    data = result.data or {}
    nsfw_score = data.get("nsfw_score", 0.0)
    classification = data.get("classification", "safe")
    context = data.get("context")
    raw_detections = data.get("detections", [])

    # Convert detections to our format
    detections = []
    for det in raw_detections:
        if isinstance(det, dict):
            detections.append(Detection(
                label=det.get("class", "unknown"),
                score=det.get("score", 0.0),
                severity=det.get("severity", 0.0),
                box=det.get("box", []),
            ))

    # Check threshold
    if nsfw_score < threshold:
        return None

    return ScanResult(
        uuid=photo.uuid,
        path=photo.path,
        filename=photo.filename,
        date_created=photo.date_created,
        max_score=nsfw_score,
        classification=classification,
        detections=detections,
        is_nsfw=(classification in ("nsfw", "suggestive")),
        context=context,
    )


def scan_photos(
    limit: int | None = None,
    threshold: float = 0.3,
    progress_callback: callable = None,
) -> Iterator[ScanResult]:
    """Scan local photos for NSFW content."""
    scanned = 0
    for photo in get_local_photos(limit=limit):
        scanned += 1
        if progress_callback:
            progress_callback(scanned, limit or 0, photo.uuid)
        result = scan_photo(photo, threshold=threshold)
        if result:
            yield result


def scan_single_path(path: str | Path, threshold: float = 0.0) -> ScanResult | None:
    """Scan a single image file by path."""
    path = Path(path)
    if not path.exists():
        logger.error(f"File not found: {path}")
        return None

    photo = PhotoInfo(
        uuid=path.stem,
        path=path,
        filename=path.name,
        date_created=None,
        is_local=True,
    )
    return scan_photo(photo, threshold=threshold)


# --- Thumbnail Generation ---

def generate_thumbnail(uuid: str, source_path: Path) -> Path | None:
    """Generate a thumbnail for review GUI."""
    THUMBNAIL_CACHE.mkdir(parents=True, exist_ok=True)
    thumb_path = THUMBNAIL_CACHE / f"{uuid}.jpg"

    if thumb_path.exists():
        return thumb_path

    try:
        img = _load_image(source_path)
        if img is None:
            return None

        img.thumbnail(THUMBNAIL_SIZE, Image.Resampling.LANCZOS)
        img.save(thumb_path, "JPEG", quality=85)
        img.close()
        return thumb_path
    except Exception as e:
        logger.warning(f"Failed to generate thumbnail for {uuid}: {e}")
        return None


def get_thumbnail_path(uuid: str) -> Path | None:
    """Get cached thumbnail path if it exists."""
    thumb_path = THUMBNAIL_CACHE / f"{uuid}.jpg"
    return thumb_path if thumb_path.exists() else None


def delete_thumbnail(uuid: str) -> bool:
    """Delete cached thumbnail for a photo."""
    thumb_path = THUMBNAIL_CACHE / f"{uuid}.jpg"
    if thumb_path.exists():
        try:
            thumb_path.unlink()
            logger.info(f"Deleted thumbnail for {uuid}")
            return True
        except Exception as e:
            logger.warning(f"Failed to delete thumbnail for {uuid}: {e}")
            return False
    return True  # Already gone


# --- Scan Logging ---

def get_scanned_uuids(include_reviewed: bool = True) -> set[str]:
    """Get set of already-scanned photo UUIDs from database.

    Args:
        include_reviewed: If True, include reviewed photos in skip list.
    """
    try:
        with get_cursor() as cur:
            if include_reviewed:
                # Skip all scanned photos
                cur.execute("SELECT uuid FROM bronze.nsfw_scan_log")
            else:
                # Only skip unreviewed photos (allow rescan of reviewed)
                cur.execute("SELECT uuid FROM bronze.nsfw_scan_log WHERE reviewed_at IS NULL")
            return {row[0] for row in cur.fetchall()}
    except DatabaseError as e:
        logger.warning(f"Could not fetch scanned UUIDs: {e}")
        return set()


def log_scan_result(result: ScanResult) -> None:
    """Log a scan result to the database."""
    try:
        with get_cursor() as cur:
            cur.execute("""
                INSERT INTO bronze.nsfw_scan_log (uuid, filename, max_score, classification, flagged)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (uuid) DO UPDATE SET
                    scanned_at = NOW(),
                    max_score = EXCLUDED.max_score,
                    classification = EXCLUDED.classification,
                    flagged = EXCLUDED.flagged
            """, (result.uuid, result.filename, result.max_score, result.classification, result.is_nsfw))
    except DatabaseError as e:
        logger.warning(f"Could not log scan result: {e}")


def log_clean_scan(uuid: str, filename: str) -> None:
    """Log a clean (non-flagged) scan to the database."""
    try:
        with get_cursor() as cur:
            cur.execute("""
                INSERT INTO bronze.nsfw_scan_log (uuid, filename, max_score, classification, flagged)
                VALUES (%s, %s, 0, 'safe', FALSE)
                ON CONFLICT (uuid) DO UPDATE SET
                    scanned_at = NOW(),
                    max_score = 0,
                    classification = 'safe',
                    flagged = FALSE
            """, (uuid, filename))
    except DatabaseError as e:
        logger.warning(f"Could not log clean scan: {e}")


def scan_photos_with_logging(
    limit: int | None = None,
    threshold: float = 0.3,
    rescan: bool = False,
    progress_callback: callable = None,
) -> Iterator[ScanResult]:
    """Scan local photos for NSFW content, with database logging."""
    # Get already-scanned UUIDs if not rescanning
    scanned_uuids = set() if rescan else get_scanned_uuids()
    if scanned_uuids:
        logger.info(f"Skipping {len(scanned_uuids)} already-scanned photos")

    scanned = 0
    skipped = 0
    for photo in get_local_photos(limit=None):  # Get all, filter later
        if photo.uuid in scanned_uuids:
            skipped += 1
            continue

        scanned += 1
        if limit and scanned > limit:
            break

        if progress_callback:
            progress_callback(scanned, limit or 0, photo.uuid)

        result = scan_photo(photo, threshold=threshold)

        if result:
            log_scan_result(result)
            # Generate thumbnail for flagged photos (for fast review)
            if photo.path:
                generate_thumbnail(result.uuid, photo.path)
            yield result
        else:
            # Log clean scans too
            log_clean_scan(photo.uuid, photo.filename)
