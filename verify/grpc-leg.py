#!/usr/bin/env python3
"""Second leg: check the gRPC route that actually produced oracle.csv.

oracle.csv was collected by collect_oracle.py over
blindbit.oracle.v1.OracleService/StreamComputeIndex on 127.0.0.1:8011, not over
the HTTP /tweaks route that sweep-verify.py queries. This script closes that
gap. For every height in sweep-results.jsonl it:

  1. pulls the index from StreamComputeIndex with the same request body
     collect_oracle.py used, {"dustlimit": 0, "cut_through": false},
  2. compares the sha256 of its sorted tweak list against ref_sha256_sorted,
     the digest of the BIP-352 reference implementation's own tweak list,
  3. compares the item count against the `tweaks` column of oracle.csv.

    python3 grpc-leg.py [--results sweep-results.jsonl]

Requires grpcurl and a BlindBit Oracle v2 gRPC endpoint on 127.0.0.1:8011.
"""
import argparse
import base64
import csv
import hashlib
import json
import os
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
GRPCURL = os.path.expanduser("~/.local/bin/grpcurl")
ADDR = "127.0.0.1:8011"
METHOD = "blindbit.oracle.v1.OracleService/StreamComputeIndex"
ORACLE_CSV = HERE.parent / "oracle.csv"


def digest(tweaks):
    return hashlib.sha256("\n".join(tweaks).encode()).hexdigest()


def grpc_index(height, timeout=600):
    req = json.dumps({"start": height, "end": height,
                      "dustlimit": 0, "cut_through": False})
    p = subprocess.run([GRPCURL, "-plaintext", "-max-time", "600", "-d", req,
                        ADDR, METHOD],
                       capture_output=True, timeout=timeout)
    if p.returncode != 0:
        raise RuntimeError(f"grpcurl rc={p.returncode}: {p.stderr.decode()[:300]}")
    dec = json.JSONDecoder()
    buf, pos, objs = p.stdout.decode(), 0, []
    while pos < len(buf):
        while pos < len(buf) and buf[pos] in " \r\n\t":
            pos += 1
        if pos >= len(buf):
            break
        obj, pos = dec.raw_decode(buf, pos)
        objs.append(obj)
    if len(objs) != 1:
        raise RuntimeError(f"expected 1 block message, got {len(objs)}")
    o = objs[0]
    bh = base64.b64decode(o["blockIdentifier"]["blockHash"]).hex()
    tweaks = [base64.b64decode(i["tweak"]).hex() for i in o.get("index", [])]
    txids = [base64.b64decode(i["txid"]).hex() for i in o.get("index", [])]
    return bh, tweaks, txids


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--results", default=str(HERE / "sweep-results.jsonl"))
    ap.add_argument("--out", default=str(HERE / "grpc-leg-results.jsonl"))
    a = ap.parse_args()

    csv_tweaks = {}
    with open(ORACLE_CSV) as f:
        for r in csv.DictReader(f):
            csv_tweaks[int(r["height"])] = int(r["tweaks"])

    recs = [json.loads(l) for l in open(a.results)]
    recs = [r for r in recs if "ref_sha256_sorted" in r]
    t0 = time.time()
    ok = csv_ok = 0
    bad = []
    with open(a.out, "w") as fh:
        for i, r in enumerate(recs):
            h = r["height"]
            out = {"height": h, "ref_count": r["ref_count"],
                   "csv_tweaks": csv_tweaks.get(h)}
            try:
                bh, tweaks, txids = grpc_index(h)
            except Exception as e:  # noqa: BLE001
                out.update(verdict="GRPC-ERROR", error=f"{type(e).__name__}: {e}")
                bad.append(out)
                fh.write(json.dumps(out) + "\n")
                continue
            out["grpc_count"] = len(tweaks)
            out["grpc_sha256_sorted"] = digest(sorted(tweaks))
            out["tweaks_match_reference"] = out["grpc_sha256_sorted"] == r["ref_sha256_sorted"]
            out["count_matches_oracle_csv"] = len(tweaks) == csv_tweaks.get(h)
            out["verdict"] = ("MATCH" if out["tweaks_match_reference"]
                              and out["count_matches_oracle_csv"] else "MISMATCH")
            if out["verdict"] == "MATCH":
                ok += 1
            else:
                out["grpc_txids_sample"] = txids[:50]
                bad.append(out)
            if out["count_matches_oracle_csv"]:
                csv_ok += 1
            fh.write(json.dumps(out) + "\n")
            fh.flush()
            if (i + 1) % 50 == 0:
                print(f"... {i+1}/{len(recs)} in {time.time()-t0:.0f}s, {ok} match",
                      file=sys.stderr, flush=True)

    print()
    print(f"heights checked over gRPC          : {len(recs)}")
    print(f"gRPC tweak set == reference        : {ok}")
    print(f"gRPC count == oracle.csv `tweaks`  : {csv_ok}")
    print(f"disagreements                      : {len(bad)}")
    print(f"tweaks compared                    : "
          f"{sum(r['ref_count'] for r in recs)}")
    print(f"elapsed                            : {time.time()-t0:.0f}s")
    for b in bad:
        print("\n" + json.dumps(b, indent=2))
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
