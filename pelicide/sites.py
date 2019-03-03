import logging
import os
import pathlib
import sys
import uuid
from configparser import ConfigParser
from tempfile import TemporaryDirectory
from typing import AsyncGenerator, Dict, Iterable, NamedTuple, NewType, Optional

from aiohttp import web
from appdirs import user_config_dir

from pelicide.runner import Runner
from pelicide.util import injector

logger = logging.getLogger(__name__)


class SiteConfig(NamedTuple):
    id: str
    interpreter: str
    pelicanconf: str

    @property
    def site_path(self) -> str:
        return f"/site/{self.id}"


class Site(NamedTuple):
    config: SiteConfig
    temp_dir: TemporaryDirectory
    runner: Runner

    @property
    def output_path(self) -> str:
        return os.path.join(self.temp_dir.name, "output")


SiteDirectory = NewType("SiteDirectory", Dict[str, Site])


def load_site_config(site_path: str) -> SiteConfig:
    config_file: Optional[pathlib.Path]
    pelicanconf: Optional[pathlib.Path]

    project_home = pathlib.Path(site_path)
    if project_home.is_dir():
        config_file = project_home / "pelicide.ini"
        if not config_file.exists():
            config_file = None
        pelicanconf = None
    elif project_home.is_file():
        if project_home.suffix == ".py":
            config_file = None
            pelicanconf = project_home
            project_home = project_home.parent
        else:
            config_file = project_home
            project_home = project_home.parent
            pelicanconf = None
    else:
        raise ValueError("Can not load site config from %s", project_home)

    for interpreter in (
        project_home / ".venv" / "bin" / "python.exe",
        project_home / ".venv" / "bin" / "python",
        project_home / "venv" / "bin" / "python.exe",
        project_home / "venv" / "bin" / "python",
    ):
        if interpreter.exists():
            break
    else:
        interpreter = pathlib.Path(sys.executable)

    config = ConfigParser({"here": str(project_home)})
    config.add_section("pelicide")
    config.set("pelicide", "python", str(interpreter))
    config.set("pelicide", "pelicanconf", "pelicanconf.py")

    # Load global config first.
    global_config = os.path.join(user_config_dir("pelicide"), "pelicide.ini")
    config.read(global_config)

    # If a config file was specified or found, load that.
    if config_file is not None:
        config.read(config_file)

    # If a pelicanconf was specified, it overrides any loaded options.
    if pelicanconf is not None:
        config.set("pelicide", "pelicanconf", str(pelicanconf))

    interpreter = project_home / os.path.expanduser(config.get("pelicide", "python"))
    pelicanconf = project_home / os.path.expanduser(
        config.get("pelicide", "pelicanconf", fallback="pelicanconf.py")
    )

    if not interpreter.exists():
        raise ValueError("Python interpreter not found.")

    if not pelicanconf.exists():
        raise ValueError("Pelican configuration not found.")

    return SiteConfig(str(uuid.uuid4()), str(interpreter), str(pelicanconf))


async def load_site(config: SiteConfig) -> Site:
    temp_dir = TemporaryDirectory(prefix="pelicide-")
    try:
        output_path = os.path.join(temp_dir.name, "output")
        os.makedirs(output_path)
        runner = Runner(
            config.interpreter,
            config.pelicanconf,
            {
                "OUTPUT_PATH": output_path,
                "SITEURL": config.site_path,
                "RELATIVE_URLS": True,
            },
        )
        try:
            await runner.start()
            await runner.command("build")
            return Site(config, temp_dir, runner)
        except:  # noqa: E722
            await runner.stop()
            raise
    except:  # noqa: E722
        temp_dir.cleanup()
        raise


async def cleanup_site(site: Site) -> None:
    try:
        await site.runner.stop()
    except:  # noqa: E722
        logger.exception("Failed to stop runner:")

    try:
        site.temp_dir.cleanup()
    except:  # noqa: E722
        logger.exception("Failed to clean up temp dir:")


async def load_sites(projects: Iterable[str], app: web.Application) -> AsyncGenerator:
    configs = [load_site_config(site_path) for site_path in projects]

    sites = SiteDirectory({})
    for config in configs:
        sites[config.id] = site = await load_site(config)
        app.router.add_static(f"{config.site_path}", site.output_path)

    with injector.scope():
        injector.register(sites, SiteDirectory)
        yield

    for site in sites.values():
        await cleanup_site(site)
