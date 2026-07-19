# CAP-ME novelty audit

- **Search cut-off:** 2026-07-19
- **Audit type:** structured scoping review, not a registered systematic review
- **Claim status:** bounded “to our knowledge” claim; novelty cannot be proven exhaustively

## Candidate contribution after audit

The defensible contribution is not “the first censorship emulator,” “the first adaptive censor,” “the first proxy survival simulator,” or “the first generated transport.” Those claims are contradicted by prior work.

The narrower candidate contribution is:

> In our structured search through 17 July 2026, we found no prior reproducible
> benchmark that jointly models messaging-function survival across path,
> endpoint, and provider/platform control, uses exact layer interventions under
> paired randomness to attribute longitudinal availability loss, and keeps
> provider trust separate from reachability.

This sentence is appropriate only with the following qualifications:

- CAP-ME is currently a controlled synthetic study.
- Architecture parameters are assumptions, not measurements of products or countries.
- The audit may have missed unpublished, non-English, proprietary, or poorly indexed work.
- A peer reviewer may identify closer prior art; the claim should then be revised.

## Search protocol

The audit searched combinations of: `censorship emulation`, `adaptive censor`, `proxy distribution game`, `ephemeral proxy`, `active probing`, `traffic classification`, `generated protocol`, `programmable protocol`, `secure messaging availability`, `messaging censorship`, `platform control`, `function-level availability`, `survival analysis`, and `layer attribution`.

Primary-source indexes and official project pages were prioritized: USENIX, NDSS, IEEE, ACM Digital Library/DOI records, PoPETs/FOCI, arXiv, authors’ official project pages, Signal specifications, official software repositories, and Citizen Lab reports. Bibliographic metadata used by the research is recorded in `artifacts/references.bib` and `artifacts/reference-validation.json`.

## Closest work and non-overlap

| Work | What it already contributes | What CAP-ME must not claim | Remaining non-overlap in CAP-ME |
|---|---|---|---|
| [CensorLab](https://censorlab.cs.umass.edu/) | Generic, high-performance emulation of deployed and hypothetical censorship, including ML logic; its official repository also contains a multi-technique `mega_gfw` demonstration | First censorship emulator, first programmable adaptive testbed, or first GFW-oriented emulator | Packet-decision to messaging-function survival bridge, provider-control dimension, adaptive campaign lifecycle, and exact longitudinal layer attribution |
| [The Game Has Changed](https://www.petsymposium.org/foci/2026/foci-2026-0003.php) | Simulation of ephemeral proxies, NAT restrictions, traffic-informed enumeration, and censor/distributor strategies | First ephemeral-proxy or adaptive enumeration simulator | Composed platform layer, function semantics, paired three-layer Shapley attribution |
| [Enemy at the Gateways](https://www.ndss-symposium.org/ndss-paper/enemy-at-the-gateways-censorship-resilient-proxy-distribution-using-game-theory/) | Game-theoretic proxy distribution and simulation | First formal proxy-assignment comparison | Cross-architecture messaging-function benchmark rather than optimal assignment |
| [Snowflake](https://www.usenix.org/conference/usenixsecurity24/presentation/bocovich) | Deployed temporary WebRTC proxies, dynamic rendezvous, recovery from disappearing proxies | First ephemeral relay architecture | Abstract cross-layer comparison and per-function survival, not a replacement design |
| [SpotProxy](https://www.usenix.org/conference/usenixsecurity24/presentation/kon) | Cloud-address churn and live connection migration | First churn-based proxy resilience | Controlled architecture comparison and layer attribution |
| [QUICstep](https://petsymposium.org/popets/2026/popets-2026-0014.php) | Evaluates connection-migration-based QUIC censorship circumvention | First connection-migration or QUIC-based circumvention mechanism | Function-level benchmark and bounded carrier-portfolio evaluation across path, endpoint, and provider control |
| [UPGen](https://www.usenix.org/conference/usenixsecurity25/presentation/wails) and [Proteus](https://www.petsymposium.org/foci/2023/foci-2023-0013.pdf) | Generated/unidentified and programmable protocols | First protocol generation or rapid protocol evolution | Effects of such diversity inside a larger messaging lifecycle model |
| [Traffic-fingerprinting work](https://www.usenix.org/conference/usenixsecurity24/presentation/xue-fingerprinting) | Protocol-agnostic passive features and low-collateral classification evidence | First passive classifier or first encrypted-traffic fingerprint | Classifier is a transparent model component, not the principal novelty |
| [Active-probing work](https://www.ndss-symposium.org/ndss-paper/detecting-probe-resistant-proxies/) | Empirical techniques for confirming proxy endpoints | First probing-aware threat model | Endpoint burn as one layer in a composed availability process |
| [Camoufler](https://doi.org/10.1145/3433210.3453080) and [Raceboat](https://petsymposium.org/popets/2024/popets-2024-0027.php) | IM-based tunneling and modular application-tunneling/signaling frameworks | First application-aware or IM-related circumvention work | Native messaging-function availability and provider-control analysis rather than carrying arbitrary web traffic |
| [Citizen Lab platform studies](https://citizenlab.ca/research/should-we-chat-too-security-analysis-of-wechats-mmtls-encryption-protocol/) | Evidence that transport encryption and provider visibility are distinct | First observation of platform trust differences | A benchmark dimension that refuses to collapse reachability and confidentiality into one score |

## Negative search findings

Within the searched corpus, no work was found that simultaneously included all four elements below:

1. messaging functions (text, presence, media, file, real-time) as distinct availability outcomes;
2. path, endpoint, and provider/platform control in the same longitudinal model;
3. all eight interventions over those three layers with common random numbers; and
4. attribution of AUAC loss to layers while reporting a separate privacy/trust matrix.

This is a negative search result, not proof of absence.

The structural-uncertainty ensemble and closed multi-host packet testbed improve
the evidence for the implemented benchmark; they do not enlarge this novelty
claim or establish correspondence to a deployed censor.

FSO is a mechanism case study, not the principal priority claim. Persistent
sessions, heterogeneous multipath use, deadline/reliability scheduling,
connection migration, erasure coding, and authenticated encryption are prior
art. The corrected matched-baseline experiment does not establish that FSO's
additional burn or failure-domain terms outperform ordinary deadline-and-cost-
aware failover. Its defensible role is to make CAP-ME's function-survival and
trust constraints executable and falsifiable in closed testbeds.

## Pre-submission refresh

Repeat the search immediately before submission, especially for 2026–2027 proceedings and preprints. Search forward citations of CensorLab, Fares et al., UPGen, Snowflake, SpotProxy, Raceboat, and the GFW classification papers. Record any changed claim in this file and in the private manuscript’s introduction.
