"""Dev1 stand-in strategy double. Invariant: decisions in [F, L]; accept iff bid_valid_as_made."""
from .contracts import Action, Decision, Mode, View


class Strategy:
    def __init__(self, cfg=None):
        self.cfg = cfg

    def decide(self, v: View) -> Decision:
        if v.L <= 0:
            return Decision(Action.WALK_AWAY, reason="empty")
        fr = v.F / v.L
        ratio = 1.0 - (1.0 - fr) * (min(v.round - 1, 6) / 6.0) if v.round <= 7 else fr
        target = max(v.F, min(v.L, int(round(ratio * v.L))))
        b = v.bids[-1] if v.bids else -1.0
        if v.round >= 10:
            if v.bid_valid_as_made and b >= fr:
                return Decision(Action.ACCEPT, reason="r10_accept")
            return Decision(Action.COUNTER, total=v.F, mode=Mode.AT_MOST, reason="r10_floor", ratio=fr)
        if v.bid_valid_as_made and b >= ratio:
            return Decision(Action.ACCEPT, reason="accept_target")
        return Decision(Action.COUNTER, total=target, mode=Mode.AT_MOST, reason="counter", ratio=ratio)
