# Website brief

## What the site is for

FinOps agent is free, open-source software that a company installs on its own server. It shows the exact monthly cost
of every server they rent from Iranian cloud providers, compares like-for-like plans, and suggests savings with the
evidence behind each one.

The website has one job: someone arrives, understands what it does, trusts it, and installs it. There is nothing to
sign up for or sign in to, because there is no hosted service, and no pricing page, because it's free.

## Who reads it

1. **Infrastructure and DevOps engineers** at Iranian startups and small companies. They install it. They want to
   know what it does, that it's safe (it runs on their own server, only reads, and the code is open), and then they
   want the install command and the docs.
2. **Founders and finance leads** deciding whether it's worth an engineer's afternoon. They want the outcome: what
   their servers really cost, and where money is being wasted. Most will read in Persian.

## What it must say, most important first

1. **What it is, in one sentence:** the exact cost of your Iranian cloud servers, on your own server.
2. **What it looks like:** the dashboard, with real-looking figures. Screenshots are in `docs/images/`.
3. **How to install it:** the one command, copyable, plus a few of the commands that run it afterwards, and links to
   the installation guide, the releases (with offline bundles) and the source code.
4. **How it works,** in five steps: add your servers, confirm them, see the exact cost, compare providers, decide on
   savings.
5. **Why it can be trusted:** prices come from providers' official pages with a source and date, never from AI; cheaper
   plans are shown only when they really match; it never changes anything on your servers; the data stays on your
   server; the code is open (Apache 2.0).
6. **The providers it covers:** ArvanCloud, Liara, Server.ir, IranServer, Chabokan, ParsPack, MobinHost, Abrha.
7. **Footer:** GitHub, the installation guide, the license, and «قدرت‌گرفته از پندار».

Welcome later: questions and answers (Docker Hub is blocked, what now? Does it change my servers? Which providers?),
release news, and a way to get in touch.

## What's fixed

- **Pendar's design system, version 3:** its colours, type, spacing, corners and motion tokens, the Estedad font, its
  icons, and its wordmark with the brick-laying animation. The product name sits beside Pendar's wordmark, as in the
  products guideline.
- **Persian first,** right to left, with a complete English version behind a toggle.
- **Light and dark.**
- **Works well from Iran:** nothing loads from other servers (no Google Fonts, analytics, video embeds or CDNs), and
  it must be quick on a phone on a mobile connection.
- **Accessible:** readable contrast, usable by keyboard, and still when reduced motion is on.
- **The install command is shown exactly,** left to right even inside Persian text, in a monospace face, with a copy
  button. Pendar has no monospace font, so commands use the system's.

Everything else is open: layout, sections, illustration, imagery, motion within the guideline, and the wording. We'll
check the wording for accuracy.

## What we'd like back

- Pages at phone (360px), tablet (768px) and desktop (1280px and up) widths, in Persian and English. Light is enough
  where dark follows from the tokens.
- States for anything interactive: links, buttons, the copy button before and after copying, the language toggle.
- New artwork as SVG (or PNG at 2×), including a 1200×630 image for link previews.
- Notes on any motion, in terms of the motion tokens.

A developer then builds it in `site/` as static files. The current version is there to look at: see
[README.md](README.md) to run it, or ask for screenshots.
