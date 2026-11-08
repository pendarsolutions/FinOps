"""deploy/backup.sh, driven with stand-ins for `docker` and `id` that record every call.

The real database round trip (pg_dump into pg_restore) is checked on a server; this pins down everything around it:
what a backup contains, which settings a restore keeps, the order of the steps, rotation, and refusing to go on
when it isn't safe.
"""

from __future__ import annotations

import io
import os
import shutil
import subprocess
import tarfile
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
BASH = shutil.which("bash")
pytestmark = pytest.mark.skipif(BASH is None, reason="needs bash")

FAKE_DOCKER = r"""#!/usr/bin/env bash
echo "docker $*" >> "$FAKE_LOG"
case "$*" in
  "compose ps --status running --services") [ -n "${FAKE_NO_DB:-}" ] || printf 'postgres\nredis\napi\n' ;;
  *"pg_dump"*) printf 'PGDMP %s' "${FAKE_DB:-original}" ;;
  *"api tar -C /app/var/uploads -cf - ."*) printf 'uploads %s' "${FAKE_DB:-original}" ;;
  *"pg_restore"*) cat > "$FAKE_OUT/restored.dump" ;;
  *"find /app/var/uploads"*) cat > "$FAKE_OUT/restored-uploads.tar" ;;
esac
"""

CURRENT_ENV = """FINOPS_APP_IMAGE=ghcr.io/pendarsolutions/finops-agent-app:0.3.0
FINOPS_WEB_IMAGE=ghcr.io/pendarsolutions/finops-agent-web:0.3.0
POSTGRES_PASSWORD=this-servers-db-password
FINOPS_JWT_SECRET=this-servers-jwt
FINOPS_CREDENTIALS_KEY=this-servers-key
FINOPS_CORS_ORIGINS=["https://new.example.ir"]
FINOPS_PUBLIC_URL=https://new.example.ir
FINOPS_HTTPS_PORT=443
FINOPS_HTTP_BIND=80
"""


def _sh_path(p: Path) -> str:
    """A path bash and GNU tar read as a local file on every platform (tar takes "C:/..." for a remote host)."""
    s = p.as_posix()
    if os.name == "nt" and len(s) > 1 and s[1] == ":":
        return f"/{s[0].lower()}{s[2:]}"
    return s


@pytest.fixture
def box(tmp_path):
    install = tmp_path / "opt"
    install.mkdir()
    shutil.copy(ROOT / "deploy" / "backup.sh", install / "backup.sh")
    (install / "compose.yml").write_text("name: finops-agent\n")
    (install / ".env").write_text(CURRENT_ENV.replace("this-servers", "original"), newline="\n")
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    for name, body in (("docker", FAKE_DOCKER), ("id", "#!/usr/bin/env bash\necho 0\n")):
        (bin_dir / name).write_text(body, newline="\n")
        (bin_dir / name).chmod(0o755)
    out = tmp_path / "out"
    out.mkdir()
    env = dict(os.environ, FAKE_LOG=_sh_path(tmp_path / "docker.log"), FAKE_OUT=_sh_path(out),
               FINOPS_BACKUP_DIR=_sh_path(tmp_path / "backups"))
    if os.name != "nt":
        env["PATH"] = f"{bin_dir}{os.pathsep}{env['PATH']}"

    class Box:
        dir, backups, log, restored = install, tmp_path / "backups", tmp_path / "docker.log", out

        def run(self, *args, extra=None, stdin=None):
            e = dict(env, **(extra or {}))
            if os.name == "nt":  # Git Bash: put the stand-ins first on its own PATH
                return subprocess.run([BASH, "-c", 'PATH="$FAKE_BIN:$PATH" exec bash "$0" "$@"',
                                       _sh_path(install / "backup.sh"), *args],
                                      env=dict(e, FAKE_BIN=_sh_path(bin_dir)), capture_output=True, text=True,
                                      input=stdin, timeout=60)
            return subprocess.run([BASH, str(install / "backup.sh"), *args], env=e, capture_output=True, text=True,
                                  input=stdin, timeout=60)

        def calls(self):
            return self.log.read_text().splitlines() if self.log.exists() else []

        def files(self, pattern="finops-agent-*.tar.gz"):
            return sorted(self.backups.glob(pattern))

    return Box()


def _members(path: Path) -> dict[str, bytes]:
    with tarfile.open(path) as t:
        return {m.name.lstrip("./"): t.extractfile(m).read() for m in t.getmembers() if m.isfile()}


