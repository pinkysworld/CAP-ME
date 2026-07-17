"""Researcher-controlled encrypted UDP loopback testbed for FSO."""

from __future__ import annotations

import asyncio
import hashlib
import ipaddress
import json
import random
import time
from collections import Counter
from pathlib import Path
from typing import Any

from capme.io import write_csv, write_json
from capme.model import WORKLOADS

from .crypto import AckAuthenticator, EnvelopeCipher, EnvelopeError
from .framing import (
    FragmentReassembler,
    FramingError,
    fragment_envelope,
    peek_fragment,
)
from .protocol import FSOReceiver, FSOSender
from .scheduler import build_scheduler
from .types import FUNCTIONS, LaneProfile, Operation

MAX_FRAGMENT_DATA = 7600


def require_loopback(host: str) -> None:
    try:
        address = ipaddress.ip_address(host)
    except ValueError as error:
        raise ValueError(f"testbed host must be a literal loopback address: {host}") from error
    if not address.is_loopback:
        raise ValueError(f"external destination rejected by loopback testbed: {host}")


class _ServerProtocol(asyncio.DatagramProtocol):
    def __init__(
        self,
        *,
        receiver: FSOReceiver,
        ack_authenticator: AckAuthenticator,
        loss_rate: float,
        latency_ms: float,
        jitter_ms: float,
        seed: int,
    ) -> None:
        self.receiver = receiver
        self.ack_authenticator = ack_authenticator
        self.loss_rate = loss_rate
        self.latency_ms = latency_ms
        self.jitter_ms = jitter_ms
        self.rng = random.Random(seed)
        self.transport: asyncio.DatagramTransport | None = None
        self.received = 0
        self.dropped = 0
        self.auth_failures = 0
        self.reassembler = FragmentReassembler()

    def connection_made(self, transport: asyncio.BaseTransport) -> None:
        self.transport = transport  # type: ignore[assignment]

    def datagram_received(self, data: bytes, addr: tuple[str, int]) -> None:
        self.received += 1
        try:
            peek_fragment(data)
        except FramingError:
            self.auth_failures += 1
            return
        if self.rng.random() < self.loss_rate:
            self.dropped += 1
            return
        delay = max(0.0, self.rng.gauss(self.latency_ms, self.jitter_ms)) / 1000.0
        asyncio.get_running_loop().call_later(
            delay,
            self._accept_fragment,
            data,
            addr,
        )

    def _accept_fragment(
        self,
        data: bytes,
        addr: tuple[str, int],
    ) -> None:
        try:
            result = self.reassembler.ingest(
                data, peer=f"{addr[0]}:{addr[1]}"
            )
        except FramingError:
            self.auth_failures += 1
            return
        if result.status != "complete" or result.packet is None:
            return
        self._deliver(
            result.packet,
            addr,
            result.header.message_id,
            result.header.shard_index,
        )

    def _deliver(
        self,
        data: bytes,
        addr: tuple[str, int],
        message_id: bytes,
        shard_index: int,
    ) -> None:
        if self.transport is None:
            return
        try:
            self.receiver.ingest(data)
        except (EnvelopeError, ValueError):
            self.auth_failures += 1
            return
        self.transport.sendto(
            self.ack_authenticator.seal(message_id, shard_index), addr
        )


class _ClientProtocol(asyncio.DatagramProtocol):
    def __init__(self, ack_authenticator: AckAuthenticator) -> None:
        self.ack_authenticator = ack_authenticator
        self.transport: asyncio.DatagramTransport | None = None
        self.pending: dict[tuple[bytes, int], asyncio.Future[float]] = {}
        self.ack_auth_failures = 0

    def connection_made(self, transport: asyncio.BaseTransport) -> None:
        self.transport = transport  # type: ignore[assignment]

    def datagram_received(self, data: bytes, _addr: tuple[str, int]) -> None:
        try:
            ack = self.ack_authenticator.open(data)
        except EnvelopeError:
            self.ack_auth_failures += 1
            return
        if ack.status != 1:
            return
        future = self.pending.pop((ack.message_id, ack.shard_index), None)
        if future is not None and not future.done():
            future.set_result(time.perf_counter())

    async def send(self, packet: bytes, timeout_ms: float) -> tuple[bool, float, int]:
        if self.transport is None:
            raise RuntimeError("client transport is not connected")
        public = EnvelopeCipher.peek(packet)
        key = (public.message_id, public.index)
        future = asyncio.get_running_loop().create_future()
        self.pending[key] = future
        started = time.perf_counter()
        datagrams = fragment_envelope(
            packet, max_fragment_data=MAX_FRAGMENT_DATA
        )
        wire_bytes = 0
        for datagram in datagrams:
            wire_bytes += len(datagram)
            self.transport.sendto(datagram)
        try:
            completed = await asyncio.wait_for(future, timeout_ms / 1000.0)
            return True, (completed - started) * 1000.0, wire_bytes
        except TimeoutError:
            self.pending.pop(key, None)
            return False, timeout_ms, wire_bytes


