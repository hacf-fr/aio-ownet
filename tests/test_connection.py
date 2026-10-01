"""Test connection"""

import asyncio
import struct
from unittest.mock import AsyncMock
from unittest.mock import MagicMock
from unittest.mock import patch

import pytest

from .conftest import FakeOWServer
from .conftest import Handler
from .conftest import Request
from .conftest import make_response
from aio_ownet.connection import MAX_PAYLOAD
from aio_ownet.connection import OWServerConnection
from aio_ownet.connection import OWServerRxHeader
from aio_ownet.connection import OWServerTxHeader
from aio_ownet.definitions import OWServerControlFlag
from aio_ownet.definitions import OWServerMessageType
from aio_ownet.exceptions import OWServerConnectionError
from aio_ownet.exceptions import OWServerMalformedHeaderError
from aio_ownet.exceptions import OWServerProtocolError
from aio_ownet.exceptions import OWServerShortReadError


def _const(response: bytes) -> Handler:
    """Return a fake owserver handler always sending `response`."""

    async def _handler(_request: Request) -> bytes:
        return response

    return _handler


async def _request(
    owserver: FakeOWServer,
    msgtype: OWServerMessageType = OWServerMessageType.READ,
    payload: bytes = b"/x\x00",
) -> tuple[int, int, bytes]:
    """Send a single request to the fake owserver."""
    async with OWServerConnection("127.0.0.1", owserver.port) as conn:
        return await conn.request(msgtype, payload, 0)


def test_tx_header_pack_defaults() -> None:
    """Test packing a default TX header"""
    assert OWServerTxHeader().pack() == struct.pack(
        ">iiiiii",
        0,
        0,
        OWServerMessageType.NOP,
        OWServerControlFlag.OWNET,
        0,
        0,
    )


def test_tx_header_pack() -> None:
    """Test packing a TX header"""
    header = OWServerTxHeader(
        version=1,
        payload=2,
        type=OWServerMessageType.WRITE,
        control_flags=4,
        size=5,
        offset=-6,
    )
    assert header.pack() == struct.pack(">iiiiii", 1, 2, 3, 4, 5, -6)


def test_rx_header_from_packed() -> None:
    """Test unpacking an RX header"""
    data = struct.pack(">iiiiii", 0, 10, -1, 0x102, 8, 2)
    assert OWServerRxHeader.from_packed(data) == OWServerRxHeader(
        version=0, payload=10, ret=-1, control_flags=0x102, size=8, offset=2
    )
    assert OWServerRxHeader.HEADER_SIZE == len(data)


def test_rx_header_from_packed_wrong_size() -> None:
    """Test unpacking an RX header of the wrong size"""
    with pytest.raises(struct.error):
        OWServerRxHeader.from_packed(b"\x00" * 23)


async def test_request(owserver: FakeOWServer) -> None:
    """Test a request/response round trip over a real socket"""
    owserver.handler = _const(make_response(-7, b"hello", control_flags=0x1234))
    async with OWServerConnection("127.0.0.1", owserver.port) as conn:
        result = await conn.request(
            OWServerMessageType.READ, b"/foo\x00", 0x20, size=100, offset=3
        )
    assert result == (-7, 0x1234, b"hello")
    assert owserver.requests == [
        Request(
            version=0,
            payload=5,
            type=OWServerMessageType.READ,
            control_flags=0x20,
            size=100,
            offset=3,
            data=b"/foo\x00",
        )
    ]


async def test_request_empty_payload(owserver: FakeOWServer) -> None:
    """Test a response without payload"""
    owserver.handler = _const(make_response(0))
    assert await _request(owserver, OWServerMessageType.NOP, b"") == (
        0,
        OWServerControlFlag.OWNET,
        b"",
    )
    assert owserver.requests[0].payload == 0


async def test_request_payload_truncated_to_size(
    owserver: FakeOWServer,
) -> None:
    """Test the payload is truncated to the size field of the header"""
    owserver.handler = _const(make_response(0, b"21.5\x00\x00\x00\x00", size=4))
    assert await _request(owserver) == (0, OWServerControlFlag.OWNET, b"21.5")


