# Independent review records

External implementation remains disabled until all three JSON records contain
real decisions from distinct reviewers who did not develop or author the
artifact. Copy the current `bundle_id` from
`field/review-bundle-manifest.json`; a record for any other bundle is rejected.

The templates are deliberately pending. Do not change `status`, independence
attestations, dates, findings, or decision references unless the named reviewer
has actually issued that decision. The validator checks completeness, file
integrity, bundle identity, expiry, reviewer separation, and unresolved
findings. It cannot determine whether a submitted approval is genuine.

Review coverage:

- `security-review-checklist.md`: cryptography, protocol, implementation, and abuse cases;
- `ethics-review-checklist.md`: participants, third parties, data minimization, and harms;
- `legal-review-checklist.md`: applicable jurisdictions, authorizations, and restrictions.
