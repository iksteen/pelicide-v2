import asyncio
import json
import logging
import subprocess
from types import TracebackType
from typing import Any, Dict, Iterable, Optional, Type, cast

import pkg_resources

logger = logging.getLogger(__name__)

RunnerData = Optional[Dict[str, Any]]


class RunnerException(Exception):
    pass


class RunnerExitedException(RunnerException):
    pass


class RunnerProcess:
    queue: asyncio.Queue

    def __init__(self, args: Iterable[str]) -> None:
        self.args = args
        self.queue = asyncio.Queue(1)

    @property
    def loop(self) -> asyncio.AbstractEventLoop:
        return asyncio.get_event_loop()

    async def run(self, settings_future: asyncio.Future) -> None:
        pending = {0: settings_future}

        process = await asyncio.create_subprocess_exec(
            *self.args, stdin=subprocess.PIPE, stdout=subprocess.PIPE
        )
        assert process.stdin is not None and process.stdout is not None
        stdin, stdout = process.stdin, process.stdout

        async def command_writer() -> None:
            request_id = 0
            while True:
                request_id += 1
                command, args, f = await self.queue.get()
                pending[request_id] = f
                stdin.write(f"{request_id} {command} {args}\n".encode("utf-8"))
                await stdin.drain()

        async def result_reader() -> None:
            while not stdout.at_eof():
                line = await stdout.readline()
                if line:
                    request_id, result, data_json = line.split(b" ", 2)
                    f = pending.pop(int(request_id))
                    success = result == b"+"
                    data = json.loads(data_json)

                    if success:
                        f.set_result(data)
                    else:
                        f.set_exception(RunnerException(data))

        command_writer_task = self.loop.create_task(command_writer())
        try:
            await result_reader()
        except asyncio.CancelledError:
            process.terminate()
        command_writer_task.cancel()
        await process.wait()

        for task in pending.values():
            task.set_exception(RunnerExitedException())

    async def __call__(self, command: str, args: RunnerData) -> RunnerData:
        args_json = json.dumps(args)
        f = self.loop.create_future()
        await self.queue.put((command, args_json, f))
        return cast(RunnerData, await f)


class Runner:
    process: Optional[RunnerProcess] = None
    process_task: Optional[asyncio.Task] = None
    settings: Optional[RunnerData] = None

    def __init__(
        self, interpreter: str, pelicanconf: str, init_settings: Dict[str, str]
    ) -> None:
        self.interpreter = interpreter
        self.pelicanconf = pelicanconf
        self.init_settings = init_settings

    @property
    def loop(self) -> asyncio.AbstractEventLoop:
        return asyncio.get_event_loop()

    async def start(self) -> None:
        assert self.process is None

        runner = pkg_resources.resource_filename(__package__, "pelican-runner.py")
        self.process = RunnerProcess(
            [self.interpreter, runner, self.pelicanconf, json.dumps(self.init_settings)]
        )
        f = self.loop.create_future()
        self.process_task = process_task = self.loop.create_task(self.process.run(f))
        process_task.add_done_callback(self.handle_process_exit)
        self.settings = await f

    async def stop(self) -> None:
        process_task = self.process_task
        if process_task is not None:
            process_task.cancel()
            await process_task

    async def __aenter__(self) -> "Runner":
        await self.start()
        return self

    async def __aexit__(
        self,
        exc_type: Optional[Type[BaseException]],
        exc_value: Optional[BaseException],
        traceback: Optional[TracebackType],
    ) -> None:
        await self.stop()

    def handle_process_exit(self, f: asyncio.Future) -> None:
        self.process = self.process_task = None
        try:
            f.result()
        except:  # noqa: E722
            logger.exception("Runner exited with error:")

    async def command(self, command: str, args: RunnerData = None) -> RunnerData:
        if self.process is not None:
            return await self.process(command, args)
        else:
            raise RunnerExitedException()

    async def restart(self) -> None:
        process = self.process
        if process:
            await self.command("quit")

        process_task = self.process_task
        if process_task:
            await process_task

        await self.start()
