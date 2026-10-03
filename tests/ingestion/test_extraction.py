import os
from unittest.mock import patch

from ingestion.extraction import extract_from_image_bytes


@patch("ingestion.extraction.extract_scores_from_image")
def test_extract_from_image_bytes_writes_calls_and_cleans_up_temp_file(mock_extract):
    captured = {}

    def fake_extract(path):
        captured["path"] = path
        with open(path, "rb") as f:
            captured["contents"] = f.read()
        return {"match_result": "IMPERIAL VICTORY", "teams": {}}

    mock_extract.side_effect = fake_extract

    result = extract_from_image_bytes(b"fake-image-bytes", suffix=".png")

    assert result == {"match_result": "IMPERIAL VICTORY", "teams": {}}
    assert captured["contents"] == b"fake-image-bytes"
    assert captured["path"].endswith(".png")
    assert not os.path.exists(captured["path"])
