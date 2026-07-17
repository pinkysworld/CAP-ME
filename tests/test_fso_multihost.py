from __future__ import annotations

import json
import unittest
from pathlib import Path

from capme.fso.multihost import (
    decode_control,
    encode_control,
    is_closed_lab_address,
    packet_success_probability,
    resolve_closed_lab_host,
    validate_multihost_config,
)

ROOT = Path(__file__).resolve().parents[1]


class FSOMultihostTests(unittest.TestCase):
    def test_address_policy_accepts_only_loopback_private_and_ula(self) -> None:
        for value in (
            "127.0.0.1",
            "::1",
            "10.1.2.3",
            "172.16.4.5",
            "172.31.255.254",
            "192.168.20.3",
            "fd12:3456::1",
        ):
            self.assertTrue(is_closed_lab_address(value), value)
        for value in (
            "0.0.0.0",
            "8.8.8.8",
            "172.32.0.1",
            "169.254.1.1",
            "224.0.0.1",
            "2001:4860:4860::8888",
        ):
            self.assertFalse(is_closed_lab_address(value), value)
        self.assertEqual(resolve_closed_lab_host("127.0.0.1", 9000), ("127.0.0.1",))
        with self.assertRaisesRegex(ValueError, "external destination"):
            resolve_closed_lab_host("8.8.8.8", 9000)

    def test_control_plane_authentication_rejects_tampering(self) -> None:
        key = bytes(range(32))
        packet = encode_control(
            key, {"kind": "set_phase", "phase": "clean_start", "token": "1"}
        )
        self.assertEqual(decode_control(key, packet)["phase"], "clean_start")
        tampered = bytearray(packet)
        tampered[-1] ^= 0x01
        with self.assertRaisesRegex(ValueError, "authentication"):
            decode_control(key, bytes(tampered))

    def test_reviewed_config_is_closed_and_complete(self) -> None:
        config = json.loads(
            (ROOT / "configs" / "fso-multihost.json").read_text(encoding="utf-8")
        )
        validate_multihost_config(config)
        self.assertTrue(config["closed_world"])
        self.assertTrue(config["docker_internal_network_required"])
        self.assertTrue(config["strict_trust"])
        self.assertEqual(config["scheduler_strategy"], "fso_no_feedback")
        self.assertGreaterEqual(len(config["phases"]), 6)
        self.assertTrue(
            any(row["provider_controls_delivery"] for row in config["lanes"])
        )

    def test_declared_packet_probability_includes_every_fragment_and_ack(self) -> None:
        impairment = {
            "data_loss": 0.1,
            "ack_loss": 0.2,
            "data_corruption": 0.0,
            "ack_corruption": 0.0,
            "data_duplication": 0.0,
            "latency_ms": 5.0,
            "jitter_ms": 0.0,
        }
        value = packet_success_probability(
            fragment_count=2, impairment=impairment, timeout_ms=20.0
        )
        self.assertAlmostEqual(value, 0.9**2 * 0.8)
        impairment["latency_ms"] = 11.0
        self.assertEqual(
            packet_success_probability(
                fragment_count=2, impairment=impairment, timeout_ms=20.0
            ),
            0.0,
        )


if __name__ == "__main__":
    unittest.main()