class _Lane:
    def __init__(
        self,
        name: str,
        server_transport: asyncio.DatagramTransport,
        server_protocol: _ServerProtocol,
        client_transport: asyncio.DatagramTransport,
        client_protocol: _ClientProtocol,
        address: tuple[str, int],
    ) -> None:
        self.name = name
        self.server_transport = server_transport
        self.server_protocol = server_protocol
        self.client_transport = client_transport
        self.client_protocol = client_protocol
        self.address = address

    async def send(self, packet: bytes, timeout_ms: float) -> tuple[bool, float, int]:
        return await self.client_protocol.send(packet, timeout_ms)

    def close(self) -> None:
        self.client_transport.close()
        self.server_transport.close()


def _profile(row: dict[str, Any]) -> LaneProfile:
    prefix = str(row["name"]).split("-", 1)[0]
    architecture = {
        "direct": "direct_e2ee",
        "fixed": "fixed_proxy",
        "generated": "generated_transport",
        "ephemeral": "ephemeral_relay",
        "permitted": "platform_controlled",
    }[prefix]
    resilience = {
        "direct": 0.12,
        "fixed": 0.10,
        "generated": 0.72,
        "ephemeral": 0.92,
        "permitted": 0.98,
    }[prefix]
    return LaneProfile(
        name=str(row["name"]),
        architecture=architecture,
        failure_domain=str(row["failure_domain"]),
        latency_prior_ms=float(row["latency_ms"]),
        survival_prior=1.0 - float(row["loss_rate"]),
        endpoint_resilience=resilience,
        provider_controls_delivery=bool(row["provider_controls_delivery"]),
    )


async def _open_lane(
    row: dict[str, Any],
    receiver: FSOReceiver,
    ack_authenticator: AckAuthenticator,
    *,
    host: str,
    seed: int,
) -> _Lane:
    require_loopback(host)
    loop = asyncio.get_running_loop()
    server_protocol = _ServerProtocol(
        receiver=receiver,
        ack_authenticator=ack_authenticator,
        loss_rate=float(row["loss_rate"]),
        latency_ms=float(row["latency_ms"]),
        jitter_ms=float(row["jitter_ms"]),
        seed=seed,
    )
    server_transport, _ = await loop.create_datagram_endpoint(
        lambda: server_protocol, local_addr=(host, 0)
    )
    address = server_transport.get_extra_info("sockname")
    if not isinstance(address, tuple):
        raise RuntimeError("failed to obtain loopback socket address")
    require_loopback(str(address[0]))
    client_protocol = _ClientProtocol(ack_authenticator)
    client_transport, _ = await loop.create_datagram_endpoint(
        lambda: client_protocol, remote_addr=(address[0], address[1])
    )
    return _Lane(
        str(row["name"]),
        server_transport,  # type: ignore[arg-type]
        server_protocol,
        client_transport,  # type: ignore[arg-type]
        client_protocol,
        (str(address[0]), int(address[1])),
    )


async def _dispatch(
    prepared: Any,
    lanes: dict[str, _Lane],
    *,
    timeout_ms: float,
) -> list[tuple[str, bool, float, int]]:
    names = prepared.decision.lanes
    packets = prepared.packets
    mode = prepared.decision.dispatch_mode
    results: list[tuple[str, bool, float, int]] = []
    if mode == "sequential":
        for name, packet in zip(names, packets, strict=True):
            success, latency, wire_bytes = await lanes[name].send(packet, timeout_ms)
            results.append((name, success, latency, wire_bytes))
            if success:
                break
        return results
    if mode == "hot_standby" and len(names) > 1:
        first_task = asyncio.create_task(lanes[names[0]].send(packets[0], timeout_ms))
        fallback_ms = min(timeout_ms * 0.22, 30.0)
        try:
            success, latency, wire_bytes = await asyncio.wait_for(
                asyncio.shield(first_task), fallback_ms / 1000.0
            )
            results.append((names[0], success, latency, wire_bytes))
            if success:
                return results
        except TimeoutError:
            pass
        remaining = [
            asyncio.create_task(lanes[name].send(packet, timeout_ms))
            for name, packet in zip(names[1:], packets[1:], strict=True)
        ]
        first_success, first_latency, first_wire_bytes = await first_task
        results.append((names[0], first_success, first_latency, first_wire_bytes))
        for name, packet, outcome in zip(names[1:], packets[1:], await asyncio.gather(*remaining), strict=True):
            success, latency, wire_bytes = outcome
            results.append((name, success, fallback_ms + latency, wire_bytes))
        return results
    outcomes = await asyncio.gather(
        *(lanes[name].send(packet, timeout_ms) for name, packet in zip(names, packets, strict=True))
    )
    return [
        (name, success, latency, wire_bytes)
        for name, (success, latency, wire_bytes) in zip(names, outcomes, strict=True)
    ]


