# Private detection: can a server find your silent payments without learning they are yours?

**Verdict, 3 September 2026: no, not with any cryptography that exists, and the lane is
closed by arithmetic.** Every published scheme for "the server detects my messages without
learning they are mine" needs either a tag the sender attaches to each payment, or a
homomorphic evaluation of the receiver's curve math. Silent payments carry no sender tag by
design, and the homomorphic route costs about 100 machines per user. What remains is the
plain design already running: the phone scans on-device, and the server learns nothing
because everyone gets the same data. The one gap that lane really has, an iPhone in a pocket
not learning a payment arrived, is fixed with no cryptography at all. See "The blind push"
below.

This note exists so nobody here re-opens the question without a new number. Every claim is
labelled VERIFIED (read on the cited page or PDF) or INFERRED (arithmetic on verified
figures).

## The question

A BIP-352 receiver must test every silent-payment-eligible transaction: one 33-byte tweak
point per transaction from an index server, one ECDH plus a tagged hash plus a point add on
the phone. Measured volume on mainnet: 36,340 candidates a day, 13.3 million a year, 188
million since taproot activation. One test costs 35 to 65 microseconds on the ARM laptops and
x86 server that have been measured (below), so a year of chain is under 15 minutes on one
core. **The iPhone run itself is still pending**: the harness in `phonebench/` is built and
gated on finding a real mainnet payment, but no number has come off a device yet. Compute
is not the problem at any figure in that range. The two real
constraints were bandwidth, 33 bytes per candidate as a structural floor, and liveness on
iOS, where an app cannot scan while closed.

The question was whether Oblivious Message Retrieval, Fuzzy Message Detection, Private
Information Retrieval or fully homomorphic encryption could move the detection to the
server without the server learning anything.

## The deciding number

| Quantity | Value | Status |
|---|---|---|
| Cleartext ECDH per tweak, ARM laptops | 39.3 µs (libsecp256k1 bench, Snapdragon X Elite), 34.9 µs (Frigate, Apple M1) | upstream commit e2ead23 VERIFIED; the Frigate figure INFERRED from our benchmark notes |
| Cleartext ECDH per tweak, our x86 server | 62 to 72 µs (AMD EPYC, single core; 36,340 tweaks in 2.6 s on 2026-09-03) | measured, `phonebench/linux` |
| Cleartext ECDH per tweak on an iPhone | not yet measured | harness built, run pending |
| Full homomorphic ECDSA signature on secp256k1, Zama TFHE | "1-2 day on 64 cores machine" | VERIFIED [1] |
| Share spent on the scalar multiplication | "almost half of the final run time" | VERIFIED [1] |
| One encrypted-scalar point multiplication | 770 to 1,540 core-hours | INFERRED |
| Best 2026 improvement claimed for 256-bit modular FHE | "twenty times lower" latency, "about two thousand times lower" amortized | VERIFIED [2] |
| Optimistic amortized cost per tweak | about 23 core-minutes | INFERRED |
| Per user per day at 36,340 tweaks | about 13,900 core-hours | INFERRED |
| One 6-core server per day | 144 core-hours | arithmetic |

One dedicated machine serves about one percent of one user. The slowdown against the
clear is roughly 2 x 10^7 even at the slowest measured figure. The authors of the original OMR paper named this exact
"clueless" design and dismissed it: "This does not even require any new clues or clue keys,
since it reuses whatever means the system already has to define pertinence. Alas, for
typical protocols this would be completely impractical." (VERIFIED, [3] section 6.) No
paper through May 2026 attempts homomorphic ECDH over a stealth-address point.

## Why the cheap schemes do not fit

**Oblivious Message Retrieval is affordable and structurally wrong.** Server cost per
message per recipient fell from about 65 ms and "~$1.02 per million messages" in 2022 [3]
to 7.9 ms and "~$0.12 per million" in PerfOMR [4], 4.9 ms in the DoS-resistant variant
[5], about 1.7 ms in SophOMR [6], and roughly 0.05 ms in UnifOMR [7] (INFERRED from 25 s
per 2^19 messages). At PerfOMR speed one recipient-year of Bitcoin is 29 core-hours, so a
6-core box could serve about 1,800 users. The blocker is not cost. In every variant "a
sender generates a clue consisting of ℓ FHE ciphertexts, all encrypting 1's to the intended
recipient's clue key" (VERIFIED, [3]). The clue is 583 to 2,181 bytes per message. A silent
payment has no such field; adding one on-chain roughly doubles the transaction and marks it,
and adding one off-chain is the nostr notification with heavier cryptography. Either way it
needs the sender to cooperate, and the senders who matter most, a donation page or an
exchange withdrawal, never will.

