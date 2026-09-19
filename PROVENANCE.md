# Provenance

Every value in this repository comes from the run described here. Facts only.

## Range

| | |
|---|---|
| Chain | bitcoin mainnet |
| First height | 709,656 |
| First block hash | `00000000000000000004d3108aa91c58d85027536139dcc359f5926a871b2111` |
| Last height | 965,089 |
| Last block hash | `00000000000000000001aac3149e56d0328dcf2d53517f9af71b7f8463694854` |
| Blocks | 255,434 (no sampling) |
| Collected | 2026-09-02 |

## Sources

| | |
|---|---|
| Node | Bitcoin Core v31.1.0, REST on loopback, `blockfilterindex=1` |
| Indexer | BlindBit Oracle v2, gRPC on loopback |
| Indexer source | `bitsagarob/blindbit-oracle` @ `7317cd0` |
| Indexer upstream base | `setavenger/blindbit-oracle` @ `bd17922` |
| Local delta | 2 commits: `039fc5b` (chaininfo `warnings` JSON type) and `7317cd0` (opt-in `include_input_only` query parameter on the HTTP `/full-block` route). Neither is on the `StreamComputeIndex` path used for `oracle.csv`. |

## Measurement definitions

| Column | Definition |
|---|---|
| `bip158_bytes` | HTTP body bytes of `/rest/blockfilter/basic/<hash>.bin`, as served. Includes the 33-byte type+blockhash prefix and the compactsize length, ~0.16% above the raw filter. |
| `taproot_n` | Count of taproot outputs of BIP-352-eligible transactions, exact, from `StreamComputeIndex` (`len(outputs_short)/8`). |
| `taproot_filter_bytes` | The real encoded size of a BIP-158 style filter over the block's distinct taproot output keys. Not modelled: siphash-2-4 and Golomb-Rice actually run, `P=19, M=784931`, element set deduplicated as BIP-158 and Bitcoin Core do. Measured twice by independently written C implementations that agree on all 255,434 blocks with zero differing bytes, each first proved byte-for-byte identical to Core's own basic filters (11,275 and 1,283 blocks, zero mismatches). Per block in `taproot_filter.csv`. The earlier modelled figure of 0.943 GB fed the size formula the raw output count instead of the element count and was 2.9x too high. |
| `v2_bytes` | `32 + 33 + len(outputs_short)` summed over the block's index items: txid, tweak, and the 8-byte output-key prefixes. Wire payload, no framing or compression. |
| `tweaks` | Count of BIP-352-eligible transactions in the block. |

## Filtering: none, and none is available

`collect_oracle.py` requests `{"dustlimit": 0, "cut_through": false}`.

BlindBit Oracle v2 applies neither, at any setting. Four functions in
`internal/database/dbpebble/read.go` implement dust and cut-through filtering
(`TweaksForBlock`, `FetchOutputsCutThroughDustLimit`, `TweaksForBlockCutThrough`,
`TweaksForBlockCutThroughDustLimit`); none of the four has a caller. `StreamComputeIndex` and
`StreamBlockScanDataShort` accept `dustlimit` and `cut_through` on
`RangedBlockHeightRequestFiltered` and read neither field; upstream documents both as reserved and
"not yet applied by the server" (`internal/server/GRPC.md`, lines 89-90, commit `8ca09b9`,
2026-05-27). The three `tweaks_*` configuration flags reach only the `/info`
response body and two startup checks (a warning when all three are false, a fatal error
when cut-through is combined with `tweaks_only`). They change neither indexing nor serving.
`internal/indexer/` contains no dust or spentness branch at all.

Verified on the live server: `StreamComputeIndex` for height 900,000 returns byte-identical
39,677-byte responses for `{"dustlimit": 0, "cut_through": false}` and for
`{"dustlimit": 100000000, "cut_through": true}`.

So the figures here are not a conservative choice. They are what the shipping server
serves, because it serves nothing else.

## Reproduce

`summarize.py` rebuilds `comparison.csv` from `bip158.csv`, `oracle.csv` and
`taproot_filter.csv`, and prints every
figure quoted in `README.md`. It needs no node and no indexer. `comparison.csv` is not
committed because it is fully derived.
