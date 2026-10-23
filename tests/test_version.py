import os
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

# app builds its NudeDetector at import time; stub it exactly as test_pdf does.
IMPORT_APP = """
from unittest.mock import Mock, patch
import nudenet
with patch.object(nudenet, "NudeDetector", return_value=Mock()):
    import app
print(app.app.version)
"""


def reported_version(env_value: str | None) -> str:
    """Import app in a fresh interpreter, so APP_VERSION is read at import
    time exactly as it is when uvicorn loads the module in the image."""
    env = {k: v for k, v in os.environ.items() if k != "APP_VERSION"}
    if env_value is not None:
        env["APP_VERSION"] = env_value
    out = subprocess.run(
        [sys.executable, "-c", IMPORT_APP],
        cwd=REPO, env=env, capture_output=True, text=True, check=True,
    )
    return out.stdout.strip().splitlines()[-1]


def test_version_comes_from_app_version():
    assert reported_version("1.2.3") == "1.2.3"


def test_version_defaults_to_dev_outside_a_release_build():
    assert reported_version(None) == "dev"
