import heapq

class Simulation:
    def __init__(self,abilities):
        self.queue = []
        self.current_time = 0.0
        self.ability_db = self.build_ability_db(abilities)

    def build_ability_db(self, abilities):
        ability_db = {
            key.lower().replace(" ", "_"): val
            for key, val in abilities.items()
        }
        return ability_db
    def schedule_relative(self, delay, event):
        heapq.heappush(self.queue, (self.current_time + delay, event))

    def schedule_absolute(self, absolute_time, event):
        heapq.heappush(self.queue, (absolute_time, event))

    def run_timed(self, duration = 300.0): #starting with timed because it will be better for early testing.
        while self.queue:
            timestamp, event = heapq.heappop(self.queue)
            if timestamp > duration:
                break
            self.current_time = timestamp
            event.resolve(self)

    def run_prio(self, priority, event):
        heapq.heappush(self.queue, (priority, event))