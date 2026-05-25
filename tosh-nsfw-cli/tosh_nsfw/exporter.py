"""
Export detected NSFW photos to a review folder.
"""

import json
import logging
import shutil
from datetime import datetime
from pathlib import Path

from .scanner import ScanResult

logger = logging.getLogger(__name__)


def export_photos(
    results: list[ScanResult],
    output_dir: str | Path,
    create_index: bool = True,
) -> int:
    """
    Export NSFW photos to a review folder.

    Photos are copied with naming: {score}_{uuid}_{original_name}

    Args:
        results: List of ScanResult objects to export.
        output_dir: Destination directory.
        create_index: Whether to create index.json with metadata.

    Returns:
        Number of photos exported.
    """
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    exported = 0
    index_data = []

    for result in results:
        if not result.path or not result.path.exists():
            logger.warning(f"Skipping {result.uuid}: file not found")
            continue

        # Create filename: 0.95_uuid_originalname.jpg
        score_str = f"{result.max_score:.2f}".replace(".", "")
        new_name = f"{score_str}_{result.uuid}_{result.filename}"
        dest_path = output_path / new_name

        try:
            shutil.copy2(result.path, dest_path)
            exported += 1
            logger.info(f"Exported: {new_name}")

            index_data.append({
                "uuid": result.uuid,
                "original_path": str(result.path),
                "exported_name": new_name,
                "max_score": result.max_score,
                "date_created": result.date_created,
                "detections": [
                    {"label": d.label, "score": d.score}
                    for d in result.detections
                ],
            })

        except Exception as e:
            logger.error(f"Failed to export {result.uuid}: {e}")

    if create_index and index_data:
        index_path = output_path / "index.json"
        with open(index_path, "w") as f:
            json.dump({
                "exported_at": datetime.now().isoformat(),
                "count": exported,
                "photos": index_data,
            }, f, indent=2)
        logger.info(f"Created index: {index_path}")

    return exported


def export_single(result: ScanResult, output_dir: str | Path) -> Path | None:
    """
    Export a single NSFW photo.

    Args:
        result: ScanResult to export.
        output_dir: Destination directory.

    Returns:
        Path to exported file, or None on failure.
    """
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    if not result.path or not result.path.exists():
        return None

    score_str = f"{result.max_score:.2f}".replace(".", "")
    new_name = f"{score_str}_{result.uuid}_{result.filename}"
    dest_path = output_path / new_name

    try:
        shutil.copy2(result.path, dest_path)
        return dest_path
    except Exception as e:
        logger.error(f"Failed to export {result.uuid}: {e}")
        return None
