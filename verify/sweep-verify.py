#!/usr/bin/env python3
"""Cross-check the BIP-352 tweak series in this repo against two independent
implementations.

  reference : the BIP-352 reference implementation vendored unmodified from
              the bip-0352/ directory of github.com/bitcoin/bips, driven over
              Bitcoin Core's REST interface by verify_block_lib.py. Shares no
              code with any indexer.
  blindbit  : BlindBit Oracle v2 (Go), GET http://127.0.0.1:8010/tweaks/{height}

For every swept height the driver compares:
  1. the block hash BlindBit says it indexed against Core's block hash,
  2. the tweak count,
  3. the tweak list as an ordered sequence,
  4. the tweak list as a multiset.

On any disagreement the block is recomputed a second time with txid
attribution, so the offending transactions are named rather than summarised.

    python3 sweep-verify.py --plan                 print the height plan only
    python3 sweep-verify.py --run  [--workers 4]   run the sweep
    python3 sweep-verify.py --run 800000 800010    run an explicit height list

Requires: a fully synced Bitcoin Core with -rest=1 on 127.0.0.1:8332 and a
BlindBit Oracle v2 on 127.0.0.1:8010.
"""
import argparse
import concurrent.futures
import csv
import hashlib
import json
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import verify_block_lib  # noqa: E402
from bitcoin_utils import COutPoint, CTxInWitness, deser_txid, is_p2tr  # noqa: E402
from reference import get_input_hash, get_pubkey_from_input, VinInfo  # noqa: E402

BLINDBIT = "http://127.0.0.1:8010"


def digest(tweaks):
    """sha256 over the newline-joined tweak list, as given."""
    return hashlib.sha256("\n".join(tweaks).encode()).hexdigest()

ORACLE_CSV = HERE.parent / "oracle.csv"

RANGE_LO = 709656
RANGE_HI = 965089


# --------------------------------------------------------------------------
# height plan


def load_csv():
    rows = []
    with open(ORACLE_CSV) as f:
        for r in csv.DictReader(f):
            rows.append((int(r["height"]), int(r["tweaks"])))
    return rows


def select_heights():
    """Deterministic height plan. Returns (sorted_heights, strata_dict)."""
    rows = load_csv()
    by_h = dict(rows)
    strata = {}

    # A. uniform coverage of the whole measured range
    n = 400
    strata["A_uniform_400"] = sorted({
        RANGE_LO + round(i * (RANGE_HI - RANGE_LO) / (n - 1)) for i in range(n)
    })
    # B. the first heights of the range, where eligible transactions are rare
    strata["B_first_40"] = list(range(RANGE_LO, RANGE_LO + 40))
    # C. the most recent heights of the measured range
    strata["C_last_40"] = list(range(RANGE_HI - 39, RANGE_HI + 1))
    # D. the 20 densest blocks in oracle.csv, whole range
    strata["D_densest_20_all"] = sorted(
        h for h, _ in sorted(rows, key=lambda r: (-r[1], r[0]))[:20]
    )
    # E. the 20 densest blocks of the inscription era, 800000 to 850000
    era = [r for r in rows if 800000 <= r[0] <= 850000]
    strata["E_densest_20_inscription_era"] = sorted(
        h for h, _ in sorted(era, key=lambda r: (-r[1], r[0]))[:20]
    )
    # F. 20 blocks that oracle.csv records as having zero eligible transactions
    zeros = [h for h, t in rows if t == 0]
    strata["F_zero_tweak_20"] = sorted({
        zeros[round(i * (len(zeros) - 1) / 19)] for i in range(20)
    })

    heights = sorted({h for s in strata.values() for h in s})
    return heights, strata, by_h


# --------------------------------------------------------------------------
# sources


def get_blindbit(height, timeout=180):
    with urllib.request.urlopen(f"{BLINDBIT}/tweaks/{height}", timeout=timeout) as resp:
        body = json.load(resp)
    if isinstance(body, dict):
        bh = body.get("block_identifier", {}).get("block_hash", "")
        idx = body.get("index", [])
    else:
        bh, idx = None, body
    tweaks = [(t if isinstance(t, str) else t.get("tweak", "")).lower() for t in idx]
    return bh, tweaks


def tweaks_with_txids(height):
    """Same computation as verify_block_lib.tweaks_for_block, carrying the txid
    of the transaction each tweak came from. Only called to attribute a
    disagreement; the headline comparison always uses the unmodified
    verify_block_lib."""
    blockhash = verify_block_lib.blockhash_for_height(height)
    block = verify_block_lib.rest_json(f"block/{blockhash}.json")
    out = []
    for tx in block["tx"]:
        if "coinbase" in tx["vin"][0]:
            continue
        if not any(is_p2tr(bytes.fromhex(o["scriptPubKey"]["hex"])) for o in tx["vout"]):
            continue
        vins = []
        for vin in tx["vin"]:
            witness = CTxInWitness()
            witness.scriptWitness.stack = [bytes.fromhex(w) for w in vin.get("txinwitness", [])]
            vins.append(VinInfo(
                outpoint=COutPoint(deser_txid(vin["txid"]), vin["vout"]),
                scriptSig=bytes.fromhex(vin.get("scriptSig", {}).get("hex", "")),
                txinwitness=witness,
                prevout=verify_block_lib.prevout_spk(vin["txid"], vin["vout"]),
            ))
        pubkeys = [pk for pk in (get_pubkey_from_input(v) for v in vins) if not pk.infinity]
        if not pubkeys:
            continue
        A_sum = pubkeys[0]
        for pk in pubkeys[1:]:
            A_sum = A_sum + pk
        if A_sum.infinity:
            continue
        input_hash = get_input_hash([v.outpoint for v in vins], A_sum)
        tweak = int.from_bytes(input_hash, "big") * A_sum
        out.append((tx["txid"], tweak.to_bytes_compressed().hex()))
    return out


