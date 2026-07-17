# Stage-3 authorized deployment protocol

Version 0.3 deliberately contains no external carrier implementation. This
document defines the evidence required before such code may be added or run.

## Entry criteria

All of the following are mandatory:

1. named, researcher-owned client, carrier, and receiver hosts;
2. institutional ethics approval or a written non-human-subject determination;
3. legal review for every source, transit, and destination jurisdiction;
4. independent cryptographic and implementation security review tied to the
   exact review-bundle ID;
5. an approved data-management and deletion schedule;
6. no unrelated third-party traffic or active probing;
7. prospective operation and duration limits;
8. a reachable safety contact and tested shutdown procedure;
9. distinct, unexpired security, ethics, and legal review records with no
   unresolved release-blocking findings; and
10. a completed authorization manifest accepted by the repository validator.

## Permitted initial study

The first external study must use only synthetic payloads between owned hosts.
It may measure delivery success, completion time, bytes, and local error codes.
It must not collect packet contents, user identifiers, contact graphs, unrelated
addresses, or third-party service data.

## Required progression

1. reproduce deterministic-lab and loopback results;
2. obtain the three independent review decisions and validate their exact
   bundle ID;
3. only after the external gate passes, design and separately review a minimal
   connector for the named owned endpoints;
4. run on one private LAN or isolated cloud network;
5. review logs for unexpected identifiers or destinations;
6. run a bounded two-site owned-infrastructure test; and
7. pause for a new independent review before any broader or user-facing work.

Passing the authorization validator confirms document completeness only. It is
not ethical, legal, or security approval.
