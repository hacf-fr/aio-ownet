"""Sample interation with Async OWFS (owserver) client."""

from __future__ import annotations

import asyncio
import logging
import os

from aio_ownet.proxy import OWServerStatelessProxy

host: str | None = os.environ.get("OWFS_HOST")
port: str | None = os.environ.get("OWFS_PORT")


async def main() -> None:
    """Main entry point."""
    logging.basicConfig(level=logging.DEBUG)
    if host is None:
        raise ValueError("Missing host")
    proxy = OWServerStatelessProxy(host=host, port=int(port or 4304))
    await proxy.validate()
    for device in await proxy.dir():
        family = await proxy.read(f"{device}family")
        print(f"{device}family: {family.decode()}")


if __name__ == "__main__":
    asyncio.run(main())
