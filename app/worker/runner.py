import asyncio
import signal
from typing import Protocol


class Worker(Protocol):
    async def process_one(self) -> bool: ...


def install_signal_handlers(stop: asyncio.Event) -> None:
    loop = asyncio.get_running_loop()
    for signal_number in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(signal_number, stop.set)
        except NotImplementedError:
            signal.signal(signal_number, lambda *_: stop.set())


async def run(worker: Worker, poll_seconds: float) -> None:
    stop = asyncio.Event()
    install_signal_handlers(stop)
    while not stop.is_set():
        processed = await worker.process_one()
        if not processed:
            try:
                await asyncio.wait_for(stop.wait(), timeout=poll_seconds)
            except TimeoutError:
                pass
