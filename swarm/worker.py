import requests
from forge.learning.feedback import FeedbackEngine
from forge.core.plugin_loader import load_modules

SERVER_URL = "http://<controller-ip>:8000"

feedback = FeedbackEngine()
modules = load_modules()
module_names = list(modules.keys())

def select_module():
    response = requests.post(
        f"{SERVER_URL}/select",
        json={"modules": module_names}
    )
    return response.json()["module"]

def update_module(module, reward):
    requests.post(
        f"{SERVER_URL}/update",
        json={"module": module, "reward": reward}
    )

while True:
    selected = select_module()
    result = modules[selected].run(target, context)
    reward = feedback.evaluate(result)
    update_module(selected, reward)
