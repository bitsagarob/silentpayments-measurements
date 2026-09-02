#!/usr/bin/env python3
"""Merge oracle.csv + bip158.csv into comparison.csv and print/save the summary."""
import csv, os

DIR = os.path.dirname(os.path.abspath(__file__))
P = 19
START, END = 709656, 965089
ERAS = [(709656, 749999), (750000, 799999), (800000, 849999),
        (850000, 899999), (900000, 965089)]


def varint_len(n):
    return 1 if n < 0xfd else 3 if n <= 0xffff else 5 if n <= 0xffffffff else 9


def main():
    oracle = {}
    with open(os.path.join(DIR, "oracle.csv")) as f:
        r = csv.reader(f); next(r)
        for h, n, v2, tw in r:
            oracle[int(h)] = (int(n), int(v2), int(tw))
    bip158 = {}
    with open(os.path.join(DIR, "bip158.csv")) as f:
        r = csv.reader(f); next(r)
        for h, b in r:
            bip158[int(h)] = int(b)
    heights = list(range(START, END + 1))
    missing_o = [h for h in heights if h not in oracle]
    missing_b = [h for h in heights if h not in bip158]
    assert not missing_o, f"oracle missing {len(missing_o)}: {missing_o[:5]}"
    assert not missing_b, f"bip158 missing {len(missing_b)}: {missing_b[:5]}"

    with open(os.path.join(DIR, "comparison.csv"), "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["height", "bip158_bytes", "taproot_n", "taproot_est_bytes",
                    "v2_bytes", "tweaks"])
        for h in heights:
            n, v2, tw = oracle[h]
            est = round(n * (P + 2) / 8 + varint_len(n), 1)
            w.writerow([h, bip158[h], n, est, v2, tw])

    def agg(lo, hi):
        hs = range(lo, hi + 1)
        nb = hi - lo + 1
        b158 = sum(bip158[h] for h in hs)
        tap = sum(oracle[h][0] * (P + 2) / 8 + varint_len(oracle[h][0]) for h in hs)
        v2 = sum(oracle[h][1] for h in hs)
        tw = sum(oracle[h][2] for h in hs)
        tn = sum(oracle[h][0] for h in hs)
        return nb, b158, tap, v2, tw, tn

    print(f"{'era':>16} {'blocks':>7} {'bip158 avg':>11} {'taproot avg':>11} "
          f"{'v2 avg':>11} {'tap/158':>8} {'v2/158':>7} {'v2/tap':>7} {'tweaks/blk':>10}")
    for lo, hi in ERAS + [(START, END)]:
        nb, b158, tap, v2, tw, tn = agg(lo, hi)
        label = f"{lo}-{hi}" if (lo, hi) != (START, END) else "TOTAL"
        print(f"{label:>16} {nb:>7} {b158/nb:>11.0f} {tap/nb:>11.0f} {v2/nb:>11.0f} "
              f"{tap/b158:>8.4f} {v2/b158:>7.4f} {v2/tap:>7.2f} {tw/nb:>10.1f}")
    nb, b158, tap, v2, tw, tn = agg(START, END)
    G = 1e9
    print(f"\nTotals: bip158={b158/G:.3f} GB  taproot_est={tap/G:.3f} GB  "
          f"v2={v2/G:.3f} GB  tweaks={tw}  taproot_items={tn}")
    # tip-following daily budget at 900k-965k averages
    nb9, b9, t9, v9, _, _ = agg(900000, 965089)
    print(f"Daily (144 blk, 900k-965k era): bip158={144*b9/nb9/1e6:.2f} MB  "
          f"taproot={144*t9/nb9/1e6:.3f} MB  v2={144*v9/nb9/1e6:.2f} MB")


if __name__ == "__main__":
    main()
