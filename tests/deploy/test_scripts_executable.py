"""The README says `sudo ./install.sh`: that only works if git hands out the script as executable.

Git on Windows often doesn't track the executable bit, so a script added from there silently loses it.
"""

import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.skipif(shutil.which("git") is None or not (ROOT / ".git").exists(), reason="needs a git checkout")
def test_every_shell_script_is_executable_in_git():
    listed = subprocess.run(["git", "ls-files", "-s", "--", "*.sh"], cwd=ROOT, capture_output=True, text=True,
                            check=True).stdout.splitlines()
    assert listed, "no shell scripts found"
    not_executable = [line.split("\t", 1)[1] for line in listed if not line.startswith("100755")]
    assert not_executable == [], f"run: git update-index --chmod=+x {' '.join(not_executable)}"
