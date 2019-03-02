import os

import pkg_resources
from aiohttp import web


async def get_index(request: web.Request) -> web.Response:
    index_path = os.path.join(request.app["static_path"], "index.html")
    return web.FileResponse(index_path)


def main() -> None:
    app = web.Application()
    app["static_path"] = static_path = pkg_resources.resource_filename(
        __package__, "ui"
    )

    app.add_routes([web.get("/", get_index)])
    app.router.add_static("/", static_path)

    web.run_app(app)


if __name__ == "__main__":
    main()
