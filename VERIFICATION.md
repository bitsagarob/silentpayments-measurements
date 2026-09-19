# Verification

Independent recomputation of the BIP-352 tweak series in this repository,
against the reference implementation published with the BIP itself.
Run 2026-09-18, bitcoin mainnet.

## What was compared

| | |
|---|---|
| Object compared | The per transaction BIP-352 tweak, `input_hash * A_sum`, serialised as a 33 byte compressed point |
| Per height, compared | block hash, tweak count, tweak list as an ordered sequence, tweak list as a multiset |
| Also compared | tweak count against the `tweaks` column of `oracle.csv` |
| Heights | 529 distinct, spanning 709,656 to 965,089 |
| Tweaks | 526,166 |
| Disagreements | 0 |

## Implementations

| Role | Implementation | Version |
|---|---|---|
| A | BIP-352 reference implementation, Python, vendored unmodified from the `bip-0352/` directory of github.com/bitcoin/bips | see file digests below; `bip-0352/` head at `1259a23acc3c9ff0d750028e1c3be6f1e1718f99`, 2026-05-15 |
| B | BlindBit Oracle v2, Go | binary build metadata `vcs.revision=7317cd00bfd7674d77a8693082fe15e93c23d664`, `vcs.time=2026-09-02T19:03:40Z`, `vcs.modified=true`, `go1.27.0` |
| Block data for A | Bitcoin Core, REST on `127.0.0.1:8332` | daemon reports `v31.1.0` |
| Host | Linux 6.8.0-138-generic x86_64, Python 3.12.3 | |

A and B share no code. A derives every tweak from raw block and prevout data
fetched over Core REST. B serves its own PebbleDB index built by its own Go
implementation of BIP-352.

BlindBit provenance, read from the running process image and from the git
repository the binary was built in:

| | |
|---|---|
| Fork | `bitsagarob/blindbit-oracle` at `7317cd00bfd7674d77a8693082fe15e93c23d664` ("feat(full-block): opt-in include_input_only") |
| Upstream base | `setavenger/blindbit-oracle` at `bd17922efbff8a2058dfea434f9c690e8f06f934` ("add GetSpentOutputsShort endpoint", 2026-05-27) |
| `bd17922` is an ancestor of `7317cd0` | yes, verified with `git merge-base --is-ancestor` |
| Commits in `bd17922..7317cd0` | 2: `039fc5b` (chaininfo `warnings` JSON type), `7317cd0` (opt-in `include_input_only` on the HTTP `/full-block` route) |
| Working tree at build time | `vcs.modified=true`, explained. The build writes its output binary `blindbit-oracle` into the repository root, and that path is absent from `.gitignore`, so the build's own artefact makes `git status --porcelain` non-empty and Go records the tree as modified. Reproduced on 2026-09-18: a pristine checkout of `7317cd0` builds with `vcs.modified=false`, and the same checkout with only that one untracked binary present builds with `vcs.modified=true`. |
| Rebuild comparison | **Byte identical.** Rebuilding `7317cd0` at the same absolute path with go1.27.0 reproduces the running binary exactly (`cmp`, no differing byte). The running binary therefore carries no uncommitted source change. |

Vendored reference files, sha256, each byte identical to the same path under
`bip-0352/` on `bitcoin/bips` master as fetched 2026-09-18:

| File | sha256 |
|---|---|
| `verify/reference.py` | `a0bc88e8024dff880e6c89a1330557b6177b0dfa284931033cd0a77d1d387912` |
| `verify/bitcoin_utils.py` | `80dd73fd9aafea15a37879124bafe4a59aa78f76de2d7d778ed0a62f2c49e7b5` |
| `verify/bech32m.py` | `b38e16a9a2f3960945773ccad020d15cd27dd1871c5a9dd26147a8fa9b14df5b` |
| `verify/ripemd160.py` | `99da6dafa9804d3ca5490a736354027b10ec3d517206caad6ea28c0e097f6b9a` |
| `verify/secp256k1lab/bip340.py` | `428ee8110175b32b67d22a88efe07a44cede2419d0f547949164f2a8f9d76b96` |
| `verify/secp256k1lab/ecdh.py` | `8ee93a3442bce4c438bd6373565071a09fd7c1075e998b7e90b51ae17a8df0e1` |
| `verify/secp256k1lab/__init__.py` | `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` |
| `verify/secp256k1lab/keys.py` | `25a7c9d4d70dec7acea57245a529ef5f8454616d075a31fe27964d3e237c2860` |
| `verify/secp256k1lab/secp256k1.py` | `3a3316ea6717f8dd6d89eb65e80a09265551955d5c9eb872fae3e12504cc63b0` |
| `verify/secp256k1lab/util.py` | `3aeccf814f0bd67cdfb0791a6bf054b367c580942acd44942fdf505e5a1af707` |
| `verify/send_and_receive_test_vectors.json` | `f5f9ed4afd76a1b76f3c70b1cbe67532f89abbe559f8e02d7fc3d8ecb93af4a1` |

