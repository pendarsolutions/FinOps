# Installation

You need one Linux server (Ubuntu or Debian is easiest) with at least 2 GB of memory and root access. It doesn't have to
be empty: if ports 80 and 443 are taken, for example by nginx, the installer picks a free port such as 8443 and leaves
the existing service alone. Choose the port yourself with `--port`.

```bash
git clone https://github.com/pendarsolutions/FinOps.git
cd FinOps
sudo ./install.sh --domain finops.example.ir
```

Without `--domain` it uses the server's IP address, and your browser will warn about the certificate. Open the address
it prints and create the first account. Sign-up closes after that, and admins add other people from **Settings**.

Back up `/opt/finops-agent/.env`, because it holds the key that decrypts your data, and the Docker volumes for the
database. To upgrade, get the new version and run the installer again. Your settings and data are kept.

## If foreign registries are blocked

Docker Hub and other foreign sources can be blocked or unreliable from Iran. There are two ways around that.

**Use a mirror.** Give the installer a registry mirror that you trust:

```bash
sudo ./install.sh --registry-mirror https://mirror.example.ir
```

**Use an offline bundle.** It holds every image the app needs, so nothing else is downloaded except Docker itself
if it's missing. Each [release](https://github.com/pendarsolutions/FinOps/releases) has one attached, with a checksum file.
Download both on a machine with good internet access and copy them over:

```bash
scp finops-agent-0.2.0.tar.gz SHA256SUMS server:
```

```bash
sha256sum -c SHA256SUMS                                        # on the server
tar xzf finops-agent-0.2.0.tar.gz && cd finops-agent-0.2.0
sudo ./install.sh --bundle images.tar.gz
```

To build a bundle yourself, for example from an unreleased change, run `scripts/make-bundle.sh` on a machine with
Docker and internet access.

## Alerts

Add these to `/opt/finops-agent/.env` and run `docker compose up -d` there. You can use either channel or both.

```bash
FINOPS_SMTP_HOST=smtp.example.ir
FINOPS_SMTP_USER=alerts@example.ir
FINOPS_SMTP_PASSWORD=...
FINOPS_ALERT_EMAIL_TO=you@example.ir

FINOPS_BALE_BOT_TOKEN=...
FINOPS_BALE_CHAT_ID=...
```

You'll hear about price changes (naming your servers on those plans), failed price updates, price moves that need
review, and renewals 7, 3 and 1 days ahead.

## Backups

The installer sets up a nightly backup at 03:30. It keeps the newest 14 in `/var/backups/finops-agent`, readable only
by root. Each backup is one file with the database, the uploaded invoices, and the settings file. The settings file
holds the keys that decrypt the SSH keys stored for your servers, so keep backups as safe as the server.

```bash
sudo /opt/finops-agent/backup.sh                          # back up now
sudo /opt/finops-agent/backup.sh --restore FILE           # put a backup back
```

**Copy backups off the server.** A backup on the same disk doesn't survive losing the server. For example, from
another machine:

```bash
rsync -a root@your-server:/var/backups/finops-agent/ ./finops-backups/
```

**Restoring** asks for confirmation (or add `--yes`). It first backs up the current data, so a restore can be undone
with that file. It then puts back the database, the invoices and the settings. Settings that belong to the machine stay as
they are: the image versions, ports, address and database password. A backup from an older version is upgraded when
the app starts.

**Moving to a new server:** install there with `install.sh`, copy a backup over, and restore it.

To turn the nightly backup off, run the installer with `--no-daily-backup` (and `--daily-backup` to turn it back on).
`FINOPS_BACKUP_DIR` changes where backups go.

## Members and passwords

Admins add people under **Settings → Members**, choose their role, give them a temporary password, or remove them.
Removing someone ends their access at once and keeps everything they did. Admins manage only roles below their own,
so an admin can't change another admin or the owner.

Anyone can change their own password under **Settings → Your account**, which signs them out everywhere else.

**Forgotten passwords.** With email set up (see [Alerts](#alerts)), the sign-in page offers a link that emails a
one-time reset link, valid for 30 minutes. The link points at `FINOPS_PUBLIC_URL`, which the installer sets from your
domain or IP address. Without email, an admin sets a temporary password instead. If the owner is the one locked out,
run this on the server:

```bash
cd /opt/finops-agent
sudo docker compose exec api python -m finops_api.cli reset-password --email you@example.ir
```

It prints a new password and signs that person out everywhere. To choose the password yourself, add
`--password-stdin` and type it.

## Sharing one price catalog

One installation can scrape prices and publish a signed catalog, so the others don't each have to scrape.

**On the publisher:**

```bash
docker compose exec api python -m finops_api.cli catalog-keygen
```

Add this to its `.env`, using the signing key the command printed, and keep that key secret:

```bash
FINOPS_CATALOG_SIGNING_KEY=...
FINOPS_CATALOG_PUBLISH_DIR=/app/var/catalog
```

The catalog is then served at `https://your-publisher/catalog/` and refreshed after each scrape. Host the publisher in
Iran, because Iranian providers' sites may block foreign addresses.

**On every other installation:**

```bash
FINOPS_CATALOG_URL=https://your-publisher/catalog
FINOPS_CATALOG_PUBLIC_KEY=...
```

Those installations stop scraping and check the catalog twice a day. A file without a valid signature is refused, an
older file can't roll prices back, and sharp price moves are still held for review.
