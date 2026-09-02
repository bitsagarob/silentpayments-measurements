# Silent payments light-client measurements

Full-range mainnet measurements behind the numbers posted to the delving
bitcoin thread "Silent Payments: Light Client Protocol": per-block sizes of
three BIP-352 light-client hint mechanisms across all 255,434 blocks from
taproot activation (709,656) to 965,089, measured 2026-09-01/02 against
Bitcoin Core v31 and a production BlindBit Oracle v2, no sampling.

- `SUMMARY.md`: methodology, results, caveats.
- `comparison.csv`: per block: height, stock BIP-158 filter bytes, taproot-only
  filter item count and estimated bytes, shipped v2 payload bytes, tweak count.
- `bip158.csv`, `oracle.csv`: the raw collected series.
- `gcs_validation.csv`: real GCS encodings vs the size formula, 21 sample blocks.
- `collect_*.py`, `validate_gcs.py`, `summarize.py`: reproduction scripts
  (loopback-only: a Core node with blockfilterindex plus a BlindBit v2 oracle).

Data: CC0. Scripts: MIT. From the operators of https://silentpayments.net.