async def test_request_max_payload(owserver: FakeOWServer) -> None:
    """Test a payload of exactly MAX_PAYLOAD bytes is accepted"""
    data = bytes(range(256)) * (MAX_PAYLOAD // 256)
    owserver.handler = _const(make_response(0, data))
    assert await _request(owserver) == (0, OWServerControlFlag.OWNET, data)


async def test_request_skips_keepalive(owserver: FakeOWServer) -> None:
    """Test keepalive frames (negative payload) are skipped"""
    keepalive = make_response(0, payload=-1, size=0)
    owserver.handler = _const(keepalive + keepalive + make_response(3, b"data"))
    assert await _request(owserver) == (3, OWServerControlFlag.OWNET, b"data")


async def test_request_keepalive_reply_to_nop(owserver: FakeOWServer) -> None:
    """Test a keepalive frame in reply to a NOP message"""
    keepalive = make_response(0, payload=-1, size=0)
    owserver.handler = _const(keepalive + make_response(0))
    with pytest.raises(
        OWServerProtocolError, match="unexpected keepalive in reply to ping"
    ):
        await _request(owserver, OWServerMessageType.NOP, b"")


async def test_request_bad_version(owserver: FakeOWServer) -> None:
    """Test a response with a non-zero version"""
    owserver.handler = _const(make_response(0, version=1))
    with pytest.raises(OWServerMalformedHeaderError) as exc_info:
        await _request(owserver)
    assert exc_info.value.msg == "bad version"
    assert exc_info.value.header.version == 1


async def test_request_huge_payload(owserver: FakeOWServer) -> None:
    """Test a response announcing a payload bigger than MAX_PAYLOAD"""
    owserver.handler = _const(make_response(0, payload=MAX_PAYLOAD + 1))
    with pytest.raises(OWServerMalformedHeaderError) as exc_info:
        await _request(owserver)
    assert exc_info.value.msg == "huge payload, unwilling to read"
    assert exc_info.value.header.payload == MAX_PAYLOAD + 1


async def test_request_no_response(owserver: FakeOWServer) -> None:
    """Test the server closing the connection without answering"""
    owserver.handler = _const(b"")
    with pytest.raises(OWServerShortReadError) as exc_info:
        await _request(owserver)
    assert (exc_info.value.read, exc_info.value.expected) == (0, 24)


async def test_request_truncated_header(owserver: FakeOWServer) -> None:
    """Test the server closing the connection mid-header"""
    owserver.handler = _const(make_response(0)[:10])
    with pytest.raises(OWServerShortReadError) as exc_info:
        await _request(owserver)
    assert (exc_info.value.read, exc_info.value.expected) == (10, 24)


async def test_request_truncated_payload(owserver: FakeOWServer) -> None:
    """Test the server closing the connection mid-payload"""
    owserver.handler = _const(make_response(0, b"0123456789")[:-6])
    with pytest.raises(OWServerShortReadError) as exc_info:
        await _request(owserver)
    assert (exc_info.value.read, exc_info.value.expected) == (4, 10)


async def test_request_timeout(owserver: FakeOWServer) -> None:
    """Test the command timeout when the server does not answer"""
    owserver.handler = owserver.stall
    async with OWServerConnection("127.0.0.1", owserver.port) as conn:
        with pytest.raises(TimeoutError):
            await conn.request(
                OWServerMessageType.READ, b"/x\x00", 0, command_timeout=0
            )


async def test_connection_refused(unused_port: int) -> None:
    """Test connecting to a closed port raises the raw OSError"""
    with pytest.raises(ConnectionRefusedError):
        async with OWServerConnection("127.0.0.1", unused_port):
            pass


async def test_connection_timeout() -> None:
    """Test the connection timeout"""

    async def _hang(*_args: object) -> tuple[object, object]:
        await asyncio.Event().wait()
        raise AssertionError

    with patch("asyncio.open_connection", _hang), pytest.raises(TimeoutError):
        async with OWServerConnection("127.0.0.1", 4304, connection_timeout=0):
            pass


def _mock_connection(
    *chunks: bytes | Exception,
) -> tuple[OWServerConnection, AsyncMock, MagicMock]:
    """Return a connection whose reader returns the given chunks."""
    conn = OWServerConnection("127.0.0.1", 4304)
    read = AsyncMock(side_effect=list(chunks))
    writer = MagicMock(spec=asyncio.StreamWriter)
    conn._reader = MagicMock(spec=asyncio.StreamReader, read=read)
    conn._writer = writer
    return conn, read, writer


async def test_read_in_chunks() -> None:
    """Test header and payload received in several chunks"""
    raw = make_response(2, b"abcdef")
    conn, read, _ = _mock_connection(
        raw[:5], raw[5:20], raw[20:24], raw[24:27], raw[27:]
    )
    assert await conn.request(OWServerMessageType.READ, b"", 0) == (
        2,
        OWServerControlFlag.OWNET,
        b"abcdef",
    )
    assert [c.args for c in read.await_args_list] == [
        (24,),
        (19,),
        (4,),
        (6,),
        (3,),
    ]


@pytest.mark.parametrize(
    "chunks",
    [
        (ConnectionResetError(),),
        (make_response(0)[:4], ConnectionResetError()),
    ],
    ids=["first_read", "subsequent_read"],
)
async def test_read_os_error(chunks: tuple[bytes | Exception, ...]) -> None:
    """Test OSError while reading is wrapped in OWServerConnectionError"""
    conn, _, _ = _mock_connection(*chunks)
    with pytest.raises(OWServerConnectionError) as exc_info:
        await conn.request(OWServerMessageType.READ, b"", 0)
    assert isinstance(exc_info.value.__cause__, ConnectionResetError)


@pytest.mark.parametrize("method", ["write", "drain"])
async def test_send_os_error(method: str) -> None:
    """Test OSError while sending is wrapped in OWServerConnectionError"""
    conn, read, writer = _mock_connection()
    if method == "write":
        writer.write.side_effect = BrokenPipeError
    else:
        writer.drain = AsyncMock(side_effect=BrokenPipeError)
    with pytest.raises(OWServerConnectionError) as exc_info:
        await conn.request(OWServerMessageType.READ, b"", 0)
    assert isinstance(exc_info.value.__cause__, BrokenPipeError)
    read.assert_not_awaited()


async def test_aexit_closes_writer() -> None:
    """Test leaving the context manager closes the connection"""
    reader = MagicMock(spec=asyncio.StreamReader)
    writer = MagicMock(spec=asyncio.StreamWriter)
    with patch(
        "asyncio.open_connection", AsyncMock(return_value=(reader, writer))
    ) as mock_open:
        conn = OWServerConnection("myhost", 1234)
        async with conn as entered:
            assert entered is conn
    mock_open.assert_awaited_once_with("myhost", 1234)
    writer.close.assert_called_once_with()
    writer.wait_closed.assert_awaited_once_with()


async def test_payload_size_larger_than_payload(
    owserver: FakeOWServer,
) -> None:
    """Test a header whose size field exceeds the payload length"""
    owserver.handler = _const(make_response(0, b"abc", size=10))
    with pytest.raises(
        OWServerMalformedHeaderError, match="size larger than payload"
    ):
        await _request(owserver)
