# Silent payments light-client measurements

A phone wallet cannot scan the chain itself. It downloads per-block scanning data from a
server to find incoming [BIP-352 silent payments](https://bips.dev/352/). Three designs
exist for that data. This repository measures all three on the same range.

The 2024 [light-client thread](https://delvingbitcoin.org/t/silent-payments-light-client-protocol/891)
asked for one of these numbers directly (post 3: "Do you have any numbers for how using a
taproot filter vs an off-the-shelf BIP158 filter impacts the bandwidth?") and went quiet on
2024-06-08 without an answer.

Every one of the 255,434 mainnet blocks from 709,656 to 965,089. No sampling. Bitcoin Core
v31.1.0 and a production BlindBit Oracle v2, both on loopback, collected 2026-09-02.
Provenance: [PROVENANCE.md](./PROVENANCE.md).

## Results

| What the wallet downloads | Whole range | Per day |
|---|---|---|
| BIP-158 basic filter, what light wallets use today | 5.78 GB | 2.84 MB |
| Taproot-only filter, proposed 2024, never built | 0.94 GB | 0.44 MB |
| Raw tweaks, 33 bytes per eligible transaction | 6.20 GB | 4.87 MB |
| BlindBit v2 scanning payload, what ships | 15.08 GB | 8.04 MB |

Per day is 144 blocks at blocks 900,000 to 965,089 averages.

## Two findings

**A taproot-only filter is 6.13x smaller than the stock BIP-158 filter over the whole
range.** The ratio moves hard with era: 3.18x over blocks 800,000 to 849,999, the
inscription peak, and 12.99x over the last 10,000 blocks. The 2024 conjecture was that
taproot adoption would close the gap. It has not.

**The shipping design costs 2.11x the filter route.** A filter is only a hint, so a filter
client must also fetch every raw tweak, 6.20 GB, more than the filters themselves, plus a
full block on every match. Filters plus tweaks is 7.14 GB against the payload route's
15.08 GB, and the payload route buys zero false positives and no block fetches while
scanning. Those block fetches are not counted, so 2.11x is an upper bound on the payload
route's disadvantage, not a measurement of it.

Even the heaviest option is 8 MB a day on a phone.

## What filtering would save

Skipping outputs already spent takes the 15.08 GB restore to 3.10 GB. A 546 sat dust limit
on top takes it to 2.29 GB. It saves a wallet following the chain nothing, because a new
block's outputs are unspent by definition. Tables, both dust readings and the server-side
cost: [FILTERS.md](./FILTERS.md).

## Limits

| | |
|---|---|
| Taproot-only filter bytes | Computed, not served: no such filter is deployed anywhere. Item counts per block are exact. The formula `N*(P+2)/8 + varint(N)`, P=19, was checked against real Golomb-Rice encodings of 19 blocks: aggregate -0.27%, worst single block -2.50%. See `gcs_validation.csv`. |
| Dust and cut-through | Measured with neither, because BlindBit Oracle v2 applies neither at any setting: it accepts both request parameters and reads neither. Proven in upstream source and on the live server, see [PROVENANCE.md](./PROVENANCE.md). |
| BIP-158 bytes | REST body bytes, a fixed 36 bytes per block above the raw filter (1 type byte, 32 blockhash, 3 compactsize). That is 0.16% of the range total and 1.41% of block 965,089's filter. |
| Independent check | The tweak series was recomputed against the BIP-352 reference implementation, 529 blocks and 526,166 tweaks, zero disagreements, see [VERIFICATION.md](./VERIFICATION.md). The other three columns are single-source. |

## Reproduce

`summarize.py` rebuilds `comparison.csv` from `bip158.csv` and `oracle.csv` and prints every
figure above. It needs no node. Collection needs Core with `blockfilterindex=1` and a
BlindBit v2 oracle on loopback: `collect_filters.py`, `collect_oracle.py`,
`validate_gcs.py`. The independent check is in `verify/`.

Also here: `SPCOMMIT.md`, the normative format for the per-block index commitments the
server publishes, with five real-data vectors in `spcommit-test-vectors.json`; and
[LIGHT-CLIENT-PROTOCOL-DRAFT.md](./LIGHT-CLIENT-PROTOCOL-DRAFT.md), a pre-draft that merges
the two existing spec efforts with what shipped. Neither is a measurement.

Elsewhere: [blindbit-v1-shim](https://github.com/bitsagarob/blindbit-v1-shim) serves the
removed v1 HTTP API in front of a v2 oracle, and rebuilds the taproot-only filters measured
above, since v2 serves none.

Data: CC0. Scripts: MIT. From the operators of https://silentpayments.net.
