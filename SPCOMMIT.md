# spcommit: tweak-index commitments

Normative specification for the per-block commitments and hash chain over the
BlindBit tweak index served by silentpayments.net. The reference implementation
is `commitments.js` in this directory; where prose and code disagree, the code
wins. Test vectors: `spcommit-test-vectors.json` (same directory).

## Motivation

A tweak server's one real power is silent omission: drop one transaction's
tweak and the receiving wallet never learns money arrived, which is undetectable
today. Per-block commitments chained into one head and checkpointed onto relays
we do not control make both omission and equivocation attributable: serving a
different history than yesterday breaks a hash somebody else already holds.
This is explicitly NOT a defense against the targeted fake-hint attack; the
client-side defense there remains fetching the full block on any filter match.

## Common rules

- Hash function: SHA-256. Every preimage is an ASCII string; hex characters
  are hashed as their ASCII bytes, never decoded to raw bytes.
- All hex is lowercase. All integers (height, counts) are decimal ASCII with
  no padding.
- `blockhash` is the oracle's wire hash byte-reversed, hex encoded. In the
  production chain this is the internal byte order: the zero bytes of the
  familiar display hash sit at the END of the string. Verifiers must use the
  exact string served, not the display-order form.
- Newlines are a single `\n` (0x0a), placed exactly as shown below.

## Format v1: the tweak set

Commits to the set of per-block tweaks from `StreamComputeIndex`
(request `{"start":H,"end":H,"dustlimit":0,"cut_through":false}`).

Preimage, hashed as one ASCII string:

    "spcommit-v1\n" height "\n" blockhash "\n" count "\n" tweak1 "\n" tweak2 ...

- Tweaks are 33-byte compressed points as 66-char lowercase hex, sorted
  lexicographically as strings. Sorting makes the commitment independent of
  server-side stream order, which gRPC does not fix.
- The tweak list is joined with `\n` and has NO trailing newline. With
  `count = 0` the list is the empty string, so the preimage ends with the
  `\n` after `0`.

Worked example (fake block, 2 tweaks). The preimage is these 5 lines with a
`\n` after each of the first 4 and nothing after the last:

    spcommit-v1
    840000
    0000000000000000000320283a032748cef8227873ff4872689bf23f1cda83a5
    2
    aa17b3e63e9ea3a10ca55e29cf1a08bb59dc23a99b8ba2a35a83c765a273bdaf
    bb45a1e6237c25f0a716a2a132e37e10917db00fda1c542947c322a41b7fbc07

    sha256 = 2bbaec4f3a0197f095d23063945344164cba7f3c549359e7e40e757d929094a7

## Format v2: the complete served set

Commits to EVERYTHING `StreamBlockScanDataShort` hands a scanning client
(same request shape): per-tx txid, tweak and output prefixes, plus the block's
spent-outputs blob. No served artifact can be doctored or dropped without
breaking the chain.

Preimage, hashed as one ASCII string:

    "spcommit-v2\n" height "\n" blockhash "\n" tx_count "\n"
    then per tx, sorted ascending by txid hex string:
        txid "\n" tweak "\n" outputs_hex "\n"
    then "spent\n" spent_blob_hex "\n"

- Transactions are sorted by their txid hex string; ties cannot occur.
- `outputs_hex` is the tx's `outputs_short` field as one opaque lowercase hex
  string, kept exactly in server order; it is a single field on the wire and
  is never split or sorted.
- `spent_blob_hex` is the block's `spent_outputs` bytes as lowercase hex;
  empty string if absent.
- Unlike v1, EVERY line ends with `\n`, including the last (`spent_blob_hex`).
  An empty block still commits to `"spent\n" spent_blob_hex "\n"`.

Worked example (same fake block, fake txids, spent blob `907b775220939dfc`),
preimage is these 12 lines, each followed by `\n`:

    spcommit-v2
    840000
    0000000000000000000320283a032748cef8227873ff4872689bf23f1cda83a5
    2
    1111111111111111111111111111111111111111111111111111111111111111
    aa17b3e63e9ea3a10ca55e29cf1a08bb59dc23a99b8ba2a35a83c765a273bdaf
    983f0dbc51af457b
    2222222222222222222222222222222222222222222222222222222222222222
    bb45a1e6237c25f0a716a2a132e37e10917db00fda1c542947c322a41b7fbc07
    0188b8ed6c5b9db7
    spent
    907b775220939dfc

    sha256 = 5b1298779e2a89a80d749f1a7933cb41e5bc0c65d22bf0e6b8d65d979e89204f

## Chain construction

Each format has its own independent chain, starting at height 709656 (the
first block the index serves) and advancing one block at a time with no gaps:

    head(H) = sha256( head(H-1) || commitment(H) )

Both operands are the 64-char lowercase hex STRINGS, concatenated and hashed
as ASCII (128 bytes in), never decoded to raw bytes. Genesis values:

    v1: head(709655) = sha256("spcommit-v1-genesis")
                     = ef4085e8fda4301f1dce6fce304aaf950a186413fea31e61042a88311e9bf377
    v2: head(709655) = sha256("spcommit-v2-genesis")
                     = 504f3285185adca6f8c0caa7940dab2dd96515f5fdd9c7aaab4cb1c004daf8f6

One published head therefore pins every block from 709656 up to that height,
in both content and order.

## Checkpointing

Heads are published to public nostr relays by `api/oracle-checkpoint.js` as a
kind 1 note with tags:

    ["t", "silentpayments-tweak-index"]
    ["head", <v1 head>]        ["height", <v1 height, decimal string>]
    ["head2", <v2 head>]       ["height2", <v2 height, decimal string>]
    ["d", "silentpayments.net/tweak-index"]

The note body restates both heads and formats in plain text. The signing key
is the same one used for the change-log checkpoints and holds no funds; it
proves continuity of the publisher, nothing more. Refusal-to-sign rule: before
publishing, the full chain is recomputed from the stored per-block commitments
(gap check plus head recomputation from genesis), and publishing REFUSES if
any stored head does not recompute, because a signature on a broken chain
endorses the broken version.

## Versioning

Formats are frozen once published. A change to what is committed or how it is
serialized is a NEW format: new version tag in the preimage, new genesis tag
(`spcommit-vN-genesis`), its own parallel chain and its own head/height tags
in the checkpoint note. Old chains keep being built, verified and published
alongside; historical heads stay verifiable under the rules of their own
version forever. v1 and v2 running side by side is the working example.

## Test vectors

`spcommit-test-vectors.json` holds five real blocks (709656, 709700, 709731,
715000, 750000) generated from the production oracle and cross-checked against
the production commitment chains: full input data, expected v1 and v2
commitments, both genesis heads, and one application of the chain rule
(head after 709656 from each genesis). The heights are not consecutive, so
the vectors cannot be chained together beyond that first step.
