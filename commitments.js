#!/usr/bin/env node
'use strict'

/**
 * Tamper-evident commitments over the BlindBit tweak index we serve.
 *
 * For every block: commitment = sha256 over a canonical serialization of
 * (height, block hash, tweak count, the sorted tweak set). Commitments chain:
 * head(H) = sha256(head(H-1) || commitment(H)), so one published head pins the
 * entire index below it. A server that silently omits a transaction's tweak
 * (the failure mode that has already cost Cake Wallet users real money
 * elsewhere) can no longer do so without changing a hash somebody else holds.
 *
 * No tweak server anywhere offers this. It is the change-log trick applied to
 * the one power a tweak server has: withholding.
 *
 *     node commitments.js build             walk from last stored height to tip
 *     node commitments.js build --to N      stop at height N
 *     node commitments.js head              print current head + height
 *     node commitments.js verify N          recompute block N from the oracle and compare
 *     node commitments.js compare N         our block N vs oracle.setor.dev (>=800000 only)
 *
 * Reads the oracle over gRPC via grpcurl (zero npm dependencies, same
 * no-framework rule as the rest of this service). The DB is append-only in
 * spirit: build refuses to overwrite an existing height with different data,
 * because a changed commitment is exactly the event this exists to catch.
 */

const { execFileSync, spawnSync } = require('node:child_process')
const crypto = require('node:crypto')
const os = require('node:os')
const path = require('node:path')
const { DatabaseSync } = require('node:sqlite')

const GRPCURL = process.env.GRPCURL || path.join(os.homedir(), '.local/bin/grpcurl')
const ORACLE = process.env.ORACLE_GRPC || '127.0.0.1:8011'
const REMOTE = process.env.REMOTE_ORACLE || 'oracle.setor.dev:443'
const DB_PATH = process.env.COMMIT_DB || path.join(os.homedir(), '.blindbit-oracle', 'commitments.sqlite')
const CHUNK = 500

const db = new DatabaseSync(DB_PATH)
db.exec(`
  CREATE TABLE IF NOT EXISTS commitments (
    height INTEGER PRIMARY KEY,
    blockhash TEXT NOT NULL,
    tweak_count INTEGER NOT NULL,
    commitment TEXT NOT NULL,
    head TEXT NOT NULL
  ) STRICT;
  CREATE TABLE IF NOT EXISTS commitments_v2 (
    height INTEGER PRIMARY KEY,
    blockhash TEXT NOT NULL,
    tx_count INTEGER NOT NULL,
    spent_bytes INTEGER NOT NULL,
    commitment TEXT NOT NULL,
    head TEXT NOT NULL
  ) STRICT;
`)

function sha256hex(...parts) {
  const h = crypto.createHash('sha256')
  for (const p of parts) h.update(p)
  return h.digest('hex')
}

/**
 * Canonical serialization, version-tagged so it can evolve the way the
 * change-log formats do: future versions verify old blocks with old rules.
 *   "spcommit-v1\n" height "\n" blockhash "\n" count "\n" tweak1 "\n" tweak2 ...
 * Tweaks are lowercase hex, sorted lexicographically. Sorting makes the
 * commitment independent of server-side ordering, which gRPC does not fix.
 */
function commitBlock(height, blockhash, tweaks) {
  const sorted = [...tweaks].map((t) => t.toLowerCase()).sort()
  return sha256hex(
    `spcommit-v1\n${height}\n${blockhash.toLowerCase()}\n${sorted.length}\n`,
    sorted.join('\n'),
  )
}

/** Split grpcurl's streamed output (concatenated JSON objects) into objects. */
function splitJsonStream(text) {
  const out = []
  let depth = 0
  let start = -1
  let inString = false
  let escaped = false
  for (let i = 0; i < text.length; i++) {
    const c = text[i]
    if (inString) {
      if (escaped) escaped = false
      else if (c === '\\') escaped = true
      else if (c === '"') inString = false
      continue
    }
    if (c === '"') inString = true
    else if (c === '{') {
      if (depth === 0) start = i
      depth++
    } else if (c === '}') {
      depth--
      if (depth === 0) out.push(JSON.parse(text.slice(start, i + 1)))
    }
  }
  return out
}

/** Fetch [start, end] from an oracle as {height -> {blockhash, tweaks[]}}. */
function fetchRange(target, start, end) {
  const req = JSON.stringify({ start, end, dustlimit: 0, cut_through: false })
  const args = []
  if (!target.includes(':443')) args.push('-plaintext')
  args.push('-max-time', '600', '-d', req, target, 'blindbit.oracle.v1.OracleService/StreamComputeIndex')
  const res = spawnSync(GRPCURL, args, { encoding: 'utf8', maxBuffer: 1024 * 1024 * 512 })
  if (res.status !== 0) {
    throw new Error(`grpcurl ${target} [${start},${end}] failed: ${res.stderr.slice(0, 400)}`)
  }
  const blocks = new Map()
  for (const obj of splitJsonStream(res.stdout)) {
    const id = obj.blockIdentifier || {}
    const height = Number(id.blockHeight)
    if (!Number.isFinite(height)) continue
    const hash = Buffer.from(id.blockHash || '', 'base64').reverse().toString('hex')
    const tweaks = (obj.index || []).map((it) => Buffer.from(it.tweak, 'base64').toString('hex'))
    blocks.set(height, { blockhash: hash, tweaks })
  }
  return blocks
}

