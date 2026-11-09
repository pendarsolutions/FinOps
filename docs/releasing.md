# Releasing

A release is a tag. Pushing `vX.Y.Z` runs [`.github/workflows/release.yml`](../.github/workflows/release.yml), which
runs the tests, builds the one-file installer and the offline bundle, pushes the app and web images to GitHub Container
Registry, and publishes a GitHub release with `install.sh`, the bundle, their checksums and the notes.

`install.sh` on the release is what `curl -fsSL .../releases/latest/download/install.sh | sudo bash` downloads, so a
release is live for new installs the moment it's published. Existing installations get it with
`sudo finops-agent upgrade`.

1. Set the version everywhere it appears:

   ```bash
   scripts/bump-version.sh 0.3.0
   ```

2. Add a `## [0.3.0] — YYYY-MM-DD` section to [CHANGELOG.md](../CHANGELOG.md), and write the release notes in
   `docs/releases/v0.3.0.md`. In the notes, `{{REPO}}` and `{{VERSION}}` are replaced when the release is published.

3. Commit, tag and push:

   ```bash
   git commit -am "Release 0.3.0"
   git tag -a v0.3.0 -m "FinOps agent 0.3.0"
   git push origin main v0.3.0
   ```

The workflow stops before publishing anything if the tag, `VERSION` in `deploy/finops-agent`, the changelog and the
notes don't agree. It also stops if `IMAGE_PREFIX` there isn't `ghcr.io/<repository owner>`, because that's where the
images are published and where installations pull them from.

The public website (`site/`) rebuilds when a release is published, and serves that release's `install.sh` at
`/install.sh` too. See [site/README.md](../site/README.md).

The first time images are published, check that both packages (`finops-agent-app` and `finops-agent-web`) are public
under the owner's **Packages** tab. Otherwise installs that pull images instead of using the bundle will fail.
