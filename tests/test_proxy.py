"""Test proxy"""

import asyncio
import logging
from unittest.mock import patch

import pytest

from .conftest import ENOENT
from .conftest import RETURN_CODES
from .conftest import FakeOWServer
from .conftest import Request
from .conftest import make_response
from aio_ownet.connection import MAX_PAYLOAD
from aio_ownet.definitions import OWServerCommonPath
from aio_ownet.definitions import OWServerControlFlag
from aio_ownet.definitions import OWServerMessageType
from aio_ownet.exceptions import OWServerConnectionError
from aio_ownet.exceptions import OWServerProtocolError
from aio_ownet.exceptions import OWServerReturnError
from aio_ownet.proxy import OWServerStatelessProxy

TEMPERATURE = "/10.67C6697351FF/temperature"


async def test_validate(
    owserver: FakeOWServer,
    proxy: OWServerStatelessProxy,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Test validate connects, pings and loads the return codes"""
    with caplog.at_level(logging.DEBUG, logger="aio_ownet"):
        await proxy.validate()
    # probe connection (no request sent) + ping + return codes
    assert owserver.connections == len(owserver.requests) + 1
    assert [(r.type, r.path, r.size) for r in owserver.requests] == [
        (OWServerMessageType.NOP, "", 0),
        (
            OWServerMessageType.READ,
            OWServerCommonPath.RETURN_CODES,
            MAX_PAYLOAD,
        ),
    ]
    assert proxy._return_code_messages == RETURN_CODES
    assert "Validated connection to 127.0.0.1" in caplog.text

    # return codes are now used in error messages
    with pytest.raises(OWServerReturnError) as exc_info:
        await proxy.read("/missing")
    assert exc_info.value.ret == ENOENT
    assert exc_info.value.msg == RETURN_CODES[ENOENT]
    assert exc_info.value.path == "/missing"


async def test_validate_connection_refused(
    unused_port: int, caplog: pytest.LogCaptureFixture
) -> None:
    """Test validate wraps connection failures"""
    proxy = OWServerStatelessProxy("127.0.0.1", unused_port)
    with pytest.raises(OWServerConnectionError) as exc_info:
        await proxy.validate()
    assert isinstance(exc_info.value.__cause__, ConnectionRefusedError)
    assert f"Failed to connect to 127.0.0.1 on port {unused_port}" in (caplog.text)


async def test_validate_connection_timeout() -> None:
    """Test validate wraps connection timeouts"""

    async def _hang(*_args: object) -> tuple[object, object]:
        await asyncio.Event().wait()
        raise AssertionError

    proxy = OWServerStatelessProxy("127.0.0.1", 4304, connection_timeout=0)
    with (
        patch("asyncio.open_connection", _hang),
        pytest.raises(OWServerConnectionError) as exc_info,
    ):
        await proxy.validate()
    assert isinstance(exc_info.value.__cause__, TimeoutError)


async def test_validate_ping_error(
    owserver: FakeOWServer, proxy: OWServerStatelessProxy
) -> None:
    """Test validate propagates ping errors"""

    async def _handler(_request: Request) -> bytes:
        return make_response(1)

    owserver.handler = _handler
    with pytest.raises(OWServerProtocolError):
        await proxy.validate()
    assert len(owserver.requests) == 1


async def test_init_error_codes_unavailable(
    owserver: FakeOWServer, proxy: OWServerStatelessProxy
) -> None:
    """Test return codes are ignored when the server cannot provide them"""
    del owserver.files[OWServerCommonPath.RETURN_CODES]
    await proxy.init_error_codes()
    assert proxy._return_code_messages == ()
    with pytest.raises(OWServerReturnError) as exc_info:
        await proxy.read("/missing")
    assert exc_info.value.msg == "Unknown return code"


@pytest.mark.parametrize(
    ("messages", "ret", "expected"),
    [
        ((), 0, "Unknown return code"),
        (("a", "b"), 0, "a"),
        (("a", "b"), 1, "b"),
        (("a", "b"), 2, "Unknown return code"),
    ],
)
def test_get_return_code_message(
    messages: tuple[str, ...], ret: int, expected: str
) -> None:
    """Test return code message lookup"""
    proxy = OWServerStatelessProxy("127.0.0.1", 4304)
    proxy._return_code_messages = messages
    assert proxy._get_return_code_message(ret) == expected


async def test_ping(owserver: FakeOWServer, proxy: OWServerStatelessProxy) -> None:
    """Test ping sends a NOP message"""
    await proxy.ping()
    assert owserver.requests == [
        Request(
            version=0,
            payload=0,
            type=OWServerMessageType.NOP,
            control_flags=0,
            size=0,
            offset=0,
            data=b"",
        )
    ]


@pytest.mark.parametrize(
    "response",
    [make_response(1), make_response(0, b"x")],
    ids=["positive_ret", "with_data"],
)
async def test_ping_invalid_reply(
    owserver: FakeOWServer, proxy: OWServerStatelessProxy, response: bytes
) -> None:
    """Test ping with an invalid reply"""

    async def _handler(_request: Request) -> bytes:
        return response

    owserver.handler = _handler
    with pytest.raises(OWServerProtocolError, match="invalid reply to ping message"):
        await proxy.ping()


async def test_ping_error(
    owserver: FakeOWServer, proxy: OWServerStatelessProxy
) -> None:
    """Test ping with an error return code"""

    async def _handler(_request: Request) -> bytes:
        return make_response(-ENOENT)

    owserver.handler = _handler
    proxy._return_code_messages = RETURN_CODES
    with pytest.raises(OWServerReturnError) as exc_info:
        await proxy.ping()
    assert exc_info.value.ret == ENOENT
    assert exc_info.value.msg == RETURN_CODES[ENOENT]
    assert exc_info.value.path is None


async def test_read(owserver: FakeOWServer, proxy: OWServerStatelessProxy) -> None:
    """Test reading a value"""
    assert await proxy.read(TEMPERATURE) == b"     21.5"
    assert owserver.requests == [
        Request(
            version=0,
            payload=len(TEMPERATURE) + 1,
            type=OWServerMessageType.READ,
            control_flags=0,
            size=MAX_PAYLOAD,
            offset=0,
            data=TEMPERATURE.encode() + b"\x00",
        )
    ]


async def test_read_size_offset(
    owserver: FakeOWServer, proxy: OWServerStatelessProxy
) -> None:
    """Test reading with explicit size and offset"""
    assert await proxy.read(TEMPERATURE, size=3, offset=5) == b"21."
    assert (owserver.requests[0].size, owserver.requests[0].offset) == (3, 5)


async def test_read_size_too_big(proxy: OWServerStatelessProxy) -> None:
    """Test reading more than MAX_PAYLOAD bytes is refused"""
    with pytest.raises(ValueError, match=f"Size cannot exceed {MAX_PAYLOAD}"):
        await proxy.read(TEMPERATURE, size=MAX_PAYLOAD + 1)


async def test_read_error(proxy: OWServerStatelessProxy) -> None:
    """Test reading a missing path"""
    with pytest.raises(OWServerReturnError) as exc_info:
        await proxy.read("/missing")
    assert exc_info.value.ret == ENOENT
    assert exc_info.value.msg == "Unknown return code"
    assert exc_info.value.path == "/missing"


async def test_read_timeout(
    owserver: FakeOWServer, proxy: OWServerStatelessProxy
) -> None:
    """Test the command timeout"""
    owserver.handler = owserver.stall
    with pytest.raises(OWServerConnectionError) as exc_info:
        await proxy.read(TEMPERATURE, command_timeout=0)
    assert isinstance(exc_info.value.__cause__, TimeoutError)


async def test_read_connection_refused(unused_port: int) -> None:
    """Test connection errors outside validate are wrapped"""
    proxy = OWServerStatelessProxy("127.0.0.1", unused_port)
    with pytest.raises(OWServerConnectionError) as exc_info:
        await proxy.read(TEMPERATURE)
    assert isinstance(exc_info.value.__cause__, ConnectionRefusedError)


@pytest.mark.parametrize(
    ("slash", "bus", "msgtype", "flags", "expected"),
    [
        (
            True,
            False,
            OWServerMessageType.DIRALLSLASH,
            0,
            ["/10.67C6697351FF/", "/bus.0/"],
        ),
        (
            False,
            False,
            OWServerMessageType.DIRALL,
            0,
            ["/10.67C6697351FF", "/bus.0"],
        ),
        (
            True,
            True,
            OWServerMessageType.DIRALLSLASH,
            OWServerControlFlag.BUS_RET,
            ["/10.67C6697351FF/", "/bus.0/"],
        ),
    ],
)
async def test_dir(
    owserver: FakeOWServer,
    proxy: OWServerStatelessProxy,
    slash: bool,
    bus: bool,
    msgtype: OWServerMessageType,
    flags: int,
    expected: list[str],
) -> None:
    """Test listing a directory"""
    assert await proxy.dir(slash=slash, bus=bus) == expected
    assert owserver.requests[0].type == msgtype
    assert owserver.requests[0].control_flags == flags
    assert owserver.requests[0].data == b"/\x00"


async def test_dir_clears_bus_flag(
    owserver: FakeOWServer, proxy: OWServerStatelessProxy
) -> None:
    """Test bus=False clears a BUS_RET flag set on the proxy"""
    proxy._flags = OWServerControlFlag.BUS_RET | OWServerControlFlag.UNCACHED
    await proxy.dir(bus=False)
    assert owserver.requests[0].control_flags == OWServerControlFlag.UNCACHED


async def test_dir_empty(owserver: FakeOWServer, proxy: OWServerStatelessProxy) -> None:
    """Test listing an empty directory"""
    assert await proxy.dir("/empty") == []
    assert owserver.requests[0].path == "/empty"


async def test_dir_error(proxy: OWServerStatelessProxy) -> None:
    """Test listing a missing directory"""
    with pytest.raises(OWServerReturnError) as exc_info:
        await proxy.dir("/missing")
    assert exc_info.value.ret == ENOENT
    assert exc_info.value.path == "/missing"


async def test_write(owserver: FakeOWServer, proxy: OWServerStatelessProxy) -> None:
    """Test writing a value"""
    await proxy.write(TEMPERATURE, b"42", offset=1)
    assert owserver.requests == [
        Request(
            version=0,
            payload=len(TEMPERATURE) + 3,
            type=OWServerMessageType.WRITE,
            control_flags=0,
            size=2,
            offset=1,
            data=TEMPERATURE.encode() + b"\x0042",
        )
    ]
    assert owserver.files[TEMPERATURE] == b"42"


async def test_write_not_bytes(proxy: OWServerStatelessProxy) -> None:
    """Test writing non-binary data is refused"""
    with pytest.raises(TypeError, match="'data' argument must be binary"):
        await proxy.write(TEMPERATURE, "42")  # ty: ignore[invalid-argument-type]


async def test_write_invalid_reply(
    owserver: FakeOWServer, proxy: OWServerStatelessProxy
) -> None:
    """Test a write reply carrying data"""

    async def _handler(_request: Request) -> bytes:
        return make_response(0, b"x")

    owserver.handler = _handler
    with pytest.raises(OWServerProtocolError, match="invalid reply to write message"):
        await proxy.write(TEMPERATURE, b"42")


async def test_write_error(proxy: OWServerStatelessProxy) -> None:
    """Test writing to a missing path"""
    with pytest.raises(OWServerReturnError) as exc_info:
        await proxy.write("/missing", b"1")
    assert exc_info.value.ret == ENOENT
    assert exc_info.value.path == "/missing"


async def test_persistence_flag_refused(
    proxy: OWServerStatelessProxy,
) -> None:
    """Test the stateless proxy refuses the persistence flag"""
    proxy._flags = OWServerControlFlag.PERSISTENCE
    with pytest.raises(AssertionError):
        await proxy.ping()


async def test_dir_defaults(
    owserver: FakeOWServer, proxy: OWServerStatelessProxy
) -> None:
    """Test listing the root directory with default arguments"""
    assert await proxy.dir() == ["/10.67C6697351FF/", "/bus.0/"]
    assert owserver.requests[0].type == OWServerMessageType.DIRALLSLASH
    assert owserver.requests[0].control_flags == 0
