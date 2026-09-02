# BIP-352 Light Client Protocol, converged pre-draft

**Status: pre-draft v0.1, for discussion. Not a BIP. Not final anywhere.**

This document attempts to converge, into one specification, the two existing spec efforts
and the code that actually shipped:

- [setavenger/BIP0352-light-client-specification](https://github.com/setavenger/BIP0352-light-client-specification)
  (the client-side workflow, written 2024 against BlindBit Oracle v1, dormant since Nov 2024)
- [silent-payments/BIP0352-index-server-specification](https://github.com/silent-payments/BIP0352-index-server-specification)
  (the server-side capability catalogue, dormant since Oct 2025)
- BlindBit Oracle v2 as deployed (gRPC, filters removed, new spent-output semantics), which
  contradicts both documents
  ([lcspec issue #2](https://github.com/setavenger/BIP0352-light-client-specification/issues/2),
  [index-server-spec PR #1](https://github.com/silent-payments/BIP0352-index-server-specification/pull/1))
- the conclusions of the 2024 delving thread
  [Silent Payments Light Client Protocol](https://delvingbitcoin.org/t/silent-payments-light-client-protocol/891),
  which neither spec absorbed
- the measurements in this repository, which answer the two open questions the 2024 thread
  stalled on

It is written by the operator of an independent production BlindBit Oracle v2 deployment
(full mainnet index, height 709,656 to tip). Corrections and objections are the point:
file them against this repo, or in either spec repo's thread.

Authorship note: the intended home of a converged spec is not this repository. This file
exists so there is a concrete document to disagree with. If the working group prefers to
adopt, rewrite, or cannibalise it into either existing repo, that is success, not theft.

---

## 1. Motivation

One protocol, four wire formats, zero interoperability. Today:

| Format | Served by | Spoken by | Status |
|---|---|---|---|
| BlindBit v1 HTTP-JSON | nobody (removed) | every shipped spdk/Dana build | clients orphaned |
| BlindBit v2 gRPC | blindbit-oracle deployments (setor.dev, ours) | blindbit-cli, blindbit-desktop, spdk v2 branch | live, undocumented in any spec |
| Cake Electrum dialect (`blockchain.tweaks.subscribe`) | Cake's servers | Cake Wallet | live, documented nowhere but client source |
| Bare per-block tweak array | silentiumd; Bitcoin Core's unmerged index ([Sjors/bitcoin#86](https://github.com/Sjors/bitcoin/pull/86)) | | the shape Core could one day serve |

A wallet team cannot switch providers without an architecture change. A third-party
developer building an Electrum silent-payments plugin reported the server spec as their
main blocker
([delving 1816, post 17](https://delvingbitcoin.org/t/stealth-addresses-using-nostr/1816/17)).
And the absence of any integrity mechanism has already cost real users: Cake's 2024
"BTC in the void" incident ([cake_wallet#1564](https://github.com/cake-tech/cake_wallet/issues/1564),
post-mortem in [#2395](https://github.com/cake-tech/cake_wallet/issues/2395)) combined a
silently faulty feed, irreversible server-side cut-through, and no client-side detection,
so payments became undetectable through the protocol with no self-healing path.

The index-server spec states the goal this draft serves: "common endpoints across service
providers will allow users and developers the freedom to migrate to the best service
provider without requiring architectural changes."

## 2. Definitions

- **Tweak**: the per-transaction 33-byte compressed public key `input_hash * A_sum`
  defined by BIP-352, sufficient for a client holding a scan secret to derive the
  transaction's candidate silent-payment outputs.
- **Indexer**: a server that computes and serves per-block tweak data and auxiliary
  scanning data. Called tweak server, oracle, or index server elsewhere; one thing.
- **Light client**: a wallet that scans via an indexer instead of its own node, and that
  reveals to the indexer nothing more specific than interest in whole blocks.
- **Cut-through**: omitting or deleting tweaks of transactions whose taproot outputs are
  all spent. Reduces data (~38% historically per setavenger, unmeasured recently) at the
  cost of historical rescan completeness.
- **Match**: a client-side equality between a derived candidate output key and an output
  identifier served for a block.

## 3. Threat model

Absent from both existing specs, and the direct cause of the 2024 design drift. Normative
reading: a conforming client MUST assume the indexer is adversarial in exactly the ways
listed here.

### 3.1 What an indexer can never learn, by construction

A client that follows this spec sends only block-range requests, carrying no keys, no
addresses, no outpoints, and no match feedback. The indexer cannot distinguish which of a
block's tweaks, if any, interested the client. This is the protocol's core invariant,
inherited from setavenger's spec: **interest is expressed at block granularity only**.

### 3.2 What a malicious indexer can do, and the accepted defence

The 2024 thread settled this
([harding, posts 12 and 14](https://delvingbitcoin.org/t/silent-payments-light-client-protocol/891/12);
conceded in post 15). Summarised because the draft's normative choices depend on it:

An indexer that wants the network identity behind silent-payment address X can serve
scanning data that only X's owner will act on, then observe who acts. In its strongest
forms the served data is **entirely honest**: a phantom-transaction filter built from a
never-broadcast double-spend of a real payment (only the filter is fake, and only
recomputation from the block detects it); a legitimately mined block containing only a
payment to X; or plain dust spam to X across several blocks, watching who fetches
follow-up data every time. No integrity mechanism detects the last two, because there is
nothing false to detect. The leak channel is the client's **conditional fetch behaviour**.

Therefore, normatively:

1. On any match, the client MUST fetch the **full block**, and SHOULD fetch it from a
   source unlinkable to its indexer requests (a random full node, a different network
   identity, ideally an ephemeral Tor circuit). A client that fetches per-match
   "simplified UTXO" data from the indexer converts every match into a targeted
   deanonymisation beacon. This retires the simplified-UTXOs-on-match flow of the 2024
   client spec, as the thread itself concluded and as the index-server spec's comparison
   table already states ("Should download full block on filtered match").
2. Full-block fetching also makes a BIP-352 light client's network behaviour
   indistinguishable from an ordinary BIP-158 client's, which is itself cover.
3. Clients that expect more than about one payment a day SHOULD run their own
   infrastructure; the light protocol optimises the low-volume common case.

### 3.3 What integrity commitments do and do not buy

An indexer can also cheat by **omission** (drop one tweak; the wallet behind it silently
never sees its money; this is the Cake incident's failure class) and by **equivocation**
(serve complete data to everyone except one target). Per-block commitments over the
served data, chained and checkpointed outside the operator's control, make both
**detectable and attributable after the fact**, including by third parties and rival
servers (see section 9).

Scope this honestly: commitments do **not** defeat the section 3.2 attack, whose winning
variants serve honest data, and audits are retrospective, so they never protect the first
victim. Commitments and full-block-on-match are complementary layers, not substitutes.
Any text implying a committed server is therefore safe to fetch matches from is wrong.

### 3.4 The BIP-37 lesson, applied

Every tunable that trades privacy against bandwidth will be tuned toward bandwidth by
wallets (BIP-37's false-positive rate proved it). This draft therefore makes the private
behaviour the **default and cheapest** path: full-block-on-match is normative, dust
filtering defaults to off, and no request parameter narrows interest below a block.

### 3.5 Out of scope: the custodial shape

Servers that take the client's **scan private key** (Frigate-style
`blockchain.silentpayments.subscribe`, Cake's hosted scanning, any "remote scanner") are a
different trust model: the operator can link every payment the wallet ever receives,
retroactively, and "keys held in RAM only" is a promise, not a property. That model is
legitimate for self-hosted deployments (the "My Scanner" stack of the index-server spec)
and out of scope here. A server MUST NOT describe scan-key custody as conforming to this
protocol.

## 4. Data model

Tiered, so that every real server class can conform to some tier, including a future
Bitcoin Core index that will plausibly serve nothing but bare tweak arrays.

### Tier 0: tweak list (minimum conforming indexer)

Per block: the list of 33-byte tweaks of eligible transactions (eligibility per BIP-352),
plus the block hash and height. Nothing else. Satisfiable by Core's prospective
`-bip352index` and by silentiumd today.

### Tier 1: compute index (indexed tier)

Per block, per eligible transaction: `txid`, `tweak` (33 bytes), and `outputs_short`, the
list of 8-byte prefixes of the x-only public keys of the transaction's taproot outputs.
Optionally per block: `spent_outputs`, the list of 8-byte prefixes of the x-only keys of
outputs **spent** in the block (for wallet spent-detection). This is shipped BlindBit v2's
shape, chosen here as the canonical indexed tier because three independent clients
already consume it.

Matching in tier 1 is prefix equality between derived candidate keys and `outputs_short`
entries. An 8-byte prefix has negligible false-positive probability against a wallet's
own derived keys (~2^-64 per pair) but a nonzero block-level collision rate; either way a
match leads to the full-block fetch of section 3.2, which resolves it.

### Optional profile: taproot-only block filters

The 2024 client spec's BIP-158-style filter over new taproot output keys, measured in
this repository at ~6.1x smaller than stock BIP-158 over full history (0.94 GB vs
5.78 GB; the gap is not closing with taproot adoption, contrary to 2024's conjecture).
Kept as an **optional bandwidth profile**, not the mandatory path, because the shipped
ecosystem dropped filters and because a filter's false-positive rate is dual-use: a
bandwidth knob and plausible-deniability cover for the section 3.2 phantom-filter
variant. A server offering this profile MUST publish the GCS parameters (P, M) and the
filter-type identifier; the 2024 spec never pinned them, which this draft considers a
blocking gap for the profile, not for the protocol.

The full-history cost comparison this draft inherits from the measurements: a complete
filter stack (filters + raw tweaks) is ~7.1 GB; the tier-1 self-contained payload is
~15.1 GB, about 2.1x, in exchange for zero false positives and no per-match fetch
against the indexer. Both are dust-limit-0, no-cut-through upper bounds.

### Spent-output identifier: decision and rationale

Three shipped answers exist: salted outpoint hashes `sha256(outpoint || block_hash)[:8]`
behind a filter (v1, per the 2024 spec), raw unsalted 8-byte x-only key prefixes (v2),
and server-side omission with an optional spending-input marker (Cake). This draft
adopts **v2's raw 8-byte output-key prefixes** as canonical: it is what live servers
serve and live clients consume, it needs no filter machinery, and the data it reveals
(which outputs a block spends) is public chain data in any case. The salted design's
marginal obfuscation does not survive the fact that spentness is globally recomputable.
Servers MAY additionally serve the salted form for v1 compatibility; new clients SHOULD
NOT depend on it. If the working group overrules this, the salt's serialization must be
pinned this time; the 2024 text left the block-hash byte order in the preimage ambiguous.

### Byte order, said once, with vectors to follow

In JSON bindings, hashes are hex strings in standard display order. In binary bindings,
`txid` and `block_hash` fields are raw bytes in **display order** (verified against a
live v2 deployment; note that upstream documentation calls this order "little-endian",
which is exactly backwards, and that outpoints embedded in v2's full-block `inputs`
field use internal order, the opposite of the top-level fields in the same message).
This draft bans the words big-endian and little-endian from all future text in favour of
"display order" and "internal order" plus byte-level test vectors. Getting this wrong
produced a real bug in the one client migration attempted so far: every reported
outpoint byte-reversed, spends impossible.

## 5. Capability discovery

Scalar version numbers rot (the Electrum protocol's forked 1.4/1.5/1.6 lines collide
across implementations). This draft uses **named capability flags**, BOLT-style,
returned by an `info` call and required before use of anything optional:

```
network            main | test | signet | regtest
height             current tip
tiers              [0] | [0,1]
filters            absent | { type_id, P, M }
spent_outputs      absent | prefix8
dust_filtering     none | request      (client-requested, echoed per response)
cut_through        none | request | always
prune_horizon      absent | height     (below this, cut-through history is gone)
commitments        absent | { scheme, publication }
```

Two rules the shipped world currently violates: a server MUST NOT silently ignore a
request parameter it advertises (v2's REST layer today accepts and ignores dust and
cut-through parameters); and a server that prunes (cut-through or partial history) MUST
advertise its horizon, because Cake's incident shows what silent pruning does to rescue
scans. A request the server cannot honour MUST be an error, not a degraded answer.

## 6. Transports

One data model, two normative bindings, mirroring what exists:

- **HTTP-JSON**: `GET /info`, `GET /tweaks/{height}` (tier 0),
  `GET /compute-index/{height}`, `GET /spent-outputs/{height}` (tier 1), with an
  explicit error object. Range requests via repeated single-height calls or a
  `?start=&end=` extension; servers advertise limits.
- **gRPC**: the shipped v2 surface (`GetInfo`, `GetBestBlockHeight`,
  `GetBlockHashByHeight`, `StreamComputeIndex`, `StreamBlockScanDataShort`,
  `GetFullBlock`, `GetSpentOutputsShort`), adopted as-is with the section 4 byte-order
  and capability rules layered on.

Electrum-verb bindings (`blockchain.tweaks.subscribe` and relatives) are acknowledged as
a live third dialect and left to a compatibility appendix: they presuppose the
subscription model and, in Cake's shipped form, omit block hashes entirely, which
section 7 forbids.

Every per-block payload, in every binding, MUST carry the block hash and height.

## 7. Reorg handling

Nobody specifies this today. Minimum procedure: clients track the (height, hash) of each
scanned block; on each sync, re-fetch the current hash at the last scanned height; on
mismatch, walk back until hashes agree and rescan forward. Servers MUST serve identified
(height, hash) data for stale branches for at least N blocks of depth, or answer with an
explicit gone-error that distinguishes "reorged away" from "not yet indexed". The value
of N and the stale-branch retention question are open items for implementers.

## 8. Client obligations

Carried over from the 2024 spec because they are correct and easy to lose:

- Dust limit is client-chosen, **default 0**. A non-zero limit is a completeness trade
  the user consents to, not a server default.
- A wallet MUST permanently track its own previously matched scriptPubKeys, because
  senders demonstrably reuse derived bc1p addresses out-of-band, invisible to any scan.
- Wallet state should live in one instance; concurrent instances diverge on unconfirmed
  data. Multi-device wants your own scanner, not this protocol.
- On any match: full block, separate identity (section 3.2). Not optional.

## 9. Integrity commitments (optional capability)

The index-server spec asks, verbatim: "How does a wallet know all tweaks were received
for a given block request?" This section is the current live answer; it is optional
because tier-0 conformance must stay Core-satisfiable.

A committing server publishes, per block, a digest binding everything it serves for that
block (tweak set, and spent-output set where offered), each digest chained to its
predecessor, and periodically **checkpoints the chain head to a venue outside its own
control** (this deployment: nostr events on public relays, every six hours). Anyone with
a node can recompute any block's digest from consensus data and the spec, so omission
contradicts the published chain, and two clients served different data hold mutually
incompatible proofs. Detection is attributable to third parties, including rival servers,
which turns "trust me" into "catch me".

Properties, restated within section 3.3's limits: detects omission and equivocation
after the fact; does not detect honest-data unmasking attacks; never protects the first
victim. The concrete scheme this deployment runs, with test vectors, is
[SPCOMMIT.md](./SPCOMMIT.md) in this repository; its serialization is explicitly open
for feedback before it ossifies, and the digest definition is deliberately
transport-agnostic so an HTTP server, a gRPC server and, one day, a P2P-serving node can
emit identical chains. Cross-server digest comparison is exactly the check the
[tweak-service-auditor](https://github.com/silent-payments/tweak-service-auditor) gropes
toward with full-data comparisons; digests make it cheap.

## 10. Test vectors and the interoperability gate

- Tweak computation is covered by BIP-352's vectors; block-level canonical outputs
  belong in the tweak-service-auditor's `test_data` framework
  ([auditor issue #1](https://github.com/silent-payments/tweak-service-auditor/issues/1)),
  which this draft adopts as the vector home rather than inventing one.
- Byte-order vectors (section 4) and commitment vectors
  ([spcommit-test-vectors.json](./spcommit-test-vectors.json)) exist in this repository.
- Promotion rule, borrowed from the BOLT process because it is the best-validated device
  in bitcoin standardisation: **nothing in this document is final until two independent
  implementations interoperate against it**. One implementation slot is filled
  (blindbit-oracle v2 plus its clients); the second slot is open, and filling it is the
  gate, not review consensus.

## 11. Explicitly deferred

- **Consensus commitment of the tweak set** (the endgame where servers become
  untrusted couriers): deferred to a one-line reservation. This draft's structures keep
  a reserved type/capability hook so a future committed structure can slot in without a
  flag day, on the precedent of BIP-158's reserved filter-type byte. Specifying more
  today would repeat the scope mistake that killed three prior Core attempts.
- **Out-of-band payment notifications** (nostr or otherwise,
  [delving 2203](https://delvingbitcoin.org/t/silent-payments-notifications-via-nostr/2203)):
  an optimisation layer over scanning, never a replacement; nothing here depends on it.
- Mempool/unconfirmed scanning, transaction broadcast, address-history convenience APIs,
  server incentive schemes, and libsecp256k1 light-client APIs (upstream deferred them;
  this spec must not couple to that timeline).

## 12. Deprecations this draft names

- **BlindBit v1 HTTP-JSON**: removed server-side, still spoken by every shipped
  spdk/Dana build. Servers MAY bridge it (a v1-to-v2 shim is ~days of work); the shape
  is otherwise historical.
- **Cake's `blockchain.tweaks.subscribe` dialect**: live, undocumented outside client
  source, carries no block hashes, always cut-through, no integrity story. Its users
  deserve a documented migration path to a conforming tier.

## Appendix A: measured costs (from this repository, all 255,434 blocks, 709,656 to tip)

| Quantity | Value |
|---|---|
| Eligible-transaction tweaks | 187,814,353 (~6.2 GB raw, avg 735/block, era-skewed) |
| Stock BIP-158 filters, full history | 5.78 GB |
| Taproot-only filter, full history | 0.94 GB (~6.1x smaller; 3.2x at the inscription peak) |
| Tier-1 self-contained payload, full history | 15.08 GB (~2.1x the complete filter stack, zero false positives) |
| Full serving index on disk (v2, both dust modes) | ~109 GB |

All values dust-limit 0, no cut-through: upper bounds. Reproduction scripts in this
repository.

## Appendix B: what this draft settled by adoption rather than argument

For reviewers checking the receipts: full-block-on-match (delving 891 posts 12 to 15);
dust as client parameter (891 post 3, already shipped); tweaks and filters fetched
together where filters exist (891 posts 3/5); the three-stack deployment taxonomy and
the capability-discovery idea (index-server spec); the block-granular privacy invariant,
paid-scriptPubKey tracking, and the single-instance caveat (light-client spec); the
tier-1 wire shapes (shipped BlindBit v2); named capability flags over scalar versions
(Electrum's forks as the cautionary tale); the two-implementation interop gate (BOLTs).
