# FSO mechanism novelty audit

- **Search cut-off:** 2026-07-18
- **Status:** candidate contribution; negative searches do not prove novelty
- **Claim scope:** mechanism-level composition, not novelty of its components

## Defensible candidate claim

> In a structured search through 17 July 2026, we found no prior evaluation
> contract that jointly measures messaging-function survival across path,
> endpoint, and provider control, attributes longitudinal loss to those layers,
> and tests a carrier-portfolio mechanism under an explicit provider-control
> constraint.

This is a defeasible search result, not proof of priority. It is appropriate
only for the implemented and evaluated combination. FSO is a benchmark-driven
case study, not a priority claim for an adaptive circumvention protocol. The
statement must not be shortened to “first multipath circumvention system,”
“first deadline-aware scheduler,” or “first transport-independent session.”

## Closest work and required distinction

| Work | Existing contribution | FSO's remaining candidate non-overlap |
|---|---|---|
| [CensorLab](https://censorlab.cs.umass.edu/) | Generic packet-level emulation of past and hypothetical censor mechanisms | CAP-ME supplies longitudinal function outcomes, layer interventions, and trust separation; the bridge uses rather than replaces CensorLab |
| [Tor Pluggable Transports](https://spec.torproject.org/pt-spec/) | Standard interface for modular traffic-transforming circumvention subprocesses | FSO consumes abstract carrier instances; it does not define a new pluggable-transport interface or wire disguise |
| [Format-Transforming Encryption](https://doi.org/10.1145/2508859.2516657) | Ciphertexts can be generated to match chosen regular-language formats and induce protocol misclassification | FSO does not transform ciphertext format or claim protocol mimicry |
| [Marionette](https://www.usenix.org/conference/usenixsecurity15/technical-sessions/presentation/dyer) | Programmable control over ciphertext formats, stateful protocol semantics, and traffic properties | FSO schedules declared carrier instances; it does not claim programmable traffic obfuscation |
| [Geneva](https://doi.org/10.1145/3319535.3363189) | Genetic search composes packet-manipulation primitives into censor-evasion strategies | FSO neither trains against live censors nor claims automated evasion discovery |
| [Turbo Tunnel](https://www.usenix.org/conference/foci20/presentation/fifield) | Reliable inner session survives changes in transient outer carriers | Function-specific plan selection, hard provider-control constraints, and explicit failure-domain discounting |
| [Raceboat](https://petsymposium.org/popets/2024/popets-2024-0027.php) | Modular application-tunneling and signaling-channel framework | Native messaging-operation deadlines and adaptive multi-carrier scheduling |
| [CoMPS](https://doi.org/10.56553/popets-2022-0083) | Mid-session splitting across heterogeneous paths and protocols | Resource-bounded censor survival rather than single-vantage traffic-analysis resistance |
| [Snowflake](https://www.usenix.org/conference/usenixsecurity24/presentation/bocovich) | Temporary WebRTC proxies and secure rendezvous | Uses ephemeral relays as one carrier family; does not claim relay novelty |
| [UPGen](https://www.usenix.org/conference/usenixsecurity25/presentation/wails) | Large populations of generated structured protocols | Uses generated transports as one family; does not claim generation novelty |
| [STORM](https://www.usenix.org/conference/atc25/presentation/hu-liekun) | Reliability-aware Multipath QUIC scheduling for unstable mobile streaming | Censorship-survival and trust constraints across heterogeneous carrier families |
| [DAMS](https://ieeexplore.ieee.org/document/9796942) | Deadline-aware block ordering and allocation over multiple paths | CAP-ME evaluates cross-layer censor survival and provider trust; FSO adds carrier failure domains but does not claim deadline-aware scheduling novelty |
| [DTN architecture](https://www.rfc-editor.org/rfc/rfc4838) | Message-oriented store-and-forward over disrupted paths | Does not claim message overlays or disruption tolerance generally |
| [MIRAGE](https://www.ndss-symposium.org/ndss-paper/mirage-private-mobility-based-routing-for-censorship-evasion/) | Privacy-preserving mobility-based censorship-resistant messaging | FSO is Internet-carrier orchestration, not mobility routing |

## Search result

The searched primary literature did not reveal a system containing all of:

1. native messaging-function classes with different deadline/coding policies;
2. replaceable generated, ephemeral, fixed, and provider-controlled carrier
   families under one encrypted session;
3. sender-local delivery history (evaluated separately and disabled by default
   after the frozen no-benefit result);
4. explicit failure-domain correlation penalties; and
5. a hard provider-control policy distinct from availability.

The audit can miss patents, proprietary deployments, non-English publications,
unindexed theses, and work published after the cut-off. Repeat patent and
forward-citation searches before submission or public novelty claims.
