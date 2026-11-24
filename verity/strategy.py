# verity/strategy.py — owned by Dev2. Python 3.9, stdlib only.
from __future__ import annotations

from verity.config import Config
from verity.contracts import Action, Decision, Mode, View


class Strategy:
    """Pure decision logic: decide(view) -> Decision.

    Implements the spike's decision tree (legacy_spike.py:118-205) after the bid
    has been read.  Uses cfg fields instead of the spike's p dict.

    View fields used (contracts.py:43-50):
      view.round, view.L, view.F, view.bids, view.bid_complete,
      view.bid_valid_as_made, view.last_offer_ratio

    Decision fields returned (contracts.py:35-39):
      action, total, mode, reason, ratio
    """

    def __init__(self, cfg: Config) -> None:
        self._cfg = cfg
        # NotImplementedError guard: echo_buyer_total=False and r10_close_margin != 0.03
        # are the two unsupported spike deviations.  Raising here (not in decide) lets
        # the caller fail fast at construction time.
        if not cfg.echo_buyer_total:
            raise NotImplementedError("echo_buyer_total=False is not yet implemented")
        if cfg.r10_close_margin != 0.03:
            raise NotImplementedError(
                "r10_close_margin != 0.03 is not yet implemented "
                "(walk_slack is the operative field; changing r10_close_margin would "
                "silently disagree with walk_slack)"
            )

    # ------------------------------------------------------------------
    # spike helpers (legacy_spike.py:119-128)
    # ------------------------------------------------------------------

    def _target(self, r: int, fr: float, last_o: "float | None") -> float:
        """Spike's target() (legacy_spike.py:119-123)."""
        cfg = self._cfg
        # legacy_spike.py:122
        o = 1.0 if r <= 1 else fr + (1 - fr) * max(0.0, 1 - (r - 1) / cfg.T) ** cfg.e
        # legacy_spike.py:123
        return min(o, last_o) if last_o is not None else o

    def _estimate_limit(self, bids: "list[float]") -> float:
        """Spike's estimate_limit() (legacy_spike.py:125-128)."""
        # legacy_spike.py:127
        inc = max(0.0, bids[-1] - bids[-2]) if len(bids) > 1 else 0.0
        # legacy_spike.py:128
        return bids[-1] + inc * self._cfg.g * 2

    # ------------------------------------------------------------------
    # main decision
    # ------------------------------------------------------------------

    def decide(self, view: View) -> Decision:
        """Map View -> Decision following the spike's _respond logic.

        Spike reference: legacy_spike.py:136-205.
        View fields: contracts.py:43-50.
        Decision fields: contracts.py:35-39.
        """
        cfg = self._cfg
        F, L = view.F, view.L
        r = view.round
        R_MAX = cfg.max_round  # spike uses literal 10; cfg.max_round is the config equivalent

        # Degenerate basket guard (should not normally reach strategy)
        if L == 0:
            return Decision(action=Action.WALK_AWAY, reason="empty_basket")

        floor_ratio = F / L

        # --- no bids yet (legacy_spike.py:174-178) ---
        if not view.bids:
            # Offer at list price; ratio = 1.0 (legacy_spike.py:177)
            return Decision(
                action=Action.COUNTER,
                total=L,
                mode=Mode.AT_MOST,
                reason="no_bid",
                ratio=1.0,
            )

        b = view.bids[-1]  # most recent bid ratio (legacy_spike.py:179)
        # view.last_offer_ratio corresponds to spike's self.last_o (contracts.py:50)
        last_o = view.last_offer_ratio

        o = self._target(r, floor_ratio, last_o)  # legacy_spike.py:180
        est = self._estimate_limit(view.bids)      # legacy_spike.py:181

        # --- round-10 / R_MAX branch: bid still below floor (legacy_spike.py:182-189) ---
        if r >= R_MAX and b < floor_ratio:
            # walk_slack test (legacy_spike.py:183)
            if est >= floor_ratio * cfg.walk_slack:
                # Offer at floor — round-10 floor offer; ratio=None per spec
                # Clamp to [F, L]: total=F is already the minimum; harmless because
                # F <= L always holds by construction, so this is the tightest valid offer.
                return Decision(
                    action=Action.COUNTER,
                    total=F,
                    mode=Mode.AT_MOST,
                    reason="r10_floor",
                    ratio=None,  # per task spec: ratio=None for round-10 floor offer
                )
            return Decision(action=Action.WALK_AWAY, reason="r10_walk")

        # --- take? (legacy_spike.py:190) ---
        take = (b >= o * (1 - cfg.slack) - 1e-9 or r >= R_MAX) and b * L >= F

        # --- markup branch (legacy_spike.py:191-195): r>=R_MAX, m>0, len(bids)>1 ---
        if take and r >= R_MAX and cfg.m > 0 and len(view.bids) > 1:
            inc = max(0.0, view.bids[-1] - view.bids[-2])
            pr = min(1.0, b + cfg.m * inc)
            # Clamp COUNTER total to [F, L]: spike does int(pr * L); pr can round below F
            # or above L due to floating point.  Clamping is harmless because the final
            # offer is still within policy bounds and the buyer gets a valid price.
            total = max(F, min(L, int(pr * L)))
            return Decision(
                action=Action.COUNTER,
                total=total,
                mode=Mode.AT_MOST,
                reason="markup",
                ratio=pr,
            )

        # --- accept branch (legacy_spike.py:196-201) ---
        if take:
            # ACCEPT iff bid_valid_as_made and (bid_complete or not accept_require_complete)
            if view.bid_valid_as_made and (view.bid_complete or not cfg.accept_require_complete):
                return Decision(action=Action.ACCEPT, reason="take_accept", ratio=b)
            # Echo buyer's total (echo branch) — ratio = b (spike's last_o = b, line 199)
            # Clamp to [F, L]: int(b * L) could be slightly below F due to float; harmless.
            total = max(F, min(L, int(b * L)))
            return Decision(
                action=Action.COUNTER,
                total=total,
                mode=Mode.EXACT,
                reason="take_echo",
                ratio=b,
            )

        # --- counter branch (legacy_spike.py:202-204) ---
        o = max(o, floor_ratio)   # legacy_spike.py:202
        # Clamp to [F, L]: int(o * L) could be slightly below F or above L due to float; harmless.
        total = max(F, min(L, int(o * L)))
        return Decision(
            action=Action.COUNTER,
            total=total,
            mode=Mode.AT_MOST,
            reason="counter",
            ratio=o,  # spike stores this as self.last_o (legacy_spike.py:203)
        )
