"""Statistics + markdown rendering for arena results. stdlib only, deterministic (seeded bootstrap)."""

import random
import statistics


def mean(xs):
    xs = list(xs)
    return statistics.mean(xs) if xs else 0.0


def paired_bootstrap(a, b, n_boot=5000, seed=12345):
    """a, b: {key: score}. Returns (mean diff b-a, lo95, hi95) resampling shared keys with a seeded RNG."""
    keys = sorted(set(a) & set(b))
    if not keys:
        return 0.0, 0.0, 0.0
    d = [b[k] - a[k] for k in keys]
    rng, n = random.Random(seed), len(d)
    means = sorted(sum(d[rng.randrange(n)] for _ in range(n)) / n for _ in range(n_boot))
    return mean(d), means[int(0.025 * n_boot)], means[int(0.975 * n_boot) - 1]


def pooled(res):
    """Headline metrics of one results dict: per-seed values averaged; violations/deadlocks summed."""
    ps = list(res["per_seed"].values())

    def m(k):
        return mean(p[k] for p in ps)

    return {
        "score": m("score"),
        "deal_rate": m("deal_rate"),
        "vpn": m("value_per_negotiation"),
        "vpd": m("value_among_deals"),
        "margin": m("margin_kept"),
        "policy": sum(p["policy"] for p in ps),
        "truth": sum(p["truth"] for p in ps),
        "deadlocks": sum(p["deadlocks"] for p in ps),
    }


def seed_table(res):
    out = [
        "| seed | score | deal rate | value/neg | value/deal | margin | policy | truth | deadlocks |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for s, p in res["per_seed"].items():
        out.append(
            "| %s | %.1f | %.3f | %.3f | %.3f | %.3f | %d | %d | %d |"
            % (
                s,
                p["score"],
                p["deal_rate"],
                p["value_per_negotiation"],
                p["value_among_deals"],
                p["margin_kept"],
                p["policy"],
                p["truth"],
                p["deadlocks"],
            )
        )
    return "\n".join(out)


def ladder_markdown(rows, base="A", title="Ablation ladder"):
    """rows: [(name, description, results-or-None, error-or-None)]. CI = paired bootstrap over negotiations."""
    by = {n: r for n, _, r, _ in rows if r}
    out = [
        "# " + title,
        "",
        "Score = mean over seeds. \u0394 vs %s = paired difference with bootstrap 95%% CI over negotiations "
        "pooled across seeds (5000 resamples, fixed RNG seed)." % base,
        "",
        "| row | variant | score | \u0394 vs %s [95%% CI] | deal rate | value/neg | value/deal | margin | policy | truth | deadlocks |"
        % base,
        "|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for name, desc, res, err in rows:
        if not res:
            out.append("| %s | %s | unavailable: %s |||||||||" % (name, desc, (err or "")[-160:].replace("|", "/")))
            continue
        p = pooled(res)
        if name == base or base not in by:
            delta = "\u2014"
        else:
            d, lo, hi = paired_bootstrap(by[base]["per_negotiation"], res["per_negotiation"])
            delta = "%+.2f [%+.2f, %+.2f]" % (d, lo, hi)
        out.append(
            "| %s | %s | %.1f | %s | %.3f | %.3f | %.3f | %.3f | %d | %d | %d |"
            % (
                name,
                desc,
                p["score"],
                delta,
                p["deal_rate"],
                p["vpn"],
                p["vpd"],
                p["margin"],
                p["policy"],
                p["truth"],
                p["deadlocks"],
            )
        )
    out += ["", "## Per-buyer score (mean over seeds)", ""]
    names = sorted({b for r in by.values() for p in r["per_seed"].values() for b in p["by_buyer"]})
    out += ["| row | " + " | ".join(names) + " |", "|---|" + "---|" * len(names)]
    for name, _, res, _ in rows:
        if res:
            cells = []
            for b in names:
                v = [p["by_buyer"][b] for p in res["per_seed"].values() if b in p["by_buyer"]]
                cells.append("%.1f" % mean(v) if v else "\u2014")
            out.append("| %s | %s |" % (name, " | ".join(cells)))
    return "\n".join(out) + "\n"
