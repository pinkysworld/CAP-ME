from __future__ import annotations

import unittest

from capme.fso.crypto import AckAuthenticator, EnvelopeCipher, EnvelopeError
from capme.fso.framing import FragmentReassembler, fragment_envelope
from capme.fso.protocol import FSOReceiver, FSOSender
from capme.fso.types import Operation, ScheduleDecision


class FSOCryptoTests(unittest.TestCase):
    def setUp(self) -> None:
        self.cipher = EnvelopeCipher(bytes(range(32)))
        self.decision = ScheduleDecision(
            "fso",
            "text",
            1,
            2,
            ("generated-0", "ephemeral-0"),
            "parallel",
            0.95,
            2.0,
            "test",
        )

    def test_semantics_and_plaintext_are_not_visible(self) -> None:
        payload = b"synthetic-secret-message"
        prepared = FSOSender(self.cipher).prepare(
            Operation("text", payload, 5000), self.decision
        )
        for packet in prepared.packets:
            self.assertNotIn(payload, packet)
            self.assertNotIn(b"text", packet)

    def test_tampering_is_rejected(self) -> None:
        prepared = FSOSender(self.cipher).prepare(
            Operation("text", b"payload", 5000), self.decision
        )
        tampered = bytearray(prepared.packets[0])
        tampered[-1] ^= 0x01
        with self.assertRaisesRegex(EnvelopeError, "authentication"):
            self.cipher.open(bytes(tampered))

    def test_replay_is_rejected_after_completion(self) -> None:
        prepared = FSOSender(self.cipher).prepare(
            Operation("text", b"payload", 5000), self.decision
        )
        receiver = FSOReceiver(self.cipher)
        first = receiver.ingest(prepared.packets[0])
        second = receiver.ingest(prepared.packets[0])
        self.assertEqual(first.status, "complete")
        self.assertEqual(second.status, "replay")

    def test_acknowledgement_authentication_rejects_tampering(self) -> None:
        authenticator = AckAuthenticator(bytes(range(32)))
        message_id = bytes(range(16))
        packet = authenticator.seal(message_id, 7)
        ack = authenticator.open(packet)
        self.assertEqual(ack.message_id, message_id)
        self.assertEqual(ack.shard_index, 7)
        tampered = bytearray(packet)
        tampered[-1] ^= 0x01
        with self.assertRaisesRegex(EnvelopeError, "acknowledgement authentication"):
            authenticator.open(bytes(tampered))

    def test_fragmentation_reassembles_out_of_order_and_ignores_duplicate(self) -> None:
        prepared = FSOSender(self.cipher).prepare(
            Operation("text", bytes(range(251)) * 8, 5000), self.decision
        )
        datagrams = fragment_envelope(
            prepared.packets[0], max_fragment_data=113
        )
        self.assertGreater(len(datagrams), 2)
        reassembler = FragmentReassembler()
        duplicate = reassembler.ingest(datagrams[-1], peer="lane-a")
        self.assertEqual(duplicate.status, "buffered")
        duplicate = reassembler.ingest(datagrams[-1], peer="lane-a")
        self.assertEqual(duplicate.status, "duplicate")
        result = duplicate
        for datagram in reversed(datagrams[:-1]):
            result = reassembler.ingest(datagram, peer="lane-a")
        self.assertEqual(result.status, "complete")
        self.assertEqual(result.packet, prepared.packets[0])


if __name__ == "__main__":
    unittest.main()