# --------------------------------------------------------------------------
# one height


def check_height(height):
    t0 = time.time()
    rec = {"height": height}
    try:
        core_hash = verify_block_lib.blockhash_for_height(height)
        ref = verify_block_lib.tweaks_for_block(height, blockhash=core_hash)
        ref = [t.lower() for t in ref]
    except Exception as e:  # noqa: BLE001
        rec.update(verdict="REFERENCE-ERROR", error=f"{type(e).__name__}: {e}")
        return rec
    finally:
        verify_block_lib._tx_cache.clear()
    try:
        bb_hash, bb = get_blindbit(height)
    except Exception as e:  # noqa: BLE001
        rec.update(verdict="BLINDBIT-ERROR", error=f"{type(e).__name__}: {e}",
                   ref_count=len(ref))
        return rec

    rec["ref_count"] = len(ref)
    rec["bb_count"] = len(bb)
    rec["core_blockhash"] = core_hash
    rec["bb_blockhash"] = bb_hash
    rec["blockhash_match"] = (bb_hash or "").lower() == core_hash.lower()
    rec["ordered_equal"] = ref == bb
    rec["multiset_equal"] = sorted(ref) == sorted(bb)
    rec["ref_sha256_ordered"] = digest(ref)
    rec["ref_sha256_sorted"] = digest(sorted(ref))
    rec["bb_sha256_sorted"] = digest(sorted(bb))
    rec["seconds"] = round(time.time() - t0, 1)

    if rec["blockhash_match"] and rec["ordered_equal"]:
        rec["verdict"] = "MATCH"
        return rec

    rec["verdict"] = "MISMATCH"
    only_ref = sorted(set(ref) - set(bb))
    only_bb = sorted(set(bb) - set(ref))
    rec["only_in_reference"] = only_ref
    rec["only_in_blindbit"] = only_bb
    try:
        attributed = tweaks_with_txids(height)
    except Exception as e:  # noqa: BLE001
        rec["attribution_error"] = f"{type(e).__name__}: {e}"
    else:
        bad = set(only_ref)
        rec["offending_txids"] = [
            {"txid": txid, "tweak": tw} for txid, tw in attributed if tw in bad
        ]
    finally:
        verify_block_lib._tx_cache.clear()
    return rec


# --------------------------------------------------------------------------


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--plan", action="store_true")
    ap.add_argument("--run", action="store_true")
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--out", default=str(HERE / "sweep-results.jsonl"))
    ap.add_argument("heights", nargs="*", type=int)
    a = ap.parse_args()

    if a.heights:
        heights, strata = sorted(set(a.heights)), {"explicit": sorted(set(a.heights))}
        by_h = {}
    else:
        heights, strata, by_h = select_heights()

    if a.plan or not a.run:
        for name, s in strata.items():
            print(f"{name}: {len(s)} heights, {min(s)} to {max(s)}")
        print(f"union: {len(heights)} distinct heights, {min(heights)} to {max(heights)}")
        if by_h:
            print(f"expected tweaks over the plan (from oracle.csv): "
                  f"{sum(by_h.get(h, 0) for h in heights)}")
        if not a.run:
            return

    workers = max(1, min(4, a.workers))
    t0 = time.time()
    done = mismatch = 0
    with open(a.out, "w") as fh, \
            concurrent.futures.ProcessPoolExecutor(max_workers=workers) as ex:
        for rec in ex.map(check_height, heights, chunksize=1):
            done += 1
            fh.write(json.dumps(rec) + "\n")
            fh.flush()
            v = rec["verdict"]
            if v != "MATCH":
                mismatch += 1
            print(f"{rec['height']} {v} ref={rec.get('ref_count')} "
                  f"bb={rec.get('bb_count')} {rec.get('seconds', '')}s"
                  + (f" ERROR {rec['error']}" if "error" in rec else ""), flush=True)
            if done % 25 == 0:
                print(f"... {done}/{len(heights)} in {time.time()-t0:.0f}s, "
                      f"{mismatch} not MATCH", file=sys.stderr, flush=True)

    recs = [json.loads(l) for l in open(a.out)]
    ok = [r for r in recs if r["verdict"] == "MATCH"]
    print()
    print(f"blocks compared      : {len(recs)}")
    print(f"MATCH                : {len(ok)}")
    print(f"not MATCH            : {len(recs) - len(ok)}")
    print(f"tweaks compared      : {sum(r.get('ref_count', 0) for r in ok)}")
    print(f"blockhash agreements : {sum(1 for r in recs if r.get('blockhash_match'))}")
    print(f"ordered-equal blocks : {sum(1 for r in recs if r.get('ordered_equal'))}")
    print(f"zero-tweak blocks    : {sum(1 for r in ok if r.get('ref_count') == 0)}")
    print(f"elapsed              : {time.time()-t0:.0f}s with {workers} workers")
    for r in recs:
        if r["verdict"] != "MATCH":
            print("\n" + json.dumps(r, indent=2))
    sys.exit(1 if len(ok) != len(recs) else 0)


if __name__ == "__main__":
    main()
