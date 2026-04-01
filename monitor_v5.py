#!/usr/bin/env python3
"""
EARNY Monitor v5.3 — FAST MONITOR
Key changes from v5.2:
- Check interval: 60s → 15s
- Max positions: 5 → 3
- EMERGENCY SELL: -25% price drop from entry triggers immediate sell
- Slippage tighter (10 instead of 5) for better fills
- Uses Alchemy for everything (faster, more reliable)
"""
import requests
import json
import time
import base58
import base64
from dotenv import load_dotenv

load_dotenv("/root/.openclaw/workspace-minimaxbot/trading-bot/.env")

ALCH_RPC = "https://solana-mainnet.g.alchemy.com/v2/koEw2jzP14JkBeAU4Wzw9"
JUPITER_KEY = "491784ae-9799-4ecf-8d18-63bfd5f932dd"
headers = {"x-api-key": JUPITER_KEY}
WALLET = "FRGVy5xEk7tKyeBcWP1Mkj97Tv4aFPWHaQJnNggKe7Cf"
PRIVATE_KEY = "2ph75CovJ4wwcyMxUBKATswphUWb6SSep5TH2Z4XChCSBbnxW7U2uxWaAvr2UqRbB5QriQAvNFx9uH1b8MtPrwzT"
BUY_AMOUNT = 0.005
TP_PCT = 1.00    # +100% profit target
SL_PCT = 0.20    # -20% per token (Kevin's rule)
EMERGENCY_PCT = 0.25  # -25% price drop = EMERGENCY sell
CHECK_INTERVAL = 15   # 15 seconds (fast!)
MAX_POSITIONS = 3
DATA_FILE = "/root/.openclaw/workspace-minimaxbot/trading-bot/data/trades.json"
LOG_FILE = "/root/.openclaw/workspace-minimaxbot/trading-bot/monitor.log"

from solders.keypair import Keypair
from solders.transaction import VersionedTransaction
keypair = Keypair.from_bytes(base58.b58decode(PRIVATE_KEY))


