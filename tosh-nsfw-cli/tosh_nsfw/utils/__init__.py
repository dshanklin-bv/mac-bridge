"""Utility modules for tosh-nsfw-cli."""

from .db import get_connection
from .photos import get_local_photos

__all__ = ["get_connection", "get_local_photos"]
