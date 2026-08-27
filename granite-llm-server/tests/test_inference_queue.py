from __future__ import annotations

import threading
import unittest

from app.inference_queue import (
    ADMITTED,
    CANCELLED,
    QUEUE_FULL,
    QUEUE_MEMORY_FULL,
    TIMED_OUT,
    WAITING,
    InferenceQueue,
)


class FakeClock:
    def __init__(self):
        self.now_ns = 0

    def __call__(self):
        return self.now_ns

    def advance_seconds(self, seconds):
        self.now_ns += round(seconds * 1_000_000_000)


def make_queue(
    *,
    max_active=1,
    max_waiting=4,
    max_bytes=1024,
    wait_seconds=30,
    clock=None,
):
    return InferenceQueue(
        max_active_requests=max_active,
        max_waiting_requests=max_waiting,
        max_queued_bytes=max_bytes,
        wait_timeout_seconds=wait_seconds,
        **({"clock_ns": clock} if clock is not None else {}),
    )


class InferenceQueueTests(unittest.TestCase):
    def test_configuration_rejects_invalid_limits(self):
        cases = (
            {"max_active_requests": 0},
            {"max_active_requests": True},
            {"max_waiting_requests": -1},
            {"max_queued_bytes": -1},
            {"wait_timeout_seconds": -0.1},
            {"wait_timeout_seconds": float("nan")},
            {"wait_timeout_seconds": "30"},
            {"clock_ns": None},
        )
        defaults = {
            "max_active_requests": 1,
            "max_waiting_requests": 4,
            "max_queued_bytes": 1024,
            "wait_timeout_seconds": 30,
        }

        for overrides in cases:
            with self.subTest(overrides=overrides), self.assertRaises(ValueError):
                InferenceQueue(**{**defaults, **overrides})

    def test_request_bytes_must_be_a_non_negative_integer(self):
        queue = make_queue()
        for value in (-1, True, 1.5, "1"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                queue.request_slot(value)

    def test_immediate_admission_and_release_are_bounded_and_idempotent(self):
        queue = make_queue()

        ticket = queue.request_slot(100)

        self.assertEqual(ticket.snapshot().status, ADMITTED)
        self.assertEqual(ticket.snapshot().initial_position, 0)
        self.assertEqual(ticket.snapshot().wait_ms, 0)
        self.assertEqual(ticket.snapshot().capacity, 4)
        self.assertEqual(queue.snapshot().active_requests, 1)
        self.assertTrue(ticket.release())
        self.assertFalse(ticket.release())
        self.assertEqual(queue.snapshot().active_requests, 0)
        self.assertTrue(ticket.snapshot().released)

    def test_waiting_tickets_are_admitted_in_fifo_order(self):
        queue = make_queue(max_waiting=3)
        active = queue.request_slot(10)
        waiting = [queue.request_slot(size) for size in (20, 30, 40)]

        self.assertEqual(
            [ticket.snapshot().initial_position for ticket in waiting],
            [1, 2, 3],
        )
        self.assertEqual(
            [ticket.snapshot().status for ticket in waiting],
            [WAITING, WAITING, WAITING],
        )

        for index, expected in enumerate(waiting):
            self.assertTrue(active.release())
            self.assertEqual(expected.snapshot().status, ADMITTED)
            for later in waiting[index + 1:]:
                self.assertEqual(later.snapshot().status, WAITING)
            active = expected

        self.assertTrue(active.release())
        self.assertEqual(queue.snapshot().active_requests, 0)

    def test_multiple_active_slots_still_preserve_fifo_order(self):
        queue = make_queue(max_active=2, max_waiting=3)
        active_one = queue.request_slot(1)
        active_two = queue.request_slot(1)
        waiting_one = queue.request_slot(1)
        waiting_two = queue.request_slot(1)
        waiting_three = queue.request_slot(1)

        active_two.release()
        self.assertEqual(waiting_one.snapshot().status, ADMITTED)
        self.assertEqual(waiting_two.snapshot().status, WAITING)
        active_one.release()
        self.assertEqual(waiting_two.snapshot().status, ADMITTED)
        self.assertEqual(waiting_three.snapshot().status, WAITING)
        waiting_one.release()
        self.assertEqual(waiting_three.snapshot().status, ADMITTED)

        waiting_two.release()
        waiting_three.release()
        self.assertEqual(queue.snapshot().active_requests, 0)

    def test_waiting_request_count_is_bounded(self):
        queue = make_queue(max_waiting=1)
        active = queue.request_slot(10)
        waiting = queue.request_slot(20)
        rejected = queue.request_slot(30)

        self.assertEqual(waiting.snapshot().status, WAITING)
        self.assertEqual(rejected.snapshot().status, QUEUE_FULL)
        self.assertIsNone(rejected.snapshot().initial_position)
        self.assertEqual(rejected.snapshot().depth_on_arrival, 1)
        self.assertEqual(rejected.snapshot().capacity, 1)
        self.assertEqual(queue.snapshot().waiting_requests, 1)

        active.release()
        waiting.release()

    def test_waiting_request_bytes_are_bounded_and_reclaimed(self):
        queue = make_queue(max_waiting=4, max_bytes=10)
        active = queue.request_slot(100)
        six_bytes = queue.request_slot(6)
        rejected = queue.request_slot(5)
        four_bytes = queue.request_slot(4)

        self.assertEqual(rejected.snapshot().status, QUEUE_MEMORY_FULL)
        self.assertEqual(rejected.snapshot().queued_bytes_on_arrival, 6)
        self.assertEqual(queue.snapshot().queued_bytes, 10)

        self.assertTrue(six_bytes.cancel())
        self.assertEqual(queue.snapshot().queued_bytes, 4)
        active.release()
        self.assertEqual(four_bytes.snapshot().status, ADMITTED)
        four_bytes.release()

    def test_zero_waiting_capacity_does_not_block_immediate_admission(self):
        queue = make_queue(max_waiting=0, max_bytes=0)
        active = queue.request_slot(10_000)
        rejected = queue.request_slot(0)

        self.assertEqual(active.snapshot().status, ADMITTED)
        self.assertEqual(rejected.snapshot().status, QUEUE_FULL)
        active.release()

    def test_zero_wait_timeout_rejects_only_when_a_wait_is_required(self):
        queue = make_queue(wait_seconds=0)
        active = queue.request_slot(1)
        timed_out = queue.request_slot(1)

        self.assertEqual(active.snapshot().status, ADMITTED)
        self.assertEqual(timed_out.snapshot().status, TIMED_OUT)
        self.assertEqual(timed_out.snapshot().wait_ms, 0)
        self.assertEqual(queue.snapshot().waiting_requests, 0)
        active.release()

    def test_polling_returns_waiting_without_resetting_the_deadline(self):
        clock = FakeClock()
        queue = make_queue(wait_seconds=5, clock=clock)
        active = queue.request_slot(1)
        waiting = queue.request_slot(1)

        self.assertEqual(waiting.wait(poll_seconds=0), WAITING)
        clock.advance_seconds(5)
        self.assertEqual(waiting.wait(poll_seconds=0), TIMED_OUT)
        self.assertEqual(waiting.snapshot().wait_ms, 5000)
        self.assertEqual(queue.snapshot().waiting_requests, 0)
        active.release()

    def test_wait_time_is_recorded_when_a_waiter_is_admitted(self):
        clock = FakeClock()
        queue = make_queue(wait_seconds=5, clock=clock)
        active = queue.request_slot(1)
        waiting = queue.request_slot(1)

        clock.advance_seconds(2.25)
        active.release()

        self.assertEqual(waiting.snapshot().status, ADMITTED)
        self.assertEqual(waiting.snapshot().wait_ms, 2250)
        waiting.release()

    def test_expired_tickets_do_not_consume_newly_released_capacity(self):
        clock = FakeClock()
        queue = make_queue(wait_seconds=5, clock=clock)
        active = queue.request_slot(1)
        first = queue.request_slot(2)
        second = queue.request_slot(3)

        clock.advance_seconds(6)
        active.release()

        self.assertEqual(first.snapshot().status, TIMED_OUT)
        self.assertEqual(second.snapshot().status, TIMED_OUT)
        self.assertEqual(queue.snapshot().active_requests, 0)
        self.assertEqual(queue.snapshot().queued_bytes, 0)

    def test_cancelling_a_waiter_is_idempotent_and_advances_the_queue(self):
        queue = make_queue()
        active = queue.request_slot(1)
        cancelled = queue.request_slot(2)
        next_ticket = queue.request_slot(3)

        self.assertTrue(cancelled.cancel())
        self.assertFalse(cancelled.cancel())
        self.assertEqual(cancelled.snapshot().status, CANCELLED)
        self.assertEqual(queue.snapshot().waiting_requests, 1)

        active.release()
        self.assertEqual(next_ticket.snapshot().status, ADMITTED)
        next_ticket.release()

    def test_admitted_and_rejected_tickets_cannot_be_cancelled(self):
        queue = make_queue(max_waiting=0)
        admitted = queue.request_slot(1)
        rejected = queue.request_slot(1)

        self.assertFalse(admitted.cancel())
        self.assertFalse(rejected.cancel())
        admitted.release()

    def test_rejected_or_waiting_tickets_cannot_release_capacity(self):
        queue = make_queue(max_waiting=1)
        active = queue.request_slot(1)
        waiting = queue.request_slot(1)
        rejected = queue.request_slot(1)

        self.assertFalse(waiting.release())
        self.assertFalse(rejected.release())
        self.assertEqual(queue.snapshot().active_requests, 1)
        active.release()
        waiting.release()

    def test_concurrent_waiters_complete_in_fifo_order(self):
        queue = make_queue(max_waiting=6)
        active = queue.request_slot(1)
        tickets = [queue.request_slot(1) for _ in range(6)]
        completion_order = []
        completion_lock = threading.Lock()
        worker_errors = []

        def consume(index, ticket):
            try:
                status = ticket.wait()
                with completion_lock:
                    if status != ADMITTED:
                        worker_errors.append(f"ticket {index}: {status}")
                    else:
                        completion_order.append(index)
            except Exception as error:  # pragma: no cover - asserted in parent
                with completion_lock:
                    worker_errors.append(f"ticket {index}: {type(error).__name__}")
            finally:
                ticket.release()

        threads = [
            threading.Thread(target=consume, args=(index, ticket))
            for index, ticket in enumerate(tickets)
        ]
        for thread in threads:
            thread.start()

        active.release()
        for thread in threads:
            thread.join(timeout=2)

        self.assertTrue(all(not thread.is_alive() for thread in threads))
        self.assertEqual(worker_errors, [])
        self.assertEqual(completion_order, list(range(6)))
        self.assertEqual(queue.snapshot().active_requests, 0)
        self.assertEqual(queue.snapshot().waiting_requests, 0)

    def test_invalid_clock_value_fails_closed(self):
        for value in (-1, True, 1.5):
            with self.subTest(value=value):
                queue = make_queue(clock=lambda: value)
                with self.assertRaisesRegex(RuntimeError, "clock"):
                    queue.request_slot(1)

    def test_poll_interval_must_be_a_non_negative_number(self):
        queue = make_queue()
        active = queue.request_slot(1)
        waiting = queue.request_slot(1)

        for value in (-1, True, "1"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                waiting.wait(poll_seconds=value)

        waiting.cancel()
        active.release()


if __name__ == "__main__":
    unittest.main()
