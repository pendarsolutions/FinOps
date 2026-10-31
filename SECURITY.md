# Security

Please report security problems
privately using [GitHub's private vulnerability reporting](../../security/advisories/new), not in a
public issue. Include the steps to reproduce and the impact you expect.

## Current scope

FinOps agent stores cost data and uploaded invoices. Passwords are hashed, sign-up is closed after the
first account, and sign-in is rate limited. It doesn't connect to your servers yet.
