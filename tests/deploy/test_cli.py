"""deploy/finops-agent and install.sh, driven with stand-ins for docker, ss, curl and the rest that record every call.

A real server run (Docker pulling, Caddy getting a certificate) is checked on a server; this pins down what the
commands write, what they refuse, and what they ask Docker to do.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
BASH = shutil.which("bash")
pytestmark = pytest.mark.skipif(BASH is None, reason="needs bash")

FAKES = {
    "docker": r"""#!/usr/bin/env bash
echo "docker $*" >> "$FAKE_LOG"
case "$*" in
  "compose ps -q api") echo api-container ;;
  "inspect -f {{.State.Health.Status}} api-container") echo healthy ;;
  "compose ps --status running --services") printf '%s\n' ${FAKE_RUNNING-postgres redis api worker beat web caddy} ;;
  "pull -q "*) [ -z "${FAKE_NO_REGISTRY:-}" ] || exit 1 ;;
  "image inspect "*) [ -z "${FAKE_NO_IMAGES:-}" ] || exit 1 ;;
  "create "*) echo new-container ;;
  "load") cat > /dev/null ;;
esac
if [ "$1" = cp ]; then cp -r "$FAKE_DEPLOY/." "$3"; fi
exit 0
""",
    "id": "#!/usr/bin/env bash\necho 0\n",
    "ss": '#!/usr/bin/env bash\np="${2##*:}"; for b in ${FAKE_BUSY:-}; do [ "$b" = "$p" ] && echo "LISTEN 0 4096 *:$p"; done; exit 0\n',
    "hostname": "#!/usr/bin/env bash\necho 203.0.113.10 10.0.0.5\n",
    "systemctl": "#!/usr/bin/env bash\nexit 0\n",
    "getent": "#!/usr/bin/env bash\necho \"203.0.113.10 STREAM $3\"\n",
    "curl": r"""#!/usr/bin/env bash
case "$*" in
  *api.github.com*) echo "{\"tag_name\": \"v${FAKE_LATEST:-0.2.0}\"}" ;;
  *http_code*) printf '%s' "${FAKE_HTTP:-200}" ;;
