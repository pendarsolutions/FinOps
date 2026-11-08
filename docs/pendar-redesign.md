# Pendar redesign

The web app (`apps/web`) is restyled to follow the Pendar design system, version 3, from Specimen. This is a visual
redesign only: routes, API calls, data handling, validation, permissions and business logic don't change.

Sources read before any code was written: Pendar's brand record and every guideline page as published on 2026-11-07:
about (v1), logo (v1), symbol (v2), colour (v1), type (v1), icons (v3), motion (v1), voice (v2), products (v3),
setup (v5), buttons, fields, choices, navigation, overlays, feedback, display, shopping-and-flows (all v1), social (v3),
stationery, email-signature and launch-screen (v1). The component reference images (Components and Examples
collections) were used to match layout and spacing.

## 1. Audit (before)

### Stack

React 18, TypeScript and Vite, with React Router and TanStack Query. Styling is plain CSS: there is no Tailwind and no
component library. `index.html` and `lib/i18n.tsx` set `lang` and `dir` on `<html>` (Persian by default, English as
an option).

| File | Lines | Hex / rgb literals | px values | font/radius/shadow/motion declarations |
|---|---|---|---|---|
| `src/styles.css` | 1131 | 32 | 83 | 56 |
| `src/experience.css` | 1106 | 87 | 117 | 99 |
| `src/review.css` | 1026 | 14 | 101 | 94 |
| `src/lib/viz.ts` | 38 | 1 (comment) | 0 | 1 |
| `src/components/viz.tsx` | | 0 | 2 | |
| `src/pages/Landing.tsx` | | 0 | 1 | 6 inline style declarations |

### Theme

- One `:root` palette in `styles.css`: `--bg`, `--surface`, `--surface-2`, `--text`, `--muted`, `--border`, `--brand`
  (green), `--brand-ink`, `--brand-soft`, `--good`/`--warn`/`--bad`/`--info` with `-bg` pairs, `--low-conf`,
  `--radius` (10px), `--shadow`, `--font`, `--nav-w` (220px) and `--topbar-h` (56px).
- `experience.css` adds a chart palette (`--series-1`…`--series-8`, `--series-other`) and chart roles
  (`--viz-accent`, `--viz-accent-track`, `--viz-accent-ink`, `--viz-deemph`, `--viz-grid`, `--viz-ink-2`, `--viz-ink-3`).
- Most used: `--border` (42), `--surface` (30), `--bad` (30), `--surface-2` (26), `--brand` (26), `--muted` (23).
- No dark mode. `index.html` declares `color-scheme: light`, and there is no theme switch.
- Rounded corners everywhere (10px cards, pill-shaped badges and chips) and shadows on cards.

### Type

Vazirmatn 400/500/700 from `@fontsource/vazirmatn`, at a 15px base size and line height 1.6. Headings are set in
`rem` (1.45, 1.12, 1, 0.95). Code uses `ui-monospace, Consolas, monospace`.

### Icons and brand marks

- Status and actions use Unicode characters: ✓ ✕ ✗ ! i • ⚠ ⓘ ▲ ▼ ≠ ☰ ↻ Σ ▸ ▾ ← → (30 places in 14 files).
- Two hand-drawn inline SVG sets: `ServiceIcon` (server, database, storage, cloud) in `components/records.tsx`, and
  the feature icons on `pages/Landing.tsx`.
- A letter in a green square stands in for the logo ("F" in the app bar, "P" on the landing page). `public/favicon.svg`
  is a green square with a "P".

### RTL, focus and motion

- Six physical properties (`left`, `right`, `padding-left`, `padding-right`, `text-align: right`) in `review.css` and
  `experience.css`. Everything else already uses logical properties.
- Focus: a 2px green outline on `:focus-visible`.
- Reduced motion: respected in `experience.css` and `lib/viz.ts`.

### Routes

Public: `/welcome` (landing), `/how-it-works`, `/login`, `/register`. Signed in: `/` (overview), `/servers`,
`/infrastructure`, `/costs`, `/opportunities`, `/compare`, `/reports`, `/catalog`, `/integrations`, `/guide`,
`/settings`.

### Shared components

