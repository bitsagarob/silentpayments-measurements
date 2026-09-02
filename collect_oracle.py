#!/usr/bin/env python3
"""Collect per-block silent-payments compute-index stats from the BlindBit v2 oracle.

Streams OracleService/StreamComputeIndex over gRPC (via grpcurl) in chunks and
writes oracle.csv: height,taproot_n,v2_bytes,tweaks
  taproot_n = sum(len(outputs_short)/8) over index items  (taproot outputs of eligible txs)
  v2_bytes  = sum(32 + 33 + len(outputs_short))           (txid + tweak + prefixes wire payload)
  tweaks    = len(index)
Resume-safe: skips ranges already fully present in the CSV.
"""
import base64, csv, json, os, subprocess, sys

GRPCURL = os.path.expanduser("~/.local/bin/grpcurl")
ADDR = "127.0.0.1:8011"
METHOD = "blindbit.oracle.v1.OracleService/StreamComputeIndex"
START, END = 709656, 965089
CHUNK = 1000
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "oracle.csv")


def process_chunk(s, e, writer, fh):
    req = json.dumps({"start": s, "end": e, "dustlimit": 0, "cut_through": False})
    p = subprocess.Popen(
        [GRPCURL, "-plaintext", "-max-time", "3600", "-d", req, ADDR, METHOD],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    dec = json.JSONDecoder()
    buf = ""
    seen = {}
    while True:
        chunk = p.stdout.read(1 << 20)
        if not chunk:
            break
        buf += chunk.decode()
        pos = 0
        while True:
            while pos < len(buf) and buf[pos] in " \r\n\t":
                pos += 1
            if pos >= len(buf):
                break
            try:
                obj, pos = dec.raw_decode(buf, pos)
            except json.JSONDecodeError:
                break
            h = int(obj["blockIdentifier"]["blockHeight"])
            n = v2 = 0
            idx = obj.get("index", [])
            for item in idx:
                os_len = len(base64.b64decode(item.get("outputsShort", "")))
                assert os_len % 8 == 0, f"outputs_short len {os_len} not /8 at height {h}"
                n += os_len // 8
                v2 += 32 + 33 + os_len
            seen[h] = (n, v2, len(idx))
        buf = buf[pos:]
    rc = p.wait()
    if rc != 0:
        raise RuntimeError(f"grpcurl rc={rc} for {s}-{e}: {p.stderr.read().decode()[:500]}")
    missing = [h for h in range(s, e + 1) if h not in seen]
    if missing:
        raise RuntimeError(f"missing heights in {s}-{e}: {missing[:10]}...")
    for h in range(s, e + 1):
        n, v2, tw = seen[h]
        writer.writerow([h, n, v2, tw])
    fh.flush()


def main():
    done = set()
    if os.path.exists(OUT):
        with open(OUT) as f:
            r = csv.reader(f)
            next(r, None)
            for row in r:
                done.add(int(row[0]))
    new = not os.path.exists(OUT) or not done
    fh = open(OUT, "a", newline="")
    w = csv.writer(fh)
    if new:
        w.writerow(["height", "taproot_n", "v2_bytes", "tweaks"])
    s = START
    while s <= END:
        e = min(s + CHUNK - 1, END)
        if all(h in done for h in range(s, e + 1)):
            s = e + 1
            continue
        process_chunk(s, e, w, fh)
        print(f"oracle: done {s}-{e}", flush=True)
        s = e + 1
    fh.close()
    print("oracle: ALL DONE")


if __name__ == "__main__":
    main()
