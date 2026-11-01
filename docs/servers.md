# Monitoring your servers

Install FinOps agent on one server, then add your other servers from the **Servers** page. Nothing keeps running on
them. Every 5 minutes the installation connects over SSH and reads a few usage counters.

## Adding a server

1. On the **Servers** page, copy the setup command.
2. Run it once on the server you want to add, as root or a user with `sudo`. Running it again is safe.
3. Add the server's address and SSH port on the same page.
4. Choose its provider and plan. A server can't tell us which plan it's on, so the page suggests plans with matching
   specs and you pick the right one. Nothing is priced until you do.

Costs are calculated from list prices, so your actual invoice can differ if you have a discount or an older plan.

## What the setup command does

- Creates a user called `finops-collector`, with no password and no sudo.
- Installs one read-only script at `/usr/local/lib/finops-agent/collect.sh`.
- Adds your installation's public key, restricted so that it can only run that script. Forwarding and terminals are
  turned off, and root owns the key file, so the user can't change these limits.

The command contains only a public key, so it isn't secret.

## What is collected

CPU and memory counters, root disk usage, total network traffic, hostname and operating system. It doesn't read files,
processes, logs or application data. Usage is kept for 90 days.

| Shown as | How it's worked out |
|---|---|
| CPU and memory | 95th percentile over the last 30 days, a value that was really observed |
| Monthly traffic | Measured over 30 days. Before that, projected from at least one day and labelled as projected |
| Rightsizing advice | Only after 14 days of observation, because allocated size alone proves nothing |

Download means traffic leaving the server. Providers may count traffic differently, so check this against your invoice
if you're close to a quota.

## If a server's identity changes

The first connection remembers the server's SSH identity. If it changes later, collection stops and the page warns you.
That's expected after a reinstall, so choose **Trust new identity**. If you didn't reinstall the server, find out why
before trusting it. Every such approval is recorded in the audit log.

## Limiting where the key works

Set `FINOPS_COLLECTOR_SOURCE_IP` to your installation's public IP before copying the setup command. The key then works
only from that address. Servers that are already set up need the command run again.

## Removing a server

Remove it on the **Servers** page, then run this on the server itself:

```bash
userdel -r finops-collector; rm -rf /usr/local/lib/finops-agent   # as root
```

## If you can't connect

| Message | What to do |
|---|---|
| Cannot reach | Check the address and port, and that your firewall allows this installation |
| The server refused the key | Run the setup command on it. If `sshd_config` uses `AllowUsers`, add `finops-collector` there |
