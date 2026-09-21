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
| Taproot-only filter, proposed 2024, never built | 0.33 GB | 0.14 MB |
| Raw tweaks, 33 bytes per eligible transaction | 6.20 GB | 3.40 MB |
| BlindBit v2 scanning payload, what ships | 15.08 GB | 8.04 MB |

Per day is 144 blocks at blocks 900,000 to 965,089 averages.

## Two findings

**A taproot-only filter is 17.63x smaller than the stock BIP-158 filter over the whole
range.** The ratio moves hard with era: 7.65x over blocks 800,000 to 849,999, the
inscription peak, and 23.61x over the last 10,000 blocks. The 2024 conjecture was that
taproot adoption would close the gap. It has not.

**The shipping design costs 2.31x the filter route.** A filter is only a hint, so a filter
client must also fetch every raw tweak, 6.20 GB, nearly twenty times the filters
themselves, plus a full block on every match. Filters plus tweaks is 6.53 GB against the
payload route's 15.08 GB, and the payload route buys zero false positives and no block
fetches while scanning. Those block fetches are not counted, so 2.31x is an upper bound on
the payload route's disadvantage, not a measurement of it.

Even the heaviest option is 8 MB a day on a phone.

## What filtering would save

Skipping transactions whose outputs are all spent takes the 15.08 GB restore to 3.43 GB. A
546 sat dust limit on top takes it to 2.57 GB. It saves a wallet following the chain
nothing, because a new block's outputs are unspent by definition. A filter must drop a whole
transaction or none of it, or a scanner stops at the first output it cannot match. Full
tables and the server-side cost: [FILTERS.md](./FILTERS.md).

## Limits

| | |
|---|---|
| Taproot-only filter bytes | **Encoded, not modelled.** No such filter is deployed anywhere, so every block's filter was built and weighed: real siphash-2-4, real Golomb-Rice, P=19, M=784931. Two independent C implementations, written separately, agree on all 255,434 blocks with zero differing bytes, and each was first proved byte-for-byte identical to Bitcoin Core's own basic filters (11,275 and 1,283 blocks, zero mismatches). Per-block results in `taproot_filter.csv`. |
| Duplicate keys | BIP-158 encodes an element **set**, which is what Core does and what byte-for-byte agreement with Core requires. Over this range 359,001,723 eligible taproot outputs carry only 124,299,689 distinct x-only keys, 65.4% repeats, so the filter has 124.3M elements. Keeping duplicates instead would give 0.958 GB and 6.02x. A wallet matches on key membership, so a repeated key adds nothing. |
| Dust and cut-through | Measured with neither, because upstream BlindBit Oracle v2 applies neither at any setting: it accepts both request parameters and reads neither. Proven in upstream source, see [PROVENANCE.md](./PROVENANCE.md). The server these figures came from now implements both ([blindbit-oracle#61](https://github.com/setavenger/blindbit-oracle/pull/61)), which does not change any figure in the results table above. |
| BIP-158 bytes | REST body bytes: 1 type byte, 32 blockhash, then a compactsize length. Usually 36 bytes of framing, but 34 on 1,172 small-filter blocks and 38 on block 826,052. 0.159% of the range total, 9,193,282 bytes. |
| Independent check | The tweak series was recomputed against the BIP-352 reference implementation, 529 blocks and 526,166 tweaks, zero disagreements, see [VERIFICATION.md](./VERIFICATION.md). The other three columns are single-source. |

## Reproduce

`summarize.py` rebuilds `comparison.csv` from `bip158.csv`, `oracle.csv` and
`taproot_filter.csv`, and prints every figure above. It needs no node. Collection needs Core with `blockfilterindex=1` and a
BlindBit v2 oracle on loopback: `collect_filters.py`, `collect_oracle.py`,
`validate_gcs.py`. The independent check is in `verify/`.

Also here: `SPCOMMIT.md`, the normative format for the per-block index commitments the
server publishes, with `commitments.js` as its reference implementation and five real-data
vectors in `spcommit-test-vectors.json`; and
[LIGHT-CLIENT-PROTOCOL-DRAFT.md](./LIGHT-CLIENT-PROTOCOL-DRAFT.md), a pre-draft that merges
the two existing spec efforts with what shipped. Neither is a measurement.

Elsewhere: [blindbit-v1-shim](https://github.com/bitsagarob/blindbit-v1-shim) serves the
removed v1 HTTP API in front of a v2 oracle, and rebuilds the taproot-only filters measured
above, since v2 serves none.

Data: CC0. Scripts: MIT. From the operators of https://silentpayments.net.
