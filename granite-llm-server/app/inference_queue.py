from __future__ import annotations

import math
import time
from collections import deque
from dataclasses import dataclass
from threading import Condition
from typing import Callable


WAITING = "waiting"
ADMITTED = "admitted"
QUEUE_FULL = "queue_full"
QUEUE_MEMORY_FULL = "queue_memory_full"
TIMED_OUT = "timed_out"
CANCELLED = "cancelled"


def _non_negative_integer(name: str, value: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{name} must be a non-negative integer.")
    return value


def _positive_integer(name: str, value: int) -> int:
    value = _non_negative_integer(name, value)
    if value < 1:
        raise ValueError(f"{name} must be a positive integer.")
    return value


def _non_negative_seconds(name: str, value: float | int) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be a non-negative finite number.")
    normalized = float(value)
    if not math.isfinite(normalized) or normalized < 0:
        raise ValueError(f"{name} must be a non-negative finite number.")
    return normalized


@dataclass(frozen=True)
class InferenceQueueSnapshot:
    active_requests: int
    waiting_requests: int
    queued_bytes: int
    max_active_requests: int
    max_waiting_requests: int
    max_queued_bytes: int


@dataclass(frozen=True)
class QueueTicketSnapshot:
    status: str
    initial_position: int | None
    depth_on_arrival: int
    queued_bytes_on_arrival: int
    wait_ms: int | None
    capacity: int
    released: bool


class QueueTicket:
    """One request's private admission lifecycle."""

    def __init__(
        self,
        owner: InferenceQueue,
        *,
        request_bytes: int,
        created_ns: int,
        deadline_ns: int,
        status: str,
        initial_position: int | None,
        depth_on_arrival: int,
        queued_bytes_on_arrival: int,
        terminal_ns: int | None = None,
    ):
        self._owner = owner
        self._request_bytes = request_bytes
        self._created_ns = created_ns
        self._deadline_ns = deadline_ns
        self._status = status
        self._initial_position = initial_position
        self._depth_on_arrival = depth_on_arrival
        self._queued_bytes_on_arrival = queued_bytes_on_arrival
        self._terminal_ns = terminal_ns
        self._released = False

    def wait(self, poll_seconds: float | int | None = None) -> str:
        """
        Wait for admission or another terminal result.

        A finite poll interval lets a streaming response emit a heartbeat while
        preserving the ticket's original queue deadline. Returning ``waiting``
        means only that the poll interval elapsed.
        """
        return self._owner._wait_for_ticket(self, poll_seconds)

    def cancel(self) -> bool:
        """Remove this ticket if it is still waiting."""
        return self._owner._cancel_ticket(self)

    def release(self) -> bool:
        """Release this ticket's active inference slot exactly once."""
        return self._owner._release_ticket(self)

    def snapshot(self) -> QueueTicketSnapshot:
        return self._owner._ticket_snapshot(self)


class InferenceQueue:
    """A bounded, process-local FIFO admission queue for model inference."""

    def __init__(
        self,
        *,
        max_active_requests: int,
        max_waiting_requests: int,
        max_queued_bytes: int,
        wait_timeout_seconds: float | int,
        clock_ns: Callable[[], int] = time.monotonic_ns,
    ):
        self._max_active_requests = _positive_integer(
            "max_active_requests", max_active_requests
        )
        self._max_waiting_requests = _non_negative_integer(
            "max_waiting_requests", max_waiting_requests
        )
        self._max_queued_bytes = _non_negative_integer(
            "max_queued_bytes", max_queued_bytes
        )
        wait_seconds = _non_negative_seconds(
            "wait_timeout_seconds", wait_timeout_seconds
        )
        if not callable(clock_ns):
            raise ValueError("clock_ns must be callable.")

        self._wait_timeout_ns = round(wait_seconds * 1_000_000_000)
        self._clock_ns = clock_ns
        self._condition = Condition()
        self._waiting: deque[QueueTicket] = deque()
        self._active_requests = 0
        self._queued_bytes = 0

    def request_slot(self, request_bytes: int) -> QueueTicket:
        """Admit immediately, enqueue, or return a rejected queue ticket."""
        request_bytes = _non_negative_integer("request_bytes", request_bytes)

        with self._condition:
            now_ns = self._now_ns()
            self._advance_locked(now_ns)
            depth_on_arrival = len(self._waiting)
            queued_bytes_on_arrival = self._queued_bytes

            if (
                not self._waiting
                and self._active_requests < self._max_active_requests
            ):
                self._active_requests += 1
                return self._new_ticket(
                    request_bytes=request_bytes,
                    now_ns=now_ns,
                    status=ADMITTED,
                    initial_position=0,
                    depth_on_arrival=depth_on_arrival,
                    queued_bytes_on_arrival=queued_bytes_on_arrival,
                    terminal_ns=now_ns,
                )

            if depth_on_arrival >= self._max_waiting_requests:
                return self._new_ticket(
                    request_bytes=request_bytes,
                    now_ns=now_ns,
                    status=QUEUE_FULL,
                    initial_position=None,
                    depth_on_arrival=depth_on_arrival,
                    queued_bytes_on_arrival=queued_bytes_on_arrival,
                    terminal_ns=now_ns,
                )

            if self._queued_bytes + request_bytes > self._max_queued_bytes:
                return self._new_ticket(
                    request_bytes=request_bytes,
                    now_ns=now_ns,
                    status=QUEUE_MEMORY_FULL,
                    initial_position=None,
                    depth_on_arrival=depth_on_arrival,
                    queued_bytes_on_arrival=queued_bytes_on_arrival,
                    terminal_ns=now_ns,
                )

            if self._wait_timeout_ns == 0:
                return self._new_ticket(
                    request_bytes=request_bytes,
                    now_ns=now_ns,
                    status=TIMED_OUT,
                    initial_position=None,
                    depth_on_arrival=depth_on_arrival,
                    queued_bytes_on_arrival=queued_bytes_on_arrival,
                    terminal_ns=now_ns,
                )

            ticket = self._new_ticket(
                request_bytes=request_bytes,
                now_ns=now_ns,
                status=WAITING,
                initial_position=depth_on_arrival + 1,
                depth_on_arrival=depth_on_arrival,
                queued_bytes_on_arrival=queued_bytes_on_arrival,
            )
            self._waiting.append(ticket)
            self._queued_bytes += request_bytes
            return ticket

    def snapshot(self) -> InferenceQueueSnapshot:
        with self._condition:
            self._advance_locked(self._now_ns())
            return InferenceQueueSnapshot(
                active_requests=self._active_requests,
                waiting_requests=len(self._waiting),
                queued_bytes=self._queued_bytes,
                max_active_requests=self._max_active_requests,
                max_waiting_requests=self._max_waiting_requests,
                max_queued_bytes=self._max_queued_bytes,
            )

    def _new_ticket(
        self,
        *,
        request_bytes: int,
        now_ns: int,
        status: str,
        initial_position: int | None,
        depth_on_arrival: int,
        queued_bytes_on_arrival: int,
        terminal_ns: int | None = None,
    ) -> QueueTicket:
        return QueueTicket(
            self,
            request_bytes=request_bytes,
            created_ns=now_ns,
            deadline_ns=now_ns + self._wait_timeout_ns,
            status=status,
            initial_position=initial_position,
            depth_on_arrival=depth_on_arrival,
            queued_bytes_on_arrival=queued_bytes_on_arrival,
            terminal_ns=terminal_ns,
        )

    def _now_ns(self) -> int:
        now_ns = self._clock_ns()
        if isinstance(now_ns, bool) or not isinstance(now_ns, int) or now_ns < 0:
            raise RuntimeError("The inference queue clock returned an invalid value.")
        return now_ns

    def _wait_for_ticket(
        self,
        ticket: QueueTicket,
        poll_seconds: float | int | None,
    ) -> str:
        poll_ns = (
            None
            if poll_seconds is None
            else round(_non_negative_seconds("poll_seconds", poll_seconds) * 1_000_000_000)
        )

        with self._condition:
            self._require_owned_ticket(ticket)
            poll_deadline_ns = None
            if poll_ns is not None:
                poll_deadline_ns = self._now_ns() + poll_ns

            while ticket._status == WAITING:
                now_ns = self._now_ns()
                self._advance_locked(now_ns)
                if ticket._status != WAITING:
                    break

                remaining_ns = ticket._deadline_ns - now_ns
                if poll_deadline_ns is not None:
                    remaining_ns = min(
                        remaining_ns,
                        poll_deadline_ns - now_ns,
                    )
                if remaining_ns <= 0:
                    break
                self._condition.wait(remaining_ns / 1_000_000_000)

            if ticket._status == WAITING:
                self._advance_locked(self._now_ns())
            return ticket._status

    def _cancel_ticket(self, ticket: QueueTicket) -> bool:
        with self._condition:
            self._require_owned_ticket(ticket)
            if ticket._status != WAITING:
                return False
            self._remove_waiting_locked(ticket, CANCELLED, self._now_ns())
            self._advance_locked(self._now_ns())
            self._condition.notify_all()
            return True

    def _release_ticket(self, ticket: QueueTicket) -> bool:
        with self._condition:
            self._require_owned_ticket(ticket)
            if ticket._status != ADMITTED or ticket._released:
                return False
            if self._active_requests < 1:
                raise RuntimeError("Inference queue active-request count is inconsistent.")
            ticket._released = True
            self._active_requests -= 1
            self._advance_locked(self._now_ns())
            self._condition.notify_all()
            return True

    def _ticket_snapshot(self, ticket: QueueTicket) -> QueueTicketSnapshot:
        with self._condition:
            self._require_owned_ticket(ticket)
            self._advance_locked(self._now_ns())
            wait_ms = None
            if ticket._terminal_ns is not None:
                wait_ms = max(
                    0,
                    (ticket._terminal_ns - ticket._created_ns) // 1_000_000,
                )
            return QueueTicketSnapshot(
                status=ticket._status,
                initial_position=ticket._initial_position,
                depth_on_arrival=ticket._depth_on_arrival,
                queued_bytes_on_arrival=ticket._queued_bytes_on_arrival,
                wait_ms=wait_ms,
                capacity=self._max_waiting_requests,
                released=ticket._released,
            )

    def _advance_locked(self, now_ns: int) -> None:
        while self._waiting and self._waiting[0]._deadline_ns <= now_ns:
            self._remove_waiting_locked(self._waiting[0], TIMED_OUT, now_ns)

        while (
            self._waiting
            and self._active_requests < self._max_active_requests
        ):
            ticket = self._waiting[0]
            self._waiting.popleft()
            self._queued_bytes -= ticket._request_bytes
            ticket._status = ADMITTED
            ticket._terminal_ns = now_ns
            self._active_requests += 1
            self._condition.notify_all()

    def _remove_waiting_locked(
        self,
        ticket: QueueTicket,
        status: str,
        terminal_ns: int,
    ) -> None:
        self._waiting.remove(ticket)
        self._queued_bytes -= ticket._request_bytes
        ticket._status = status
        ticket._terminal_ns = terminal_ns

    def _require_owned_ticket(self, ticket: QueueTicket) -> None:
        if not isinstance(ticket, QueueTicket) or ticket._owner is not self:
            raise ValueError("Queue ticket does not belong to this inference queue.")
