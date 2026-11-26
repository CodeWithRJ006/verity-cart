# verity/config.py — owned by Dev2 after I0 bootstrap. Python 3.9 stdlib only.
from __future__ import annotations

from dataclasses import dataclass, fields
from typing import Any, Dict

# from_switches alias: r10_close_margin == 1 - walk_slack (one stored field).
_COMPLEMENT_KEY = "r10_close_margin"


@dataclass
class Config:
    # Spike defaults
    T: float = 6.0
    e: float = 0.5
    slack: float = 0.0
    m: float = 0.0
    g: float = 0.5
    # Round-10 close margin: ONE source of truth.
    # walk_slack and r10_close_margin are the same quantity
    # (r10_close_margin == 1 - walk_slack).  walk_slack is the stored field;
    # r10_close_margin is a read-only derived property, so the two can never
    # disagree.  from_switches accepts either spelling.
    walk_slack: float = 0.97
    # Framework extensions
    max_round: int = 10
    partial_bid_policy: str = "matched"
    echo_buyer_total: bool = True
    r10_require_rising: bool = False
    allocator: str = "proportional"
    accept_require_complete: bool = False

    @property
    def r10_close_margin(self) -> float:
        """Derived view of walk_slack (legacy_spike.py:183 uses walk_slack)."""
        return 1.0 - self.walk_slack

    def __post_init__(self) -> None:
        if self.partial_bid_policy not in {"matched", "ignore"}:
            raise ValueError(
                f"partial_bid_policy must be 'matched' or 'ignore', got {self.partial_bid_policy!r}"
            )
        if self.allocator not in {"proportional", "greedy"}:
            raise ValueError(
                f"allocator must be 'proportional' or 'greedy', got {self.allocator!r}"
            )

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
            if k == _COMPLEMENT_KEY:
                try:
                    kwargs[k] = float(v)
                except ValueError:
                    raise ValueError(f"Invalid float value for {k}: {v!r}") from None
                continue
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
        if _COMPLEMENT_KEY in kwargs:
            margin = kwargs.pop(_COMPLEMENT_KEY)
            walk = 1.0 - margin
            if "walk_slack" in kwargs and abs(kwargs["walk_slack"] - walk) > 1e-9:
                raise ValueError(
                    "walk_slack and r10_close_margin disagree: "
                    f"walk_slack={kwargs['walk_slack']!r} but "
                    f"1 - r10_close_margin={walk!r}"
                )
            kwargs["walk_slack"] = walk
        return cls(**kwargs)