/**
 * spcommit-v2: commit to EVERYTHING the server hands a scanning client, not
 * just the tweak set. Covers the per-tx compute-index items (txid, tweak,
 * output prefixes) and the block's spent-outputs blob, so no served artifact
 * can be doctored or dropped without breaking the chain.
 *
 * Canonical serialization, hashed as ascii:
 *   "spcommit-v2\n" height "\n" blockhash "\n" tx_count "\n"
 *   then per tx, sorted by txid hex: txid "\n" tweak "\n" outputs_hex "\n"
 *   then "spent\n" spent_blob_hex "\n"
 * All hex lowercase. Sorting by txid makes the commitment independent of
 * server-side stream order; within a tx, outputs_short keeps server order
 * (it is a single opaque field on the wire).
 */
function commitBlockV2(height, blockhash, txs, spentHex) {
  const sorted = [...txs].sort((a, b) => (a.txid < b.txid ? -1 : a.txid > b.txid ? 1 : 0))
  const parts = [`spcommit-v2\n${height}\n${blockhash.toLowerCase()}\n${sorted.length}\n`]
  for (const t of sorted) parts.push(`${t.txid}\n${t.tweak}\n${t.outputs}\n`)
  parts.push(`spent\n${spentHex}\n`)
  return sha256hex(parts.join(''))
}

/** Fetch [start, end] of full scan data as {height -> {blockhash, txs, spentHex}}. */
function fetchRangeV2(target, start, end) {
  const req = JSON.stringify({ start, end, dustlimit: 0, cut_through: false })
  const args = []
  if (!target.includes(':443')) args.push('-plaintext')
  args.push('-max-time', '600', '-d', req, target, 'blindbit.oracle.v1.OracleService/StreamBlockScanDataShort')
  const res = spawnSync(GRPCURL, args, { encoding: 'utf8', maxBuffer: 1024 * 1024 * 512 })
  if (res.status !== 0) {
    throw new Error(`grpcurl v2 ${target} [${start},${end}] failed: ${res.stderr.slice(0, 400)}`)
  }
  const blocks = new Map()
  for (const obj of splitJsonStream(res.stdout)) {
    const id = obj.blockIdentifier || {}
    const height = Number(id.blockHeight)
    if (!Number.isFinite(height)) continue
    const hash = Buffer.from(id.blockHash || '', 'base64').reverse().toString('hex')
    const txs = (obj.compIndex || []).map((it) => ({
      txid: Buffer.from(it.txid, 'base64').toString('hex'),
      tweak: Buffer.from(it.tweak, 'base64').toString('hex'),
      outputs: Buffer.from(it.outputsShort || '', 'base64').toString('hex'),
    }))
    const spentHex = Buffer.from(obj.spentOutputs || '', 'base64').toString('hex')
    blocks.set(height, { blockhash: hash, txs, spentHex })
  }
  return blocks
}

function buildV2(toArg) {
  const START = 709656
  const tip = oracleTip()
  const to = toArg ? Math.min(toArg, tip) : tip
  const last = db.prepare('SELECT height, head FROM commitments_v2 ORDER BY height DESC LIMIT 1').get()
  let from = last ? last.height + 1 : START
  let head = last ? last.head : sha256hex('spcommit-v2-genesis')
  if (from > to) {
    console.log(`v2: nothing to do, stored through ${from - 1}, target ${to}`)
    return
  }
  const insert = db.prepare(
    'INSERT INTO commitments_v2 (height, blockhash, tx_count, spent_bytes, commitment, head) VALUES (?, ?, ?, ?, ?, ?)',
  )
  while (from <= to) {
    const end = Math.min(from + CHUNK - 1, to)
    const blocks = fetchRangeV2(ORACLE, from, end)
    db.exec('BEGIN')
    try {
      for (let h = from; h <= end; h++) {
        const b = blocks.get(h)
        if (!b) throw new Error(`v2: oracle served no data for height ${h}; refusing to commit a gap`)
        const c = commitBlockV2(h, b.blockhash, b.txs, b.spentHex)
        head = sha256hex(head, c)
        insert.run(h, b.blockhash, b.txs.length, b.spentHex.length / 2, c, head)
      }
      db.exec('COMMIT')
    } catch (e) {
      db.exec('ROLLBACK')
      throw e
    }
    console.log(`v2 committed through ${end}, head ${head.slice(0, 16)}…`)
    from = end + 1
  }
}

