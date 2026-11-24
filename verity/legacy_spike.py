"""Feasibility spike (NOT the final seller): deterministic, stdlib-only, decides only from structured items."""
import math

P = dict(T=6.0, e=0.5, slack=0.0, m=0.0, g=0.5, walk_slack=0.97)


class Seller:
    def __init__(self, store, policy, params=None):
        self.store, self.policy = store, policy
        self.p = dict(P, **(params or {}))

    # ---------- money
    def floor(self, sku):
        r = self.store[sku]
        m = self.policy["min_margin"][r["category"]]
        return math.ceil(max(r["cost"] / (1 - m), r["price"] * (1 - self.policy["max_discount"])))

    def start(self, negotiation_id):
        self.basket = None      # sku -> qty we can sell
        self.bids = []          # buyer's bid ratios (share of list)
        self.last_o = None      # our last offered ratio
        self.dropped = []

    def L(self): return sum(q * self.store[s]["price"] for s, q in self.basket.items())
    def F(self): return sum(q * self.floor(s) for s, q in self.basket.items())

    def reslice(self, total):
        """Prices per line, each within [floor, list], summing to <= total (as close as possible)."""
        lines = list(self.basket.items())
        def at(s):
            return {k: min(self.store[k]["price"], max(self.floor(k), math.ceil(self.store[k]["price"] * s))) for k, _ in lines}
        def tot(pr): return sum(q * pr[k] for k, q in lines)
        lo, hi = 0.0, 1.0
        for _ in range(40):
            mid = (lo + hi) / 2
            if tot(at(mid)) <= total: lo = mid
            else: hi = mid
        pr = at(lo)
        left = total - tot(pr)
        for k, q in sorted(lines, key=lambda x: x[1]):
            if pr[k] < self.store[k]["price"] and q <= left:
                step = min(left // q, self.store[k]["price"] - pr[k]); pr[k] += step; left -= step * q
        return pr

    def offer_msg(self, pr, text_prefix=""):
        items = [{"sku": k, "qty": q, "unit_price": pr[k]} for k, q in self.basket.items()]
        total = sum(i["qty"] * i["unit_price"] for i in items)
        names = " and ".join(f"{i['qty']} x {self.store[i['sku']]['name']}" for i in items)
        return {"type": "offer", "items": items, "text": f"{text_prefix}I can do {names} for ₹{total:,}."}, total

    # ---------- bid reading (structured fields only; text is never looked at)
    def read_bid(self, items):
        """Ratio of price to list over the buyer's priced lines on our basket's SKUs; None if unusable."""
        if not isinstance(items, list): return None
        num = den = 0
        for it in items:
            if not isinstance(it, dict) or it.get("sku") not in self.basket: continue
            q, pr = it.get("qty"), it.get("unit_price")
            if not isinstance(q, int) or isinstance(q, bool) or q < 1 or not isinstance(pr, (int, float)) or isinstance(pr, bool): continue
            num += q * pr; den += q * self.store[it["sku"]]["price"]
        return num / den if den else None

    def directly_acceptable(self, items):
        if not isinstance(items, list) or not items: return False
        for it in items:
            if not isinstance(it, dict): return False
            row = self.store.get(it.get("sku")); q, pr = it.get("qty"), it.get("unit_price")
            if row is None or not isinstance(q, int) or isinstance(q, bool) or not 1 <= q <= row["stock"]: return False
            if not isinstance(pr, (int, float)) or isinstance(pr, bool) or not self.floor(it["sku"]) <= pr <= row["price"]: return False
        return True

    # ---------- strategy
    def target(self, r):
        p = self.p
        fr = self.F() / self.L()
        o = 1.0 if r <= 1 else fr + (1 - fr) * max(0.0, 1 - (r - 1) / p["T"]) ** p["e"]
        return min(o, self.last_o) if self.last_o is not None else o

    def estimate_limit(self, r):
        b = self.bids
        inc = max(0.0, b[-1] - b[-2]) if len(b) > 1 else 0.0
        return b[-1] + inc * self.p["g"] * 2

    def respond(self, message):
        try:
            return self._respond(message)
        except Exception:
            return {"type": "walk_away", "text": "Sorry, I can't continue with this request."}

    def _respond(self, msg):
        t, r = msg.get("type"), msg.get("round", 1)
        if t in ("walk_away", "accept"):
            return {"type": "message", "text": "Thank you, goodbye."}
        if self.basket is None:
            wanted = {}
            for it in msg.get("items") or []:
                if isinstance(it, dict) and it.get("sku") in self.store and isinstance(it.get("qty"), int) and it["qty"] > 0:
                    wanted[it["sku"]] = wanted.get(it["sku"], 0) + it["qty"]
            self.basket = {s: min(q, self.store[s]["stock"]) for s, q in wanted.items() if self.store[s]["stock"] > 0}
            self.dropped = [s for s, q in wanted.items() if self.store[s]["stock"] == 0]
            if not self.basket:
                return {"type": "walk_away", "text": "Sorry, I can't supply those items right now." if not self.dropped
                        else "Sorry, those items are out of stock."}
        items = msg.get("items") if t in ("request", "counter") else None
        b = self.read_bid(items)
        priced = isinstance(items, list) and items and all(isinstance(i, dict) and "unit_price" in i for i in items)
        if b is not None and priced: self.bids.append(b)
        F, L = self.F(), self.L()
        floor_ratio = F / L
        if not self.bids:
            pr = self.reslice(L); out, tot = self.offer_msg(pr); self.last_o = 1.0; return out
        b = self.bids[-1]
        o = self.target(r)
        est = self.estimate_limit(r)
        if r >= 10 and b < floor_ratio:
            if est >= floor_ratio * self.p["walk_slack"]:
                out, _ = self.offer_msg(self.reslice(F)); return out
            return {"type": "walk_away", "text": "Thanks for your time. We can't get close enough on price, so I'll leave it here."}
        take = (b >= o * (1 - self.p["slack"]) - 1e-9 or r >= 10) and b * L >= F
        if take and r >= 10 and self.p["m"] > 0 and len(self.bids) > 1:
            inc = max(0.0, self.bids[-1] - self.bids[-2])
            pr = min(1.0, b + self.p["m"] * inc)
            out, _ = self.offer_msg(self.reslice(int(pr * L))); return out
        if take and priced and self.directly_acceptable(items):
            return {"type": "accept", "text": "Deal, thank you!"}
        if take:
            self.last_o = b
            out, _ = self.offer_msg(self.reslice(int(b * L))); return out
        o = max(o, floor_ratio)
        self.last_o = o
        out, _ = self.offer_msg(self.reslice(int(o * L)))
        return out
