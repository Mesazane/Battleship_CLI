import struct

MAGIC = b'BSHP'  # Battleship magic header
HEADER_FMT = '!4sI'

class ProtocolError(Exception):
    pass


def pack_message(msg_type: str, data: str) -> bytes:
    """
    Pack a message with custom header:
    - 4 bytes magic
    - 4 bytes payload length (big-endian uint)
    Payload format: msg_type|data
    """
    payload = f"{msg_type}|{data}".encode()
    header = struct.pack(HEADER_FMT, MAGIC, len(payload))
    return header + payload


def unpack_message(buf: bytes) -> tuple[str, str]:
    """
    Unpack header and payload, return (msg_type, data)
    """
    if len(buf) < 8:
        raise ProtocolError("Buffer too small for header")
    magic, length = struct.unpack(HEADER_FMT, buf[:8])
    if magic != MAGIC:
        raise ProtocolError("Invalid magic header")
    if len(buf) < 8 + length:
        raise ProtocolError("Incomplete payload")
    payload = buf[8:8+length].decode()
    try:
        msg_type, data = payload.split('|', 1)
    except ValueError:
        raise ProtocolError("Malformed payload")
    return msg_type, data