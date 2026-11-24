# verity/registry.py  (Dev1)
import os


def load_impl(name=None):
    name = name or os.environ.get("VERITY_IMPL", "stub")
    if name == "stub":
        from . import repair_stub as repair
        from .strategy_stub import Strategy
    elif name == "real":
        from . import repair
        from .strategy import Strategy
    elif name == "baseline":
        from . import repair
        from .strategy_baseline import Strategy
    else:
        raise ValueError(name)
    return Strategy, repair
