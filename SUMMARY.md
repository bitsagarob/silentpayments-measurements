# BIP-352 light-client hint mechanisms: per-block size comparison

Measured 2026-09-01/02 on bitsaga-vps2, entirely locally (Bitcoin Core v31 REST +
BlindBit oracle v2 gRPC StreamComputeIndex, dustlimit=0, cut_through=false).
Full mainnet range **709656 (taproot activation) to 965089**, all 255,434 blocks,
no sampling. Per-block data: `comparison.csv` (height, bip158_bytes, taproot_n,
taproot_est_bytes, v2_bytes, tweaks).

## The three mechanisms

1. **Stock BIP-158 basic filter** - actual body bytes of Core's
   `/rest/blockfilter/basic/<hash>.bin` (includes a 33-byte type+blockhash prefix
   plus ~3-byte compactsize, ~0.1% overstatement; see caveats).
2. **Taproot-only filter** (the 2024 lcspec design josibake asked about) - a
   BIP-158-parameter GCS filter with one item per taproot output of each
   silent-payments-ELIGIBLE transaction. N per block comes from the oracle
   (`sum(len(outputs_short)/8)`; every `outputs_short` verified `len % 8 == 0`).
   Size estimated as `N*(P+2)/8 + varint(N)` bytes with P=19 (~21 bits/item at
   M=784931), validated against a real encoding (below).
3. **Shipped v2 compute-index** - the actual wire payload a v2 client (friglet)
   downloads per block for prefix matching without filters:
   `sum(32 txid + 33 tweak + len(outputs_short))` per eligible tx.

## Results

### Totals over 709656-965089 (255,434 blocks)

| mechanism | total | avg bytes/block |
|---|---|---|
| BIP-158 basic filter | **5.779 GB** | 22,623 |
| Taproot-only filter (est.) | **0.943 GB** | 3,692 |
| v2 compute-index payload | **15.080 GB** | 59,037 |

Tweaks (eligible txs) total: 187,814,353 (735.3/block avg).
Taproot outputs of eligible txs (filter items): 359,001,723.

### Per-era breakdown (avg bytes/block)

| era | blocks | BIP-158 | taproot-only | v2 payload | tap/158 | v2/158 | v2/tap | tweaks/blk |
|---|---|---|---|---|---|---|---|---|
| 709656-749999 | 40,344 | 24,809 | 15 | 374 | 0.0006 | 0.015 | 25.4 | 5.1 |
| 750000-799999 | 50,000 | 25,160 | 2,174 | 31,546 | 0.086 | 1.25 | 14.5 | 383.5 |
| 800000-849999 | 50,000 | 23,956 | 7,523 | 104,665 | 0.314 | 4.37 | 13.9 | 1,257.6 |
| 850000-899999 | 50,000 | 20,729 | 5,171 | 92,444 | 0.249 | 4.46 | 17.9 | 1,179.9 |
| 900000-965089 | 65,090 | 19,751 | 3,057 | 55,802 | 0.155 | 2.83 | 18.3 | 715.3 |
| **TOTAL** | 255,434 | 22,623 | 3,692 | 59,037 | **0.163** | **2.61** | **16.0** | 735.3 |

### The 2024 answer (taproot-only filter vs stock BIP-158)

A taproot-only, eligibility-filtered GCS filter is **~6.1x smaller than the stock
BIP-158 basic filter** over the whole range (ratio 0.163), and never worse in any
era. The gap is era-dependent: at the ordinals/inscriptions peak (800k-850k) it
narrows to ~3.2x; in the recent 900k-965k era it is ~6.5x. Early (pre-750k) the
taproot filter is near-empty. The stock filter's size is nearly flat (~20-25 KB)
because it indexes ALL scripts; the taproot filter tracks eligible-taproot
activity only.

### The 2026 answer (shipped v2 compute-index vs either)

The v2 compute-index payload is **2.6x LARGER than the stock BIP-158 filter** and
**~16x larger than a taproot-only filter** on average. But it is not the same
kind of object: the filters are only probabilistic hints - a filter-based SP
client additionally needs the per-block tweaks (33 bytes x 187.8M = 6.20 GB over
this range, i.e. more than the BIP-158 filters themselves) to compute candidate
outputs before it can even query the filter, plus a full block download on every
match (false-positive or real). The v2 payload is self-contained: tweaks +
txids + 8-byte output prefixes, enough to detect payments by prefix match with
no block downloads for scanning. So the honest 2026 comparison is:
taproot-filter+tweaks ≈ 0.94 + 6.20 = **7.14 GB** vs v2's **15.08 GB** (~2.1x),
with v2 buying zero-false-positive detection and no per-match block fetches for
that 2.1x.

### GCS formula validation

Real BIP-158-construction filters (siphash-2-4 keyed with the first 16 bytes of
the serialized block hash - implementation verified against the official siphash
test vectors - mapped into [0, N*M), deduped, sorted, Golomb-Rice delta-encoded
at P=19) were built in Python for 21 sample blocks spanning the range (2 had
zero eligible items). Formula vs real encoded bytes over the 19 usable samples:

- mean deviation **-0.54%** (formula slightly under), range -2.43% to -0.10%
- aggregate est/real = **0.9973**; for N >= 90 the deviation is within -0.5%

The worst deviations are tiny-N blocks (N <= 13) where varint/rounding dominate.
The per-era and total taproot-filter figures above therefore understate real
filter bytes by roughly 0.3%. Per-sample data: `gcs_validation.csv`.

### Tip-following daily budget (144 blocks/day at 900k-965k era averages)

| mechanism | per day |
|---|---|
| BIP-158 basic filter | 2.84 MB |
| Taproot-only filter | 0.44 MB |
| v2 compute-index payload | 8.04 MB |

(For a complete filter-based SP client add tweaks: 715.3 tweaks/block x 33 B x
144 ≈ 3.40 MB/day on top of either filter line.)

## Caveats

- **Taproot-only filter sizes are a validated approximation**, not served bytes:
  `N*(P+2)/8 + varint(N)`, shown to sit within ~0.3% of a real GCS encoding on
  the samples. No such filter is actually deployed; item definition (one item
  per taproot output of each eligible tx) follows the 2024 lcspec discussion.
- **dustlimit=0 and cut_through=false basis**: the oracle counted every eligible
  tx and every taproot output, including dust and outputs later spent within the
  measured range. Any dust cutoff or cut-through would shrink mechanisms 2 and 3
  (only) - these numbers are their upper bound, the stock filter is unaffected.
- **BIP-158 numbers are REST body bytes**: they include Core's 33-byte
  type+blockhash serialization prefix and ~3-byte compactsize, overstating the
  raw filter by ~36 bytes/block (~0.16%). Not corrected, per method spec.
- **v2 payload is raw field bytes** (32+33+prefixes); gRPC/protobuf framing and
  block_identifier overhead are excluded. All three mechanisms likewise exclude
  transport/header-chain overhead, so the comparison is like-for-like.
- Filters are hints with false positives (and require tweak data separately);
  the v2 payload is a complete scanning dataset. The headline ratios compare
  bytes-per-block of the downloadable object, not total end-to-end bandwidth of
  a full client protocol - see "the 2026 answer" for the corrected comparison.
- Range starts at taproot activation (709656) and ends at 965089 (tip was 965099
  at measurement time). Eras are height-based, boundary-inclusive as shown.

## Reproduce

`collect_oracle.py` (oracle stream → oracle.csv), `collect_filters.py`
(Core REST → bip158.csv, hashes.csv), `validate_gcs.py` (formula validation),
`summarize.py` (merge → comparison.csv + this table). All loopback-only.
