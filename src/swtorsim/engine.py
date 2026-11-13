"""Discrete-event simulation clock and priority queue manager."""

import heapq
from src.swtorsim.metrics import Metrics
from src.swtorsim.triggers import TriggerManager

def sim_log(sim, message: str, timestamp: float | None = None) -> None:
    """Verbose console line stamped with fight-relative time (works with lightweight test sims)."""
    if sim is None or not getattr(sim, "verbose", True):
        return
    if hasattr(sim, "log"):
        sim.log(message, timestamp)
        return
    t = getattr(sim, "current_time", 0.0) if timestamp is None else timestamp
    print(f"[{t:.2f}s] {message}")


class Simulation:
    """Manages the event queue and core combat timeline."""

    _PRE_COMBAT_HARD_CAP: float = 600.0

    def __init__(
        self,
        in_flashpoint_operation: bool | None = None,
        verbose: bool = True,
        seed: int | None = None,
        tracer=None,
    ):
        self.queue = []
        self.current_time = 0.0
        self.combat_start_time = None
        self.pre_combat_runner = None
        self.pre_combat_end_time = None
        self._pending_log: list[tuple[float, str]] = []
        self.event_counter = 0
        self.seed = seed
        self.tracer = tracer
        # True while prepare_simulation applies the character's load-time passives and buffs: effects applied then
        # scale with the Alacrity stat only, anything applied later uses total Alacrity.
        self.loading = False
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

    def time_origin(self) -> float:
        """Raw sim time shown as 0.00: first damage, else pre-combat end, else 0."""
        if self.combat_start_time is not None:
            return self.combat_start_time
        return self.pre_combat_end_time or 0.0

    def relative_time(self, timestamp: float | None = None) -> float:
        """Converts a raw sim timestamp to fight-relative time (pre-combat is negative)."""
        t = self.current_time if timestamp is None else timestamp
        return t - self.time_origin()

    def log(self, message: str, timestamp: float | None = None) -> None:
        """Prints a verbose line stamped relative to T0 (first damage).

        Before the first damage T0 is unknown, so lines are buffered and printed with their
        (negative) relative times once combat starts or the run ends.
        """
        if not self.verbose:
            return
        t = self.current_time if timestamp is None else timestamp
        if self.combat_start_time is None:
            self._pending_log.append((t, message))
            return
        self.flush_log()
        print(f"[{t - self.combat_start_time:.2f}s] {message}")

    def flush_log(self) -> None:
        """Prints buffered pre-combat lines relative to the current time origin."""
        if not self._pending_log:
            return
        origin = self.time_origin()
        for t, message in self._pending_log:
            print(f"[{t - origin:.2f}s] {message}")
        self._pending_log.clear()

    def get_combat_duration(self) -> float:
        """Returns elapsed combat duration (seconds) since the first damage landed."""
        if self.combat_start_time is None:
            return 0.0
        return max(0.0, self.current_time - self.combat_start_time)

    def _stop_time(self, duration: float) -> float | None:
        """Fight end time: ``duration`` after the first damage; pre-combat time never counts.

        Before combat starts: unbounded while a pre-combat runner is active (hard-capped at
        ``_PRE_COMBAT_HARD_CAP + duration`` as a deadlock guard), else ``duration`` after the
        pre-combat phase ended (``duration`` when there was none).
        """
        if self.combat_start_time is not None:
            return self.combat_start_time + duration
        if getattr(self, "pre_combat_runner", None) is not None and self.pre_combat_runner.active:
            return self._PRE_COMBAT_HARD_CAP + duration
        return (self.pre_combat_end_time or 0.0) + duration

    def run_until(self, absolute_time: float, target=None):
        """Resolves events up to ``absolute_time`` on the raw simulation clock (no finalization)."""
        while self.queue and self.queue[0][0] <= absolute_time:
            timestamp, seq, event = heapq.heappop(self.queue)
            self.current_time = timestamp
            event.resolve(self)
            if target is not None and getattr(target, "hp", 1) <= 0:
                break

    def run_timed(self, duration=300.0, target=None):
        """Pops and resolves events in chronological order until ``duration`` of combat is reached or ``target.hp <= 0``."""
        while self.queue:
            stop_time = self._stop_time(duration)
            if stop_time is not None and self.queue[0][0] > stop_time:
                break
            timestamp, seq, event = heapq.heappop(self.queue)
            self.current_time = timestamp
            event.resolve(self)
            if target is not None and getattr(target, "hp", 1) <= 0:
                self.log("Rip dummy.", timestamp)
                break
        self.flush_log()
        if hasattr(self, "tracker") and hasattr(self.tracker, "finalize_stalls"):
            self.tracker.finalize_stalls(self.current_time)
        if getattr(self, "tracer", None) is not None:
            self.tracer.finalize(
                self.current_time,
                metrics=getattr(self, "tracker", None),
                pre_combat_end=self.pre_combat_end_time,
            )
