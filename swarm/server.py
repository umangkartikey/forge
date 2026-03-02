from fastapi import FastAPI
from pydantic import BaseModel
import math
import threading

app = FastAPI()

lock = threading.Lock()
stats = {}  # {module: {"count": int, "value": float}}

class UpdateRequest(BaseModel):
    module: str
    reward: float

class SelectRequest(BaseModel):
    modules: list[str]

@app.post("/select")
def select_module(req: SelectRequest):
    with lock:
        for m in req.modules:
            if m not in stats:
                stats[m] = {"count": 0, "value": 0.0}

        total = sum(stats[m]["count"] for m in req.modules)

        for m in req.modules:
            if stats[m]["count"] == 0:
                return {"module": m}

        ucb_scores = {}
        for m in req.modules:
            count = stats[m]["count"]
            value = stats[m]["value"]
            bonus = math.sqrt((2 * math.log(total)) / count)
            ucb_scores[m] = value + bonus

        selected = max(ucb_scores, key=ucb_scores.get)
        return {"module": selected}

@app.post("/update")
def update_module(req: UpdateRequest):
    with lock:
        if req.module not in stats:
            stats[req.module] = {"count": 0, "value": 0.0}

        count = stats[req.module]["count"] + 1
        value = stats[req.module]["value"]

        new_value = ((count - 1) / count) * value + (1 / count) * req.reward

        stats[req.module] = {"count": count, "value": new_value}

        return {"status": "updated"}
