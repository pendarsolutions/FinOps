# Security

Please report security problems
privately using [GitHub's private vulnerability reporting](../../security/advisories/new), not in a
public issue. Include the steps to reproduce and the impact you expect.

## Current scope

FinOps agent stores cost data and uploaded invoices, and holds an SSH key that reads usage figures from the
servers you add. Passwords are hashed, sign-up closes after the first account, and sign-in is rate limited.

On a monitored server:

- The key can run only one read-only script. It has no sudo, and forwarding and terminals are turned off.
- Root owns the key file, so the collector user can't change those limits.
- Root passwords and root keys are never asked for or stored.
- Each organization has its own key, and its private half is encrypted at rest.
- A changed server identity stops collection until an admin approves it.
- A server is removed by deleting one user on it (see [docs/servers.md](docs/servers.md)).
