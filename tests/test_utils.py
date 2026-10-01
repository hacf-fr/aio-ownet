"""Test utils"""

import pytest

from aio_ownet.utils import bytes2str
from aio_ownet.utils import str2byteszero


@pytest.mark.parametrize(
    ("input_bytes", "expected_value"), [(b"12", "12"), (b"26", "26")]
)
def test_bytes2str(input_bytes: bytes, expected_value: str) -> None:
    """Tset bytes2str"""
    assert bytes2str(input_bytes) == expected_value


@pytest.mark.parametrize(
    ("input_string", "expected_bytes"),
    [
        ("/12.8CF1A0000000/family", b"/12.8CF1A0000000/family\x00"),
        ("/26.0B691D020000/family", b"/26.0B691D020000/family\x00"),
    ],
)
def test_str2byteszero(input_string: str, expected_bytes: bytes) -> None:
    """Test str2byteszero"""
    assert str2byteszero(input_string) == expected_bytes


def test_bytes2str_type_error() -> None:
    """Test bytes2str with a non-bytes argument"""
    with pytest.raises(TypeError):
        bytes2str("12")  # type: ignore[arg-type]  # ty: ignore[invalid-argument-type]


def test_str2byteszero_type_error() -> None:
    """Test str2byteszero with a non-str argument"""
    with pytest.raises(TypeError):
        str2byteszero(b"/12.8CF1A0000000/family")  # type: ignore[arg-type]  # ty: ignore[invalid-argument-type]
