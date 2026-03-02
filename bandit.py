import random
import math
from collections import defaultdict

class AdaptiveBandit:
    def __init__(self):
        self.counts = defaultdict(int)     # number of times module used
        self.values = defaultdict(float)   # average reward

    def select(self, modules):
        """
        Select module using UCB1 (Upper Confidence Bound)
        """
        total_counts = sum(self.counts[m] for m in modules)

        # Ensure each module is tried at least once
        for m in modules:
            if self.counts[m] == 0:
                return m

        ucb_scores = {}
        for m in modules:
            bonus = math.sqrt((2 * math.log(total_counts)) / self.counts[m])
            ucb_scores[m] = self.values[m] + bonus

        return max(ucb_scores, key=ucb_scores.get)

    def update(self, module, reward):
        """
        Reward should be between 0 and 1
        """
        self.counts[module] += 1
        n = self.counts[module]
        value = self.values[module]

        # incremental average
        self.values[module] = ((n - 1) / n) * value + (1 / n) * reward
