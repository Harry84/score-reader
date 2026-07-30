"""Adapter between raw uploaded image bytes and score_extractor's vision call,
which only knows how to read from a file path. Keeps the temp-file lifecycle
out of the API layer and the ingestion workflow core.
"""

import os
import tempfile

from score_extractor import extract_scores_from_image


def extract_from_image_bytes(image_bytes, suffix=".jpg"):
    fd, temp_path = tempfile.mkstemp(suffix=suffix)
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(image_bytes)
        return extract_scores_from_image(temp_path)
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)
