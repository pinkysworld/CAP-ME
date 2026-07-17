# Claim and evidence ledger

This ledger is the audit trail for the public artifact and the privately maintained manuscript. “Generated” claims must be reproducible from repository outputs; “external” claims must have a verified primary source in `artifacts/references.bib` and `artifacts/reference-validation.json`.

## Generated quantitative claims

| Claim | Evidence file | Scope guard |
|---|---|---|
| Main matrix contains 900 runs; ablation matrix contains 320 runs | `results/processed/study/analysis_manifest.json` | Deterministic synthetic runs only |
| Direct E2EE mobile AUAC changes 0.827 → 0.266 | `aggregate_metrics.csv`; `paired_contrasts.csv` | Declared model and seed set |
| Fixed App Proxy mobile AUAC changes 0.735 → 0.113 | Same | Not a named product measurement |
| Generated Transport adaptive mobile AUAC is 0.815 | `aggregate_metrics.csv` | Parameterized archetype only |
| Ephemeral Relay adaptive mobile AUAC is 0.771 | Same | Parameterized archetype only |
| Permitted Platform adaptive mobile AUAC is 0.885 | Same | Availability does not imply provider confidentiality |
| Endpoint attribution is 0.585 for Direct E2EE and 0.697 for Fixed App Proxy | `shapley_attribution.csv` | Exact three-layer model, eight paired seeds |
| Path attribution exceeds endpoint attribution for Ephemeral Relay | Same | 0.089 versus 0.016 in this model |
| Media is not uniformly worse than text | `aggregate_metrics.csv`; generated function table | H6 is only partly supported |
| FSO confirmation AUAC is 0.912 [0.907, 0.917] | `results/processed/fso/confirmation/aggregate_metrics.csv` | Synthetic adaptive-mobile trace replay; 20 disjoint seeds |
| FSO exceeds session failover by 0.016 [0.014, 0.018] | `results/processed/fso/confirmation/paired_contrasts.csv` | Paired synthetic seeds; not a deployment effect |
| FSO byte overhead is 1.246 versus 1.212 for session failover | FSO aggregate metrics | Payload-normalized encoded/envelope bytes in replay |
| No-semantics duplication reaches 0.927 AUAC at overhead 2.000 | FSO aggregate metrics | Higher availability with 60.5% more bytes than FSO |
| Full FSO is 0.0024 AUAC below no-feedback | FSO paired contrasts | Retained adverse result; current feedback not credited |
| Failure-domain diversity adds 0.024 AUAC | FSO paired contrasts | Specific declared correlation model and trace |
| Strict-trust FSO assigns zero provider-controlled attempts | FSO study and loopback manifests | Policy invariant, not empirical confidentiality measurement |
| Deterministic full-protocol lab completes 100/125 operations | `results/processed/fso/deterministic-lab/manifest.json` | One frozen descriptive failure matrix; not an inferential or field result |
| Two deterministic-lab executions produce identical CSV and manifest bytes | `tests/test_fso_lab.py`; deterministic-lab manifest | Laboratory-only deterministic entropy; prohibited for deployment |
| The lab injects 318 drops, 39 corruptions, 57 duplicates, two ACK drops, and six corrupted ACKs | Deterministic-lab manifest | Injected events, not observed censor behavior |
| Envelope and ACK authenticators reject eight and six delivered corruptions, respectively | Deterministic-lab manifest | Other corrupted fragments belonged to incomplete sets and never reached AEAD verification |
| Loopback run completes 57/60 operations | `results/processed/fso/loopback/manifest.json` | One localhost impairment scenario only |
| The pinned official CensorLab `mega_gfw` composite censors 127/654 packets while the bridge reconstructs 60/60 successful application operations | `results/processed/fso/censorlab/manifest.json`; packet and operation CSVs | Declared synthetic rules and lane mappings only; not evidence about China or a deployed GFW |
| In the official composite, application choices move to the two declared UDP lanes after two feedback epochs | `results/processed/fso/censorlab/operations.csv` | Demonstrates scheduler response to this rule set; does not establish durable evasion |
| The transparent cross-transport campaign censors 436/654 packets and permits 13/60 application operations | `results/processed/fso/censorlab-campaign/manifest.json` | Original synthetic stress scenario, not a measurement or faithful censor replica |
| Campaign function availability is text 0.667, presence 0.250, media 0.083, realtime 0.083, and file 0.000 | Same | Descriptive single-scenario result; no population inference |
| Both CensorLab scenarios record zero external destinations, live interfaces, and provider-controlled attempts | Both CensorLab manifests and environment records | Safety and policy invariants, not empirical anonymity or confidentiality claims |

