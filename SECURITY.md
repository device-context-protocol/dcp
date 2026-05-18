# Security policy

## Reporting a vulnerability

If you believe you have found a security vulnerability in DCP — the protocol,
the Python Bridge, the CLI, or the reference firmware — please report it
privately.

**Do not open a public GitHub issue.**

Use GitHub's private vulnerability reporting:
[github.com/device-context-protocol/dcp/security/advisories/new](https://github.com/device-context-protocol/dcp/security/advisories/new)

We will acknowledge receipt within 72 hours and aim to ship a fix or a public
advisory within 30 days. If the issue is in a dependency, we will coordinate
with upstream.

## Scope

In scope:

- Authentication, capability scoping, or token verification bypass.
- Memory safety issues in the firmware (buffer overruns, CBOR parser, COBS
  decoder).
- Wire-format parsing crashes or panics on malformed input.
- Bridge bugs that let an LLM cause a side effect outside its granted
  capabilities.

Out of scope:

- Attacks that require physical access to a paired device.
- Denial of service via the underlying transport (we rely on the transport's
  own guarantees).
- Misuse via a legitimately granted capability — that's the deployer's policy
  to set, not DCP's.

## Hardening notes for deployers

- Treat the Bridge as a privileged process. Run it under a service account
  with minimum filesystem access.
- Store HMAC secrets in your OS keychain or a secret manager, not in plain
  files or env vars baked into shell history.
- Set short TTLs on capability tokens (the v0.2 default of 3600 s is a
  ceiling, not a target — minutes are better when the workload allows).
- If the bus is shared (RS-485 multi-drop, public MQTT broker), terminate
  TLS / link-layer encryption at the Bridge.