async def run_loopback(config_path: Path, output_dir: Path) -> dict[str, object]:
    config = json.loads(config_path.read_text(encoding="utf-8"))
    if not config.get("loopback_only"):
        raise ValueError("loopback_only must be true")
    host = "127.0.0.1"
    require_loopback(host)
    seed = int(config["seed"])
    key = hashlib.sha256(f"fso-loopback-{seed}".encode()).digest()
    cipher = EnvelopeCipher(key)
    ack_authenticator = AckAuthenticator(key)
    receiver = FSOReceiver(cipher)
    sender = FSOSender(cipher)
    profiles = [_profile(row) for row in config["lanes"]]
    scheduler = build_scheduler(
        "fso", profiles, strict_trust=True, seed=seed, correlation_weight=0.35
    )
    lane_rows = {str(row["name"]): row for row in config["lanes"]}
    lanes: dict[str, _Lane] = {}
    for index, row in enumerate(config["lanes"]):
        lane = await _open_lane(
            row,
            receiver,
            ack_authenticator,
            host=host,
            seed=seed + 1009 * index,
        )
        lanes[lane.name] = lane
    observations: list[dict[str, object]] = []
    attempted_counts: Counter[str] = Counter()
    try:
        for function_index, function in enumerate(FUNCTIONS):
            payload_size = int(config["payload_bytes"][function])
            for operation_index in range(int(config["operations_per_function"])):
                payload = bytes(
                    ((function_index + operation_index + offset) % 251 for offset in range(payload_size))
                )
                operation = Operation(
                    function,
                    payload,
                    WORKLOADS[function].deadline_ms,
                    strict_trust=True,
                )
                decision = scheduler.plan(operation)
                prepared = sender.prepare(operation, decision)
                timeout_ms = min(250.0, max(70.0, operation.deadline_ms * 0.42))
                started = time.perf_counter()
                results = await _dispatch(prepared, lanes, timeout_ms=timeout_ms)
                elapsed_ms = (time.perf_counter() - started) * 1000.0
                completed = prepared.message_id in receiver.completed
                recovered = receiver.completed.get(prepared.message_id)
                if completed and recovered is not None and recovered.payload != payload:
                    raise AssertionError("loopback payload mismatch")
                for lane_name, success, latency, _packet_size in results:
                    attempted_counts[lane_name] += 1
                    scheduler.update(
                        lane_name,
                        function,
                        success=success,
                        latency_ms=latency,
                    )
                observations.append(
                    {
                        "function": function,
                        "operation": operation_index,
                        "success": int(completed),
                        "elapsed_ms": elapsed_ms,
                        "payload_bytes": payload_size,
                        "wire_bytes": sum(result[3] for result in results),
                        "byte_overhead": sum(result[3] for result in results) / payload_size,
                        "threshold": decision.threshold,
                        "total_shards": decision.total_shards,
                        "dispatch_mode": decision.dispatch_mode,
                        "attempted_lanes": ";".join(result[0] for result in results),
                        "acked_shards": sum(int(result[1]) for result in results),
                        "provider_controlled_attempts": sum(
                            int(lane_rows[result[0]]["provider_controls_delivery"])
                            for result in results
                        ),
                    }
                )
    finally:
        for lane in lanes.values():
            lane.close()
        await asyncio.sleep(0)
    successes = sum(int(row["success"]) for row in observations)
    wire_bytes = sum(int(row["wire_bytes"]) for row in observations)
    payload_bytes = sum(int(row["payload_bytes"]) for row in observations)
    observation_hash = write_csv(output_dir / "observations.csv", observations)
    manifest = {
        "schema_version": 1,
        "loopback_only": True,
        "synthetic_payloads": True,
        "external_destinations": 0,
        "bound_addresses": [f"{lane.address[0]}:{lane.address[1]}" for lane in lanes.values()],
        "operations": len(observations),
        "successful_operations": successes,
        "availability": successes / len(observations),
        "payload_bytes": payload_bytes,
        "wire_bytes": wire_bytes,
        "byte_overhead": wire_bytes / payload_bytes,
        "provider_controlled_attempts": sum(
            int(row["provider_controlled_attempts"]) for row in observations
        ),
        "lane_attempts": dict(sorted(attempted_counts.items())),
        "server_counters": {
            name: {
                "received": lane.server_protocol.received,
                "dropped": lane.server_protocol.dropped,
                "auth_failures": lane.server_protocol.auth_failures,
                "ack_auth_failures": lane.client_protocol.ack_auth_failures,
            }
            for name, lane in sorted(lanes.items())
        },
        "cryptography": (
            "ChaCha20-Poly1305 envelopes and domain-separated HMAC-SHA-256 "
            "acknowledgements with a laboratory pre-shared session key"
        ),
        "observations_sha256": observation_hash,
    }
    if manifest["provider_controlled_attempts"] != 0:
        raise AssertionError("strict-trust loopback used a provider-controlled lane")
    write_json(output_dir / "manifest.json", manifest)
    return manifest


def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    manifest = asyncio.run(run_loopback(args.config, args.output))
    print(json.dumps(manifest, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
