from __future__ import annotations

import itertools
import unittest

from capme.fso.coding import ReedSolomonCodec


class FSOCodingTests(unittest.TestCase):
    def test_every_three_of_five_subset_recovers(self) -> None:
        payload = bytes((index * 17) % 251 for index in range(4097))
        codec = ReedSolomonCodec(3, 5)
        shards = codec.encode(payload, b"m" * 16)
        for indices in itertools.combinations(range(5), 3):
            self.assertEqual(codec.decode([shards[index] for index in indices]), payload)

    def test_insufficient_shards_are_rejected(self) -> None:
        codec = ReedSolomonCodec(2, 3)
        shards = codec.encode(b"payload", b"i" * 16)
        with self.assertRaisesRegex(ValueError, "insufficient"):
            codec.decode(shards[:1])


if __name__ == "__main__":
    unittest.main()