Reference self-test, run from this repository on 2026-09-18:
`python3 verify/reference.py verify/send_and_receive_test_vectors.json`
prints `All tests passed`, exit 0.

## Method

Two legs. Both compare implementation A against implementation B.

| Leg | Script | B reached over | Comparison |
|---|---|---|---|
| 1 | `verify/sweep-verify.py` | HTTP `GET http://127.0.0.1:8010/tweaks/{height}` | block hash, count, ordered sequence, multiset |
| 2 | `verify/grpc-leg.py` | gRPC `blindbit.oracle.v1.OracleService/StreamComputeIndex` on `127.0.0.1:8011`, request body `{"dustlimit": 0, "cut_through": false}` | sha256 of the sorted tweak list against leg 1's reference digest, and item count against `oracle.csv` |

Leg 2 exists because `oracle.csv` was collected over the gRPC route
(`collect_oracle.py`), not over the HTTP route. Leg 2 queries that same route
with the same request body.

Per height, leg 1:

1. Core REST `blockhashbyheight/{height}.json` gives the block hash.
2. `verify/verify_block_lib.py` walks the block, skips the coinbase, skips
   transactions with no taproot output, builds `VinInfo` per input from the
   raw `scriptSig`, `txinwitness` and the prevout `scriptPubKey` fetched over
   REST, calls the reference `get_pubkey_from_input`, sums the non infinity
   keys, skips the transaction if the sum is the point at infinity, calls the
   reference `get_input_hash`, and emits `input_hash * A_sum` compressed.
3. BlindBit is asked for the same height. The block hash it reports is
   compared against Core's.
4. Counts, ordered sequences and multisets are compared. A mismatch triggers a
   second recomputation with txid attribution, so offending transactions are
   named, not summarised.

Parallelism: 4 worker processes. Neither server was restarted or reconfigured.

## Heights swept, and how they were chosen

Deterministic, computed by `select_heights()` in `verify/sweep-verify.py` from
`oracle.csv`. Six strata, unioned and deduplicated.

| Stratum | Rule | Heights | Span |
|---|---|---:|---|
| A | 400 evenly spaced over the measured range, step 640 | 400 | 709,656 to 965,089 |
| B | the first 40 heights of the range, contiguous | 40 | 709,656 to 709,695 |
| C | the last 40 heights of the range, contiguous | 40 | 965,050 to 965,089 |
| D | the 20 densest blocks in `oracle.csv` by `tweaks` | 20 | 791,432 to 868,494 |
| E | the 20 densest blocks with 800,000 <= height <= 850,000 | 20 | 802,630 to 849,495 |
| F | 20 blocks that `oracle.csv` records with `tweaks` = 0, evenly spaced over the 8,720 such blocks | 20 | 709,657 to 965,038 |
| | union, deduplicated | **529** | 709,656 to 965,089 |

D and E overlap on 8 heights. A and D do not overlap.

Stratum D includes 791,433, the single densest block in `oracle.csv`
(7,334 tweaks). It was swept and matched.

Distribution of the 529 swept heights:

| Band | Blocks swept | Tweaks compared | Densest block swept in band |
|---|---:|---:|---|
| 709,656 to 749,999 | 118 | 330 | 726,941 (18) |
| 750,000 to 799,999 | 84 | 56,569 | 791,433 (7,334) |
| 800,000 to 849,999 | 98 | 230,279 | 843,420 (7,149) |
| 850,000 to 899,999 | 87 | 153,064 | 853,021 (7,159) |
| 900,000 to 965,089 | 142 | 85,924 | 919,636 (4,769) |
| total | 529 | 526,166 | 791,433 (7,334) |

