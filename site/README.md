# FinOps agent website

The public website: what FinOps agent is, how it works, and the command that installs it. It is a separate project
from the dashboard in `apps/web`, and an installation never serves it.

The design is being redone: see [BRIEF.md](BRIEF.md). What's here now is the old in-app landing page moved out, with
an install section added. Treat it as a starting point.

## Run it

```bash
cd site
npm install
npm run dev        # http://localhost:5174, reloads as you edit
npm run build      # static files in site/dist
```

Add `?lang=en` to the address for English. The language toggle remembers the choice.

## Where things are

| File | What it holds |
| --- | --- |
| `src/Landing.tsx` | The page |
| `src/strings.ts` | Every word on it, in Persian and English |
| `src/links.ts` | GitHub, the docs, and the install command |
| `src/site.css` | The styles, forked from the app on 9 Nov 2026; free to diverge |
| `src/Brand.tsx`, `src/Icon.tsx` | Pendar's wordmark (laid brick by brick) and icons |
| `src/motion.ts` | Sections rise once as they scroll into view |
| `public/` | Favicons |

**Pendar's design system** (tokens, the Estedad font, icons, the wordmark) comes from `apps/web/src/pendar` through
the `@pendar` alias in `vite.config.ts`, so the site and the dashboard always match. `scripts/pull-pendar.sh`
generates those files and copies the favicons into `public/`; don't edit them by hand. If the site moves to its own
repository, copy that folder along and point the alias at it.

## Rules

- **Nothing from other servers at run time:** no web fonts, analytics, trackers, CDNs or embeds. The site has to work
  from Iran, where many of those are blocked, and visitors' privacy matters.
- **Persian first,** right to left, with complete English.
- Light and dark, following the visitor's system. Motion follows Pendar's motion tokens and stops for reduced motion.
- The install command must match the release exactly.

## Publishing

[`.github/workflows/site.yml`](../.github/workflows/site.yml) builds the site on every change and publishes it with
GitHub Pages once that's switched on:

1. **Settings → Pages → Source: GitHub Actions,** and enter the custom domain there.
2. Point the domain's DNS at GitHub Pages (a `CNAME` record to `pendarsolutions.github.io`).
3. Add the repository variable `SITE_DOMAIN` with the domain (**Settings → Secrets and variables → Actions →
   Variables**). Until it's set, the workflow only builds.

The workflow also puts the latest release's `install.sh` at `/install.sh`. To advertise the shorter
`curl -fsSL https://your-domain/install.sh | sudo bash`, change `INSTALL_URL` in `src/links.ts`.

Any static host works as well: copy `site/dist` to nginx, Caddy, or object storage behind a CDN. Hosting inside Iran
makes the site faster there.
