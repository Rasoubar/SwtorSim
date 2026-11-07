"""Discrete-event simulation clock and priority queue manager."""

import heapq
from src.swtorsim.metrics import Metrics
from src.swtorsim.triggers import TriggerManager

class Simulation:
    """Manages the event queue and core combat timeline."""
    def __init__(
        self,
        in_flashpoint_operation: bool | None = None,
        verbose: bool = True,
        seed: int | None = None,
    ):
        self.queue = []
        self.current_time = 0.0
        self.event_counter = 0
        self.seed = seed
        self.tracker = Metrics()
        self.tracker.seed = seed
        self.triggers = TriggerManager()
        self.verbose = verbose
        from src.swtorsim.settings import is_in_flashpoint_operation
        self.in_flashpoint_operation = (
            bool(in_flashpoint_operation)
            if in_flashpoint_operation is not None
            else is_in_flashpoint_operation()
        )

    def schedule_relative(self, delay, event):
        """Schedules an event to resolve at ``current_time + delay`` seconds."""
        self.event_counter += 1
        heapq.heappush(self.queue, (self.current_time + delay, self.event_counter, event))

    def schedule_absolute(self, absolute_time, event):
        """Schedules an event to resolve at ``absolute_time`` seconds on the simulation clock."""
        self.event_counter += 1
        heapq.heappush(self.queue, (absolute_time,self.event_counter, event))

    def run_timed(self, duration=300.0, target=None):
        """Pops and resolves events in chronological order until ``duration`` is reached or ``target.hp <= 0``."""
        while self.queue:
            if self.queue[0][0] > duration:
                break
            timestamp, seq, event = heapq.heappop(self.queue)
            self.current_time = timestamp
            event.resolve(self)
            if target is not None and getattr(target, "hp", 1) <= 0:
                if self.verbose:
                    print(f"\n[{timestamp:.2f}s] Rip dummy.")
                break
        if hasattr(self, "tracker") and hasattr(self.tracker, "finalize_stalls"):
            self.tracker.finalize_stalls(self.current_time)