**Fuzzy Message Detection has the same sender problem and a proven privacy decay.** The
flag ciphertext is sender-made: "flag ciphertexts are 68 bytes in size and require 1.927 ms
to generate, while testing a match requires only 0.548 ms" (VERIFIED, [8]). Seres, Pinter
and Burcsi show the anonymity set is about p times the user count, that "the two anonymity
sets intersect with constant probability if p = θ(1/√U)", that "the relationship anonymity
of any pair of users could be broken by a handful of exchanged messages", and conclude "the
privacy protection what FMD offers is weak" (VERIFIED, [9]). At a false-positive rate of
2^-10 and 36,340 candidates a day a client downloads about 35 decoys a day and, with 10,000
light clients, hides among about 10 wallets. A recurring sender is exposed after a few
payments.

Penumbra is the field test. It shipped FMD structurally, one clue per output with the
precision enforced by consensus, and its mainnet genesis sets the precision to zero bits,
so every clue matches every key and clients still trial-decrypt everything:

    "fmdMetaParams": { "fmdGracePeriodBlocks": "360", "fixedPrecisionBits": 0 }

(VERIFIED, [10]; the library default is also `Precision(0)`, [11].)

**Private Information Retrieval is the wrong shape.** SimplePIR runs at 10 GB/s per core
with a 242 KB answer per query and a 121 MB client hint that depends on the database and
must be refreshed when it changes (VERIFIED, [12]). Here the database changes every block
and the client wants every record in a range. No PIR returns a range for less than the
range's own size, so the only thing it could hide is which range was fetched, which is the
wallet birthday, and fetching from a fixed earlier height hides that for free.

## What the others actually shipped

No production privacy coin or stealth-address system in 2026 has a server-side detector
that learns nothing. Each is either download-everything or hand-over-the-view-key.

| System | Shipped | Server learns | Source |
|---|---|---|---|
| Zcash light wallets | compact blocks, "the light client can trial-decrypt it against a set of Sapling incoming viewing keys" | "The act of sending and receiving transactions is visible to the lightwalletd server" | VERIFIED [13], [14] |
| Zcash OMR grant | terminated 2023-03-08; Foundation: "we don't think it's a priority at this time" | | VERIFIED [15], [16] |
| Monero | 1-byte view tag, "50-70% reduction in scan time per tx", compute only; light wallet servers hold the view key | "allowing access to view every incoming transaction" | VERIFIED [17], [18] |
| Penumbra | FMD clues at precision 0 | nothing, client trial-decrypts all | VERIFIED [10] |
| Ethereum ERC-5564 | 1-byte view tag, "reduce the parsing time by around 6x" | | VERIFIED [19] |
| Fluidkey | "she allows Fluidkey to use this key to notify her of incoming payments in real time" | all incoming payments | VERIFIED [20] |

BIP-352 itself designed the scan key to be handed to a third party: "Bob can instead publish
an address of the form (Bscan, Bspend) ... perform the scanning with the public key Bspend
and private key bscan" (VERIFIED, [21]). That is the view-key lane, and it is what Frigate
and Sparrow's Remote Scanner do.

**Prior art in Bitcoin: none found.** Searched: delvingbitcoin.org, the bitcoindev list,
the silent-payments GitHub organisation, bitcoin/bips issues, eprint.iacr.org, and the
monero-project/research-lab issue tracker, for silent payments or BIP-158 with oblivious
message retrieval, fuzzy message detection, private information retrieval or homomorphic
encryption. The 2024 light-client protocol thread [22] mentions none of them. Verified for
those queries, not claimed exhaustive.

## The boring baseline, which is most of the answer

- **Wallet birthday.** A new wallet never scans the 188 million. For an old-wallet restore
  BIP-352 points at the UTXO set, cut-through removes "as much as 38% of tweaks" and a
  1,000 sat dust floor covers "85% of taproot UTXOs" (VERIFIED, [23]).
- **Bandwidth.** 1.2 MB a day is 36 MB a month. BIP-352 projected "~450 MB per month,
  assuming 100% taproot usage" (VERIFIED, [21]). It only bites on multi-year restores.
- **Sender notifications over nostr** [24]. Useful when the sender cooperates, and only
  then. setavenger's own objections: "If Alice and Bob don't share a relay Bob will not see
  notes broadcasted by Alice", "Malicious actors flooding the receiver with fake
  notifications", "Bob has no option to find out whether all transactions made to him have
  been seen by him", and "Alice must not send to Bob if Bob does not signal support for the
  protocol" (VERIFIED). Scanning stays the safety net.

## The blind push: liveness without cryptography

Apple's rules (VERIFIED, [25], [26], [27]): a background push gives the app "30 seconds to
perform any tasks", "don't try to send more than two or three per hour", and "If something
force quits or kills the app, the system discards the held notification". App refresh gives
"30 seconds of run time, each time it's launched". Processing tasks give "several minutes"
and requiring external power is optional. iOS 26 adds a task that "starts in the foreground
and can continue running in the background as needed".

