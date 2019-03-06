import asyncio
import logging
import mimetypes
import pathlib
from typing import Any, Dict, Iterable, cast

import aiofiles
from aiohttp_json_rpc import (
    JsonRpc,
    RpcGenericServerDefinedError,
    RpcInvalidParamsError,
)
from aiohttp_json_rpc.communicaton import JsonRpcRequest
from jsonschema import ValidationError, validate

from pelicide.sites import SiteDirectory
from pelicide.util import inject

logger = logging.getLogger(__name__)

LIST_SITE_FILES_PARAMS_SCHEMA = {
    "type": "object",
    "properties": {"id": {"type": "string"}},
    "required": ["id"],
}

GET_FILE_CONTENT_PARAMS_SCHEMA = {
    "type": "object",
    "properties": {
        "site_id": {"type": "string"},
        "anchor": {"type": "string", "enum": ["content", "theme"]},
        "path": {"type": "array", "items": {"type": "string"}},
        "name": {"type": "string"},
    },
    "required": ["site_id", "anchor", "path", "name"],
}


class RpcSiteNotFound(RpcGenericServerDefinedError):
    ERROR_CODE = 1
    MESSAGE = "Invalid site ID"


class RpcFileNotFound(RpcGenericServerDefinedError):
    ERROR_CODE = 2
    MESSAGE = "File not found"


@inject  # type: ignore
async def list_sites(
    request: JsonRpcRequest, *, sites: SiteDirectory
) -> Iterable[Dict[str, str]]:
    return [
        {"id": site_id, "name": cast(dict, site.runner.settings)["SITENAME"]}
        for site_id, site in sites.items()
    ]


@inject  # type: ignore
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
        validate(params, LIST_SITE_FILES_PARAMS_SCHEMA)
    except ValidationError:
        logger.exception("Invalid params for list_site_files method:")
        raise RpcInvalidParamsError()

    site = sites.get(params["id"])
    if site is None:
        logger.error("Client request non-existent site %s.", params["site_id"])
        raise RpcSiteNotFound()

    loop = asyncio.get_event_loop()
    content, theme = await asyncio.gather(
        site.runner.command("scan"),
        loop.run_in_executor(
            None, list_theme_files, cast(dict, site.runner.settings)["THEME"]
        ),
    )

    return {"content": cast(dict, content)["content"], "theme": theme}


@inject  # type: ignore
async def get_file_content(
    request: JsonRpcRequest, *, sites: SiteDirectory
) -> Dict[str, str]:
    params = request.params
    try:
        validate(params, GET_FILE_CONTENT_PARAMS_SCHEMA)
    except ValidationError:
        logger.exception("Invalid params for scan method:")
        raise RpcInvalidParamsError()

    site = sites.get(params["site_id"])
    if site is None:
        logger.error("Client request non-existent site %s.", params["site_id"])
        raise RpcInvalidParamsError(message="Site does not exist.")

    root = pathlib.Path(cast(dict, site.runner.settings)[params["anchor"].upper()])
    path = root.joinpath(*params["path"], params["name"])
    try:
        async with aiofiles.open(str(path)) as f:
            return {"content": await f.read()}
    except FileNotFoundError:
        raise RpcFileNotFound()


def rpc_factory() -> JsonRpc:
    rpc = JsonRpc()

    rpc.add_methods(("", list_sites), ("", list_site_files), ("", get_file_content))

    return rpc
