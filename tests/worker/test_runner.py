import asyncio

import pytest

from app.worker import runner


@pytest.mark.asyncio
async def test_runner_stops_without_polling_when_shutdown_is_requested(monkeypatch) -> None:
    calls = 0

    class Worker:
        async def process_one(self) -> bool:
            nonlocal calls
            calls += 1
            return False

    def request_stop(stop: asyncio.Event) -> None:
        stop.set()

    monkeypatch.setattr(runner, "install_signal_handlers", request_stop)

    await runner.run(Worker(), poll_seconds=0.01)

    assert calls == 0


def test_install_signal_handlers_registers_supported_signals(monkeypatch) -> None:
    registered = []

    class Loop:
        def add_signal_handler(self, signal_number, callback) -> None:
            registered.append((signal_number, callback))

    monkeypatch.setattr(asyncio, "get_running_loop", lambda: Loop())
    stop = asyncio.Event()

    runner.install_signal_handlers(stop)

    assert len(registered) == 2
    registered[0][1]()
    assert stop.is_set()
