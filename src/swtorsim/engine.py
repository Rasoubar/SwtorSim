import heapq
from .metrics import Metrics

class Simulation:
    def __init__(self,abilities):
        self.queue = []
        self.current_time = 0.0
        self.ability_db = self.build_ability_db(abilities)
        self.event_counter = 0
        self.tracker = Metrics()

    def build_ability_db(self, abilities):
        ability_db = {
            key.lower().replace(" ", "_"): val
            for key, val in abilities.items()
        }
        return ability_db

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
