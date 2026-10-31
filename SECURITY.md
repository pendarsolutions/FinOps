# Security

FinOps agent holds SSH access to its users' servers and their cost data, so please report problems
privately using [GitHub's private vulnerability reporting](../../security/advisories/new), not in a
public issue. Include the steps to reproduce and the impact you expect.

## What the design promises

- The collector key on each monitored server can run only one read-only script. It has no shell and no sudo.
- Root passwords and root keys are never requested or stored.
- The collector key is encrypted at rest and is unique to each organization.
- A server is removed by deleting one user on it (see [docs/servers.md](docs/servers.md)).
