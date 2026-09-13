# Publisher boundary

v0.1 includes two local publisher modes:

- `DryRunPublisher` returns a structured plan with `remote_write=0`.
- `ManualPublisher` creates a human handoff manifest and local text files.

Both require an approved, integrity-valid content packet. A mutation after
approval invalidates the packet. The duplicate guard reuses the logical
package identity for the same approved content.

No HTTP upload, browser automation, OAuth flow, account session, scheduling,
or social write implementation is included. A future live publisher belongs
in an optional adapter with explicit credentials, remote-write consent,
idempotency, resume, platform policy, failure handling, tests, and a human
authorization boundary.
