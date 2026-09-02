# Silent payments light-client measurements

**The question:** a phone wallet cannot scan the blockchain itself, so it
downloads per-block "scanning data" from a server to discover incoming
[BIP-352 silent payments](https://bips.dev/352/). Three designs exist for that data. Until now, nobody
had measured what any of them actually costs. The [developer discussion](https://delvingbitcoin.org/t/silent-payments-light-client-protocol/891)
that needed these numbers stalled in June 2024 waiting for them.

**What we did:** measured all three designs across **every one of the 255,434
mainnet blocks** from taproot activation (block 709,656, November 2021) to
block 965,089 (September 2026). No sampling. Sources: a Bitcoin Core v31 node
and a production BlindBit Oracle v2, both queried locally.

## Results in one table

| what the wallet downloads | whole range | average per block | per day, following the chain* |
|---|---|---|---|
| stock [BIP-158](https://github.com/bitcoin/bips/blob/master/bip-0158.mediawiki) filter (what light wallets use today) | 5.78 GB | 22.6 KB | 2.8 MB |
| taproot-only filter ([proposed 2024](https://github.com/setavenger/BIP0352-light-client-specification), never built)** | 0.94 GB | 3.7 KB | 0.4 MB |
| complete scanning payload ([BlindBit v2](https://github.com/setavenger/blindbit-oracle), what ships) | 15.08 GB | 59.0 KB | 8.0 MB |

\* 144 blocks/day at recent-era (blocks 900k-965k) averages.
\*\* Estimated from exact per-block item counts; the size formula was validated
against real filter encodings of 21 sample blocks (within ~0.5%).

## The two findings

1. **The 2024 answer:** a filter tailored to silent payments would be about
   **6.1x smaller** than the stock BIP-158 filter wallets already download.
   This was the exact number requested in the discussion and never delivered.
2. **The 2026 tradeoff:** the server design that actually ships skips filters
   and sends complete scanning data instead. Filters are only hints: a
   filter-based wallet must also download the raw tweak values (6.2 GB over
   this range, more than the filters themselves) and a full block for every
   match. Compared end to end, the filter route costs about 7.1 GB against
   the payload route's 15.1 GB, so the shipping design pays roughly **2.1x
   the bandwidth for zero false positives and no block downloads while
   scanning**. Neither side of that trade had ever been quantified.

For scale: even the heaviest option is 8 MB per day on a phone.

## Caveats, honestly

- Taproot-only filter sizes are computed, not served bytes: no such filter is
  deployed anywhere. Item counts per block are exact; the byte estimate is
  the validated formula.
- Measured at dust limit 0 with no cut-through, so the two shrinkable
  mechanisms are shown at their upper bound.
- BIP-158 figures are REST body bytes (~0.16% above the raw filter).
- Full methodology and per-era breakdowns are in the collection scripts and
  the delving thread context.

## Files

- `comparison.csv`: per block: height, BIP-158 bytes, taproot item count and
  estimated bytes, v2 payload bytes, tweak count.
- `bip158.csv`, `oracle.csv`: the raw collected series.
- `gcs_validation.csv`: real filter encodings vs the size formula, 21 blocks.
- `collect_filters.py`, `collect_oracle.py`, `validate_gcs.py`,
  `summarize.py`: reproduce everything (needs a Core node with
  blockfilterindex plus a BlindBit v2 oracle; loopback only).

Also here: `SPCOMMIT.md`, the normative format for the per-block index
commitments the server publishes (the tamper-evident fingerprints), and
`spcommit-test-vectors.json`, five real-data vectors so any implementation can
verify byte-for-byte agreement.

Data: CC0. Scripts: MIT. From the operators of https://silentpayments.net,
where the index behind these numbers publishes [tamper-evident fingerprints](https://njump.me/npub1wc5were3y63h4nwcckdrw72gceh4kgz8eg7fz0zrk2xufr4dx9xqlvmcx8)
of everything it serves; plain-language story [here](https://bitsaga.be/insights/the-server-that-can-be-caught-lying).