## Results

Leg 1, reference against BlindBit over HTTP:

| Measure | Count |
|---|---:|
| Blocks compared | 529 |
| Blocks where every check passed | 529 |
| Tweaks compared | 526,166 |
| Blocks where BlindBit's block hash equals Core's | 529 |
| Blocks where the tweak lists are equal as ordered sequences | 529 |
| Blocks where the tweak lists are equal as multisets | 529 |
| Blocks where the reference count equals `oracle.csv` `tweaks` | 529 |
| Blocks with zero eligible transactions, both sides agreeing on zero | 54 |
| Disagreements | 0 |
| Reference errors | 0 |
| BlindBit errors | 0 |
| Wall clock | 1,642 s, 4 workers |

Leg 2, reference against BlindBit over the gRPC route that produced `oracle.csv`:

| Measure | Count |
|---|---:|
| Heights queried | 529 |
| Heights where the gRPC sorted tweak digest equals the reference sorted tweak digest | 529 |
| Heights where the gRPC item count equals `oracle.csv` `tweaks` | 529 |
| Tweaks compared | 526,166 |
| Disagreements | 0 |
| Wall clock | 19 s |

Note on ordering: over HTTP, BlindBit returns tweaks in the same order the
reference emits them, so the stronger ordered comparison holds for all 529
blocks. Over gRPC the order differs, so leg 2 compares multisets.

Per height records: `verify/sweep-results.jsonl` (leg 1),
`verify/grpc-leg-results.jsonl` (leg 2).

## Disagreements

None. Zero heights in either leg. No txids to report.

## Not covered by this check

| Item | Status |
|---|---|
| The 254,905 heights of the measured range not in the 529 block plan | not checked |
| Frigate | not checked. Verified 2026-09-18: the Frigate on `127.0.0.1:50021` answers `server.version` with `["Frigate 1.5.3","1.4"]` and answers `blockchain.silentpayments.tweaks` with `{"code":-32601,"message":"Method not found"}`. Nothing listens on `127.0.0.1:50031`, connection refused. This is a two implementation check, not three. |
| `taproot_n`, `v2_bytes` in `oracle.csv` | not checked. Only the `tweaks` column was compared. |
| `bip158.csv`, `gcs_validation.csv`, `comparison.csv` | not checked |
| Bitcoin Core's own block and prevout data | not independently checked. Both implementations read the same node, so a fault in that node's block data would not be caught by this comparison. |
| The `dustlimit` and `cut_through` request parameters | not independently tested here. The 529 block agreement is consistent with the claim in `PROVENANCE.md` that BlindBit Oracle v2 applies neither, but this check does not vary those parameters. |
| The receiving and scanning side of BIP-352 | not checked. Only the tweak the index serves was compared, not output key derivation, label handling or spending. |
| The exact source of the running BlindBit binary | covered. A same-path rebuild of `7317cd0` is byte identical to the running binary. |
| Anything about a released or third party BlindBit build | not covered. The binary checked is the one running on this host. |

## Reproduce

From a checkout of this repository, with a fully synced Bitcoin Core with
`rest=1` on `127.0.0.1:8332` and a BlindBit Oracle v2 on `127.0.0.1:8010`
(HTTP) and `127.0.0.1:8011` (gRPC):

```
python3 verify/reference.py verify/send_and_receive_test_vectors.json
python3 verify/sweep-verify.py --plan
python3 verify/sweep-verify.py --run --workers 4
python3 verify/grpc-leg.py
```

`verify/verify_block_lib.py` and the vendored reference files are byte
identical copies of the tooling in
`bitsaga/services/silentpayments/oracle/`. `verify/sweep-verify.py` and
`verify/grpc-leg.py` were written for this verification.
`verify/grpc-leg.py` needs `grpcurl` at `~/.local/bin/grpcurl`.

Licence of the vendored reference files: BSD-2-Clause, see
`verify/LICENSE-BIP352.txt`. It covers only `verify/reference.py`,
`verify/bitcoin_utils.py`, `verify/bech32m.py`, `verify/ripemd160.py`,
`verify/secp256k1lab/` and `verify/send_and_receive_test_vectors.json`.
