import heapq
from src.swtorsim.metrics import Metrics

class Simulation:
    """Manages the event queue and core combat timeline."""
    def __init__(self):
        self.queue = []
        self.current_time = 0.0
        self.event_counter = 0
        self.tracker = Metrics()

    def schedule_relative(self, delay, event):
        self.event_counter += 1
        heapq.heappush(self.queue, (self.current_time + delay, self.event_counter, event))

    def schedule_absolute(self, absolute_time, event):
        self.event_counter += 1
        heapq.heappush(self.queue, (absolute_time,self.event_counter, event))

    def run_timed(self, duration=300.0, target=None):
        while self.queue:
            timestamp, seq, event = heapq.heappop(self.queue)
            if timestamp > duration:
                break
            self.current_time = timestamp
            event.resolve(self)
            if target.hp <= 0:
                print(f"\n[{timestamp:.2f}s] Rip dummy.")
                break
