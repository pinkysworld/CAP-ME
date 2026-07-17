# CAP-ME packet-plane bridge for CensorLab

## Why this exists

CensorLab is already a generic censorship-emulation engine. Its official
`demos/mega_gfw` example combines IP blocking, DNS poisoning, HTTP filtering,
TLS-SNI filtering, QUIC-SNI filtering, fully encrypted traffic detection, and
SSH-banner detection. Building another generic “GFW simulator” would therefore
duplicate existing work.

CAP-ME instead supplies the layer that CensorLab does not target: encrypted
messaging envelopes are fragmented across declared carrier adapters, CensorLab
makes packet-plane decisions, CAP-ME reconstructs deadline-level messaging
outcomes, and the survival-aware scheduler updates from those observed outcomes
over subsequent epochs. This creates a reusable bridge between packet
classification and longitudinal application-function survival.

The official sources are the [CensorLab documentation](https://censorlab.cs.umass.edu/docs/),
the [CensorLab paper](https://arxiv.org/abs/2412.16349), and the
[CensorLab repository](https://github.com/SPIN-UMass/censorlab).

## Safety and interpretation boundary

The supplied study is closed-world and synthetic:

- it writes PCAP files; it never transmits their packets;
- every server address is from an RFC 5737 documentation range;
- CensorLab runs in offline PCAP mode in a container with networking disabled,
  a read-only filesystem, all Linux capabilities dropped, and
  `no-new-privileges` enabled;
- the trace includes real CAP-ME ChaCha20-Poly1305 envelopes, bounded
  fragmentation, and authenticated acknowledgements, but no user data; and
- the declared TCP/UDP lane mappings are experimental factors, not claims about
  commercial systems or deployed circumvention protocols.

The pinned `mega_gfw` configuration is an educational composite of published
techniques. A result against it characterizes those declared rules on the
synthetic trace. It is not a measurement, digital twin, or current operational
model of China’s Great Firewall.

## Reproduce

Use a separate CensorLab checkout at the exact recorded commit:

```bash
git clone https://github.com/SPIN-UMass/censorlab.git /path/to/censorlab
git -C /path/to/censorlab checkout 3eb5997face2d897ddb50771189057815880affc
```

Build only the official CensorLab binary and its offline PCAP dependencies:

```bash
docker build \
  -f "$PWD/testbeds/censorlab/Dockerfile.pcap" \
  --build-arg BUILD_HASH=3eb5997face2d897ddb50771189057815880affc \
  -t censorlab-capme:3eb5997-pcap \
  /path/to/censorlab
```

Run the six-epoch study:

```bash
PYTHONPATH=src python3 analysis/run_censorlab_study.py \
  --config configs/fso-censorlab.json \
  --output results/processed/fso/censorlab \
  --censorlab-repo /path/to/censorlab
```

Run the transparent cross-transport campaign scenario:

```bash
PYTHONPATH=src python3 analysis/run_censorlab_study.py \
  --config configs/fso-censorlab-campaign.json \
  --output results/processed/fso/censorlab-campaign \
  --censorlab-repo /path/to/censorlab
```

The runner refuses a source-commit or image-label mismatch. It writes:

- `operations.csv`: per-message deadline, coding, carrier, ACK, and outcome;
- `packet-decisions.csv`: packet labels and normalized CensorLab actions;
- `epochs.csv`: longitudinal availability and processing summaries;
- `traces/`: deterministic PCAPs and packet-label tables;
- `logs/`: raw CensorLab output; and
- `manifest.json` and `environment.json`: hashes, provenance, safety state, and
  the explicit interpretation limitation.

`conditional_no_censor_availability` is a same-trace diagnostic: it removes
CensorLab’s packet actions while holding the observed scheduler choices fixed.
It is not a separately adapted counterfactual policy and must not be described
as one.

## Versioned results

Against the official pinned `mega_gfw` composite, CensorLab censors 127/654
packets and CAP-ME reconstructs 60/60 successful application operations. By
epoch two, application traffic uses only the two declared UDP relay lanes. The
correct interpretation is that the bridge and adaptive feedback work against
this declared composite; the result is not evidence of real-world GFW
effectiveness.

The artifact's original campaign scenario uses a transparent encrypted-payload
test on both TCP and UDP and quarantines a destination after three suspicious
outbound packets. It censors 436/654 packets and permits 13/60 application
operations. This negative result bounds the mechanism: portfolio scheduling
cannot create censorship survival when its nominally distinct carriers share a
detectable feature and correlated endpoint fate.

The PCAPs, label tables, packet decisions, and application outcomes matched
byte-for-byte across repeated local executions. Processing-time fields and raw
log timing are intentionally not claimed to be bit-reproducible.

## License boundary

CensorLab is GPL-3.0-only at the pinned checkout. CAP-ME is Apache-2.0. CAP-ME
therefore does not vendor, modify, import, or link CensorLab code. The image is
built from the separate external checkout and contains its executable plus the
pinned `mega_gfw` configuration under CensorLab's license. The CAP-ME bridge
emits an interoperable PCAP and invokes that image as an external process.
Reviewers must obtain CensorLab under its own license.
