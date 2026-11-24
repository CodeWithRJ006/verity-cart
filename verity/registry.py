# verity/registry.py  (Dev1)
import os


def load_impl(name=None):
    name = name or os.environ.get("VERITY_IMPL", "stub")
    if name == "stub":
        from .strategy_stub import Strategy
        from . import repair_stub as repair
    elif name == "real":
        from .strategy import Strategy
        from . import repair
    elif name == "baseline":
        from .strategy_baseline import Strategy
        from . import repair
    else:
        raise ValueError(name)
    return Strategy, repair
