# Function-Survival Overlay protocol specification

**Working name:** FSO
**Protocol version:** 0.3 laboratory prototype
**Scope:** researcher-controlled evaluation only

## Purpose

FSO is a message-oriented session layer that remains independent of any one
carrier. It assigns encrypted messaging operations to a portfolio of carrier
instances according to the operation's deadline, required delivery fraction,
recent delivery survival, endpoint-failure history, carrier correlation, and a
hard trust policy.

FSO does not define a traffic disguise, proxy-discovery technique, active probe,
or production key agreement. The prototype accepts an externally established
32-byte session key and uses a standard AEAD solely to demonstrate that every
carrier receives ciphertext. A production implementation must replace the test
key interface with an independently reviewed Double Ratchet or MLS integration.

## Design requirements

1. The logical messaging session survives loss or replacement of a carrier.
2. Text, presence, media, file, and real-time operations receive different
   scheduling policies because their deadlines and recovery costs differ.
3. No carrier receives a plaintext function label or application payload.
4. A strict-trust policy excludes provider-controlled carriers regardless of
   predicted availability.
5. Experimental delivery feedback updates only local estimates. A sender does
   not receive censor-internal labels or future trace values. Feedback is not
   credited as a benefit: the prospectively frozen 12-seed audit classified the
   current update rule as harmful in its declared synthetic model, so the
   default is disabled.
6. Correlated carrier instances are discounted; two endpoints in one failure
   domain are not counted as two independent defenses.
7. External destinations are rejected by the executable loopback testbed.

## Operation classes

| Function | Default coding | Dispatch rule | Design reason |
|---|---:|---|---|
| Text | 1-of-1, 1-of-2 | single, failover, or parallel | Small payload; reliability can justify duplication |
| Presence | 1-of-1, 1-of-2 | opportunistic or failover | Stale updates can be replaced |
| Media | 1-of-1, 1-of-2, 2-of-3 | single, failover, duplicate, or coded | Moderate deadline and segmentation |
| File | 1-of-1, 1-of-2, 2-of-3, 3-of-5 | single, failover, or coded | Bulk transfer tolerates coding delay only when useful |
| Real-time | 1-of-1, 1-of-2 | single, parallel, or timed hot standby | Striping across unequal paths can add jitter |

FSO 0.3 selects among these predeclared plans instead of assuming maximum
redundancy is always beneficial. The fixed-policy 0.1 result is retained in
`docs/fso-development-log.md` as an exploratory negative result. The operation
class is an input to the local scheduler. It is serialized only
inside encrypted shard plaintext and is therefore not visible in the FSO frame
header.

## Carrier model

Each carrier instance declares:

- a carrier family and failure domain;
- a trust domain and whether its provider controls delivery;
- an initial delivery prior and latency estimate;
- endpoint stability and rotation properties; and
- an abstract byte cost.

Carrier declarations are experimental assumptions. The repository includes no
live proxy address, platform credential, service impersonation logic, scanning,
or target acquisition.

## Scheduler

For operation `o` and candidate carrier portfolio `S`, the full scheduler ranks
feasible plans using:

`U(o,S) = P(complete before deadline | local history) - byte_cost - linkability - burn_risk - correlation_penalty`

Confidentiality and provider-control rules are constraints, not soft terms. The
prototype estimates per-function delivery probability with a beta posterior and
latency with a bounded exponentially weighted mean. Failure-domain correlation
reduces the predicted benefit of selecting related instances. The sender never
uses future outcomes from an evaluation trace.

## Coding and envelope

The prototype implements a systematic Reed--Solomon-style MDS code over
GF(256). A message is padded into `k` equal data shards and encoded into `n`
shards; any `k` valid shards recover the original bytes.

Each shard is protected independently with ChaCha20-Poly1305 using a fresh
96-bit nonce. Associated data authenticates:

- magic and protocol version;
- a random 128-bit message identifier;
- shard index;
- threshold and total shard count; and
- original plaintext length.

AEAD integrity is checked before a shard enters the decoder. Completed message
identifiers and duplicate shard indices are rejected by the receiver state
machine. The prototype does not claim forward secrecy, post-compromise security,
metadata anonymity, or resistance to endpoint compromise.

Envelope packets are split into bounded datagram fragments. The public fragment
header carries only the message identifier, shard index, part number, and total
part count. Reassembly accepts out-of-order fragments, ignores duplicates, caps
in-flight state, remembers recently completed fragment sets, and expires
incomplete message state after the application deadline. The complete envelope
AEAD—not the public fragment header—provides end-to-end integrity.

The receiver authenticates each shard acknowledgement using a 128-bit truncated
HMAC-SHA-256 tag under a key derived with an explicit FSO ACK domain label from
the laboratory session key. ACKs disclose the already-public message identifier
and shard index but cannot be accepted after modification without forging the
tag. Production key agreement and formal traffic-analysis protection remain out
of scope.

## Receiver state machine

1. Parse the fixed public header and reject malformed dimensions.
2. Authenticate and decrypt the shard.
3. Reject a replayed completed message or duplicate shard index.
4. Buffer shards under the random message identifier.
5. Once `k` shards exist, decode and validate the inner operation structure.
6. Mark the identifier complete and erase buffered shards.
7. Expire incomplete fragment and shard state at the operation deadline.

## Evaluation modes

- **Trace replay:** large deterministic experiments replay CAP-ME's versioned,
  per-function synthetic availability and completion-time traces under common
  random numbers.
- **Deterministic carrier lab:** an in-process discrete-event harness exercises
  scheduling, coding, envelopes, fragmentation, reordering, duplication,
  correlated loss and outage, integrity faults, ACK loss, and authenticated ACK
  rejection. It uses reproducible test entropy solely so independent rebuilds
  can be compared byte-for-byte; that entropy source is prohibited in any
  deployment.
- **Loopback packet testbed:** actual encrypted UDP datagrams traverse only
  `127.0.0.0/8` or `::1` endpoints with controlled loss, jitter, and delay.
- **Closed multi-host packet testbed:** a sender, six carrier-fault adapters,
  and receiver run as separate non-root containers on an internal Docker
  network with no published ports. Each destination must resolve only to
  loopback, RFC 1918, or IPv6 unique-local addresses. Frozen phases exercise
  loss, corruption, ACK faults, congestion, recovery, and deadline-bound state
  expiry; agreement with its analytic packet model is implementation
  concordance only.
- **Field package:** a non-networking validator checks authorization, expiry,
  ownership, data minimization, stop rules, exact review-bundle hashes, three
  distinct independent reviewer records, review expiry, and unresolved
  findings. No external transport is implemented in version 0.3.

## Security and deployment status

FSO 0.3 is a research prototype, not a safety-reviewed circumvention product.
Before any external implementation, the protocol needs an independent
cryptographic review, abuse analysis, jurisdiction-specific legal review,
institutional ethics review or documented exemption, owned infrastructure,
participant safety procedures, and prospective stop conditions.
