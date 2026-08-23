# Privacy

The default demo processes local synthetic fixtures and writes local files. It
does not open accounts, read browser state, send telemetry, call a provider,
or publish content.

Optional adapters can change that boundary. Before enabling one, review its
data destination, retention, training policy, identifiers, secret handling,
rights requirements, and deletion process. Keep credentials in a supported
runtime secret mechanism, never in fixtures, logs, manifests, or brand files.

Do not place personal media or account data in the public repository. Private
input should use an external path, explicit rights status, minimum retention,
and a reviewable provenance record. Generated output is not automatically safe
to publish merely because a provider returned it.
