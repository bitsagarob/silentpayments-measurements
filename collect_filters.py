#!/usr/bin/env python3
"""Collect per-block stock BIP-158 basic filter sizes from Bitcoin Core REST.

Body bytes of /rest/blockfilter/basic/<hash>.bin as-is (includes 33-byte
type+blockhash prefix and ~3-byte compactsize; noted as a caveat, ~0.1%).
Writes bip158.csv: height,bip158_bytes. Resume-safe. Also writes hashes.csv.
"""
import csv, json, os, sys, threading
from concurrent.futures import ThreadPoolExecutor
import requests

REST = "http://127.0.0.1:8332/rest"
START, END = 709656, 965089
WORKERS = 6
DIR = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(DIR, "bip158.csv")
HASHES = os.path.join(DIR, "hashes.csv")

tls = threading.local()


def sess():
    if not hasattr(tls, "s"):
        tls.s = requests.Session()
    return tls.s


def load_hashes():
    hashes = {}
    if os.path.exists(HASHES):
        with open(HASHES) as f:
            r = csv.reader(f)
            next(r, None)
            for row in r:
                hashes[int(row[0])] = row[1]
        if all(h in hashes for h in range(START, END + 1)):
            return hashes
    s = requests.Session()
    h = START
    cur = s.get(f"{REST}/blockhashbyheight/{START}.json").json()["blockhash"]
    with open(HASHES, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["height", "hash"])
        while h <= END:
            hdrs = s.get(f"{REST}/headers/2000/{cur}.json").json()
            for hd in hdrs:
                if h > END:
                    break
                hashes[h] = hd["hash"]
                w.writerow([h, hd["hash"]])
                h += 1
            print(f"hashes: {h}", flush=True)
            if h <= END:
                cur = hdrs[-1].get("nextblockhash")
                if not cur:
                    raise RuntimeError(f"chain ended at {h}")
    return hashes


def fetch(args):
    h, bh = args
    r = sess().get(f"{REST}/blockfilter/basic/{bh}.bin", timeout=60)
    r.raise_for_status()
    return h, len(r.content)


def main():
    hashes = load_hashes()
    print("hashes loaded", flush=True)
    done = set()
    if os.path.exists(OUT):
        with open(OUT) as f:
            r = csv.reader(f)
            next(r, None)
            for row in r:
                done.add(int(row[0]))
    todo = [(h, hashes[h]) for h in range(START, END + 1) if h not in done]
    new = not done
    fh = open(OUT, "a", newline="")
    w = csv.writer(fh)
    if new:
        w.writerow(["height", "bip158_bytes"])
    cnt = 0
    with ThreadPoolExecutor(WORKERS) as ex:
        for h, size in ex.map(fetch, todo, chunksize=64):
            w.writerow([h, size])
            cnt += 1
            if cnt % 5000 == 0:
                fh.flush()
                print(f"filters: {cnt}/{len(todo)}", flush=True)
    fh.close()
    print("filters: ALL DONE")


if __name__ == "__main__":
    main()