Phoenix by ACINQ runs a Lightning node inside exactly this budget in production, a
notification service extension "capped at 24 MB" with "a maximum of 30 seconds to run"
(VERIFIED, [28]).

Against that budget:

| Trigger | Data | Compute at 65 µs per tweak |
|---|---|---|
| One block, about 252 tweaks | 8 KB tweaks only, about 16 KB with each transaction's outputs | 16 ms |
| One hour, six blocks | 50 KB tweaks only; 97,912 bytes measured live in the per-transaction format the app reads | 0.1 s |
| One day, if every push was missed | 1.2 MB tweaks only; 2.4 to 3.8 MB with outputs, measured on two different days | 2.4 s |

The server sends the same payload to every registered device: the new block heights and
nothing else. It learns a push token and nothing per user, because every device receives
an identical message. The phone fetches the tweaks for those blocks, scans with its scan
key on-device, and posts a local notification. Unlike Phoenix, a dropped push here costs
only delay: the coins are on-chain, and the next push, the daily app refresh, or the next
foreground open catches up. Honest failure cases: a force-quit app hears nothing until
relaunch, Low Power Mode may defer, and Apple guarantees no delivery.

The prototype lives in `bitsaga/services/silentpayments/api/push.js` and
`phonebench/ios/SPBench/PushScan.swift`. What makes it worth publishing is the measurement:
median and tail delay from block to notification on a normally used iPhone, miss rate under
Low Power Mode and force-quit, bytes per day, battery.

## What would reopen this

A demonstration of clue-free detection over a stealth-address point at under about 1 ms per
tweak under FHE. Nothing found through May 2026 is within four orders of magnitude.

## Sources

1. Zama, ECDSA signature bounty tutorial, https://github.com/zama-ai/bounty-ecdsa-signature/blob/master/tutorial.md
2. Homomorphic Encryption for Large Integers from Nested Residue Number Systems, https://eprint.iacr.org/2025/346
3. Liu, Tromer, Oblivious Message Retrieval, CRYPTO 2022, https://eprint.iacr.org/2021/1256
4. Liu, Tromer, Wang, PerfOMR, USENIX Security 2024, https://eprint.iacr.org/2024/204
5. Liu, Sotiraki, Tromer, Wang, Snake-eye Resistant PKE, Eurocrypt 2025, https://eprint.iacr.org/2024/510
6. Lee, Yeo, SophOMR, USENIX Security 2026, https://eprint.iacr.org/2024/1814
7. Fisch, Liu, Tromer, Wang, UnifOMR, https://eprint.iacr.org/2026/910
8. Beck, Len, Miers, Green, Fuzzy Message Detection, https://eprint.iacr.org/2021/089
9. Seres, Pinter, Burcsi, The Effect of False Positives, FC 2022, https://eprint.iacr.org/2021/1180
10. Penumbra mainnet genesis, https://github.com/penumbra-zone/devops/blob/main/tools/grand-archive/artifacts/penumbra-1/genesis-0.json
11. https://github.com/penumbra-zone/penumbra/blob/main/crates/crypto/decaf377-fmd/src/precision.rs
12. Henzinger et al., SimplePIR and DoublePIR, https://eprint.iacr.org/2022/949
13. ZIP 307, https://zips.z.cash/zip-0307
14. Zcash wallet threat model, https://zcash.readthedocs.io/en/latest/rtd_pages/wallet_threat_model.html
15. https://forum.zcashcommunity.com/t/oblivious-message-retrieval/40715
16. https://zfnd.org/oblivious-message-retrieval/
17. https://github.com/monero-project/research-lab/issues/73
18. https://www.getmonero.org/resources/moneropedia/viewkey.html
19. https://eips.ethereum.org/EIPS/eip-5564
20. https://docs.fluidkey.com/readme/frequently-asked-questions/
21. https://github.com/bitcoin/bips/blob/master/bip-0352.mediawiki
22. https://delvingbitcoin.org/t/silent-payments-light-client-protocol/891
23. https://github.com/setavenger/BIP0352-light-client-specification
24. https://delvingbitcoin.org/t/stealth-addresses-using-nostr/1816
25. https://developer.apple.com/documentation/usernotifications/pushing-background-updates-to-your-app
26. WWDC 2019 session 707, Advances in App Background Execution, https://developer.apple.com/videos/play/wwdc2019/707/
27. https://developer.apple.com/documentation/backgroundtasks/bgcontinuedprocessingtask
28. ACINQ, iOS Multi-Process Architecture, https://github.com/ACINQ/phoenix/blob/master/phoenix-ios/iOS%20Multi-Process%20Architecture.md
