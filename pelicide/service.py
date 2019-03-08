import asyncio
import logging
import mimetypes
import pathlib
from typing import Any, Dict, Iterable, Tuple, cast

import aiofiles
from aiohttp_json_rpc import (
    JsonRpc,
    RpcGenericServerDefinedError,
    RpcInvalidParamsError,
)
from aiohttp_json_rpc.communicaton import JsonRpcRequest
from jsonschema import ValidationError, validate

from pelicide.sites import Site, SiteDirectory
from pelicide.util import inject

logger = logging.getLogger(__name__)

LIST_SITE_FILES_PARAMS_SCHEMA = {
    "type": "object",
    "properties": {"id": {"type": "string"}},
    "required": ["site_id"],
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

PUT_FILE_CONTENT_PARAMS_SCHEMA = {
    "type": "object",
    "properties": {
        "site_id": {"type": "string"},
        "anchor": {"type": "string", "enum": ["content", "theme"]},
        "path": {"type": "array", "items": {"type": "string"}},
        "name": {"type": "string"},
        "content": {"type": "string"},
    },
    "required": ["site_id", "anchor", "path", "name", "content"],
}

RENDER_PARAMS_SCHEMA = {
    "type": "object",
    "properties": {
        "site_id": {"type": "string"},
        "format": {"type": "string"},
        "content": {"type": "string"},
    },
    "required": ["site_id", "format", "content"],
}

BUILD_PARAMS_SCHEMA = {
    "type": "object",
    "properties": {
        "site_id": {"type": "string"},
        "paths": {
            "anyOf": [
                {"type": "null"},
                {
                    "type": "array",
                    "items": {
                        "type": "array",
                        "items": [
                            {"type": "array", "items": {"type": "string"}},
                            {"type": "string"},
                        ],
                    },
                },
            ]
        },
    },
    "required": ["site_id"],
}


class RpcSiteNotFound(RpcGenericServerDefinedError):
    ERROR_CODE = 1
    MESSAGE = "Invalid site ID"


class RpcFileNotFound(RpcGenericServerDefinedError):
    ERROR_CODE = 2
    MESSAGE = "File not found"


class RpcFormatNotSupported(RpcGenericServerDefinedError):
    ERROR_CODE = 3
    MESSAGE = "Format not supported"


def validate_params(request: JsonRpcRequest, schema: Dict[str, Any]) -> Dict[str, Any]:
    try:
        validate(request.params, schema)
    except ValidationError:
        logger.exception(f"Invalid params for method:")
        raise RpcInvalidParamsError()

    return cast(Dict[str, Any], request.params)


@inject  # type:ignore
def validate_and_get_site(
    request: JsonRpcRequest, schema: Dict[str, Any], *, sites: SiteDirectory
) -> Tuple[Dict[str, Any], Site]:
    params = validate_params(request, schema)
    site = sites.get(params["site_id"])
    if site is None:
        logger.error("Client request non-existent site %s.", params["site_id"])
        raise RpcInvalidParamsError(message="Site does not exist.")
    return params, site


@inject  # type: ignore
async def list_sites(
    request: JsonRpcRequest, *, sites: SiteDirectory
) -> Iterable[Dict[str, str]]:
    return [
        {
            "site_id": site_id,
            "name": cast(dict, site.runner.settings)["SITENAME"],
            "formats": cast(dict, site.runner.settings)["FORMATS"],
        }
        for site_id, site in sites.items()
    ]


async def list_site_files(
    request: JsonRpcRequest
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

    params, site = validate_and_get_site(request, LIST_SITE_FILES_PARAMS_SCHEMA)

    loop = asyncio.get_event_loop()
    content, theme = await asyncio.gather(
        site.runner.command("scan"),
        loop.run_in_executor(
            None, list_theme_files, cast(dict, site.runner.settings)["THEME"]
        ),
    )

    return {"content": cast(dict, content)["content"], "theme": theme}


async def get_file_content(request: JsonRpcRequest) -> Dict[str, str]:
    params, site = validate_and_get_site(request, GET_FILE_CONTENT_PARAMS_SCHEMA)

    root = pathlib.Path(
        cast(dict, site.runner.settings)[params["anchor"].upper()]
    ).resolve()
    path = root.joinpath(*params["path"], params["name"])
    try:
        path.resolve().relative_to(root)
    except ValueError:
        raise RpcFileNotFound()

    try:
        async with aiofiles.open(str(path)) as f:
            return {"content": await f.read()}
    except FileNotFoundError:
        raise RpcFileNotFound()


async def put_file_content(request: JsonRpcRequest) -> None:
    params, site = validate_and_get_site(request, PUT_FILE_CONTENT_PARAMS_SCHEMA)

    root = pathlib.Path(
        cast(dict, site.runner.settings)[params["anchor"].upper()]
    ).resolve()
    path = root.joinpath(*params["path"], params["name"])
    try:
        path.resolve().relative_to(root)
    except ValueError:
        raise RpcFileNotFound()

    try:
        async with aiofiles.open(str(path), "w") as f:
            await f.write(params["content"])
    except FileNotFoundError:
        raise RpcFileNotFound()


async def render(request: JsonRpcRequest) -> Dict[str, Any]:
    params, site = validate_and_get_site(request, RENDER_PARAMS_SCHEMA)

    settings = cast(dict, site.runner.settings)
    if not params["format"] in settings["FORMATS"]:
        raise RpcFormatNotSupported()

    content = await site.runner.command("render", [params["format"], params["content"]])
    return cast(dict, content)


async def build(request: JsonRpcRequest) -> None:
    params, site = validate_and_get_site(request, BUILD_PARAMS_SCHEMA)
    await site.runner.command("build", params.get("paths"))


def rpc_factory() -> JsonRpc:
    rpc = JsonRpc()

    rpc.add_methods(
        ("", list_sites),
        ("", list_site_files),
        ("", get_file_content),
        ("", put_file_content),
        ("", render),
        ("", build),
    )

    return rpc
