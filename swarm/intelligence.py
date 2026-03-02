import sqlite3
import threading
import math

class SwarmIntelligence:
    def __init__(self, db_path="swarm.db"):
        self.lock = threading.Lock()
        self.conn = sqlite3.connect(db_path, check_same_thread=False)
        self._init_table()

    def _init_table(self):
        self.conn.execute("""
        CREATE TABLE IF NOT EXISTS module_stats (
            name TEXT PRIMARY KEY,
            count INTEGER,
            value REAL
        )
        """)
        self.conn.commit()

    def select(self, modules):
        with self.lock:
            stats = self._load_stats(modules)

            total = sum(stats[m]["count"] for m in modules)

            for m in modules:
                if stats[m]["count"] == 0:
                    return m

            ucb_scores = {}
            for m in modules:
                count = stats[m]["count"]
                value = stats[m]["value"]
                bonus = math.sqrt((2 * math.log(total)) / count)
                ucb_scores[m] = value + bonus

            return max(ucb_scores, key=ucb_scores.get)

    def update(self, module, reward):
        with self.lock:
            cursor = self.conn.execute(
                "SELECT count, value FROM module_stats WHERE name=?",
                (module,)
            )
            row = cursor.fetchone()

            if row:
                count, value = row
            else:
                count, value = 0, 0.0

            count += 1
            value = ((count - 1) / count) * value + (1 / count) * reward

            self.conn.execute(
                "REPLACE INTO module_stats (name, count, value) VALUES (?, ?, ?)",
                (module, count, value)
            )
            self.conn.commit()

    def _load_stats(self, modules):
        stats = {}
        for m in modules:
            cursor = self.conn.execute(
                "SELECT count, value FROM module_stats WHERE name=?",
                (m,)
            )
            row = cursor.fetchone()
            if row:
                stats[m] = {"count": row[0], "value": row[1]}
            else:
                stats[m] = {"count": 0, "value": 0.0}
        return stats
