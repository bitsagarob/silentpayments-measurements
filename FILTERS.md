# What dust filtering and cut-through would save

The figures in `README.md` are measured with no dust limit and no cut-through, because
BlindBit Oracle v2 serves nothing else (see `PROVENANCE.md`). This file measures what the
two filters would save if a server applied them.

## The two filters

| Filter | Rule |
|---|---|
| Dust limit | Skip outputs below a value threshold. |
| Cut-through | Skip outputs already spent at a stated block height. |

Dust has two defensible readings. Per transaction: keep the transaction, with all of its
surviving output prefixes, when at least one of them reaches the limit. This is the reading
of the v1 `/tweaks?dustLimit=` endpoint and of the dormant `TweaksForBlock` in v2. Per
output: drop each output below the limit individually. **Measured over 120,000 comparisons,
the two readings keep exactly the same set of transactions.** They differ only in how many
8-byte prefixes each kept transaction carries, so the choice is bandwidth, never
completeness.

## Restoring the full range, blocks 709,656 to 965,089

Spentness pinned at height 967,618, hash
`00000000000000000001f9ac88c21bded8c1ea380d41afc9d17193396687841c`.
At that height, 305,878,397 of the 359,001,723 tracked taproot outputs (85.2%) are spent.

| Dust reading | Dust limit | Cut-through | Transactions | Outputs | Payload | Share |
|---|---:|---|---:|---:|---:|---:|
| | 0 | no | 187,814,353 | 359,001,723 | 15,079,946,729 | 100.00% |
| | 0 | **yes** | 41,116,276 | 53,123,326 | 3,097,544,548 | **20.54%** |
| per tx | 546 | no | 169,398,662 | 335,921,080 | 13,698,281,670 | 90.84% |
| per tx | 546 | **yes** | 30,300,936 | 39,523,450 | 2,285,748,440 | **15.16%** |
| per tx | 1000 | no | 128,942,532 | 284,839,712 | 10,659,982,276 | 70.69% |
| per tx | 1000 | **yes** | 4,842,726 | 8,192,365 | 380,316,110 | **2.52%** |
| per output | 546 | no | 169,398,662 | 317,145,775 | 13,548,079,230 | 89.84% |
| per output | 546 | yes | 30,300,936 | 38,595,283 | 2,278,323,104 | 15.11% |
| per output | 1000 | no | 128,942,532 | 231,740,158 | 10,235,185,844 | 67.87% |
| per output | 1000 | yes | 4,842,726 | 5,909,506 | 362,053,238 | 2.40% |

A dust limit on its own removes 9.16% at 546 sat and 29.31% at 1000 sat, reading dust per
transaction. Cut-through on its own removes 79.46%. The two together remove 97.48%.

The step from a 546 sat limit to a 1000 sat limit under cut-through (15.16% to 2.52%) is
unspent 546 sat taproot outputs, inscription dust. Note what a 1000 sat limit costs: a
wallet using it will not see a genuine payment of 546 to 999 sats.

## Restoring only the recent era, blocks 900,000 to 965,089

65,090 blocks, 452.0 days. Same pin.

| Dust reading | Dust limit | Cut-through | Payload | Share | Per 144 blocks |
|---|---:|---|---:|---:|---:|
| | 0 | no | 3,632,123,858 | 100.00% | 8.035 MB |
| | 0 | yes | 391,226,472 | 10.77% | 0.866 MB |
| per tx | 546 | no | 3,396,664,680 | 93.52% | 7.515 MB |
| per tx | 546 | yes | 250,575,482 | 6.90% | 0.554 MB |
| per tx | 1000 | no | 3,153,513,834 | 86.82% | 6.977 MB |
| per tx | 1000 | yes | 106,196,887 | 2.92% | 0.235 MB |
| per output | 546 | no | 3,321,379,912 | 91.44% | 7.348 MB |
| per output | 546 | yes | 247,525,674 | 6.81% | 0.548 MB |
| per output | 1000 | no | 3,025,427,874 | 83.30% | 6.693 MB |
| per output | 1000 | yes | 99,853,455 | 2.75% | 0.221 MB |

**The cut-through rows of this table are not a live-sync cost.** An output in a new block
is unspent by definition, so cut-through saves a wallet following the chain nothing. Those
rows are the cost of restoring the last 452 days as of the pinned height, divided by that
many days. A wallet staying synced pays the `cut-through: no` rows, so 8.035 MB per day
today, or 7.515 MB with a 546 sat limit.

## Server cost

Measured once, on 1000 blocks at height 900,000, read-time filtering with no dedicated
cut-through index. **Single-source**: this is the one figure here with no independent second
measurement, and it was taken on a build that is not the running indexer, since v2 applies
no filtering at all. Treat it as an order of magnitude, not a number.

| Request | Per block | Extrapolated to 255,434 blocks |
|---|---:|---:|
| `cut_through: false` | 0.6 ms | 2m33s |
| `cut_through: true` | 485.5 ms | 34h27m |

Cut-through costs one spend-index lookup per output, so as a read-time filter the server
does about 800 times more work to send about 80% less data. No wallet can request that
live.

