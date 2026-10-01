"""Shared fixtures: an in-process fake owserver speaking the binary protocol."""

from __future__ import annotations

import asyncio
import contextlib
import socket
import struct
from collections.abc import AsyncIterator
from collections.abc import Awaitable
from collections.abc import Callable
from dataclasses import dataclass
from dataclasses import field

import pytest

from aio_ownet.definitions import OWServerCommonPath
from aio_ownet.definitions import OWServerControlFlag
from aio_ownet.definitions import OWServerMessageType
from aio_ownet.proxy import OWServerStatelessProxy

HEADER = struct.Struct(">iiiiii")

# Subset of the owserver return codes (index == errno-like code)
RETURN_CODES = ("Good result", "Startup - command line parameters invalid")
ENOENT = 1
RETURN_CODES_TEXT = ",".join(RETURN_CODES).encode()


@dataclass
class Request:
    """A request received by the fake owserver."""

    version: int
    payload: int
    type: int
    control_flags: int
    size: int
    offset: int
    data: bytes

    @property
    def path(self) -> str:
        """Return the zero-terminated path contained in the payload."""
        return self.data.split(b"\x00", 1)[0].decode()

    @property
    def value(self) -> bytes:
        """Return the bytes following the zero-terminated path."""
        return self.data.split(b"\x00", 1)[1]


def make_response(
    ret: int = 0,
    data: bytes = b"",
    *,
    version: int = 0,
    payload: int | None = None,
    control_flags: int = OWServerControlFlag.OWNET,
    size: int | None = None,
    offset: int = 0,
) -> bytes:
    """Build a raw owserver response frame (header + data)."""
    return (
        HEADER.pack(
            version,
            len(data) if payload is None else payload,
            ret,
            control_flags,
            len(data) if size is None else size,
            offset,
        )
        + data
    )


Handler = Callable[[Request], Awaitable[bytes]]


@dataclass
class FakeOWServer:
    """Minimal owserver emulation, one request per connection."""

    files: dict[str, bytes] = field(
        default_factory=lambda: {
            OWServerCommonPath.RETURN_CODES: RETURN_CODES_TEXT,
            "/10.67C6697351FF/temperature": b"     21.5",
        }
    )
    directories: dict[str, list[str]] = field(
        default_factory=lambda: {
            "/": ["/10.67C6697351FF", "/bus.0"],
            "/empty": [],
        }
    )
    requests: list[Request] = field(default_factory=list)
    connections: int = 0
    handler: Handler | None = None
    release: asyncio.Event = field(default_factory=asyncio.Event)
    port: int = 0
    _server: asyncio.Server | None = None

    async def start(self) -> None:
        """Start listening on an ephemeral localhost port."""
        self._server = await asyncio.start_server(self._handle, "127.0.0.1", 0)
        self.port = self._server.sockets[0].getsockname()[1]

    async def stop(self) -> None:
        """Stop the server and release any stalled handlers."""
        self.release.set()
        assert self._server is not None
        self._server.close()
        await self._server.wait_closed()

    async def stall(self, _request: Request) -> bytes:
        """Handler that never answers until the server is stopped."""
        await self.release.wait()
        return b""

    async def default_handler(self, request: Request) -> bytes:
        """Emulate owserver for NOP, READ, DIRALL(SLASH) and WRITE."""
        if request.type == OWServerMessageType.NOP:
            return make_response()
        if request.type in (
            OWServerMessageType.DIRALL,
            OWServerMessageType.DIRALLSLASH,
        ):
            return self._dir(request)
        if request.path not in self.files:
            return make_response(-ENOENT)
        if request.type == OWServerMessageType.WRITE:
            self.files[request.path] = request.value
            return make_response()
        content = self.files[request.path]
        return make_response(
            data=content[request.offset : request.offset + request.size]
        )

    def _dir(self, request: Request) -> bytes:
        """Emulate owserver directory listings."""
        if request.path not in self.directories:
            return make_response(-ENOENT)
        suffix = "/" if request.type == OWServerMessageType.DIRALLSLASH else ""
        entries = [f"{e}{suffix}" for e in self.directories[request.path]]
        return make_response(data=",".join(entries).encode())

    async def _handle(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        """Serve a single request on a connection."""
        self.connections += 1
        try:
            try:
                raw = await reader.readexactly(HEADER.size)
            except asyncio.IncompleteReadError:
                # e.g. connection opened and closed by validate()
                return
            version, payload, type_, flags, size, offset = HEADER.unpack(raw)
            request = Request(
                version=version,
                payload=payload,
                type=type_,
                control_flags=flags,
                size=size,
                offset=offset,
                data=await reader.readexactly(payload),
            )
            self.requests.append(request)
            handler = self.handler or self.default_handler
            response = await handler(request)
            writer.write(response)
            await writer.drain()
        except ConnectionError:
            pass
        finally:
            writer.close()
            with contextlib.suppress(ConnectionError):
                await writer.wait_closed()


@pytest.fixture
async def owserver() -> AsyncIterator[FakeOWServer]:
    """Run a fake owserver for the duration of a test."""
    server = FakeOWServer()
    await server.start()
    yield server
    await server.stop()


@pytest.fixture
def proxy(owserver: FakeOWServer) -> OWServerStatelessProxy:
    """Return a proxy pointing at the fake owserver."""
    return OWServerStatelessProxy("127.0.0.1", owserver.port)


@pytest.fixture
def unused_port() -> int:
    """Return a localhost port with nothing listening on it."""
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port: int = sock.getsockname()[1]
    return port
