# Async OWFS (owserver) client

[![PyPI](https://img.shields.io/pypi/v/aio-ownet.svg)][pypi_]
[![Python Version](https://img.shields.io/pypi/pyversions/aio-ownet)][python version]
[![License](https://img.shields.io/pypi/l/aio-ownet)][license]

[![Tests](https://github.com/hacf-fr/aio-ownet/workflows/Tests/badge.svg)][tests]
[![Codecov](https://codecov.io/gh/hacf-fr/aio-ownet/branch/main/graph/badge.svg)][codecov]

[![prek](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/j178/prek/master/docs/assets/badge-v0.json)][prek]
[![ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)][ruff]

[pypi_]: https://pypi.org/project/aio-ownet/
[python version]: https://pypi.org/project/aio-ownet
[tests]: https://github.com/hacf-fr/aio-ownet/actions?workflow=Tests
[codecov]: https://app.codecov.io/gh/hacf-fr/aio-ownet
[prek]: https://github.com/j178/prek
[ruff]: https://github.com/astral-sh/ruff

## What is this?

`aio-ownet` is an async Python client for [OWFS] `owserver`. It speaks the
owserver network protocol to list, read and write 1-Wire devices, and has no
dependencies outside the standard library.

## Installation

```console
$ pip install aio-ownet
```

Python 3.11+ is required.

## Usage

```python
import asyncio

from aio_ownet.proxy import OWServerStatelessProxy


async def main() -> None:
    proxy = OWServerStatelessProxy(host="192.168.1.10", port=4304)

    # Check that the server is reachable and load its error messages.
    await proxy.validate()

    for device in await proxy.dir():
        family = await proxy.read(f"{device}family")
        print(f"{device}family: {family.decode()}")


asyncio.run(main())
```

`OWServerStatelessProxy` is stateless: each call opens a new connection to
owserver and closes it once the reply is received.

See [`example.py`][example] for a runnable script.

### Methods

| Method                                 | Description                                                                                                                                                                         |
| -------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `validate()`                           | Check that owserver is reachable, ping it and fetch its return code messages. Call it once first: without these messages, `OWServerReturnError` only reports "Unknown return code". |
| `ping()`                               | Send a no-op message and check the reply.                                                                                                                                           |
| `dir(path="/", slash=True, bus=False)` | List the entries at `path`. With `slash=True`, directories end with `/`; with `bus=True`, bus entries (`bus.0`, ...) are included.                                                  |
| `read(path, size=65536, offset=0)`     | Read the value at `path` and return it as `bytes`.                                                                                                                                  |
| `write(path, data, offset=0)`          | Write `data` (`bytes`) at `path`.                                                                                                                                                   |

The constructor takes an optional `connection_timeout`, and `dir`, `read` and
`write` take an optional `command_timeout`; both are in seconds and default
to 60.

### Errors

All errors raised by the library subclass
`aio_ownet.exceptions.OWServerError`:

- `OWServerConnectionError`: owserver can't be reached, the connection
  fails, or a command times out.
- `OWServerReturnError`: owserver returned an error code, for example for
  an unknown path. `ret`, `msg` and `path` hold the error code, its message
  and the requested path.
- `OWServerProtocolError`: owserver sent an invalid reply. Subclassed by
  `OWServerMalformedHeaderError` and `OWServerShortReadError`.

## Contributing

Contributions are very welcome. To learn more, see the [Contributor Guide].

## License

Distributed under the terms of the [MIT license][license],
_Async OWFS (owserver) client_ is free and open source software.

## Issues

If you encounter any problems,
please [file an issue] along with a detailed description.

## Credits

This project was generated from [@cjolowicz]'s [Hypermodern Python Cookiecutter] template.

[@cjolowicz]: https://github.com/cjolowicz
[hypermodern python cookiecutter]: https://github.com/cjolowicz/cookiecutter-hypermodern-python
[file an issue]: https://github.com/hacf-fr/aio-ownet/issues
[owfs]: https://owfs.org/
[example]: https://github.com/hacf-fr/aio-ownet/blob/main/example.py
[license]: https://github.com/hacf-fr/aio-ownet/blob/main/LICENSE
[contributor guide]: https://github.com/hacf-fr/aio-ownet/blob/main/CONTRIBUTING.md
