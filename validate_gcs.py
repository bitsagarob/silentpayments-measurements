#!/usr/bin/env python3
"""Validate the taproot-only filter size formula against a real GCS encoding.

Formula under test: est_bytes = N*(P+2)/8 + varint(N), P=19 (BIP-158 params
P=19, M=784931, ~21 bits/item claimed).

For ~20 sample blocks spanning the range we fetch the real per-block items
(8-byte x-only pubkey prefixes of taproot outputs of eligible txs, from the
oracle), build an actual BIP-158-construction GCS filter in Python
(siphash-2-4 keyed with first 16 bytes of the serialized block hash, map into
[0, N*M), dedupe, sort, delta-encode Golomb-Rice P=19), and compare real
encoded bytes vs the formula.
"""
import base64, json, os, subprocess, sys
import requests

GRPCURL = os.path.expanduser("~/.local/bin/grpcurl")
ADDR = "127.0.0.1:8011"
METHOD = "blindbit.oracle.v1.OracleService/StreamComputeIndex"
REST = "http://127.0.0.1:8332/rest"
P, M = 19, 784931
SAMPLES = list(range(710000, 965001, 12750))  # 21 blocks spanning all eras

MASK = (1 << 64) - 1


def _rotl(x, b):
    return ((x << b) | (x >> (64 - b))) & MASK


def siphash24(k0, k1, data):
    v0 = 0x736f6d6570736575 ^ k0
    v1 = 0x646f72616e646f6d ^ k1
    v2 = 0x6c7967656e657261 ^ k0
    v3 = 0x7465646279746573 ^ k1

    def rounds(n):
        nonlocal v0, v1, v2, v3
        for _ in range(n):
            v0 = (v0 + v1) & MASK; v1 = _rotl(v1, 13); v1 ^= v0; v0 = _rotl(v0, 32)
            v2 = (v2 + v3) & MASK; v3 = _rotl(v3, 16); v3 ^= v2
            v0 = (v0 + v3) & MASK; v3 = _rotl(v3, 21); v3 ^= v0
            v2 = (v2 + v1) & MASK; v1 = _rotl(v1, 17); v1 ^= v2; v2 = _rotl(v2, 32)

    b = len(data) & 0xff
    end = len(data) - (len(data) % 8)
    for i in range(0, end, 8):
        m = int.from_bytes(data[i:i+8], "little")
        v3 ^= m; rounds(2); v0 ^= m
    m = b << 56
    for i, ch in enumerate(data[end:]):
        m |= ch << (8 * i)
    v3 ^= m; rounds(2); v0 ^= m
    v2 ^= 0xff; rounds(4)
    return (v0 ^ v1) ^ (v2 ^ v3)


def varint_len(n):
    return 1 if n < 0xfd else 3 if n <= 0xffff else 5 if n <= 0xffffffff else 9


class BitWriter:
    def __init__(self):
        self.buf = bytearray()
        self.acc = 0
        self.nbits = 0

    def write(self, val, nbits):
        self.acc = (self.acc << nbits) | (val & ((1 << nbits) - 1))
        self.nbits += nbits
        while self.nbits >= 8:
            self.nbits -= 8
            self.buf.append((self.acc >> self.nbits) & 0xff)
        self.acc &= (1 << self.nbits) - 1

    def flush(self):
        if self.nbits:
            self.buf.append((self.acc << (8 - self.nbits)) & 0xff)
            self.acc = self.nbits = 0
        return bytes(self.buf)


def build_gcs(block_hash_hex, items):
    """Real BIP-158 construction. Returns encoded filter bytes (incl. varint N)."""
    key = bytes.fromhex(block_hash_hex)[::-1][:16]
    k0 = int.from_bytes(key[:8], "little")
    k1 = int.from_bytes(key[8:], "little")
    n = len(set(items))
    f = n * M
    hashed = sorted({(siphash24(k0, k1, it) * f) >> 64 for it in items})
    n = len(hashed)  # after value-level dedupe (BIP-158 does the same)
    bw = BitWriter()
    last = 0
    for v in hashed:
        d = v - last
        q, r = d >> P, d & ((1 << P) - 1)
        bw.write((1 << (q + 1)) - 2, q + 1)  # q ones then a zero
        bw.write(r, P)
        last = v
    return varint_len(n) + len(bw.flush()), n


def fetch_block_items(h):
    req = json.dumps({"start": h, "end": h, "dustlimit": 0, "cut_through": False})
    out = subprocess.run(
        [GRPCURL, "-plaintext", "-max-time", "300", "-d", req, ADDR, METHOD],
        capture_output=True, check=True).stdout.decode()
    obj = json.loads(out)
    items = []
    for it in obj.get("index", []):
        raw = base64.b64decode(it.get("outputsShort", ""))
        assert len(raw) % 8 == 0
        for i in range(0, len(raw), 8):
            items.append(raw[i:i+8])
    return items


def main():
    s = requests.Session()
    rows = []
    print(f"{'height':>7} {'N':>6} {'real_B':>8} {'est_B':>8} {'dev%':>7}")
    for h in SAMPLES:
        bh = s.get(f"{REST}/blockhashbyheight/{h}.json").json()["blockhash"]
        items = fetch_block_items(h)
        if not items:
            print(f"{h:>7} {0:>6} {'-':>8} {'-':>8} {'-':>7}  (no eligible items, skipped)")
            continue
        real, n = build_gcs(bh, items)
        est = n * (P + 2) / 8 + varint_len(n)
        dev = 100.0 * (est - real) / real
        rows.append((h, n, real, est, dev))
        print(f"{h:>7} {n:>6} {real:>8} {est:>8.1f} {dev:>+6.2f}%")
    if rows:
        devs = [r[4] for r in rows]
        tot_real = sum(r[2] for r in rows)
        tot_est = sum(r[3] for r in rows)
        print(f"\nsamples={len(rows)} mean_dev={sum(devs)/len(devs):+.2f}% "
              f"min={min(devs):+.2f}% max={max(devs):+.2f}% "
              f"aggregate est/real={tot_est/tot_real:.4f}")
        with open(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                               "gcs_validation.csv"), "w") as f:
            f.write("height,n,real_bytes,est_bytes,deviation_pct\n")
            for r in rows:
                f.write(f"{r[0]},{r[1]},{r[2]},{r[3]:.1f},{r[4]:.3f}\n")


if __name__ == "__main__":
    main()
