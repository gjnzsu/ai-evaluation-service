import asyncio
import logging

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


@pytest.mark.asyncio
async def test_runner_contains_unexpected_iteration_error_and_polls(
    monkeypatch, caplog
) -> None:
    calls = 0
    captured_stop = None

    class Worker:
        async def process_one(self) -> bool:
            nonlocal calls
            calls += 1
            if calls == 1:
                raise RuntimeError("runner-password-secret")
            captured_stop.set()
            return False

    def capture_stop(stop: asyncio.Event) -> None:
        nonlocal captured_stop
        captured_stop = stop

    monkeypatch.setattr(runner, "install_signal_handlers", capture_stop)

    with caplog.at_level(logging.INFO, logger="ai_evaluation_service"):
        await runner.run(Worker(), poll_seconds=0.01)

    assert calls == 2
    assert any(
        getattr(record, "safe_fields", {}).get("error_code")
        == "worker_iteration_failed"
        for record in caplog.records
    )
    assert "runner-password-secret" not in caplog.text
    assert "Traceback" not in caplog.text