function verifyV2(height) {
  const row = db.prepare('SELECT * FROM commitments_v2 WHERE height = ?').get(height)
  if (!row) throw new Error(`height ${height} not in v2 commitment DB`)
  const b = fetchRangeV2(ORACLE, height, height).get(height)
  if (!b) throw new Error(`oracle no longer serves height ${height}`)
  const c = commitBlockV2(height, b.blockhash, b.txs, b.spentHex)
  const ok = c === row.commitment
  console.log(ok ? `OK v2 height ${height}: commitment unchanged (${row.tx_count} txs, ${row.spent_bytes} spent bytes)` : `MISMATCH v2 height ${height}`)
  process.exitCode = ok ? 0 : 1
}

function oracleTip() {
  const res = execFileSync(GRPCURL, ['-plaintext', ORACLE, 'blindbit.oracle.v1.OracleService/GetBestBlockHeight'], {
    encoding: 'utf8',
  })
  return Number(JSON.parse(res).blockHeight)
}

function lastStored() {
  return db.prepare('SELECT height, head FROM commitments ORDER BY height DESC LIMIT 1').get()
}

function build(toArg) {
  const START = 709656
  const tip = oracleTip()
  const to = toArg ? Math.min(toArg, tip) : tip
  const last = lastStored()
  let from = last ? last.height + 1 : START
  let head = last ? last.head : sha256hex('spcommit-v1-genesis')
  if (from > to) {
    console.log(`nothing to do, stored through ${from - 1}, target ${to}`)
    return
  }
  const insert = db.prepare(
    'INSERT INTO commitments (height, blockhash, tweak_count, commitment, head) VALUES (?, ?, ?, ?, ?)',
  )
  while (from <= to) {
    const end = Math.min(from + CHUNK - 1, to)
    const blocks = fetchRange(ORACLE, from, end)
    db.exec('BEGIN')
    try {
      for (let h = from; h <= end; h++) {
        const b = blocks.get(h)
        if (!b) throw new Error(`oracle served no data for height ${h}; refusing to commit a gap`)
        const c = commitBlock(h, b.blockhash, b.tweaks)
        head = sha256hex(head, c)
        insert.run(h, b.blockhash, b.tweaks.length, c, head)
      }
      db.exec('COMMIT')
    } catch (e) {
      db.exec('ROLLBACK')
      throw e
    }
    console.log(`committed through ${end}, head ${head.slice(0, 16)}…`)
    from = end + 1
  }
}

function verify(height) {
  const row = db.prepare('SELECT * FROM commitments WHERE height = ?').get(height)
  if (!row) throw new Error(`height ${height} not in commitment DB`)
  const b = fetchRange(ORACLE, height, height).get(height)
  if (!b) throw new Error(`oracle no longer serves height ${height}`)
  const c = commitBlock(height, b.blockhash, b.tweaks)
  const ok = c === row.commitment
  console.log(ok ? `OK height ${height}: commitment unchanged (${row.tweak_count} tweaks)` : `MISMATCH height ${height}: stored ${row.commitment} recomputed ${c}`)
  process.exitCode = ok ? 0 : 1
}

function compare(height) {
  const ours = fetchRange(ORACLE, height, height).get(height)
  const theirs = fetchRange(REMOTE, height, height).get(height)
  if (!theirs || !theirs.blockhash) {
    console.log(`remote ${REMOTE} serves nothing at ${height} (their index starts at 800000)`)
    return
  }
  const a = new Set(ours.tweaks.map((t) => t.toLowerCase()))
  const b = new Set(theirs.tweaks.map((t) => t.toLowerCase()))
  const onlyOurs = [...a].filter((t) => !b.has(t))
  const onlyTheirs = [...b].filter((t) => !a.has(t))
  console.log(`height ${height}: ours ${a.size}, theirs ${b.size}, only-ours ${onlyOurs.length}, only-theirs ${onlyTheirs.length}`)
  for (const t of onlyOurs) console.log(`  only-ours  ${t}`)
  for (const t of onlyTheirs) console.log(`  only-theirs ${t}`)
  process.exitCode = onlyOurs.length || onlyTheirs.length ? 1 : 0
}

const [cmd, arg] = process.argv.slice(2)
if (cmd === 'build') build(arg === '--to' ? Number(process.argv[4]) : undefined)
else if (cmd === 'build2') buildV2(arg === '--to' ? Number(process.argv[4]) : undefined)
else if (cmd === 'head') {
  const last = lastStored()
  console.log(last ? `height ${last.height} head ${last.head}` : 'empty')
} else if (cmd === 'head2') {
  const last = db.prepare('SELECT height, head FROM commitments_v2 ORDER BY height DESC LIMIT 1').get()
  console.log(last ? `v2 height ${last.height} head ${last.head}` : 'v2 empty')
} else if (cmd === 'verify') verify(Number(arg))
else if (cmd === 'verify2') verifyV2(Number(arg))
else if (cmd === 'compare') compare(Number(arg))
else {
  console.log('usage: commitments.js build|build2 [--to N] | head | head2 | verify N | verify2 N | compare N')
  process.exitCode = 2
}
