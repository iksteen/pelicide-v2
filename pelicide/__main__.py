import functools
import logging
import os
from typing import Iterable

import click
import pkg_resources
from aiohttp import web

from pelicide.service import rpc_factory
from pelicide.sites import load_sites

logger = logging.getLogger("__main__")


async def get_index(request: web.Request) -> web.StreamResponse:
    index_path = os.path.join(request.app["static_path"], "index.html")
    return web.FileResponse(index_path)


@click.command()
@click.option(
    "-h", "--host", default="127.0.0.1", help="Interface to run the service on."
)
@click.option("-p", "--port", default=6300, help="Port to run the service on.")
@click.argument("projects", nargs=-1, required=True, type=click.Path(exists=True))
def main(host: str, port: int, projects: Iterable[str]) -> None:
    app = web.Application()
    app["static_path"] = static_path = pkg_resources.resource_filename(
        __package__, "ui"
    )
    app.cleanup_ctx.append(functools.partial(load_sites, projects))

    app.router.add_route("GET", "/", get_index)
    app.router.add_route("*", "/service", rpc_factory())
    app.router.add_static("/app", static_path)

    web.run_app(app, host=host, port=port)


if __name__ == "__main__":
    main()
