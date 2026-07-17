"""Transparent synthetic cross-transport campaign censor for CAP-ME.

This is an experimental failure model, not an implementation or claim about a
deployed national censor.  Its byte tests are declared approximations inspired
by published fully-encrypted-traffic measurements.  The contribution being
tested is the longitudinal packet-to-function bridge, not the classifier.
"""

from rust import log_info


PRINTABLE_LOW = 0x20
PRINTABLE_HIGH = 0x7E
CONFIRMATION_PACKETS = 3


def _is_printable(value):
    return PRINTABLE_LOW <= value <= PRINTABLE_HIGH


def _known_protocol(payload):
    if len(payload) >= 3:
        if payload[0] in (0x15, 0x16, 0x17) and payload[1] == 0x03:
            return True
    for prefix in (b"GET ", b"PUT ", b"POST ", b"HEAD ", b"SSH-"):
        if payload.startswith(prefix):
            return True
    return False


def _looks_fully_encrypted(packet):
    payload = packet.payload
    if len(payload) < 32 or _known_protocol(payload):
        return False
    if all(_is_printable(value) for value in payload[:6]):
        return False
    printable = sum(1 for value in payload if _is_printable(value))
    if printable / len(payload) > 0.50:
        return False
    popcount = packet.payload_avg_popcount
    return 3.4 < popcount < 4.6


def process(packet):
    # PCAP direction is derived from the declared client IP.  Only outbound
    # traffic contributes to endpoint reputation; potential ACKs do not.
    if packet.direction != 1 or (not packet.tcp and not packet.udp):
        return None
    if packet.payload_len == 0:
        return None
    # Reserved solely for deterministic PCAP-index calibration and the
    # declared direct-lane control.  The address is RFC 5737 documentation
    # space and is never contacted.
    if packet.ip.dst == "198.51.100.1":
        return "drop"

    endpoint = dst_host.state
    if endpoint.get("blocked", False):
        return "drop"
    if not _looks_fully_encrypted(packet):
        return None

    score = endpoint.get("suspicious_packets", 0) + 1
    endpoint["suspicious_packets"] = score
    if score >= CONFIRMATION_PACKETS:
        endpoint["blocked"] = True
        log_info(
            "[CAP-ME campaign] endpoint quarantined after "
            + str(score)
            + " suspicious outbound packets"
        )
        return "drop"
    return None
