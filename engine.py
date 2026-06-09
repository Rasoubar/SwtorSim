import heapq

class Simulation:
    def __init__(self):
        self.queue = []
        self.current_time = 0.0

    def schedule_relative(self, delay, event):
        heapq.heappush(self.queue, (self.current_time + delay, event))

    def schedule_absolute(self, absolute_time, event):
        heapq.heappush(self.queue, (absolute_time, event))

    def run_timed(self, duration = 300.0): #starting with timed because it will be better for early testing. Nevermind, didn't use this for testing at all.
        while self.queue:
            timestamp, event = heapq.heappop(self.queue)
            if timestamp > duration:
                break
            self.current_time = timestamp
            event.resolve(self)
