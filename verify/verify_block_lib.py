"""Importable core of verify-block.py (which stays a standalone CLI script;
hyphenated filenames aren't importable). Same REST + bips-reference approach,
same independence property: shares no code with blindbit-oracle.
"""
import json
import sys
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from bitcoin_utils import COutPoint, CTxInWitness, deser_txid, is_p2tr
from reference import get_input_hash, get_pubkey_from_input, VinInfo

REST = "http://127.0.0.1:8332/rest"

_tx_cache: dict = {}


def rest_json(path: str):
    with urllib.request.urlopen(f"{REST}/{path}", timeout=30) as r:
        return json.load(r)


def blockhash_for_height(height: int) -> str:
    return rest_json(f"blockhashbyheight/{height}.json")["blockhash"]


def prevout_spk(txid: str, vout: int) -> bytes:
    if txid not in _tx_cache:
        _tx_cache[txid] = rest_json(f"tx/{txid}.json")
    return bytes.fromhex(_tx_cache[txid]["vout"][vout]["scriptPubKey"]["hex"])


def tweaks_for_block(height: int, blockhash: str = None):
    blockhash = blockhash or blockhash_for_height(height)
    block = rest_json(f"block/{blockhash}.json")
    tweaks = []
    for tx in block["tx"]:
        if "coinbase" in tx["vin"][0]:
            continue
        if not any(is_p2tr(bytes.fromhex(o["scriptPubKey"]["hex"])) for o in tx["vout"]):
            continue
        vins = []
        for vin in tx["vin"]:
            witness = CTxInWitness()
            witness.scriptWitness.stack = [
                bytes.fromhex(w) for w in vin.get("txinwitness", [])
            ]
            outpoint = COutPoint(deser_txid(vin["txid"]), vin["vout"])
            vins.append(
                VinInfo(
                    outpoint=outpoint,
                    scriptSig=bytes.fromhex(vin.get("scriptSig", {}).get("hex", "")),
                    txinwitness=witness,
                    prevout=prevout_spk(vin["txid"], vin["vout"]),
                )
            )
        pubkeys = []
        for v in vins:
            pk = get_pubkey_from_input(v)
            if not pk.infinity:
                pubkeys.append(pk)
        if not pubkeys:
            continue
        A_sum = pubkeys[0]
        for pk in pubkeys[1:]:
            A_sum = A_sum + pk
        if A_sum.infinity:
            continue
        input_hash = get_input_hash([v.outpoint for v in vins], A_sum)
        tweak = int.from_bytes(input_hash, "big") * A_sum
        tweaks.append(tweak.to_bytes_compressed().hex())
    return tweaks
