# Installation

You need one Linux server (Ubuntu or Debian is easiest) with at least 2 GB of memory, ports 80 and 443 open, and root
access.

```bash
git clone https://github.com/theparsakhezli/FinOps_agent.git
cd FinOps_agent
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

**Use an offline bundle.** Build it anywhere with good internet access, copy it over, and nothing else is downloaded
except Docker itself if it's missing:

```bash
scripts/make-bundle.sh                       # on a machine with internet access
scp finops-agent-0.1.0.tar.gz server:
```

```bash
tar xzf finops-agent-0.1.0.tar.gz && cd finops-agent-0.1.0   # on the server
sudo ./install.sh --bundle images.tar.gz
```

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
