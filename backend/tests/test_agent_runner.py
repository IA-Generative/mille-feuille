import asyncio

import fakeredis
import pytest

from app.agent import runner as runner_module
from app.agent.runner import AgentRunner


@pytest.fixture(autouse=True)
def _fake_redis(monkeypatch: pytest.MonkeyPatch) -> fakeredis.FakeRedis:
    fake = fakeredis.FakeRedis(decode_responses=True)
    monkeypatch.setattr(runner_module.redis_connector, "client", fake)
    return fake


async def _until(condition, timeout: float = 2.0) -> None:
    async with asyncio.timeout(timeout):
        while not condition():
            await asyncio.sleep(0.01)


def test_start_returns_at_once_and_runs_the_job() -> None:
    async def scenario() -> None:
        runner = AgentRunner()
        gate, done = asyncio.Event(), []

        async def job() -> None:
            await gate.wait()
            done.append(True)

        runner.start("a", job)
        assert runner.is_running("a") and not done
        gate.set()
        await _until(lambda: not runner.is_running("a"))
        assert done == [True]

    asyncio.run(scenario())


def test_a_name_already_running_is_not_started_twice() -> None:
    async def scenario() -> None:
        runner = AgentRunner()
        gate, calls = asyncio.Event(), []

        async def job() -> None:
            calls.append(1)
            await gate.wait()

        runner.start("a", job)
        runner.start("a", job)
        await asyncio.sleep(0.05)
        assert calls == [1]
        gate.set()
        await _until(lambda: not runner.is_running("a"))

    asyncio.run(scenario())


def test_concurrency_is_bounded(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(runner_module.settings, "MAX_CONCURRENT_JOBS", 1)

    async def scenario() -> None:
        runner = AgentRunner()
        gate, started = asyncio.Event(), []

        def make(name: str):
            async def job() -> None:
                started.append(name)
                await gate.wait()

            return job

        runner.start("a", make("a"))
        runner.start("b", make("b"))
        await asyncio.sleep(0.05)
        assert started == ["a"]
        gate.set()
        await _until(lambda: started == ["a", "b"])
        await _until(lambda: not runner.is_running("b"))

    asyncio.run(scenario())


def test_a_failing_job_is_forgotten_and_does_not_block_the_next() -> None:
    async def scenario() -> None:
        runner = AgentRunner()
        ran = []

        async def failing() -> None:
            raise RuntimeError("boom")

        async def fine() -> None:
            ran.append(True)

        runner.start("bad", failing)
        await _until(lambda: not runner.is_running("bad"))
        runner.start("good", fine)
        await _until(lambda: not runner.is_running("good"))
        assert ran == [True]

    asyncio.run(scenario())


def test_cancel_stops_a_waiting_job() -> None:
    async def scenario() -> None:
        runner = AgentRunner()

        async def job() -> None:
            await asyncio.Event().wait()

        runner.start("a", job)
        await asyncio.sleep(0.01)
        runner.cancel("a")
        await _until(lambda: not runner.is_running("a"))

    asyncio.run(scenario())


def test_start_up_runs_the_sweeps_and_a_failing_one_does_not_stop_the_others() -> None:
    async def scenario() -> None:
        runner = AgentRunner()
        swept = []

        async def broken(is_alive) -> None:  # noqa: ANN001
            raise RuntimeError("boom")

        async def sweep(is_alive) -> None:  # noqa: ANN001
            swept.append(True)

        runner.register_sweep(broken)
        runner.register_sweep(sweep)
        await runner.start_up()
        assert swept == [True]

    asyncio.run(scenario())


def test_shut_down_cancels_running_jobs() -> None:
    async def scenario() -> None:
        runner = AgentRunner()

        async def job() -> None:
            await asyncio.Event().wait()

        runner.start("a", job)
        await asyncio.sleep(0.01)
        await runner.shut_down()
        assert not runner.is_running("a")

    asyncio.run(scenario())


def test_a_job_running_here_or_beating_elsewhere_is_alive(_fake_redis: fakeredis.FakeRedis) -> None:
    async def scenario() -> None:
        runner = AgentRunner()
        gate = asyncio.Event()

        async def job() -> None:
            await gate.wait()

        assert not await runner.is_alive("a")
        runner.start("a", job)
        assert await runner.is_alive("a")
        await _until(lambda: _fake_redis.exists("agent:job:a"))
        gate.set()
        await _until(lambda: not runner.is_running("a"))
        assert not await runner.is_alive("a")
        # Un autre pod : seul son battement dans Redis le dit.
        _fake_redis.set("agent:job:b", 1)
        assert await runner.is_alive("b")

    asyncio.run(scenario())
