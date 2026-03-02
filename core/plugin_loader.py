import os
import importlib
import inspect
from forge.core.module_base import ForgeModule

def load_modules():
    modules = {}
    module_path = "forge.modules"

    base_dir = os.path.dirname(__file__)
    modules_dir = os.path.join(os.path.dirname(base_dir), "modules")

    for file in os.listdir(modules_dir):
        if file.endswith(".py") and not file.startswith("_"):
            module_name = file[:-3]
            full_path = f"{module_path}.{module_name}"

            mod = importlib.import_module(full_path)

            for name, obj in inspect.getmembers(mod):
                if inspect.isclass(obj) and issubclass(obj, ForgeModule) and obj != ForgeModule:
                    instance = obj()
                    modules[instance.name] = instance

    return modules