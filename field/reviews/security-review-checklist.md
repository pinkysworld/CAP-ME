# Independent security review checklist

- Verify the exact review-bundle hashes before review.
- Review nonce and message-ID generation, key separation, replay behavior, and
  acknowledgement authentication.
- Review erasure-code metadata validation, fragment bounds, incomplete-state
  expiry, parser behavior, and memory/CPU denial-of-service limits.
- Review scheduler trust exclusion and failure-domain assumptions.
- Reproduce unit, deterministic-lab, tamper, and loopback tests.
- Document the absence of a production key agreement and prohibit real use
  until an independently reviewed key-management design exists.
- Threat-model malicious carriers, active injection, correlation, traffic
  analysis, endpoint compromise, rollback, logging, and update security.
- Record every finding, severity, disposition, and residual risk. Approval
  requires no unresolved release-blocking findings.
