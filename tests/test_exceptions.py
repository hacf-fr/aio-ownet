"""Test exceptions"""

import pytest

from aio_ownet.connection import OWServerRxHeader
from aio_ownet.exceptions import OWServerConnectionError
from aio_ownet.exceptions import OWServerError
from aio_ownet.exceptions import OWServerMalformedHeaderError
from aio_ownet.exceptions import OWServerProtocolError
from aio_ownet.exceptions import OWServerReturnError
from aio_ownet.exceptions import OWServerShortReadError


@pytest.mark.parametrize(
    ("exc_type", "parent"),
    [
        (OWServerError, Exception),
        (OWServerConnectionError, OWServerError),
        (OWServerProtocolError, OWServerError),
        (OWServerMalformedHeaderError, OWServerProtocolError),
        (OWServerShortReadError, OWServerProtocolError),
        (OWServerReturnError, OWServerError),
    ],
)
def test_hierarchy(exc_type: type[Exception], parent: type[Exception]) -> None:
    """Test the exception hierarchy"""
    assert issubclass(exc_type, parent)


def test_malformed_header_error() -> None:
    """Test OWServerMalformedHeaderError attributes and message"""
    header = OWServerRxHeader(version=1, payload=2)
    err = OWServerMalformedHeaderError("bad version", header)
    assert err.msg == "bad version"
    assert err.header is header
    assert str(err) == (f"bad version, got {str(header)!r} decoded as {header!r}")


def test_short_read_error() -> None:
    """Test OWServerShortReadError attributes and message"""
    err = OWServerShortReadError(3, 24)
    assert (err.read, err.expected) == (3, 24)
    assert str(err) == "received 3 bytes instead of 24."


def test_return_error() -> None:
    """Test OWServerReturnError attributes and message"""
    err = OWServerReturnError(1, "No such entity", "/foo")
    assert err.ret == 1
    assert err.msg == "No such entity"
    assert err.path == "/foo"
    assert str(err) == "Server return error No such entity (1) on path /foo"


def test_return_error_defaults() -> None:
    """Test OWServerReturnError default attributes"""
    err = OWServerReturnError(5)
    assert err.msg is None
    assert err.path is None
    assert str(err) == "Server return error None (5) on path None"