def test_backup_holds_the_database_uploads_and_settings(box):
    r = box.run()
    assert r.returncode == 0, r.stderr
    [made] = box.files()
    contents = _members(made)
    assert contents["database.dump"] == b"PGDMP original"
    assert contents["uploads.tar"] == b"uploads original"
    assert b"FINOPS_CREDENTIALS_KEY=original-key" in contents["env"]
    assert contents["app-image"].strip() == b"ghcr.io/pendarsolutions/finops-agent-app:0.3.0"
    assert "created" in contents
    assert any("pg_dump -U finops -d finops --format=custom" in c for c in box.calls())


def test_keep_rotates_dated_backups_only(box):
    for _ in range(3):
        assert box.run("--keep", "2").returncode == 0
        time.sleep(1.1)  # names are to the second
    before_restore = box.backups / "finops-agent-before-restore-20260101-000000.tar.gz"
    before_restore.write_bytes(b"kept")
    assert box.run("--keep", "2").returncode == 0
    dated = box.files("finops-agent-[0-9]*.tar.gz")
    assert len(dated) == 2
    assert before_restore.exists()


def test_restore_takes_the_datas_keys_and_keeps_the_machines_own(box):
    assert box.run().returncode == 0
    [old] = box.files()
    # a new server: its own database password, address and images; the backup's keys must replace its keys
    (box.dir / ".env").write_text(CURRENT_ENV, newline="\n")
    box.log.unlink()
    r = box.run("--restore", _sh_path(old), "--yes", extra={"FAKE_DB": "new-server"})
    assert r.returncode == 0, r.stderr + r.stdout

    env = (box.dir / ".env").read_text()
    assert "FINOPS_JWT_SECRET=original-jwt" in env and "FINOPS_CREDENTIALS_KEY=original-key" in env
    assert "POSTGRES_PASSWORD=this-servers-db-password" in env
    assert "FINOPS_PUBLIC_URL=https://new.example.ir" in env
    assert "FINOPS_APP_IMAGE=ghcr.io/pendarsolutions/finops-agent-app:0.3.0" in env
    assert env.count("FINOPS_JWT_SECRET=") == 1 and env.count("POSTGRES_PASSWORD=") == 1
    assert list(box.dir.glob(".env.before-restore-*"))[0].read_text() == CURRENT_ENV

    assert (box.restored / "restored.dump").read_bytes() == b"PGDMP original"
    assert (box.restored / "restored-uploads.tar").read_bytes() == b"uploads original"
    # the data being replaced was backed up first
    [undo] = box.files("finops-agent-before-restore-*.tar.gz")
    assert _members(undo)["database.dump"] == b"PGDMP new-server"

    order = [next(k for k in ("pg_dump", "stop", "DROP DATABASE", "pg_restore", "find /app", "up -d") if k in c)
             for c in box.calls() if any(k in c for k in ("pg_dump", "stop", "DROP DATABASE", "pg_restore",
                                                            "find /app", "up -d"))]
    assert order == ["pg_dump", "stop", "DROP DATABASE", "pg_restore", "find /app", "up -d"]


def test_restore_asks_first_and_changes_nothing_without_an_answer(box):
    assert box.run().returncode == 0
    [old] = box.files()
    box.log.unlink()
    r = box.run("--restore", _sh_path(old), stdin="")
    assert r.returncode != 0 and "--yes" in r.stderr
    assert not any("stop" in c or "pg_restore" in c for c in box.calls())


def test_restore_refuses_a_file_that_isnt_a_backup(box, tmp_path):
    bogus = tmp_path / "photo.tar.gz"
    with tarfile.open(bogus, "w:gz") as t:
        data = b"not a backup"
        info = tarfile.TarInfo("photo.jpg")
        info.size = len(data)
        t.addfile(info, io.BytesIO(data))
    r = box.run("--restore", _sh_path(bogus), "--yes")
    assert r.returncode != 0 and "isn't a FinOps agent backup" in r.stderr
    assert not any("stop" in c for c in box.calls())


def test_nothing_is_written_when_the_database_is_down(box):
    r = box.run(extra={"FAKE_NO_DB": "1"})
    assert r.returncode != 0 and "database isn't running" in r.stderr
    assert box.files() == []


def test_restore_stops_if_the_safety_backup_fails(box):
    assert box.run().returncode == 0
    [old] = box.files()
    box.log.unlink()
    r = box.run("--restore", _sh_path(old), "--yes", extra={"FAKE_NO_DB": "1"})
    assert r.returncode != 0
    assert not any("stop" in c or "DROP DATABASE" in c for c in box.calls())