- `components/ui.tsx`: Button, Badge, StatusChip, Card, Loading, Empty, Field, Tabs, Drawer, Money, Num, Pct,
  PriceUnavailableBadge, FreshnessBadge, SourceInfo, LinesTable, ErrorBox, ToneBadge, ReviewBadge.
- `components/records.tsx`: record lists and rows, ServiceIcon, ConfidenceRing, Initial (avatar).
- `components/viz.tsx`: ShareBar, RankedBars, BeforeAfter, PartMeter, tooltips.
- `components/Layout.tsx` (app bar, side navigation), `Tour.tsx`, `Advisor.tsx` (chat drawer), `Builder.tsx`,
  `ReviewTable.tsx`, `Guard.tsx`.

Before screenshots, light theme, desktop (1440px) and phone (390px): [`pendar-redesign/before/`](pendar-redesign/before/).

## 2. Plan

**No new libraries.** Pendar's own components live in `@pendar/ui`, which needs Tailwind 4. Both would be new
dependencies, so the app's existing components are restyled in place. Pendar's `tokens.css` is used directly, with no
Tailwind or JS token files, and the component images in Specimen serve as the visual reference.

1. **Pull.** `scripts/pull-pendar.sh` downloads, with `?version=3`: `tokens.css`, the Estedad variable font (plus its
   OFL license), the icons (generated into one sprite and a list of icons that mirror), the favicons and apple touch
   icon, and the wordmark and symbol paths. Everything is committed. The running site never calls Specimen.
2. **Foundation.** Import `tokens.css` first. Add `@font-face` for Estedad with `font-display: swap`, and remove
   `@fontsource/vazirmatn`. Dark mode follows the system through the tokens' own media query, with `data-theme` on
   `<html>` overriding it. Rebuild the base styles from type tokens: body (16px, line height 1.8, no letter spacing),
   headings (700–900), links, focus ring (`--color-focus`), selection, scrollbars, and `color-scheme`.
3. **Components.** Map every colour to a role:

   | Old | Pendar role |
   |---|---|
   | `--bg` | `--color-surface-page` |
   | `--surface` | `--color-surface-raised` |
   | `--surface-2` | `--color-surface-sunken` (table heads, wells) or `--color-surface-plaster` (brand band, avatars) |
   | `--text`, `--muted` | `--color-ink-default`, `--color-ink-muted` |
   | `--border` | `--color-line-default`; field and control borders use `--color-line-control` |
   | `--brand` (buttons, current nav item) | `--color-action-default` / `-hover` / `-pressed`, `--color-ink-action`, `--color-action-subtle` |
   | `--brand` (focus, selection, progress) | `--color-focus`, `--color-accent-*` |
   | `--good` / `--warn` / `--bad` / `--info` | `--color-success-*`, `--color-warning-*`, `--color-danger-*`, `--color-info-*` |

   Corners use `--radius-control` (2px) and `--radius-card` (4px). Cards, tables and lists become flat with a line,
   and only overlays keep a shadow (`--shadow-overlay`). Controls are 44px tall and 36px in dense bars, from spacing
   tokens. Icons replace the Unicode characters and inline SVGs, at 24px with 8px beside text, mirrored in English
   when the file says so. Motion uses the duration and ease tokens: buttons press down 1px, and nothing loops except
   the loader.
4. **Brand.** The app bar and public pages carry the product lockup: Pendar wordmark, a thin rule, then the product
   name in Estedad 800, drawn in code from `--color-logo-brick` and `--color-logo-glaze` so dark mode reverses it.
   Pendar's favicons replace the old one, the loader becomes the glazing wall, and «قدرت‌گرفته از پندار» goes at the
   foot of the pages (voice guideline).
5. **Pages.** Go through every route, replace what's left, and remove unused CSS.
6. **Verify.** Build, type-check, lint and tests. Every page in light and dark, at 1440px and 390px, in RTL. No request
   to Specimen from the running site.

Known gaps already visible in the tokens: no chart palette, no layout widths (side navigation, content and drawer
width, breakpoints), no scrim colour for overlays, and no border-width or focus-ring-width tokens. Section 3 records
what was done for each.
