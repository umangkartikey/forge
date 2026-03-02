import threading
import time
import requests
from forge.learning.feedback import FeedbackEngine
from forge.core.plugin_loader import load_modules
from forge.swarm.p2p_intelligence import P2PBandit
from fastapi import FastAPI
from pydantic import BaseModel
import uvicorn

# -------------------------------
# Configuration
# -------------------------------
TARGET = "127.0.0.1"     # replace with lab-safe target
CONTEXT = {}             # optional module context
PEERS = ["http://peer1:8000", "http://peer2:8000"]  # list of peer URLs
GOSSIP_INTERVAL = 10      # seconds

# -------------------------------
# Initialize engines
# -------------------------------
feedback = FeedbackEngine()
bandit = P2PBandit()
modules = load_modules()
module_names = list(modules.keys())

# -------------------------------
# FastAPI server for gossip
# -------------------------------
app = FastAPI()

class StateRequest(BaseModel):
    counts: dict
    values: dict

@app.post("/state")
def receive_state(req: StateRequest):
    bandit.merge(req.counts, req.values)
    return {"status": "merged"}

def run_server():
    uvicorn.run(app, host="0.0.0.0", port=8000)

# -------------------------------
# Gossip loop (periodic sync with peers)
# -------------------------------
def gossip_loop():
    while True:
        for peer in PEERS:
            try:
                resp = requests.post(f"{peer}/state", json={
                    "counts": bandit.counts,
                    "values": bandit.values
                }, timeout=3)
                peer_state = resp.json()
            except Exception as e:
                print(f"Failed to gossip with {peer}: {e}")
        time.sleep(GOSSIP_INTERVAL)

# -------------------------------
# Worker execution loop
# -------------------------------
def worker_loop():
    while True:
        selected_name = bandit.select(module_names)
        module = modules[selected_name]

        result = module.run(TARGET, CONTEXT)
        reward = feedback.evaluate(result)
        bandit.update(selected_name, reward)

        print(f"[{selected_name}] Reward: {reward:.2f} | Result: {result}")
        time.sleep(1)  # small delay to avoid spamming

# -------------------------------
# Start threads
# -------------------------------
if __name__ == "__main__":
    # Start FastAPI server in background
    threading.Thread(target=run_server, daemon=True).start()
    
    # Start gossip loop in background
    threading.Thread(target=gossip_loop, daemon=True).start()
    
    # Start main worker loop
    worker_loop()