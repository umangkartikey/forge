import random
import math

class P2PBandit:
    def __init__(self):
        self.counts = {}  # module: count
        self.values = {}  # module: avg reward

    def select(self, modules):
        # Ensure exploration
        for m in modules:
            if m not in self.counts or self.counts[m] == 0:
                return m

        total = sum(self.counts[m] for m in modules)
        ucb_scores = {}
        for m in modules:
            bonus = math.sqrt((2 * math.log(total)) / self.counts[m])
            ucb_scores[m] = self.values[m] + bonus
        return max(ucb_scores, key=ucb_scores.get)

    def update(self, module, reward):
        n = self.counts.get(module, 0) + 1
        val = self.values.get(module, 0.0)
        self.counts[module] = n
        self.values[module] = ((n - 1)/n) * val + (1/n) * reward

    def merge(self, other_counts, other_values):
        """Merge another node's bandit state"""
        for m, c in other_counts.items():
            v = other_values.get(m, 0.0)
            if m in self.counts:
                total_count = self.counts[m] + c
                combined_value = (
                    (self.counts[m] * self.values[m] + c * v) / total_count
                )
                self.counts[m] = total_count
                self.values[m] = combined_value
            else:
                self.counts[m] = c
                self.values[m] = v