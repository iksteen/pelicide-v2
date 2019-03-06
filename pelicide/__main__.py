import functools
import logging
import os
from typing import Awaitable, Callable, Iterable, Optional, cast

import click
import pkg_resources
from aiohttp import web

from pelicide.service import rpc_factory
from pelicide.sites import load_sites

logger = logging.getLogger("__main__")

_Handler = Callable[[web.Request], Awaitable[web.StreamResponse]]
_Middleware = Callable[[web.Request, _Handler], web.StreamResponse]


async def get_index(request: web.Request) -> web.StreamResponse:
    index_path = os.path.join(request.app["static_path"], "index.html")
    return web.FileResponse(index_path)


def host_header_verifier_factory(
    valid_hostnames: Optional[Iterable[str]] = None
) -> _Middleware:
    if valid_hostnames is None:
        hostnames = {"localhost", "127.0.0.1", "::1"}
    else:
        hostnames = set(valid_hostnames)

    @web.middleware  # type: ignore
    async def host_header_verifier(
        request: web.Request, handler: _Handler
    ) -> web.StreamResponse:
        if request.url.host not in hostnames:
            raise web.HTTPForbidden()
        return await handler(request)

    return cast(_Middleware, host_header_verifier)


@click.command()
@click.option(
    "-h", "--host", default="127.0.0.1", help="Interface to run the service on."
)
@click.option("-p", "--port", default=6300, help="Port to run the service on.")
@click.option(
    "-n",
    "--hostnames",
    default=None,
    help="Comma separated list of hostnames to allow.",
)
@click.argument("projects", nargs=-1, required=True, type=click.Path(exists=True))
def main(
    host: str, port: int, hostnames: Optional[str], projects: Iterable[str]
) -> None:
    if hostnames is None:
        valid_hostnames = None
    else:
        valid_hostnames = hostnames.split(",")

    app = web.Application(middlewares=[host_header_verifier_factory(valid_hostnames)])
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
