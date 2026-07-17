"""Authenticated FSO shard envelope using a caller-provided session key."""

from __future__ import annotations

import hashlib
import hmac
import os
import struct
from collections.abc import Callable
from dataclasses import dataclass

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import ChaCha20Poly1305

from .coding import Shard

MAGIC = b"FSO1"
HEADER = struct.Struct("!4s16sBBBI12s")
ACK_MAGIC = b"FAK1"
ACK_BODY = struct.Struct("!4s16sBB")
ACK_TAG_BYTES = 16


@dataclass(frozen=True)
class PublicHeader:
    message_id: bytes
    index: int
    threshold: int
    total: int
    original_length: int
    nonce: bytes


@dataclass(frozen=True)
class AuthenticatedAck:
    message_id: bytes
    shard_index: int
    status: int


class EnvelopeError(ValueError):
    pass


class AckAuthenticator:
    """Domain-separated HMAC-SHA-256 acknowledgements with a 128-bit tag."""

    def __init__(self, session_key: bytes) -> None:
        if len(session_key) != 32:
            raise ValueError("FSO acknowledgement authentication requires a 32-byte key")
        self._key = hmac.new(
            session_key, b"FSO-ACK-HMAC-SHA256-v1", hashlib.sha256
        ).digest()

    def seal(self, message_id: bytes, shard_index: int, *, status: int = 1) -> bytes:
        if len(message_id) != 16:
            raise ValueError("message_id must be 16 bytes")
        if not 0 <= shard_index <= 255 or not 0 <= status <= 255:
            raise ValueError("acknowledgement fields must fit in one byte")
        body = ACK_BODY.pack(ACK_MAGIC, message_id, shard_index, status)
        tag = hmac.new(self._key, body, hashlib.sha256).digest()[:ACK_TAG_BYTES]
        return body + tag

    def open(self, packet: bytes) -> AuthenticatedAck:
        if len(packet) != ACK_BODY.size + ACK_TAG_BYTES:
            raise EnvelopeError("invalid acknowledgement length")
        body = packet[: ACK_BODY.size]
        tag = packet[ACK_BODY.size :]
        expected = hmac.new(self._key, body, hashlib.sha256).digest()[:ACK_TAG_BYTES]
        if not hmac.compare_digest(tag, expected):
            raise EnvelopeError("acknowledgement authentication failed")
        magic, message_id, shard_index, status = ACK_BODY.unpack(body)
        if magic != ACK_MAGIC:
            raise EnvelopeError("wrong acknowledgement magic")
        return AuthenticatedAck(message_id, shard_index, status)


class EnvelopeCipher:
    """Per-shard AEAD; key establishment intentionally remains external."""

    def __init__(self, key: bytes, *, nonce_source: Callable[[int], bytes] = os.urandom) -> None:
        if len(key) != 32:
            raise ValueError("ChaCha20-Poly1305 requires a 32-byte key")
        self._cipher = ChaCha20Poly1305(key)
        self._nonce_source = nonce_source

    @staticmethod
    def peek(packet: bytes) -> PublicHeader:
        if len(packet) < HEADER.size + 16:
            raise EnvelopeError("truncated envelope")
        magic, message_id, index, threshold, total, original_length, nonce = HEADER.unpack_from(packet)
        if magic != MAGIC:
            raise EnvelopeError("wrong envelope magic")
        if not 1 <= threshold <= total <= 255 or index >= total:
            raise EnvelopeError("invalid public coding dimensions")
        return PublicHeader(message_id, index, threshold, total, original_length, nonce)

    def seal(self, shard: Shard) -> bytes:
        nonce = self._nonce_source(12)
        if len(nonce) != 12:
            raise ValueError("nonce source must return exactly 12 bytes")
        header = HEADER.pack(
            MAGIC,
            shard.message_id,
            shard.index,
            shard.threshold,
            shard.total,
            shard.original_length,
            nonce,
        )
        return header + self._cipher.encrypt(nonce, shard.data, header)

    def open(self, packet: bytes) -> Shard:
        public = self.peek(packet)
        header = packet[: HEADER.size]
        try:
            plaintext = self._cipher.decrypt(public.nonce, packet[HEADER.size :], header)
        except InvalidTag as error:
            raise EnvelopeError("authentication failed") from error
        return Shard(
            message_id=public.message_id,
            index=public.index,
            threshold=public.threshold,
            total=public.total,
            original_length=public.original_length,
            data=plaintext,
        )
