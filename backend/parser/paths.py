"""
Shared path resolution for GR corpus directories.
"""

from __future__ import annotations

import os
from pathlib import Path


def resolve_text_folder(root: Path) -> Path:
    """
    Resolve OCR fulltext directory.

    Priority:
    1. GR_FULLTEXT_DIR environment variable
    2. backend/maha_grs/fulltext
    3. backend/maha_grs 2/maha_grs/fulltext (legacy)
  """
    env_path = os.getenv("GR_FULLTEXT_DIR")
    if env_path:
        p = Path(env_path).expanduser().resolve()
        if p.is_dir():
            return p
        print(f"Warning: GR_FULLTEXT_DIR={env_path} does not exist; using auto-detect.")

    candidates = [
        root / "maha_grs" / "fulltext",
        root / "maha_grs 2" / "maha_grs" / "fulltext",
    ]
    for path in candidates:
        if path.is_dir():
            return path

    return candidates[0]


def resolve_metadata_folder(root: Path) -> Path:
    env_path = os.getenv("GR_METADATA_DIR")
    if env_path:
        return Path(env_path).expanduser().resolve()
    return root / "metadata"
