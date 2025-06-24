import struct

MAGIC = b'BSHP'
HEADER_SIZE = 8  # 4 bytes magic + 4 bytes length

class ProtocolError(Exception):
    """Custom exception for protocol errors."""
    pass

def recv_all(conn, n):
    """Receive exactly n bytes from the socket, raise on disconnect."""
    data = b''
    while len(data) < n:
        packet = conn.recv(n - len(data))
        if not packet:
            raise ConnectionError("Connection closed while reading data")
        data += packet
    return data

def pack_message(msg_type: str, data: str) -> bytes:
    """Frame a message with magic header and length for custom serialization."""
    payload = f"{msg_type}|{data}".encode('utf-8')
    header = struct.pack('!4sI', MAGIC, len(payload))
    return header + payload

def unpack_message(conn) -> tuple[str, str]:
    """Unpack a complete message from the connection."""
    hdr = recv_all(conn, HEADER_SIZE)
    magic, length = struct.unpack('!4sI', hdr)
    if magic != MAGIC:
        raise ProtocolError(f"Invalid magic header: {magic}")
    raw = recv_all(conn, length).decode('utf-8')
    parts = raw.split('|', 1)
    if len(parts) != 2:
        raise ProtocolError("Malformed payload: missing separator")
    return parts[0], parts[1]