# Silent payments light-client measurements

Per-block sizes of the three candidate "hint mechanisms" for BIP-352 light
clients, measured across all 255,434 mainnet blocks from taproot activation
(709,656) to 965,089 against Bitcoin Core v31 and a production BlindBit Oracle
v2. No sampling. Context: the delving thread "Silent Payments: Light Client
Protocol".

| mechanism | total | avg/block | tip-following/day* |
|---|---|---|---|
| stock BIP-158 basic filter | 5.78 GB | 22.6 KB | 2.8 MB |
| taproot-only eligible filter (2024 design, estimated**) | 0.94 GB | 3.7 KB | 0.4 MB |
| shipped v2 compute-index payload | 15.08 GB | 59.0 KB | 8.0 MB |

*144 blocks/day at 900k-965k era averages. A filter-based client additionally
needs the raw tweaks: 187,814,353 tweaks, 6.2 GB over the range (735/block).

**GCS size formula N*(P+2)/8 + varint(N) at P=19, validated against real
encodings of 21 sample blocks (within ~0.5%, see gcs_validation.csv).

Headlines: the taproot-only filter is ~6.1x smaller than stock BIP-158; the
shipped v2 payload costs ~2.1x a complete filter stack (15.1 vs 7.1 GB) in
exchange for zero false positives and no per-match block fetches. All figures
at dustlimit 0, no cut-through, i.e. upper bounds for the two mechanisms that
can shrink. BIP-158 numbers are REST body bytes (~0.16% overstatement).

Files: `comparison.csv` per block (height, bip158_bytes, taproot_n,
taproot_est_bytes, v2_bytes, tweaks); `bip158.csv`/`oracle.csv` raw series;
`collect_*.py`, `validate_gcs.py`, `summarize.py` to reproduce (needs a Core
node with blockfilterindex plus a BlindBit v2 oracle, loopback only).

Data: CC0. Scripts: MIT. From the operators of https://silentpayments.net.
