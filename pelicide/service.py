import asyncio
import logging
import mimetypes
import pathlib
from typing import Any, Dict, Iterable, cast

from aiohttp_json_rpc import JsonRpc, RpcInvalidParamsError
from aiohttp_json_rpc.communicaton import JsonRpcRequest
from jsonschema import ValidationError, validate

from pelicide.sites import SiteDirectory
from pelicide.util import injector

logger = logging.getLogger(__name__)

scan_args_schema = {
    "type": "object",
    "properties": {"id": {"type": "string"}},
    "required": ["id"],
}


@injector.inject  # type: ignore
async def list_sites(
    request: JsonRpcRequest, *, sites: SiteDirectory
) -> Iterable[Dict[str, str]]:
    return [
        {"id": site_id, "name": cast(dict, site.runner.settings)["SITENAME"]}
        for site_id, site in sites.items()
    ]


@injector.inject  # type: ignore
async def list_site_files(
    request: JsonRpcRequest, *, sites: SiteDirectory
) -> Dict[str, Iterable[Dict[str, Any]]]:
    def list_theme_files(theme: str) -> Iterable[Dict[str, Any]]:
        path = pathlib.Path(theme)
        return [
            {
                "path": file.relative_to(path).parts[:-1],
                "name": file.name,
                "mimetype": mimetypes.guess_type(file.name)[0]
                or "application/octet-stream",
            }
            for file in path.rglob("*")
            if file.is_file()
        ]

    params = request.params
    try:
        validate(params, scan_args_schema)
    except ValidationError:
        logger.exception("Invalid params for scan method:")
        raise RpcInvalidParamsError()

    site = sites.get(params["id"])
    if site is None:
        logger.error("Client request non-existent site %s.", params["site_id"])
        raise RpcInvalidParamsError("Site does not exist.")

    loop = asyncio.get_event_loop()
    content, theme = await asyncio.gather(
        site.runner.command("scan"),
        loop.run_in_executor(
            None, list_theme_files, cast(dict, site.runner.settings)["THEME"]
        ),
    )

    return {"content": cast(dict, content)["content"], "theme": theme}


def rpc_factory() -> JsonRpc:
    rpc = JsonRpc()

    rpc.add_methods(("", list_sites), ("", list_site_files))

    return rpc
