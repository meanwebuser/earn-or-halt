#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import urllib.request
from typing import Any

try:
    from eth_account import Account
except ImportError as error:  # pragma: no cover - optional adapter
    raise SystemExit("install the optional dependency: pip install -r requirements-eth.txt") from error


def rpc(url: str, method: str, params: list[Any]) -> Any:
    payload = json.dumps({"jsonrpc": "2.0", "id": 1, "method": method, "params": params}).encode()
    request = urllib.request.Request(
        url,
        data=payload,
        method="POST",
        headers={"Content-Type": "application/json", "User-Agent": "EarnOrHalt-Publisher/0.1"},
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        value = json.loads(response.read().decode("utf-8"))
    if "error" in value:
        raise RuntimeError(f"JSON-RPC {method} failed: {value['error']}")
    return value["result"]


def as_int(value: str) -> int:
    return int(value, 16)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Publish a manifest URI in an Ethereum transaction input."
    )
    parser.add_argument("pointer", help="https://, ipfs:// or ipns:// URI of the signed manifest")
    parser.add_argument("--rpc-url", default=os.getenv("EOH_ETH_RPC_URL"))
    parser.add_argument("--to", default=os.getenv("EOH_VANITY_ADDRESS"))
    parser.add_argument("--private-key", default=os.getenv("EOH_ETH_PRIVATE_KEY"))
    args = parser.parse_args()
    if not args.rpc_url or not args.to or not args.private_key:
        raise SystemExit("RPC URL, destination address and private key are required")
    if not args.pointer.startswith(("https://", "ipfs://", "ipns://")):
        raise SystemExit("pointer must be a supported manifest URI")
    data = "0x" + args.pointer.encode("utf-8").hex()
    if len(data) > 8194:
        raise SystemExit("pointer is too long")

    account = Account.from_key(args.private_key)
    chain_id = as_int(rpc(args.rpc_url, "eth_chainId", []))
    nonce = as_int(rpc(args.rpc_url, "eth_getTransactionCount", [account.address, "pending"]))
    latest = rpc(args.rpc_url, "eth_getBlockByNumber", ["latest", False])
    base_fee = as_int(latest.get("baseFeePerGas", "0x0"))
    try:
        priority_fee = as_int(rpc(args.rpc_url, "eth_maxPriorityFeePerGas", []))
    except Exception:
        priority_fee = 1_500_000_000
    max_fee = max(priority_fee * 2, base_fee * 2 + priority_fee)
    estimate_call = {
        "from": account.address,
        "to": args.to,
        "value": "0x0",
        "data": data,
    }
    gas = as_int(rpc(args.rpc_url, "eth_estimateGas", [estimate_call]))
    transaction = {
        "chainId": chain_id,
        "nonce": nonce,
        "to": args.to,
        "value": 0,
        "data": data,
        "gas": int(gas * 1.15),
        "maxFeePerGas": max_fee,
        "maxPriorityFeePerGas": priority_fee,
        "type": 2,
    }
    signed = Account.sign_transaction(transaction, args.private_key)
    raw = getattr(signed, "raw_transaction", None) or getattr(signed, "rawTransaction")
    tx_hash = rpc(args.rpc_url, "eth_sendRawTransaction", ["0x" + bytes(raw).hex()])
    print(tx_hash)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
