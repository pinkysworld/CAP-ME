# Stage-3 status: review-ready, not externally authorized

The stage-3 package is complete as a prospective study gate. It does not
authorize or implement an external deployment.

Current state:

- `loopback-authorization.json` is complete for localhost only;
- the validator reports `scope: loopback-only` and
  `ready_for_external_implementation: false`;
- `authorization-template.json` intentionally remains pending and fails the
  completeness check;
- `review-bundle-manifest.json` binds reviews to exact source, evidence, and
  protocol hashes;
- `reviews/` contains pending records and separate security, ethics, and legal
  checklists; the three decisions must come from distinct independent reviewers;
- `study-protocol.md` defines the owned-infrastructure progression;
- `stop-rules.md` defines prospective termination conditions; and
- the repository contains no external FSO carrier connector.

To begin a separate external study, the responsible investigators must first
give the exact bundle to independent security, ethics, and legal reviewers.
After all release-blocking findings are resolved, each reviewer must return a
dated decision tied to the bundle ID. The investigators must then supply a
named set of owned hosts plus genuine infrastructure and operational approvals.
The validator rejects changed bundle files, wrong or expired bundle IDs,
reused reviewer identities, unresolved findings, and incomplete authorization.
Passing it still does not establish that a record is genuine or constitute an
approval. An external connector may be designed only after this gate passes,
on a new branch and under a fresh prospective analysis plan.
