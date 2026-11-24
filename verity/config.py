# verity/config.py — owned by Dev2 after I0 bootstrap. Python 3.9 stdlib only.
from __future__ import annotations

from dataclasses import dataclass, fields
from typing import Any, Dict


@dataclass
class Config:
    # Spike defaults
    T: float = 6.0
    e: float = 0.5
    slack: float = 0.0
    m: float = 0.0
    g: float = 0.5
    walk_slack: float = 0.97
    # Framework extensions
    max_round: int = 10
    partial_bid_policy: str = "matched"
    r10_close_margin: float = 0.03
    echo_buyer_total: bool = True
    allocator: str = "proportional"

    @classmethod
    def from_switches(cls, s: str) -> Config:
        if not s or not s.strip():
            return cls()
        field_types: Dict[str, Any] = {f.name: f.type for f in fields(cls)}
        kwargs: Dict[str, Any] = {}
        for pair in s.split(","):
            pair = pair.strip()
            if not pair:
                continue
            if "=" not in pair:
                raise ValueError(f"Malformed switch (expected key=val): {pair!r}")
            k, _, v = pair.partition("=")
            k, v = k.strip(), v.strip()
            if k not in field_types:
                raise ValueError(f"Unknown config switch: {k!r}")
            ft = field_types[k]
            if ft is bool or ft == "bool":
                low = v.lower()
                if low in ("true", "1", "yes"):
                    kwargs[k] = True
                elif low in ("false", "0", "no"):
                    kwargs[k] = False
                else:
                    raise ValueError(f"Invalid boolean value for {k}: {v!r}")
            elif ft is int or ft == "int":
                kwargs[k] = int(v)
            elif ft is float or ft == "float":
                kwargs[k] = float(v)
            else:
                kwargs[k] = v
        return cls(**kwargs)
