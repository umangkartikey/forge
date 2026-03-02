import threading
import requests
import time

class P2PWorker:
    def __init__(self, bandit, peers, modules):
        self.bandit = bandit
        self.peers = peers  # list of peer URLs
        self.modules = modules
        self.feedback = FeedbackEngine()

    def gossip_loop(self, interval=10):
        while True:
            for peer in self.peers:
                try:
                    resp = requests.post(f"{peer}/state", json={
                        "counts": self.bandit.counts,
                        "values": self.bandit.values
                    }, timeout=3)
                    peer_state = resp.json()
                    self.bandit.merge(peer_state["counts"], peer_state["values"])
                except:
                    pass
            time.sleep(interval)