## External factual claims

| Claim | Primary source key | Permitted wording |
|---|---|---|
| Generic censorship emulation including hypothetical ML logic already exists | `sheffey2025censorlab` | CensorLab motivates a narrower novelty claim |
| Recent proxy-distribution simulation includes ephemeral proxies and traffic-informed enumeration | `fares2026game` | CAP-ME is not first to simulate these components |
| Passive fully encrypted-traffic detection has been empirically characterized | `wu2023fullyencrypted` | Do not generalize its exact mechanism to every censor |
| Protocol-agnostic nested-TLS fingerprints can expose obfuscated proxies | `xue2024fingerprinting` | Evidence that transport diversity is not automatically sufficient |
| Active probing can confirm suspected proxy endpoints | `ensafi2015probing`, `frolov2020probe` | Motivates endpoint control; simulator is not a replica |
| Snowflake uses a large changing pool of temporary proxies | `bocovich2024snowflake` | Motivates the ephemeral archetype |
| SpotProxy uses VM churn and migration | `kon2024spotproxy` | Motivates address churn, not numeric calibration |
| UPGen generates unidentified protocols | `wails2025upgen` | Motivates generated transport, not model validation |
| X3DH and Double Ratchet define E2EE session properties | `marlinspike2016x3dh`, `perrin2025doubleratchet` | Supports content-boundary discussion only |
| WhatsApp’s public proxy repository supports chat and says VoIP is not supported | `whatsapp2026proxy` | Product documentation snapshot as accessed date |
| WeChat studies distinguish transport encryption from provider visibility/control | `knockel2020wechat`, `wang2024mmtls` | Evidence for a separate trust axis, not a universal platform claim |
| A persistent inner session independent of transient outer carriers is prior art | `fifield2020turbo` | FSO does not claim transport-independent session novelty |
| Mid-session splitting across heterogeneous paths/protocols is prior art | `wang2022comps` | FSO does not claim multipath or migration novelty |
| Message overlays over disrupted heterogeneous networks are prior art | `cerf2007dtn` | FSO does not claim general disruption-tolerant messaging novelty |
| Reliability-aware multipath scheduling for mobile media is prior art | `hu2025storm` | FSO's distinction is censorship-survival/trust constraints |
| Reed-Solomon coding and ChaCha20-Poly1305 are established | `reed1960polynomial`, `nir2018chacha` | Component references, not novelty claims |
| HMAC is a standardized keyed-hash message-authentication construction and permits truncation | `krawczyk1997hmac` | Supports authenticated ACK component; not a protocol-security proof |

## Authorship and source-use safeguards

- Manuscript prose was drafted specifically for this artifact; no source abstract or paper passage is copied.
- Direct quotations are not used.
- Product and country names appear only when a cited source directly concerns them.
- All model numbers come from source code/configuration or generated outputs, never from a paper about a named deployment.
- The failed fixed-code pilot, corrected deadline double-counting error, and adverse feedback ablation are disclosed rather than removed.
- Citation metadata was checked against official venue, publisher, author-project, specification, or repository pages through 2026-07-17.
- The novelty statement is explicitly defeasible and should be refreshed before submission.

These controls reduce plagiarism and hallucination risk; they cannot substitute for a journal’s similarity checker, independent literature review, or author accountability.
