from __future__ import annotations

import asyncio
import threading
from typing import Callable, Optional


class AsyncLoopMixin:
    """Utilitário compartilhado para serviços que usam loop assíncrono dedicado."""

    _ASYNC_LOOP_THREAD_NAME: Optional[str] = None

    def __init__(self) -> None:
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._loop_thread: Optional[threading.Thread] = None
        self._loop_ready = threading.Event()

    @staticmethod
    async def _call_sync(func: Callable[[], None]) -> None:
        func()

    def _loop_thread_name(self) -> str:
        if self._ASYNC_LOOP_THREAD_NAME:
            return self._ASYNC_LOOP_THREAD_NAME
        return f"{self.__class__.__name__.lower()}-loop"

    def _on_loop_ready(self, loop: asyncio.AbstractEventLoop) -> None:  # pragma: no cover - hook
        """Gancho executado quando o loop assíncrono está pronto."""

    def _ensure_loop(self) -> asyncio.AbstractEventLoop:
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        if loop is not None:
            self._loop = loop
            self._loop_ready.set()
            self._on_loop_ready(loop)
            return loop

        existing = self._loop
        if existing and existing.is_running():
            self._loop_ready.set()
            self._run_on_loop(lambda: self._on_loop_ready(existing), loop=existing, wait=True)
            return existing

        loop = asyncio.new_event_loop()
        self._loop = loop
        self._loop_ready.clear()

        def runner() -> None:
            asyncio.set_event_loop(loop)
            try:
                self._on_loop_ready(loop)
            finally:
                self._loop_ready.set()
            loop.run_forever()

        thread = threading.Thread(
            target=runner,
            name=self._loop_thread_name(),
            daemon=True,
        )
        self._loop_thread = thread
        thread.start()
        self._loop_ready.wait()
        return loop

    def _run_on_loop(
        self,
        func: Callable[[], None],
        *,
        wait: bool = False,
        loop: Optional[asyncio.AbstractEventLoop] = None,
    ) -> None:
        target = loop or self._loop
        if target is None:
            return

        try:
            running = asyncio.get_running_loop()
        except RuntimeError:
            running = None

        if running is target:
            func()
            return

        fut = asyncio.run_coroutine_threadsafe(self._call_sync(func), target)
        if wait:
            fut.result()
