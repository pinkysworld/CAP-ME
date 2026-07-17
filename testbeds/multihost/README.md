# Closed multi-host packet testbed

This testbed runs the FSO sender, six carrier fault adapters, and receiver as
eight separate non-root containers. The experiment network is created with
Docker's `Internal` flag, no container publishes a port, all Linux
capabilities are dropped, `no-new-privileges` is set, and every experiment
root filesystem is read-only. The sender and proxies independently reject a
destination unless every resolved address is loopback, RFC 1918, or IPv6
unique-local space.

The root `.dockerignore` is an allowlist for this build: only `src/`, the
reviewed multi-host config, and this build directory enter the Docker context.
The private manuscript and rendered paper therefore cannot enter an image
layer or build cache. The base image is fixed by digest and Python dependencies
are fixed by exact version. The observed final image ID is recorded in
`results/processed/fso/multihost/environment.json`.

## Run

Start a local Docker or Colima engine, then from the repository root run:

```bash
make fso-multihost
```

Use `--rebuild` with `analysis/run_fso_multihost.py` to rebuild the image. Image
construction may download the pinned base image and Python wheels. The actual
experiment then runs only on the newly created internal network.

The orchestrator verifies the network, addresses, security settings, and zero
port mappings before waiting for the sender. It removes only its uniquely named
containers, output volume, and internal network; the image remains cached. It
writes:

- `observations.csv`: one row per synthetic operation;
- `manifest.json`: delivery, calibration, resource, recovery, and fault data;
- `environment.json`: image, engine, containment, source-hash, and container
  identities.

The six frozen phases are a clean start, fixed-endpoint pressure,
generated-transport classifier pressure, correlated relay discovery,
congestion, and recovery. They are author-declared failure injection—not a GFW
model. After each phase, the client waits for delayed datagrams and requests
deadline-bound expiry of incomplete receiver state. Both receiver queues must
return to zero.

The packet-path run uses `fso_no_feedback`. This keeps operating-system timing
noise from changing subsequent lane choices and leaves the disputed online
learning mechanism to its separate prospectively frozen evaluation.

## Interpretation and safety boundary

The analytic probability in the output assumes independent per-datagram
loss/corruption plus a Gaussian delay approximation. Agreement with observed
packets is an implementation-concordance check under the same declared fault
parameters. It is not calibration or external validity for a deployed censor.

Do not attach these containers to a normal bridge, host network, VPN, live
interface, or external service. This repository contains no external carrier
connector. Any external implementation remains blocked on the exact-bundle
independent security, ethics, legal, and owned-infrastructure authorization in
`field/`.
