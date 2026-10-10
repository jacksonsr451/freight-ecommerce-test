"""Project-specific asyncio fixture bridge for jsr-testrunner.

jsr-testrunner deliberately does not run coroutine tests/fixtures natively. The
suite uses only AnyIO's default asyncio backend, so this adapter runs each test
and its async-generator fixtures on one function-scoped asyncio event loop.
"""

from __future__ import annotations

import asyncio
import inspect
from collections.abc import AsyncGenerator, Callable, Generator
from typing import Any, TypeVar

import testrunner

F = TypeVar("F", bound=Callable[..., Any])


@testrunner.fixture(autouse=True)
def async_test_loop() -> Generator[asyncio.AbstractEventLoop, None, None]:
    loop = asyncio.new_event_loop()
    try:
        yield loop
    finally:
        loop.run_until_complete(loop.shutdown_asyncgens())
        loop.close()


def async_fixture(function: F) -> Any:
    """Adapt an async coroutine/generator fixture using testrunner's fixture API."""
    parameters = inspect.signature(function).parameters

    @testrunner.fixture(name=function.__name__)
    def fixture(request: testrunner.FixtureRequest, async_test_loop):
        dependencies = {name: request.getfixturevalue(name) for name in parameters}
        result = function(**dependencies)
        if inspect.isasyncgen(result):
            generator: AsyncGenerator[Any, None] = result
            try:
                value = async_test_loop.run_until_complete(generator.__anext__())
            except StopAsyncIteration as error:
                raise RuntimeError(f"Async fixture {function.__name__} yielded no value") from error
            try:
                yield value
            finally:
                try:
                    async_test_loop.run_until_complete(generator.__anext__())
                except StopAsyncIteration:
                    pass
                else:
                    raise RuntimeError(f"Async fixture {function.__name__} yielded more than once")
        elif inspect.iscoroutine(result):
            return async_test_loop.run_until_complete(result)
        else:
            raise TypeError(f"Async fixture {function.__name__} is not awaitable")

    return fixture
