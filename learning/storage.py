import sqlite3
import json

class LearningStorage:
    def __init__(self, db_path="forge_learning.db"):
        self.conn = sqlite3.connect(db_path)
        self._init_table()

    def _init_table(self):
        self.conn.execute("""
        CREATE TABLE IF NOT EXISTS module_stats (
            name TEXT PRIMARY KEY,
            count INTEGER,
            value REAL
        )
        """)

    def save(self, bandit):
        for module, count in bandit.counts.items():
            value = bandit.values[module]
            self.conn.execute(
                "REPLACE INTO module_stats (name, count, value) VALUES (?, ?, ?)",
                (module, count, value)
            )
        self.conn.commit()

    def load(self, bandit):
        cursor = self.conn.execute("SELECT name, count, value FROM module_stats")
        for name, count, value in cursor.fetchall():
            bandit.counts[name] = count
            bandit.values[name] = value