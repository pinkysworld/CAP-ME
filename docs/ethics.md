# Ethics and responsible research boundary

## Current study

CAP-ME uses synthetic feature vectors, abstract endpoint identifiers, simulated
network outcomes, and declared architecture parameters. FSO adds a
deterministic closed-world carrier lab, synthetic encrypted UDP traffic
restricted to localhost or an internal-only container network, and offline
PCAP evaluation through a separately obtained CensorLab executable. The artifact contains no human-subject data,
user messages, external packet captures, account identifiers, live targets, or
third-party service interactions. No experiment sends test traffic beyond
loopback or private addresses on that internal network; the CensorLab container
has networking disabled. The multi-host containers publish no ports, run with
read-only roots and dropped capabilities, and reject any resolved destination
outside loopback, RFC 1918, or IPv6 unique-local space.

The code is scoped to research evaluation. It provides a laboratory message
overlay but no external carrier connector, production key agreement, scanner,
endpoint-discovery tool, traffic impersonator, target list, or instructions for
evading a named censor. The loopback test rejects non-loopback destinations;
the multi-host test additionally requires the orchestrator-verified internal
network and rejects non-private destinations.

## Dual-use assessment

A cross-layer model could help defenders identify brittle assumptions, but it could also help an adversary reason about which control layer is most effective. The public artifact therefore keeps the censor abstract, uses low-dimensional synthetic features, omits operational signatures and target acquisition, reports aggregate architecture-level results, and makes external implementation conditional on a separate authorization package.

## Requirements before field work

Any extension involving real users, censored regions, live services, or network measurement requires a new protocol and is outside the authorization of this artifact. At minimum it should include:

1. institutional ethics review or a documented determination of non-human-subject research;
2. local legal and safety review for every measurement jurisdiction;
3. data minimization, informed consent where applicable, and a retention/deletion schedule;
4. no active probing of systems without explicit authorization;
5. a harm analysis for users, relay operators, service providers, and bystanders;
6. staged testing with stop conditions and independent security review;
7. coordinated disclosure if measurements reveal a deployed vulnerability; and
8. publication review to remove operational details that add risk without scientific necessity.

The files in `field/` make these requirements inspectable. The validator checks that an authorization record names owned hosts, review references, dates, limits, contacts, and prohibitions on human participants, third-party traffic, personal data, and active probing. For an external scope it also verifies the hashes of the exact review bundle and requires unexpired records from three distinct security, ethics, and legal reviewers who attest independence, conflicts, and resolution of findings. It cannot determine that a submitted record is genuine and does not grant any approval. The supplied complete record is explicitly loopback-only and cannot authorize external implementation; all external review templates intentionally remain pending and fail validation.

## Interpretation rule

High simulated availability is not equivalent to user safety. A permitted provider may be reachable while retaining delivery control or access to plaintext. Conversely, a low simulated score is not evidence that a named system fails in a real country. The paper reports availability and trust as separate axes.