This is a build cost, not a per-request cost. A spent output never becomes unspent, so a
stored cut-through view only ever shrinks and can be patched as spends arrive rather than
recomputed. Derived from the measured totals, 305,878,397 spends of tracked outputs over
255,434 blocks is about 1,200 updates per block, against a ten-minute block interval. The
full cut-through payload is 3.1 GB, against the roughly 109 GB the unfiltered index already
occupies. A dust limit can be applied on top of the stored view without a second copy,
because the amounts are already indexed.

So the shape is one build of about 34 hours followed by ordinary operation. That
materialised index is what the `tweaks_cut_through_with_dust_filter` configuration flag is
named for; v2 does not build it (see `PROVENANCE.md`). A stale view is safe, only less
efficient: it may still carry outputs that have since been spent, and it can never omit an
output that is still unspent.

## Method

Two implementations, sharing no code, each computing the same quantities. **Neither is in
this repository**, so the figures above are not reproducible from this checkout. The
reproduction path is the method below plus the pinned tip.

| | Implementation 1 | Implementation 2 |
|---|---|---|
| Source of the eligible-transaction set | BlindBit Oracle v2 index | BlindBit Oracle v2 index |
| Source of amounts | the index | raw block bytes from Bitcoin Core REST |
| Source of spentness | the index's own spend index | every spend observed by parsing all 257,963 raw blocks from 709,656 to the pin, 394.5 GB, 1,746,761,072 non-coinbase inputs |
| Filter code | Go, `FetchComputeIndexFiltered` | C, independent |
| Pinned tip | 967,625 | 967,618 |
| Coverage | 20,000 heights, systematic | all 255,434 heights |

Reconciliation over the 20,000 heights both computed, 240,000 row comparisons:

| Comparison | Rows | Disagreements |
|---|---:|---:|
| All rows with `cut_through: false` | 120,000 | **0** |
| All rows with `cut_through: true` | 120,000 | 86 |

Every one of the 86 falls on one of 16 heights, and in every case implementation 1 reports
the smaller payload, which is the direction the 7-block gap between the two pins predicts.
Each of the 16 was then checked individually: the number of that block's tracked outputs
spent in blocks 967,619 to 967,625 equals the observed difference exactly, 16 out of 16. No
residual disagreement remains.

Other checks:

| Check | Result |
|---|---|
| Implementation 2 reproduces `oracle.csv` at dust 0, no cut-through | 255,434 of 255,434 heights exact, on all three columns |
| The index's amounts against Core's raw block bytes | 414,429 outputs over 250 blocks, 0 mismatches |
| The index's tracked-output set against every P2TR vout of the same transaction | 0 mismatches |
| Implementation 1 against a third route, Core REST `getutxos` | 5 blocks, exact on transactions, outputs and bytes |
| Implementation 1 at dust 0, no cut-through, against the unfiltered index | byte identical |

## Interaction with the commitments

`SPCOMMIT.md` commits to the `StreamComputeIndex` set requested with
`{"dustlimit": 0, "cut_through": false}`. A filtered response is a subset of that set, and
the client holds neither amounts nor spend data, so it cannot check the subset for
completeness.

What survives depends entirely on how cut-through is pinned.

| Property | Unfiltered, today | Cut-through pinned to the live tip | Cut-through pinned to fixed checkpoint heights |
|---|---|---|---|
| Two clients can confirm they were served the same bytes | yes | no | **yes** |
| An outside auditor can recompute and catch an omission after the fact | yes | no | **yes** |
| The client itself can prove nothing was silently dropped | no | no | no |

Pinning to the live tip makes the answer depend on when it was asked, so it is neither
reproducible nor commitable. Pinning to fixed checkpoint heights, for example every 1,000
blocks, makes it deterministic: the same request returns the same bytes indefinitely, so it
can carry its own commitment and be audited exactly as the unfiltered set is.

The third row is not recoverable by any pinning. Proving an omission was legitimate means
showing, per omitted transaction, that every one of its outputs was already spent, which
costs about as much data as sending the transaction would have. The commitment chain's
guarantee has always been detection by third parties after the fact rather than
verification by the client, and checkpoint pinning preserves that guarantee in full.

## Not covered

| Item | Status |
|---|---|
| The eligible-transaction set | taken from the index by both implementations. Verified separately against the BIP-352 reference implementation on 529 blocks and 526,166 tweaks; see `VERIFICATION.md`. |
| Stability of the cut-through figures | none. 85.2% spent is true at height 967,618 and grows. Re-pinning at 965,089 instead moves the cut-through payload by +0.74% at dust 0, +0.83% at 546, +2.80% at 1000. Never quote a cut-through figure without its pin. |
| A `dumptxoutset` snapshot | not used. Core RPC credentials were not reachable, so spentness was derived by parsing raw blocks instead. The pinned block-hash list is kept, so the derivation is repeatable. |
| The gRPC wire path of implementation 1 | not exercised end to end. The filter arguments are proven to reach the database layer by a test that was deliberately broken twice to confirm it fails. |
| Hash collisions in implementation 2's join | 96-bit keys, 1.75e9 lookups against 359M entries, about 1e-11. Zero duplicate outpoints were found. |