esac
exit 0
""",
}


def _sh_path(p: Path) -> str:
    """A path bash reads as a local file on every platform."""
    s = p.as_posix()
    if os.name == "nt" and len(s) > 1 and s[1] == ":":
        return f"/{s[0].lower()}{s[2:]}"
    return s


class Box:
    def __init__(self, tmp: Path):
        self.tmp = tmp
        self.dir = tmp / "opt"
        self.dir.mkdir()
        shutil.copy(ROOT / "deploy" / "compose.install.yml", self.dir / "compose.yml")
        shutil.copy(ROOT / "deploy" / "backup.sh", self.dir / "backup.sh")
        self.cli = ROOT / "deploy" / "finops-agent"
        self.fakes = tmp / "fakes"
        self.fakes.mkdir()
        for name, body in FAKES.items():
            (self.fakes / name).write_text(body, newline="\n")
            (self.fakes / name).chmod(0o755)
        self.cron = tmp / "cron"
        self.cron.mkdir()
        self.bin = tmp / "bin"
        self.log = tmp / "docker.log"
        self.deploy = tmp / "new-deploy"
        self.env_vars = {
            "FINOPS_DIR": _sh_path(self.dir), "FINOPS_CRON_DIR": _sh_path(self.cron), "FINOPS_BIN_DIR": _sh_path(self.bin),
            "FINOPS_BACKUP_DIR": _sh_path(tmp / "backups"), "FINOPS_HEALTH_WAIT": "0", "FINOPS_HEALTH_TRIES": "2",
            "FAKE_LOG": _sh_path(self.log), "FAKE_DEPLOY": _sh_path(self.deploy), "FAKE_BIN": _sh_path(self.fakes),
            "FINOPS_DOCKER_DAEMON_JSON": _sh_path(tmp / "daemon.json"),
            # questions read this instead of the terminal: empty, so a question nobody expected fails fast
            "FINOPS_TTY": "/dev/null",
        }

    def run(self, *args, extra=None, stdin=None, script=None):
        """Run finops-agent (or another script) with the stand-ins first on PATH and no terminal."""
        env = {k: v for k, v in os.environ.items() if not k.startswith(("FINOPS_", "FAKE_"))}
        env.update(self.env_vars, **(extra or {}))
        target = _sh_path(script or self.cli)
        return subprocess.run([BASH, "-c", 'PATH="$FAKE_BIN:$PATH" exec bash "$0" "$@"', target, *args], env=env,
                              capture_output=True, text=True, input=stdin if stdin is not None else "", timeout=120)

    def ok(self, *args, **kw):
        r = self.run(*args, **kw)
        assert r.returncode == 0, f"{args}\n{r.stdout}\n{r.stderr}"
        return r

    def env(self) -> dict[str, str]:
        return dict(line.split("=", 1) for line in (self.dir / ".env").read_text().splitlines() if "=" in line)

    def calls(self) -> list[str]:
        return self.log.read_text().splitlines() if self.log.exists() else []

    def caddyfile(self) -> str:
        return (self.dir / "Caddyfile").read_text()


@pytest.fixture
def box(tmp_path):
    return Box(tmp_path)


# ------------------------------------------------------------------ setup

def test_fresh_install_with_a_domain(box):
    r = box.ok("setup", "--domain", "finops.example.ir")
    env = box.env()
    assert re.fullmatch(r"[0-9a-f]{64}", env["POSTGRES_PASSWORD"]) and re.fullmatch(r"[0-9a-f]{64}", env["FINOPS_JWT_SECRET"])
    assert len(env["FINOPS_CREDENTIALS_KEY"]) == 44
    assert env["FINOPS_APP_IMAGE"] == "ghcr.io/pendarsolutions/finops-agent-app:" + _cli_version()
    assert env["FINOPS_ADDRESS"] == "finops.example.ir" and env["FINOPS_BEHIND_PROXY"] == "false"
    assert env["FINOPS_PUBLIC_URL"] == "https://finops.example.ir"
    assert env["FINOPS_CORS_ORIGINS"] == "'[\"https://finops.example.ir\"]'"
    assert (env["FINOPS_HTTPS_PORT"], env["FINOPS_HTTPS_BIND"], env["FINOPS_HTTP_BIND"]) == ("443", "443", "80")
    assert env["FINOPS_DAILY_BACKUP"] == "true" and env["FINOPS_AI_PROVIDER"] == "offline"
    assert box.caddyfile().startswith("finops.example.ir {\n")
    assert "backup.sh --keep 14" in (box.cron / "finops-agent-backup").read_text()
    assert any(c.startswith("docker compose up -d") for c in box.calls())
    assert "create the first account" in r.stdout and "https://finops.example.ir" in r.stdout
    if os.name != "nt":
        assert (box.dir / ".env").stat().st_mode & 0o777 == 0o600


def test_busy_ports_are_left_alone(box):
    box.ok("setup", "--yes", extra={"FAKE_BUSY": "80 443"})
    env = box.env()
    assert env["FINOPS_ADDRESS"] == "203.0.113.10" and env["FINOPS_PUBLIC_URL"] == "https://203.0.113.10:8443"
    assert env["FINOPS_HTTPS_PORT"] == "8443" and env["FINOPS_HTTP_BIND"] == "127.0.0.1:18080"
    assert "default_sni 203.0.113.10" in box.caddyfile() and "tls internal" in box.caddyfile()


def test_running_again_keeps_secrets_address_and_ports(box):
    box.ok("setup", "--domain", "finops.example.ir")
    before = box.env()
    # now 443 and 80 are this app's own, so they look busy
    box.ok("setup", extra={"FAKE_BUSY": "80 443"})
    assert box.env() == before
    assert box.caddyfile().startswith("finops.example.ir {\n")


def test_an_install_from_before_0_3_0_keeps_its_domain(box):
    """0.2.0 kept the address only in the Caddyfile, and re-running its installer without --domain lost it."""
    (box.dir / ".env").write_text("FINOPS_APP_IMAGE=ghcr.io/pendarsolutions/finops-agent-app:0.2.0\n"
                                  "FINOPS_WEB_IMAGE=ghcr.io/pendarsolutions/finops-agent-web:0.2.0\n"
                                  "POSTGRES_PASSWORD=old-db\nFINOPS_JWT_SECRET=old-jwt\nFINOPS_CREDENTIALS_KEY=old-key\n"
                                  'FINOPS_CORS_ORIGINS=["https://finops.example.ir"]\nFINOPS_AI_PROVIDER=offline\n'
                                  "FINOPS_HTTPS_PORT=443\nFINOPS_HTTP_BIND=80\n", newline="\n")
    (box.dir / "Caddyfile").write_text("finops.example.ir {\n  encode gzip\n}\n", newline="\n")
    box.ok("setup", "--version", "0.3.0", extra={"FAKE_BUSY": "80 443"})
    env = box.env()
    assert env["FINOPS_ADDRESS"] == "finops.example.ir" and env["FINOPS_PUBLIC_URL"] == "https://finops.example.ir"
    assert env["POSTGRES_PASSWORD"] == "old-db" and env["FINOPS_CREDENTIALS_KEY"] == "old-key"
    assert env["FINOPS_APP_IMAGE"].endswith(":0.3.0") and env["FINOPS_DAILY_BACKUP"] == "true"


def test_an_older_installer_wont_downgrade(box):
    (box.dir / ".env").write_text("FINOPS_APP_IMAGE=ghcr.io/pendarsolutions/finops-agent-app:9.0.0\n", newline="\n")
    r = box.run("setup", "--yes")
    assert r.returncode != 0 and "9.0.0 is installed" in r.stderr
    assert not any("up -d" in c for c in box.calls())


def test_behind_your_own_proxy(box):
    box.ok("setup", "--proxy", "https://finops.example.ir/", "--listen", "8080")
    env = box.env()
    assert env["FINOPS_BEHIND_PROXY"] == "true" and env["FINOPS_PUBLIC_URL"] == "https://finops.example.ir"
    assert (env["FINOPS_HTTPS_PORT"], env["FINOPS_HTTPS_BIND"]) == ("8080", "127.0.0.1:8080")
    caddy = box.caddyfile()
    assert "auto_https off" in caddy and "trusted_proxies static private_ranges" in caddy and "http://:8080 {" in caddy
    assert box.run("setup", "--proxy", "https://example.ir/finops").returncode != 0  # served at the root only


def test_settings_given_at_install_are_checked_before_anything_is_written(box):
    r = box.run("setup", "--yes", "--set", "SMTP_PORT=not-a-port")
    assert r.returncode != 0 and "not a port" in r.stderr
    assert not (box.dir / ".env").exists()
    box.ok("setup", "--yes", "--set", "smtp_host=mail.example.ir", "--set", "ALERT_EMAIL_TO=ops@example.ir")
    assert box.env()["FINOPS_SMTP_HOST"] == "mail.example.ir"


def test_questions_in_a_terminal(box, tmp_path):
    answers = tmp_path / "answers"
    answers.write_text("finops.example.ir\n\nn\ny\nmail.example.ir\n\nalerts@example.ir\nmail pass\nops@example.ir\nn\ny\n",
                       newline="\n")
    box.ok("setup", extra={"FINOPS_TTY": _sh_path(answers)})
    env = box.env()
    assert env["FINOPS_ADDRESS"] == "finops.example.ir" and env["FINOPS_HTTPS_PORT"] == "443"
    assert env["FINOPS_DAILY_BACKUP"] == "false" and not (box.cron / "finops-agent-backup").exists()
    assert env["FINOPS_SMTP_HOST"] == "mail.example.ir" and env["FINOPS_SMTP_PORT"] == "587"
    assert env["FINOPS_SMTP_PASSWORD"] == "'mail pass'" and env["FINOPS_ALERT_EMAIL_TO"] == "ops@example.ir"
    assert "FINOPS_BALE_BOT_TOKEN" not in env


def test_saying_no_changes_nothing(box, tmp_path):
    answers = tmp_path / "answers"
    answers.write_text("\n\n\nn\nn\nn\n", newline="\n")
    r = box.run("setup", extra={"FINOPS_TTY": _sh_path(answers)})
    assert r.returncode != 0 and not (box.dir / ".env").exists()


# ------------------------------------------------------------------ config and address

def test_config_set_get_list_unset(box):
    box.ok("setup", "--yes")
    box.log.unlink()
    r = box.ok("config", "set", "smtp_host=mail.example.ir", "SMTP_PORT=465", "smtp_starttls=no", "SMTP_PASSWORD",
               stdin="p@ss w$rd\n")
    env = box.env()
    assert env["FINOPS_SMTP_PORT"] == "465" and env["FINOPS_SMTP_STARTTLS"] == "false"
    assert env["FINOPS_SMTP_PASSWORD"] == "'p@ss w$rd'"  # quoted, so Compose reads it literally
    assert "p@ss" not in r.stderr  # secrets aren't echoed
    assert any(c.startswith("docker compose up -d") for c in box.calls())
    assert box.ok("config", "get", "smtp_password").stdout == "p@ss w$rd\n"
    listing = box.ok("config").stdout
    assert "FINOPS_SMTP_PASSWORD=(hidden)" in listing and "FINOPS_CREDENTIALS_KEY=(hidden)" in listing
    assert "FINOPS_SMTP_HOST=mail.example.ir" in listing
    assert "Nothing changed" in box.ok("config", "set", "SMTP_PORT=465").stderr
    box.ok("config", "unset", "smtp_password")
    assert "FINOPS_SMTP_PASSWORD" not in box.env()


def test_config_refuses_what_it_shouldnt_change(box):
    box.ok("setup", "--yes")
    before = (box.dir / ".env").read_text()
    for args, says in [(("set", "CREDENTIALS_KEY=x"), "can't be changed"), (("set", "PUBLIC_URL=https://x.ir"), "address"),
                       (("set", "APP_IMAGE=evil/app:1"), "upgrade"), (("set", "SMTP_PROT=25"), "isn't a setting"),
                       (("set", "ALERT_EMAIL_TO=not-an-email"), "not an email"), (("unset", "JWT_SECRET"), "can't be changed"),
                       (("set", "SMTP_HOST=ok.example.ir", "SMTP_PORT=x"), "not a port")]:
        r = box.run("config", *args)
        assert r.returncode != 0 and says in r.stderr, (args, r.stderr)
    assert (box.dir / ".env").read_text() == before  # nothing half-applied


def test_turning_nightly_backups_off_and_on(box):
    box.ok("setup", "--yes")
    box.ok("config", "set", "DAILY_BACKUP=false")
    assert not (box.cron / "finops-agent-backup").exists()
    box.ok("config", "set", "daily_backup=on")
    assert (box.cron / "finops-agent-backup").exists()


def test_changing_the_address(box):
    box.ok("setup", "--domain", "finops.example.ir")
    box.log.unlink()
    box.ok("address", "--ip", "198.51.100.7", "--port", "9443", extra={"FAKE_BUSY": "80 443"})
    env = box.env()
    assert env["FINOPS_PUBLIC_URL"] == "https://198.51.100.7:9443" and env["FINOPS_HTTPS_BIND"] == "9443"
    assert env["FINOPS_CORS_ORIGINS"] == "'[\"https://198.51.100.7:9443\"]'"
    assert "https://198.51.100.7:9443 {" in box.caddyfile()
    assert "docker compose restart caddy" in box.calls()
    assert box.ok("address").stdout.strip() == "https://198.51.100.7:9443"


# ------------------------------------------------------------------ upgrade, status, doctor, uninstall

def _cli_version() -> str:
    return re.search(r'^VERSION="([^"]+)"', (ROOT / "deploy" / "finops-agent").read_text(), re.M).group(1)


def _new_version_files(box: Box, version: str) -> None:
    box.deploy.mkdir()
    shutil.copy(ROOT / "deploy" / "compose.install.yml", box.deploy / "compose.install.yml")
    (box.deploy / "compose.install.yml").write_text((box.deploy / "compose.install.yml").read_text() + f"# {version}\n",
                                                    newline="\n")
    shutil.copy(ROOT / "deploy" / "backup.sh", box.deploy / "backup.sh")
    cli = re.sub(r'^VERSION="[^"]+"', f'VERSION="{version}"', box.cli.read_text(), count=1, flags=re.M)
    (box.deploy / "finops-agent").write_text(cli, newline="\n")


def test_upgrade_brings_the_new_versions_files_and_keeps_everything_else(box):
    box.ok("setup", "--domain", "finops.example.ir")
    shutil.copy(box.cli, box.dir / "finops-agent")
    before = box.env()
    _new_version_files(box, "9.1.0")
    box.log.unlink()
    r = box.ok("upgrade", "--no-backup", "--yes", extra={"FAKE_LATEST": "9.1.0", "FAKE_BUSY": "80 443"})
    env = box.env()
    assert env["FINOPS_APP_IMAGE"] == "ghcr.io/pendarsolutions/finops-agent-app:9.1.0"
    assert {k: v for k, v in env.items() if "IMAGE" not in k} == {k: v for k, v in before.items() if "IMAGE" not in k}
    assert (box.dir / "compose.yml").read_text().endswith("# 9.1.0\n")
    assert 'VERSION="9.1.0"' in (box.dir / "finops-agent").read_text()
    calls = box.calls()
    assert "docker pull -q ghcr.io/pendarsolutions/finops-agent-app:9.1.0" in calls
    assert any(c.startswith("docker compose up -d") for c in calls)
    assert "9.1.0 is running" in r.stdout


def test_upgrade_refuses_to_go_back(box):
    box.ok("setup", "--yes", "--version", "9.0.0")
    r = box.run("upgrade", "0.1.0", "--yes")
    assert r.returncode != 0 and "older" in r.stderr
    assert "already" in box.ok("upgrade", "9.0.0").stderr


def test_upgrade_stops_if_the_backup_fails(box):
    box.ok("setup", "--yes")
    r = box.run("upgrade", "9.1.0", "--yes", extra={"FAKE_RUNNING": ""})  # backup.sh refuses: database not running
    assert r.returncode != 0 and "nothing was upgraded" in r.stderr
    assert not any("pull" in c and "9.1.0" in c for c in box.calls())


def test_status_and_doctor(box):
    box.ok("setup", "--yes")
    status = box.ok("status").stdout
    assert "https://203.0.113.10" in status and "Email:    not set up" in status
    doctor = box.ok("doctor").stdout
    assert "all services are running" in doctor and "the dashboard answers" in doctor
    r = box.run("doctor", extra={"FAKE_RUNNING": "postgres redis api beat web caddy", "FAKE_LATEST": "9.9.9"})
    assert r.returncode == 1 and "worker isn't running" in r.stdout and "9.9.9 is out" in r.stdout


def test_uninstall_keeps_the_data_unless_asked(box):
    box.ok("setup", "--yes")
    box.bin.mkdir()
    assert box.run("uninstall").returncode != 0  # no terminal and no --yes: refuses
    box.ok("uninstall", "--yes")
    assert "docker compose down --remove-orphans" in box.calls()
    assert (box.dir / ".env").exists() and not (box.cron / "finops-agent-backup").exists()
    box.ok("uninstall", "--yes", "--delete-data")
    assert "docker compose down --volumes --remove-orphans" in box.calls() and not box.dir.exists()


def test_commands_need_root(box):
    box.ok("setup", "--yes")
    (box.fakes / "id").write_text("#!/usr/bin/env bash\necho 1000\n", newline="\n")
    r = box.run("config", "set", "SMTP_HOST=x.example.ir")
    assert r.returncode != 0 and "sudo finops-agent config" in r.stderr
    assert box.ok("config", "keys").stdout.count("SMTP_") >= 5  # reading the list needs nothing


# ------------------------------------------------------------------ the one-file installer

@pytest.fixture
def installer(tmp_path):
    out = tmp_path / "install.sh"
    r = subprocess.run([BASH, _sh_path(ROOT / "scripts" / "make-installer.sh"), _sh_path(out)], capture_output=True,
                       text=True, env=dict(os.environ, FINOPS_VERSION="9.2.0", FINOPS_IMAGE_PREFIX="registry.example.ir/acme"),
                       timeout=60)
    assert r.returncode == 0, r.stderr
    return out


def test_the_released_installer_carries_the_deploy_files(installer, tmp_path):
    # everything but the last line, which runs main
    lib = tmp_path / "lib.sh"
    lib.write_text("\n".join(installer.read_text().splitlines()[:-1]) + "\n", newline="\n")
    for name in ("compose.install.yml", "backup.sh"):
        r = subprocess.run([BASH, "-c", f'source "$0"; embedded_file {name}', _sh_path(lib)], capture_output=True,
                           text=True, timeout=30)
        assert r.stdout == (ROOT / "deploy" / name).read_text(), name
    r = subprocess.run([BASH, "-c", 'source "$0"; embedded_file finops-agent', _sh_path(lib)], capture_output=True,
                       text=True, timeout=30)
    assert 'VERSION="9.2.0"' in r.stdout and 'IMAGE_PREFIX="registry.example.ir/acme"' in r.stdout


def test_curl_pipe_bash_installs(box, installer):
    """The way the website says to install: the released installer through a pipe, with options."""
    target = box.tmp / "srv"
    env = dict(box.env_vars, FINOPS_DIR="")
    script = f'PATH="$FAKE_BIN:$PATH" bash -s -- --dir {_sh_path(target)} --registry-mirror https://mirror.example.ir --domain finops.example.ir < "$0"'
    clean = {k: v for k, v in os.environ.items() if not k.startswith(("FINOPS_", "FAKE_"))}
    r = subprocess.run([BASH, "-c", script, _sh_path(installer)], env=dict(clean, **env), capture_output=True, text=True,
                       timeout=120)
    assert r.returncode == 0, r.stdout + r.stderr
    assert (target / "compose.yml").read_text() == (ROOT / "deploy" / "compose.install.yml").read_text()
    assert (target / "finops-agent").exists() and (box.bin / "finops-agent").exists()
    assert "registry.example.ir/acme/finops-agent-app:9.2.0" in (target / ".env").read_text()
    assert "https://mirror.example.ir" in (box.tmp / "daemon.json").read_text()
    assert "https://finops.example.ir" in r.stdout


def test_installer_from_a_clone_needs_root(box):
    (box.fakes / "id").write_text("#!/usr/bin/env bash\necho 1000\n", newline="\n")
    r = box.run(script=ROOT / "install.sh")
    assert r.returncode != 0 and "run this as root" in r.stderr


def test_versions_compare_like_semver(tmp_path):
    """A release candidate is older than its release, so the real release can upgrade a server that ran the candidate."""
    lib = tmp_path / "lib.sh"
    text = (ROOT / "deploy" / "finops-agent").read_text()
    lib.write_text(re.search(r"^version_lt\(\) \{.*?^\}\n", text, re.M | re.S).group(0), newline="\n")
    cases = {("0.3.0-rc.1", "0.3.0"): True, ("0.3.0", "0.3.0-rc.1"): False, ("0.3.0-rc.1", "0.3.0-rc.2"): True,
             ("0.2.0", "0.3.0-rc.1"): True, ("0.9.0", "0.10.0"): True, ("0.10.0", "0.9.0"): False,
             ("0.3.0", "0.3.0"): False, ("0.3.1-rc.1", "0.3.0"): False}
    for (a, b), older in cases.items():
        r = subprocess.run([BASH, "-c", f'source "$0"; version_lt {a} {b}', _sh_path(lib)], timeout=30)
        assert (r.returncode == 0) is older, (a, b)
