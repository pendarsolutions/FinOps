# Installation

You need one Linux server (Ubuntu or Debian is easiest) with at least 2 GB of memory and root access. It doesn't have to
be empty: if ports 80 and 443 are taken, for example by nginx, the installer picks a free port such as 8443 and leaves
the existing service alone. You can also put it [behind your own reverse proxy](#behind-your-own-reverse-proxy).

```bash
curl -fsSL https://github.com/pendarsolutions/FinOps/releases/latest/download/install.sh | sudo bash
```

In a terminal, it asks for a domain (or uses the server's IP address), a port, nightly backups, and optionally email
and Bale for alerts. Then it prints the address of your dashboard. Open it and create the first account. Sign-up
closes after that, and admins add everyone else from **Settings**.

The installer is one readable file. To look before running it, download it first:

```bash
curl -fsSLO https://github.com/pendarsolutions/FinOps/releases/latest/download/install.sh
less install.sh
sudo bash install.sh
```

It installs Docker if it's missing, puts the app in `/opt/finops-agent`, and installs the `finops-agent` command. From
then on, you run the installation with that command.

## Without questions

Give options and it asks nothing, which suits scripts, cloud-init and Ansible:

```bash
curl -fsSL https://github.com/pendarsolutions/FinOps/releases/latest/download/install.sh | sudo bash -s -- \
  --domain finops.example.ir \
  --set SMTP_HOST=mail.example.ir --set SMTP_USER=alerts@example.ir --set ALERT_EMAIL_TO=ops@example.ir
echo "$SMTP_PASSWORD" | sudo finops-agent config set SMTP_PASSWORD
```

| Option | What it does |
| --- | --- |
| `--domain NAME` | A domain pointing at this server. With port 443 free, it gets a real certificate automatically. |
| `--ip ADDRESS` | Serve on an IP address. Browsers warn about its certificate. This is the default, with the detected address. |
| `--port PORT` | The HTTPS port. The default is 443, or a free one if 443 is taken. |
| `--proxy URL` and `--listen [IP:]PORT` | Run [behind your own reverse proxy](#behind-your-own-reverse-proxy). |
| `--set KEY=VALUE` | Any [setting](#settings). Repeat it for more. |
| `--no-daily-backup` | No nightly backup. |
| `--version VERSION` | Install a given version instead of the installer's own. |
| `--bundle FILE` | Load the images from an [offline bundle](#if-foreign-registries-are-blocked). |
| `--registry-mirror URL` | Pull images through a mirror. |
| `--dir PATH` | Install somewhere other than `/opt/finops-agent`. |
| `--yes` | Ask nothing, and take the defaults. |

Running the installer again is safe: it keeps your settings, secrets and data.

## The `finops-agent` command

| Command | What it does |
| --- | --- |
| `finops-agent status` | What's running, the version, the address, backups and alerts |
| `finops-agent doctor` | Checks Docker, the services, the address, DNS, the certificate, disk, backups and updates, and says how to fix what's wrong |
| `finops-agent config` | Shows the settings, with secrets hidden |
| `finops-agent config keys` | Lists every setting you can change |
| `finops-agent config set KEY=VALUE...` | Changes settings and restarts what uses them |
| `finops-agent address --domain NAME` | Changes the address. Also `--ip`, `--port`, `--proxy` |
| `finops-agent test-alerts` | Sends a test message through email and Bale |
| `finops-agent logs [-f] [SERVICE]` | Recent logs |
| `finops-agent restart`, `start`, `stop` | What they say |
| `finops-agent upgrade [VERSION]` | Backs up, then moves to the latest release or the version given |
| `finops-agent backup`, `restore FILE` | [Backups](#backups) |
| `finops-agent reset-password --email ADDRESS` | For when nobody can sign in |
| `finops-agent compose ...` | Runs `docker compose` in `/opt/finops-agent` |
| `finops-agent uninstall` | Removes the app and keeps the data; `--delete-data` deletes it too |

Run them with `sudo`. `finops-agent help` lists the options.

## Settings

Settings live in `/opt/finops-agent/.env`, which only root can read. Change them with the command rather than by
hand: it checks each value, refuses ones that would break the installation, and restarts only the services that use
them.

```bash
sudo finops-agent config set SMTP_HOST=mail.example.ir SMTP_PORT=587 ALERT_EMAIL_TO=ops@example.ir
sudo finops-agent config set SMTP_PASSWORD        # asks for it, so it stays out of your shell history
sudo finops-agent config unset BALE_CHAT_ID
sudo finops-agent config keys                     # everything you can set
```

Names work with or without `FINOPS_` and in any case: `smtp_host` is `FINOPS_SMTP_HOST`. Some keys belong to other
commands: the address belongs to `address`, and the image versions belong to `upgrade`. A few keys never change,
because the data depends on them: the database password, and the key that decrypts the SSH keys stored for your
servers.

## Address and certificates

```bash
sudo finops-agent address                                  # show it
sudo finops-agent address --domain finops.example.ir       # a real certificate, once DNS points here
sudo finops-agent address --ip 203.0.113.10 --port 8443
```

A domain gets a certificate from Let's Encrypt automatically when its DNS points at the server and ports 80 and 443
are reachable. `finops-agent doctor` checks both. On any other port, or on an IP address, the app uses its own
certificate, and browsers warn about it.

**If a firewall keeps the port closed,** an installation with its own certificate also answers on the server's other
addresses, such as a VPN or LAN address, and on `localhost` through an SSH tunnel:

```bash
ssh -L 8443:127.0.0.1:8443 you@your-server      # then open https://localhost:8443
```

### Behind your own reverse proxy

If nginx, Traefik or a load balancer already handles HTTPS on the server, the app can serve plain HTTP to it on a
local port:

```bash
sudo finops-agent address --proxy https://finops.example.ir --listen 127.0.0.1:8080
```

Then point the proxy at it. The app must be at the root of its host, not under a path. For nginx:

```nginx
server {
    listen 443 ssl;
    server_name finops.example.ir;
    # ssl_certificate and ssl_certificate_key as for your other sites
    client_max_body_size 20m;

    location / {
        proxy_pass http://127.0.0.1:8080;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto https;
    }
}
```

The same options work at install time: `install.sh --proxy https://finops.example.ir --listen 8080`.

## If foreign registries are blocked

Docker Hub and other foreign sources can be blocked or unreliable from Iran. There are two ways around that.

**Use a mirror.** Give the installer a registry mirror that you trust:

```bash
curl -fsSL .../install.sh | sudo bash -s -- --registry-mirror https://mirror.example.ir
```

**Use an offline bundle.** It holds every image the app needs, so nothing else is downloaded except Docker itself
if it's missing. Each [release](https://github.com/pendarsolutions/FinOps/releases) has one attached, with a checksum file.
Download both on a machine with good internet access and copy them over:

```bash
scp finops-agent-0.3.0.tar.gz SHA256SUMS server:
```

```bash
sha256sum -c --ignore-missing SHA256SUMS                       # on the server
tar xzf finops-agent-0.3.0.tar.gz && cd finops-agent-0.3.0
sudo ./install.sh --bundle images.tar.gz
```

To build a bundle yourself, for example from an unreleased change, run `scripts/make-bundle.sh` on a machine with
Docker and internet access.

## Upgrading

```bash
sudo finops-agent upgrade            # the latest release
sudo finops-agent upgrade 0.3.1      # a given version
sudo finops-agent upgrade --bundle finops-agent-0.3.1.tar.gz     # offline
```

It backs up first and stops if the backup fails. Then it downloads the new images and applies the new version's
settings. The database is upgraded when the app starts, and your settings and data are kept. Going back to an older
version means restoring the backup taken before the upgrade.

**From 0.2.0**, which had no `finops-agent` command: run the new installer once, the same way as a fresh install. It
keeps everything, including the domain.

## Alerts

Use email, Bale, or both:

```bash
sudo finops-agent config set SMTP_HOST=smtp.example.ir SMTP_USER=alerts@example.ir ALERT_EMAIL_TO=you@example.ir
sudo finops-agent config set SMTP_PASSWORD
sudo finops-agent config set BALE_CHAT_ID=123456789
sudo finops-agent config set BALE_BOT_TOKEN
sudo finops-agent test-alerts
```

You'll hear about price changes (naming your servers on those plans), failed price updates, price moves that need
review, and renewals 7, 3 and 1 days ahead. Email also lets people [reset their own password](#members-and-passwords).

## Backups

The installer sets up a nightly backup at 03:30. It keeps the newest 14 in `/var/backups/finops-agent`, readable only
by root. Each backup is one file with the database, the uploaded invoices, and the settings file. The settings file
holds the keys that decrypt the SSH keys stored for your servers, so keep backups as safe as the server.

```bash
sudo finops-agent backup                         # back up now
sudo finops-agent restore FILE                   # put a backup back
sudo finops-agent config set DAILY_BACKUP=false  # no nightly backup (true turns it back on)
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

**Moving to a new server:** install there, copy a backup over, and restore it.

`FINOPS_BACKUP_DIR` changes where backups go.

## Members and passwords

Admins add people under **Settings → Members**, choose their role, give them a temporary password, or remove them.
Removing someone ends their access at once and keeps everything they did. Admins manage only roles below their own,
so an admin can't change another admin or the owner.

Anyone can change their own password under **Settings → Your account**, which signs them out everywhere else.

**Forgotten passwords.** With email set up (see [Alerts](#alerts)), the sign-in page offers a link that emails a
one-time reset link, valid for 30 minutes. The link points at the installation's address. Without email, an admin
sets a temporary password instead. If the owner is the one locked out, run this on the server:

```bash
sudo finops-agent reset-password --email you@example.ir
```

It prints a new password and signs that person out everywhere. To choose the password yourself, add
`--password-stdin` and type it.

## Sharing one price catalog

One installation can scrape prices and publish a signed catalog, so the others don't each have to scrape.

**On the publisher:**

```bash
sudo finops-agent compose exec api python -m finops_api.cli catalog-keygen
sudo finops-agent config set CATALOG_PUBLISH_DIR=/app/var/catalog
sudo finops-agent config set CATALOG_SIGNING_KEY       # paste the signing key it printed; keep it secret
```

The catalog is then served at `https://your-publisher/catalog/` and refreshed after each scrape. Host the publisher in
Iran, because Iranian providers' sites may block foreign addresses.

**On every other installation:**

```bash
sudo finops-agent config set CATALOG_URL=https://your-publisher/catalog CATALOG_PUBLIC_KEY=...
```

Those installations stop scraping and check the catalog twice a day. A file without a valid signature is refused, an
older file can't roll prices back, and sharp price moves are still held for review.

## Uninstalling

```bash
sudo finops-agent uninstall                  # removes the app; the data stays, and installing again brings it back
sudo finops-agent uninstall --delete-data    # also deletes the database, invoices and settings
```

Backups in `/var/backups/finops-agent` are never deleted.

## Installing from a clone

To install a branch or a change of your own, clone the repository and run the installer from it. It uses the files
next to it, and builds the images on the server if no registry has them:

```bash
git clone https://github.com/pendarsolutions/FinOps.git && cd FinOps
sudo ./install.sh --domain finops.example.ir          # add --build to always build here
```