def log(msg):
    ts = time.strftime("%H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line)
    with open(LOG_FILE, "a") as f:
        f.write(line + "\n")


def rate(s=1.0):  # Reduced from 1.5
    time.sleep(s)


def get_sol():
    r = requests.post(ALCH_RPC, json={"jsonrpc":"2.0","id":1,"method":"getBalance","params":[WALLET]}, headers={"Content-Type":"application/json"}, timeout=10)
    return r.json().get("result",{}).get("value",0)/1e9


def get_positions():
    positions = {}
    for prog in ["TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA","TokenzQdBNbLqP5VEhdkAS6EPFLC1PHnBqCXEpPxuEb"]:
        pl = {"jsonrpc":"2.0","id":1,"method":"getTokenAccountsByOwner","params":[WALLET,{"programId":prog},{"encoding":"jsonParsed"}]}
        resp = requests.post(ALCH_RPC, json=pl, headers={"Content-Type":"application/json"}, timeout=15)
        if resp.json().get("result",{}).get("value"):
            for acc in resp.json()["result"]["value"]:
                info = acc["account"]["data"]["parsed"]["info"]
                mint = info["mint"]
                amt = int(info["tokenAmount"]["amount"])
                dec = info["tokenAmount"]["decimals"]
                if mint not in ["So11111111111111111111111111111111111111112","EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"]:
                    if amt > 10000:
                        positions[mint] = {"raw": amt, "amount": amt/(10**dec)}
    return positions


def get_token_price(mint):
    """Get current price in SOL per token"""
    try:
        params = {"inputMint": mint, "outputMint": "So11111111111111111111111111111111111111112", "amount": 1000000, "slippage": 10}
        r = requests.get("https://api.jup.ag/swap/v1/quote", params=params, headers=headers, timeout=15)
        if r.status_code == 200:
            return int(r.json().get("outAmount","0")) / 1e9
    except:
        pass
    return 0


def verify_tx(tx_hash):
    if not tx_hash or len(tx_hash) < 20:
        return False
    try:
        r = requests.post(ALCH_RPC, json={
            "jsonrpc": "2.0", "id": 1, "method": "getTransaction",
            "params": [tx_hash, {"encoding": "json", "maxSupportedTransactionVersion": 0}]
        }, headers={"Content-Type": "application/json"}, timeout=30)
        res = r.json().get("result")
        if res and not res.get("meta", {}).get("err"):
            return True
    except:
        pass
    return False


def load_trades():
    try:
        with open(DATA_FILE, "r") as f:
            return json.load(f)
    except:
        return {"buys": {}, "sells": []}


def save_trades(data):
    with open(DATA_FILE, "w") as f:
        json.dump(data, f, indent=2)


def is_sold(mint, data):
    for s in data.get("sells", []):
        if s.get("token") == mint:
            return True
    return False


def do_sell(mint, pos_info, reason="SELL"):
    log(f"🚨 {reason}: {mint[:30]}... ({pos_info.get('amount',0):,.2f} tokens)")
    
    # Quote with tighter slippage
    rate(1.0)
    params = {"inputMint": mint, "outputMint": "So11111111111111111111111111111111111111112", "amount": pos_info["raw"], "slippage": 10}
    r = requests.get("https://api.jup.ag/swap/v1/quote", params=params, headers=headers, timeout=15)
    if r.status_code != 200:
        log(f"  ❌ Quote: {r.status_code}")
        return False
    
    quote = r.json()
    quote_out = int(quote.get("outAmount","0")) / 1e9
    log(f"  Quote: ~{quote_out:.6f} SOL")
    
    # Build tx
    rate(1.0)
    swap_resp = requests.post("https://api.jup.ag/swap/v1/swap", json={
        "userPublicKey": WALLET, "quoteResponse": quote, "wrapAndUnwrapSol": True
    }, headers=headers, timeout=30).json()
    
    tx = swap_resp.get("swapTransaction")
    if not tx:
        log(f"  ❌ No tx"); return False
    
    # Sign
    rate(1.0)
    try:
        unsigned = VersionedTransaction.from_bytes(base64.b64decode(tx))
        signed = VersionedTransaction(unsigned.message, [keypair])
        tx_bytes = bytes(signed)
        tx_b64 = base64.b64encode(tx_bytes).decode()
        
        send = requests.post(ALCH_RPC, json={
            "jsonrpc": "2.0", "id": 1, "method": "sendTransaction",
            "params": [tx_b64, {"encoding": "base64", "skipPreflight": True, "preflightCommitment": "processed"}]
        }, headers={"Content-Type": "application/json"}, timeout=60).json()
        
        tx_hash = send.get("result")
        if not tx_hash:
            log(f"  ❌ Broadcast: {send}")
            return False
        
        log(f"  Broadcasted: {tx_hash[:40]}...")
    except Exception as e:
        log(f"  ❌ Error: {e}")
        return False
    
    # Verify with retries
    confirmed = False
    for attempt in range(4):
        wait = (attempt + 1) * 6
        log(f"  Wait {wait}s... (attempt {attempt+1}/4)")
        rate(wait)
        if verify_tx(tx_hash):
            confirmed = True
            log(f"  ✅ CONFIRMED!")
            break
        log(f"  Not confirmed yet...")
    
    if not confirmed:
        log(f"  ❌ Never confirmed on-chain")
        return False
    
    # Record
    tokens = pos_info.get("amount", 0)
    value = quote_out * tokens
    jup_fee = value * 0.01
    net = value - jup_fee - 0.000005
    pnl = net - pos_info.get("sol_spent", BUY_AMOUNT)
    pnl_pct = (pnl / pos_info.get("sol_spent", BUY_AMOUNT)) * 100
    
    data = load_trades()
    if not is_sold(mint, data):
        data["sells"].append({
            "token": mint,
            "amount_tokens": tokens,
            "sell_amount_sol": net,
            "buy_amount_sol": pos_info.get("sol_spent", BUY_AMOUNT),
            "pnl_sol": round(pnl, 8),
            "pnl_percent": round(pnl_pct, 1),
            "sell_tx": tx_hash,
            "time": time.strftime("%Y-%m-%dT%H:%M:%S")
        })
        if mint in data.get("buys", {}):
            del data["buys"][mint]
        save_trades(data)
        log(f"  💾 Saved: P&L={pnl:+.6f} SOL ({pnl_pct:+.1f}%)")
    
    return True


def main():
    log("=" * 60)
    log("📡 EARNY MONITOR v5.3 — FAST MONITOR")
    log(f"TP: +{int(TP_PCT*100)}% | SL: -{int(SL_PCT*100)}% per token | EMERGENCY: -{int(EMERGENCY_PCT*100)}%")
    log(f"Check every: {CHECK_INTERVAL}s | Max positions: {MAX_POSITIONS}")
    log("=" * 60)
    
    while True:
        log(f"\n--- CHECK | {time.strftime('%H:%M:%S')} ---")
        
        data = load_trades()
        positions = get_positions()
        sol_now = get_sol()
        
        active = {m: {**data["buys"][m], "raw": positions[m]["raw"], "amount": positions[m]["amount"]}
                  for m in data["buys"] if m in positions}
        
        log(f"SOL: {sol_now:.6f} | Positions: {len(active)}/{MAX_POSITIONS}")
        
        for mint, info in active.items():
            rate(1.0)

            current = get_token_price(mint)
            if current == 0:
                log(f"⚠️ Price error: {mint[:20]}...")
                continue
            
            entry = info.get("price_per_token", 0)
            tokens = info.get("amount", 0)
            sol_spent = info.get("sol_spent", BUY_AMOUNT)
            
            # Price-based TP/SL
            tp_price = entry * (1 + TP_PCT)     # entry * 2.0
            sl_price = entry * (1 - SL_PCT)      # entry * 0.80
            emergency_price = entry * (1 - EMERGENCY_PCT)  # entry * 0.75
            
            value = current * tokens
            jup_fee = value * 0.01
            net = value - jup_fee - 0.000005
            pnl_sol = net - sol_spent
            price_pct = ((current - entry) / entry * 100) if entry > 0 else 0
            
            # Check triggers — EMERGENCY first (fastest drop)
            trigger = None
            trigger_reason = ""
            
            if current >= tp_price:
                trigger = "TP"
                trigger_reason = f"TP HIT! ({price_pct:+.1f}%)"
            elif current <= emergency_price:
                trigger = "EMERGENCY"
                trigger_reason = f"🚨 EMERGENCY -25%! ({price_pct:.1f}%)"
            elif current <= sl_price:
                trigger = "SL"
                trigger_reason = f"SL HIT ({price_pct:.1f}%)"
            
            status = f"🎯 TP!" if trigger == "TP" else f"🚨 EMERGENCY!" if trigger == "EMERGENCY" else f"🛡️ SL!" if trigger == "SL" else (f"🟢{pnl_sol:+.6f}" if pnl_sol > 0 else f"🔴{pnl_sol:+.6f}")
            
            log(f"📍 {mint[:30]}...")
            log(f"   {tokens:,.2f} tokens | Entry: {entry:.10f} | Now: {current:.10f}")
            log(f"   Spent: {sol_spent:.6f} SOL | Value: {net:.6f} SOL | {price_pct:+.1f}% | {status}")
            log(f"   TP: {tp_price:.10f} | SL: {sl_price:.10f} | EMERGENCY: {emergency_price:.10f}")
            
            if trigger:
                if is_sold(mint, data):
                    log(f"   Already sold - skipping")
                else:
                    log(f"   ⚡ {trigger_reason} — executing {trigger}...")
                    do_sell(mint, info, trigger)
        
        rate(CHECK_INTERVAL)


if __name__ == "__main__":
    main()
