"""FAMILY_SPLIT=TRAIN|TEST keeps MODULE order (scenario order depends on BUYERS key order)."""
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SPLIT = json.loads((ROOT / "arena" / "family_split.json").read_text())["split"]


def buyer_names(split):
    env = dict(os.environ)
    env.pop("FAMILY_SPLIT", None)
    env.pop("FAMILY_ONLY", None)
    env.pop("FAMILY_ATTACK", None)
    if split:
        env["FAMILY_SPLIT"] = split
    code = "import sys; sys.path.insert(0, 'kit'); sys.path.insert(0, '.'); from arena import family; print(','.join(family.BUYERS))"
    p = subprocess.run([sys.executable, "-c", code], cwd=str(ROOT), env=env, capture_output=True, text=True)
    assert p.returncode == 0, p.stderr[-400:]
    return p.stdout.strip().split(",")


def test_split_filters_and_keeps_module_order():
    full = buyer_names(None)
    train, test = buyer_names("TRAIN"), buyer_names("TEST")
    assert len(full) == 20 and len(train) == 12 and len(test) == 8
    assert set(train) == set(SPLIT["TRAIN"]) and set(test) == set(SPLIT["TEST"])
    assert train == [n for n in full if n in set(train)]          # module order, not JSON order
    assert test == [n for n in full if n in set(test)]
    assert not set(train) & set(test)
