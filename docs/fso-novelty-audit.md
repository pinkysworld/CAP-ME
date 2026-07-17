# FSO mechanism novelty audit

- **Search cut-off:** 2026-07-16
- **Status:** candidate contribution; negative searches do not prove novelty
- **Claim scope:** mechanism-level composition, not novelty of its components

## Defensible candidate claim

> In a structured search through 16 July 2026, we found no prior system that
> jointly selects redundant carrier portfolios using messaging-function
> deadlines, longitudinal censorship-survival estimates, a hard
> provider-control constraint, and cross-carrier failure-domain discounts.

This is a defeasible search result, not proof of priority. It is appropriate
only for the implemented and evaluated combination. It must not be shortened
to “first adaptive circumvention protocol,” “first multipath circumvention
system,” or “first transport-independent session.”

## Closest work and required distinction

| Work | Existing contribution | FSO's remaining candidate non-overlap |
|---|---|---|
| [Turbo Tunnel](https://www.usenix.org/conference/foci20/presentation/fifield) | Reliable inner session survives changes in transient outer carriers | Function-specific portfolio selection, trust constraints, and survival-hazard feedback |
| [Raceboat](https://petsymposium.org/popets/2024/popets-2024-0027.php) | Modular application-tunneling and signaling-channel framework | Native messaging-operation deadlines and adaptive multi-carrier scheduling |
| [CoMPS](https://doi.org/10.56553/popets-2022-0083) | Mid-session splitting across heterogeneous paths and protocols | Resource-bounded censor survival rather than single-vantage traffic-analysis resistance |
| [Snowflake](https://www.usenix.org/conference/usenixsecurity24/presentation/bocovich) | Temporary WebRTC proxies and secure rendezvous | Uses ephemeral relays as one carrier family; does not claim relay novelty |
| [UPGen](https://www.usenix.org/conference/usenixsecurity25/presentation/wails) | Large populations of generated structured protocols | Uses generated transports as one family; does not claim generation novelty |
| [STORM](https://www.usenix.org/conference/atc25/presentation/hu-liekun) | Reliability-aware Multipath QUIC scheduling for unstable mobile streaming | Censorship-survival and trust constraints across heterogeneous carrier families |
| [DTN architecture](https://www.rfc-editor.org/rfc/rfc4838) | Message-oriented store-and-forward over disrupted paths | Does not claim message overlays or disruption tolerance generally |
| [MIRAGE](https://www.ndss-symposium.org/ndss-paper/mirage-private-mobility-based-routing-for-censorship-evasion/) | Privacy-preserving mobility-based censorship-resistant messaging | FSO is Internet-carrier orchestration, not mobility routing |
| [CensorLab](https://censorlab.cs.umass.edu/) | Generic packet censorship emulation and an official multi-technique `mega_gfw` demonstration | FSO adds message deadlines, coded carrier portfolios, ACK-aware reconstruction, and longitudinal outcome feedback; it does not claim a new generic GFW emulator |

## Search result

The searched primary literature did not reveal a system containing all of:

1. native messaging-function classes with different deadline/coding policies;
2. replaceable generated, ephemeral, fixed, and provider-controlled carrier
   families under one encrypted session;
3. online selection based on longitudinal delivery survival and endpoint-risk
   history;
4. explicit failure-domain correlation penalties; and
5. a hard provider-control policy distinct from availability.

The audit can miss patents, proprietary deployments, non-English publications,
unindexed theses, and work published after the cut-off. Repeat patent and
forward-citation searches before submission or public novelty claims.
