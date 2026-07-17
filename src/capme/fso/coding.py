"""Small systematic MDS erasure codec over GF(256).

This is transparent research code, not a performance-optimized production
implementation. It is used to test the FSO fragment/reassembly state machine.
"""

from __future__ import annotations

from dataclasses import dataclass

_EXP = [0] * 512
_LOG = [0] * 256
_value = 1
for _index in range(255):
    _EXP[_index] = _value
    _LOG[_value] = _index
    _value <<= 1
    if _value & 0x100:
        _value ^= 0x11D
for _index in range(255, 512):
    _EXP[_index] = _EXP[_index - 255]


def _mul(left: int, right: int) -> int:
    if left == 0 or right == 0:
        return 0
    return _EXP[_LOG[left] + _LOG[right]]


def _inverse(value: int) -> int:
    if value == 0:
        raise ZeroDivisionError("zero has no inverse in GF(256)")
    return _EXP[255 - _LOG[value]]


def _power(value: int, exponent: int) -> int:
    if exponent == 0:
        return 1
    if value == 0:
        return 0
    return _EXP[(_LOG[value] * exponent) % 255]


def _matrix_inverse(matrix: list[list[int]]) -> list[list[int]]:
    size = len(matrix)
    if size == 0 or any(len(row) != size for row in matrix):
        raise ValueError("matrix must be non-empty and square")
    augmented = [row[:] + [int(i == j) for j in range(size)] for i, row in enumerate(matrix)]
    for column in range(size):
        pivot = next((row for row in range(column, size) if augmented[row][column]), None)
        if pivot is None:
            raise ValueError("singular matrix")
        augmented[column], augmented[pivot] = augmented[pivot], augmented[column]
        factor = _inverse(augmented[column][column])
        augmented[column] = [_mul(value, factor) for value in augmented[column]]
        for row in range(size):
            if row == column:
                continue
            factor = augmented[row][column]
            if factor:
                augmented[row] = [
                    value ^ _mul(factor, pivot_value)
                    for value, pivot_value in zip(augmented[row], augmented[column], strict=True)
                ]
    return [row[size:] for row in augmented]


def _matrix_multiply(left: list[list[int]], right: list[list[int]]) -> list[list[int]]:
    if not left or not right or len(left[0]) != len(right):
        raise ValueError("incompatible matrices")
    columns = len(right[0])
    output: list[list[int]] = []
    for row in left:
        result_row: list[int] = []
        for column in range(columns):
            value = 0
            for inner, coefficient in enumerate(row):
                value ^= _mul(coefficient, right[inner][column])
            result_row.append(value)
        output.append(result_row)
    return output


def _generator_matrix(threshold: int, total: int) -> list[list[int]]:
    vandermonde = [
        [_power(row + 1, column) for column in range(threshold)]
        for row in range(total)
    ]
    normalization = _matrix_inverse(vandermonde[:threshold])
    return _matrix_multiply(vandermonde, normalization)


@dataclass(frozen=True)
class Shard:
    message_id: bytes
    index: int
    threshold: int
    total: int
    original_length: int
    data: bytes

    def __post_init__(self) -> None:
        if len(self.message_id) != 16:
            raise ValueError("message_id must be 16 bytes")
        if not 0 <= self.index < self.total <= 255:
            raise ValueError("invalid shard index or total")
        if not 1 <= self.threshold <= self.total:
            raise ValueError("invalid threshold")
        if self.original_length < 0:
            raise ValueError("invalid original length")


class ReedSolomonCodec:
    def __init__(self, threshold: int, total: int) -> None:
        if not 1 <= threshold <= total <= 255:
            raise ValueError("require 1 <= threshold <= total <= 255")
        self.threshold = threshold
        self.total = total
        self.generator = _generator_matrix(threshold, total)

    def encode(self, payload: bytes, message_id: bytes) -> list[Shard]:
        if len(message_id) != 16:
            raise ValueError("message_id must be 16 bytes")
        shard_size = max(1, (len(payload) + self.threshold - 1) // self.threshold)
        padded = payload + bytes(shard_size * self.threshold - len(payload))
        data_shards = [
            padded[index * shard_size : (index + 1) * shard_size]
            for index in range(self.threshold)
        ]
        encoded: list[Shard] = []
        for row_index, coefficients in enumerate(self.generator):
            output = bytearray(shard_size)
            for column, coefficient in enumerate(coefficients):
                if coefficient == 0:
                    continue
                source = data_shards[column]
                for offset, value in enumerate(source):
                    output[offset] ^= _mul(coefficient, value)
            encoded.append(
                Shard(
                    message_id=message_id,
                    index=row_index,
                    threshold=self.threshold,
                    total=self.total,
                    original_length=len(payload),
                    data=bytes(output),
                )
            )
        return encoded

    def decode(self, shards: list[Shard]) -> bytes:
        unique = {shard.index: shard for shard in shards}
        if len(unique) < self.threshold:
            raise ValueError("insufficient unique shards")
        selected = [unique[index] for index in sorted(unique)[: self.threshold]]
        first = selected[0]
        for shard in selected:
            if (
                shard.message_id != first.message_id
                or shard.threshold != self.threshold
                or shard.total != self.total
                or shard.original_length != first.original_length
                or len(shard.data) != len(first.data)
            ):
                raise ValueError("inconsistent shard metadata")
        decode_matrix = _matrix_inverse([self.generator[shard.index] for shard in selected])
        shard_size = len(first.data)
        recovered = [bytearray(shard_size) for _ in range(self.threshold)]
        for data_index, coefficients in enumerate(decode_matrix):
            for selected_index, coefficient in enumerate(coefficients):
                if coefficient == 0:
                    continue
                source = selected[selected_index].data
                for offset, value in enumerate(source):
                    recovered[data_index][offset] ^= _mul(coefficient, value)
        return b"".join(bytes(row) for row in recovered)[: first.original_length]
