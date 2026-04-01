#!/usr/bin/env python3
"""
EARNY Deep Analysis v2 - Fixed P&L, proper TX verification
"""
import requests
import time
import json
import sys
import base58
import base64
from dotenv import load_dotenv

load_dotenv("/root/.openclaw/workspace-minimaxbot/trading-bot/.env")

QUICKNODE = "https://empty-hidden-grass.solana-mainnet.quiknode.pro/ca3087fb95c146dab3c3a247aefeecb25a4ad0af/"
ALCH_RPC = "https://solana-mainnet.g.alchemy.com/v2/koEw2jzP14JkBeAU4Wzw9"
ALCH = "https://solana-mainnet.g.alchemy.com/v2/koEw2jzP14JkBeAU4Wzw9"
JUPITER_KEY = "491784ae-9799-4ecf-8d18-63bfd5f932dd"
headers = {"x-api-key": JUPITER_KEY}
WALLET = "FRGVy5xEk7tKyeBcWP1Mkj97Tv4aFPWHaQJnNggKe7Cf"
BUY_AMOUNT = 0.005
MAX_DEV_HOLDING = 20        # v2: stricter — was 35
RATE_LIMIT_DELAY = 1.5

def rate_limit():
    time.sleep(RATE_LIMIT_DELAY)

def verify_tx_onchain(tx_sig):
    """Verify TX is confirmed on-chain"""
    r = requests.post(QUICKNODE, json={
        "jsonrpc": "2.0", "id": 1,
        "method": "getTransaction",
        "params": [tx_sig, {"encoding": "json", "maxSupportedTransactionVersion": 0}]
    }, headers={"Content-Type": "application/json"}, timeout=30)
    result = r.json().get("result")
    if result:
        meta = result.get("meta", {})
        err = meta.get("err")
        fee = meta.get("fee", 0) / 1e9
        return {"confirmed": err is None, "fee": fee, "meta": meta, "result": result}
    return {"confirmed": False, "error": r.json()}

def get_wallet_tokens():
    """Get all real token holdings from wallet"""
    tokens = {}
    for prog in ["TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA", "TokenzQdBNbLqP5VEhdkAS6EPFLC1PHnBqCXEpPxuEb"]:
        pl = {"jsonrpc": "2.0", "id": 1, "method": "getTokenAccountsByOwner",
              "params": [WALLET, {"programId": prog}, {"encoding": "jsonParsed"}]}
        resp = requests.post(QUICKNODE, json=pl, headers={"Content-Type": "application/json"}, timeout=15)
        if resp.json().get("result", {}).get("value"):
            for acc in resp.json()["result"]["value"]:
                info = acc["account"]["data"]["parsed"]["info"]
                mint = info["mint"]
                amt = int(info["tokenAmount"]["amount"])
                dec = info["tokenAmount"]["decimals"]
                # Skip SOL and dust USDC
                if mint in ["So11111111111111111111111111111111111111112", "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"]:
                    if amt > 1000:
                        tokens[mint] = {"amount": amt / (10**dec), "raw": amt, "decimals": dec}
                    continue
                if amt > 0:
                    tokens[mint] = {"amount": amt / (10**dec), "raw": amt, "decimals": dec}
    return tokens

def get_sol_balance():
    payload = {"jsonrpc": "2.0", "id": 1, "method": "getBalance", "params": [WALLET]}
    r = requests.post(QUICKNODE, json=payload, headers={"Content-Type": "application/json"}, timeout=10)
    return r.json().get("result", {}).get("value", 0) / 1e9

def deep_analyze(mint):
    print("=" * 70)
    print(f"🔍 DEEP ANALYSIS v2: {mint}")
    print("=" * 70)

    results = {"mint": mint, "checks": {}, "verdict": "PASS", "reject_reasons": []}

    # CHECK 1: BASIC INFO
    print("\n[1/10] TOKEN BASIC INFO")
    print("-" * 50)
    rate_limit()
    try:
        r = requests.post(QUICKNODE, json={
            "jsonrpc": "2.0", "id": 1, "method": "getTokenSupply", "params": [mint]
        }, headers={"Content-Type": "application/json"}, timeout=15)
        if r.status_code == 200:
            supply_data = r.json().get("result", {})
            total = int(supply_data.get("value", {}).get("amount", 0))
            decimals = supply_data.get("value", {}).get("decimals", 0)
            results["checks"]["supply"] = {"total": total, "decimals": decimals}
            print(f"   ✅ Supply: {total:,} ({decimals} decimals)")
        else:
            print(f"   ⚠️ {r.status_code}")
    except Exception as e:
        print(f"   ❌ {e}")
        results["checks"]["supply"] = {"error": str(e)}

    # CHECK 2: DEV / TOP HOLDER
    print("\n[2/10] DEV / TOP HOLDER ANALYSIS")
    print("-" * 50)
    rate_limit()
    try:
        r1 = requests.post(ALCH, json={"jsonrpc": "2.0", "id": 1, "method": "getTokenLargestAccounts", "params": [mint]}, timeout=15)
        r2 = requests.post(ALCH, json={"jsonrpc": "2.0", "id": 2, "method": "getTokenSupply", "params": [mint]}, timeout=15)
        
        holders_data = r1.json().get("result", {}).get("value", [])
        total_supply = int(r2.json().get("result", {}).get("value", {}).get("amount", 1))
        
        if not holders_data or total_supply == 0:
            results["verdict"] = "SKIP"
            results["reject_reasons"].append("No holder data")
            print("   ⚠️ No data")
        else:
            holder_analysis = []
            for i, h in enumerate(holders_data[:20]):
                raw = int(h["amount"])
                pct = (raw / total_supply) * 100
                addr = h["address"]
                label = "🔴 DEV" if i == 0 else f"🟡 TOP-{i+1}" if i < 5 else f"⚪ #{i+1}"
                print(f"   {label} {addr[:20]}... : {pct:.2f}%")
                holder_analysis.append({"rank": i+1, "address": addr, "pct": pct, "is_dev": i==0})
            
            dev_pct = holder_analysis[0]["pct"]
            top5 = sum(h["pct"] for h in holder_analysis[:5])
            top20 = sum(h["pct"] for h in holder_analysis)
            print(f"\n   📊 Dev: {dev_pct:.2f}% | Top5: {top5:.2f}% | Top20: {top20:.2f}%")
            results["checks"]["holders"] = {"dev_pct": dev_pct, "top5_pct": top5, "top20_pct": top20, "detail": holder_analysis}
            
            # Stricter checks (v2)
            MAX_TOP20 = 50  # top 20 holders max 50% (relaxed)
            if dev_pct > MAX_DEV_HOLDING:
                results["verdict"] = "REJECT"
                results["reject_reasons"].append(f"Dev {dev_pct:.1f}% > {MAX_DEV_HOLDING}%")
                print(f"   🔴 REJECTED: Dev {dev_pct:.2f}% > {MAX_DEV_HOLDING}%")
            elif top20 > MAX_TOP20:
                results["verdict"] = "REJECT"
                results["reject_reasons"].append(f"Top20 {top20:.1f}% > {MAX_TOP20}%")
                print(f"   🔴 REJECTED: Top20 {top20:.2f}% > {MAX_TOP20}%")
            else:
                print(f"   ✅ PASSED: Dev {dev_pct:.2f}% < {MAX_DEV_HOLDING}% | Top20 {top20:.2f}% < {MAX_TOP20}%")
    except Exception as e:
        print(f"   ❌ {e}")
        results["checks"]["holders"] = {"error": str(e)}
        results["verdict"] = "SKIP"

    if results["verdict"] == "REJECT":
        print("\n" + "="*70 + "\n🚫 REJECTED\n" + "="*70)
        for r in results["reject_reasons"]: print(f"  - {r}")
        return results

    # CHECK 3: JUPITER BUY
    print("\n[3/10] JUPITER BUY PRICE")
    print("-" * 50)
    rate_limit()
    sol = "So11111111111111111111111111111111111111112"
    try:
        params = {"inputMint": sol, "outputMint": mint, "amount": int(BUY_AMOUNT * 1e9), "slippage": 10}
        r = requests.get("https://api.jup.ag/swap/v1/quote", params=params, headers=headers, timeout=15)
        if r.status_code == 200:
            quote = r.json()
            out = int(quote.get("outAmount", 0))
            route = quote.get("routePlan", [{}])[0].get("swapInfo", {}).get("label", "?")
            price_per_token = BUY_AMOUNT / (out / 1e6) if out > 0 else 0
            print(f"   ✅ Route: {route}")
            print(f"   ✅ {BUY_AMOUNT} SOL → {out:,} tokens")
            print(f"   ✅ Price: {price_per_token:.10f} SOL/token")
            results["checks"]["buy_quote"] = {"price": price_per_token, "tokens": out/1e6, "route": route, "quote": quote}
        else:
            print(f"   ❌ {r.status_code}")
            results["verdict"] = "SKIP"
            results["reject_reasons"].append("No buy quote")
    except Exception as e:
        print(f"   ❌ {e}")
        results["verdict"] = "SKIP"

    # CHECK 4: JUPITER SELL
    print("\n[4/10] JUPITER SELL CHECK (Can Exit?)")
    print("-" * 50)
    rate_limit()
    try:
        decimals = results["checks"].get("supply", {}).get("decimals", 6)
        sell_amt = 1 * (10 ** decimals)
        params = {"inputMint": mint, "outputMint": sol, "amount": sell_amt, "slippage": 10}
        r = requests.get("https://api.jup.ag/swap/v1/quote", params=params, headers=headers, timeout=15)
        if r.status_code == 200:
            sq = r.json()
            out_sol = int(sq.get("outAmount", 0))
            route = sq.get("routePlan", [{}])[0].get("swapInfo", {}).get("label", "?")
            sell_price = out_sol / sell_amt if sell_amt > 0 else 0
            print(f"   ✅ CAN SELL: YES ({route})")
            print(f"   ✅ Price per token: {sell_price:.10f} SOL")
            results["checks"]["sell_quote"] = {"can_sell": True, "route": route, "sell_price": sell_price}
        else:
            print(f"   ❌ NO SELL ROUTE ({r.status_code})")
            results["checks"]["sell_quote"] = {"can_sell": False}
            results["verdict"] = "REJECT"
            results["reject_reasons"].append(f"No Jupiter sell route {r.status_code}")
    except Exception as e:
        print(f"   ❌ {e}")
        results["verdict"] = "REJECT"

    if results["verdict"] == "REJECT":
        print("\n" + "="*70 + "\n🚫 REJECTED\n" + "="*70)
        for r in results["reject_reasons"]: print(f"  - {r}")
        return results

    # CHECK 5: DEXSCREENER
    print("\n[5/10] DEXSCREENER")
    print("-" * 50)
    rate_limit()
    try:
        r = requests.get(f"https://api.dexscreener.com/v1/tokens/solana:{mint}", timeout=10)
        if r.status_code == 200:
            d = r.json()
            pairs = d.get("pairs", [])
            if pairs:
                p = sorted(pairs, key=lambda x: float(x.get("liquidity", {}).get("usd", 0) or 0), reverse=True)[0]
                liq = float(p.get("liquidity", {}).get("usd", 0) or 0)
                vol = p.get("volume", {}).get("h24", {})
                print(f"   ✅ Liquidity: ${liq:,.2f}")
                print(f"   ✅ Vol 24h: buys={vol.get('buys','?')} sells={vol.get('sells','?')}")
                results["checks"]["dexscreener"] = {"liquidity": liq, "volume": vol}
            else:
                print("   ⚠️ No pairs")
                results["checks"]["dexscreener"] = {"no_pairs": True}
        else:
            print(f"   ⚠️ {r.status_code}")
    except Exception as e:
        print(f"   ⚠️ {e}")

    # CHECK 6: GECKOTERMINAL
    print("\n[6/10] GECKOTERMINAL")
    print("-" * 50)
    rate_limit()
    try:
        r = requests.get(f"https://api.geckoterminal.com/api/v2/networks/solana/tokens/{mint}", timeout=15)
        if r.status_code == 200:
            d = r.json().get("data", {}).get("attributes", {})
            print(f"   ✅ FDV: ${d.get('fdv_usd','N/A')}")
            print(f"   ✅ Network: {d.get('network','?')}")
            results["checks"]["geckoterminal"] = {"fdv": d.get("fdv_usd")}
        else:
            print(f"   ⚠️ {r.status_code}")
    except Exception as e:
        print(f"   ⚠️ {e}")

    # CHECK 7: RUGCHECK
    print("\n[7/10] RUGCHECK")
    print("-" * 50)
    rate_limit()
    try:
        r = requests.get(f"https://api.rugcheck.xyz/v1/tokens/{mint}/report", headers={"Accept": "application/json"}, timeout=15)
        if r.status_code == 200:
            d = r.json()
            score = d.get("score", "?")
            score_norm = d.get("score_normalised", "?")
            rugged = d.get("rugged", False)
            mint_auth = d.get("mintAuthority")
            freeze_auth = d.get("freezeAuthority")
            print(f"   ✅ Score: {score} (normalized: {score_norm})")
            print(f"   ✅ Rugged: {rugged}")
            print(f"   ✅ Mint Auth: {'REVOKED ✅' if not mint_auth else 'ACTIVE ⚠️'}")
            print(f"   ✅ Freeze Auth: {'REVOKED ✅' if not freeze_auth else 'ACTIVE ⚠️'}")
            results["checks"]["rugcheck"] = {"score": score, "rugged": rugged, "mint_auth": mint_auth, "freeze_auth": freeze_auth}
        else:
            print(f"   ⚠️ {r.status_code}")
    except Exception as e:
        print(f"   ⚠️ {e}")

    # CHECK 8: EXISTING WALLET POSITION
    print("\n[8/10] EXISTING WALLET POSITION")
    print("-" * 50)
    wallet_tokens = get_wallet_tokens()
    if mint in wallet_tokens:
        info = wallet_tokens[mint]
        print(f"   ⚠️ ALREADY IN WALLET: {info['amount']:.4f} tokens")
        results["checks"]["existing_position"] = info
    else:
        print(f"   ✅ No existing position")
        results["checks"]["existing_position"] = None

    # CHECK 9: SOL BALANCE
    print("\n[9/10] SOL BALANCE")
    print("-" * 50)
    sol_bal = get_sol_balance()
    can_buy = sol_bal >= BUY_AMOUNT
    print(f"   ✅ Balance: {sol_bal:.4f} SOL")
    print(f"   ✅ Can afford {BUY_AMOUNT} SOL? {'YES ✅' if can_buy else 'NO ❌'}")
    results["checks"]["sol_balance"] = {"balance": sol_bal, "can_buy": can_buy}

    # CHECK 10: TP/SL
    print("\n[10/10] TP/SL SETTINGS")
    print("-" * 50)
    buy_price = results["checks"].get("buy_quote", {}).get("price", 0)
    if buy_price > 0:
        tp = buy_price * 2.0   # +100% profit target
        sl = buy_price * 0.8   # -20% stop loss per token
        tokens_expected = results["checks"]["buy_quote"]["tokens"]
        tp_profit = (tp - buy_price) * tokens_expected * 1e6
        sl_loss = (buy_price - sl) * tokens_expected * 1e6
        print(f"   Entry: {buy_price:.10f} SOL")
        print(f"   TP 100%: {tp:.10f} SOL (+{tp_profit:.6f} SOL)")
        print(f"   SL 20%: {sl:.10f} SOL (-{sl_loss:.6f} SOL)")
        print(f"   R:R: {abs(tp_profit)/max(abs(sl_loss), 0.000001):.1f}:1")
        results["checks"]["tp_sl"] = {"entry": buy_price, "tp": tp, "sl": sl, "tp_profit": tp_profit, "sl_loss": sl_loss}
    else:
        print("   ⚠️ No buy price")
        results["checks"]["tp_sl"] = {"error": "no buy price"}

    # FINAL
    print("\n" + "=" * 70)
    if results["verdict"] == "REJECT":
        print("🚫 STATUS: REJECTED")
        for r in results["reject_reasons"]: print(f"  - {r}")
    elif results["verdict"] == "SKIP":
        print("⚠️ STATUS: SKIPPED")
        for r in results["reject_reasons"]: print(f"  - {r}")
    else:
        print("✅ STATUS: PASSED - READY TO BUY")
        if buy_price > 0:
            print(f"   Entry: {buy_price:.10f} | TP: {results['checks']['tp_sl']['tp']:.10f} | SL: {results['checks']['tp_sl']['sl']:.10f}")
            print(f"   SOL: {sol_bal:.4f} | Can buy: {'YES' if can_buy else 'NO'}")
    print("=" * 70)

    return results


def buy_and_track(mint, amount_sol=BUY_AMOUNT):
    """Execute buy, verify on-chain, track properly"""
    from solders.keypair import Keypair
    from solders.transaction import VersionedTransaction
    import base58
    
    PRIVATE_KEY = "2ph75CovJ4wwcyMxUBKATswphUWb6SSep5TH2Z4XChCSBbnxW7U2uxWaAvr2UqRbB5QriQAvNFx9uH1b8MtPrwzT"
    keypair = Keypair.from_bytes(base58.b58decode(PRIVATE_KEY))
    sol = "So11111111111111111111111111111111111111112"
    
    print(f"\n{'='*70}")
    print(f"🟢 BUY EXECUTION: {mint[:30]}... ({amount_sol} SOL)")
    print(f"{'='*70}")
    
    # Pre-buy wallet state
    pre_tokens = get_wallet_tokens()
    pre_sol = get_sol_balance()
    print(f"Pre-buy SOL: {pre_sol:.6f}")
    
    # Get quote
    print("\n[1] Getting quote...")
    rate_limit()
    params = {"inputMint": sol, "outputMint": mint, "amount": int(amount_sol * 1e9), "slippage": 10}
    r = requests.get("https://api.jup.ag/swap/v1/quote", params=params, headers=headers, timeout=15)
    if r.status_code != 200:
        print(f"FAIL: {r.status_code}")
        return None
    quote = r.json()
    token_amount = int(quote.get("outAmount", 0))
    price_per_token = amount_sol / (token_amount / 1e6) if token_amount > 0 else 0
    print(f"   ✅ {amount_sol} SOL → {token_amount:,} tokens @ {price_per_token:.10f}")
    
    # Build swap tx
    print("\n[2] Building transaction...")
    rate_limit()
    swap_resp = requests.post("https://api.jup.ag/swap/v1/swap", json={
        "userPublicKey": WALLET, "quoteResponse": quote, "wrapAndUnwrapSol": True
    }, headers=headers, timeout=30).json()
    tx = swap_resp.get("swapTransaction")
    if not tx:
        print(f"FAIL: {swap_resp}")
        return None
    print("   ✅ Transaction built")
    
    # Sign & send
    print("\n[3] Signing & broadcasting...")
    rate_limit()
    try:
        unsigned = VersionedTransaction.from_bytes(base64.b64decode(tx))
        signed = VersionedTransaction(unsigned.message, [keypair])
        tx_b64 = base64.b64encode(bytes(signed)).decode()
        
        send = requests.post(ALCH_RPC, json={
            "jsonrpc": "2.0", "id": 1, "method": "sendTransaction",
            "params": [tx_b64, {"encoding": "base64", "skipPreflight": True, "preflightCommitment": "processed"}]
        }, headers={"Content-Type": "application/json"}, timeout=60).json()
        
        buy_tx = send.get("result")
        if not buy_tx:
            print(f"   ❌ BROADCAST FAIL: {send}")
            return None
        print(f"   ✅ Broadcasted: {buy_tx}")
    except Exception as e:
        print(f"   ❌ {e}")
        return None
    
    # Verify on-chain (THIS IS THE KEY FIX)
    print("\n[4] Verifying on-chain (CRITICAL)...")
    time.sleep(8)  # Wait for confirmation
    verify = verify_tx_onchain(buy_tx)
    if not verify["confirmed"]:
        print(f"   ❌ TX NOT CONFIRMED: {verify.get('error', 'unknown')}")
        print(f"   ⚠️ Tokens may NOT have been received despite broadcast!")
        return {"tx": buy_tx, "confirmed": False, "warning": "TX not confirmed"}
    
    print(f"   ✅ ON-CHAIN CONFIRMED! Fee: {verify['fee']:.9f} SOL")
    
    # Check actual tokens received
    print("\n[5] Checking actual tokens in wallet...")
    post_tokens = get_wallet_tokens()
    pre_token_amount = pre_tokens.get(mint, {}).get("amount", 0)
    post_token_amount = post_tokens.get(mint, {}).get("amount", 0)
    received = post_token_amount - pre_token_amount
    
    post_sol = get_sol_balance()
    sol_spent = pre_sol - post_sol
    
    print(f"   Pre: {pre_token_amount:.4f} → Post: {post_token_amount:.4f}")
    print(f"   Tokens received: {received:.4f}")
    print(f"   SOL spent: {sol_spent:.6f}")
    
    if received < 1:
        print(f"   ⚠️ WARNING: Received {received} tokens — may be dust or failed!")
        actual_price = sol_spent / received if received > 0 else 0
        print(f"   ⚠️ Actual price: {actual_price:.10f} SOL/token")
    else:
        print(f"   ✅ REAL POSITION CONFIRMED!")
        actual_price = price_per_token  # Use quoted price as entry
    
    # Save to trades.json
    tp = actual_price * 1.5
    sl = actual_price * 0.8
    
    try:
        with open("/root/.openclaw/workspace-minimaxbot/trading-bot/data/trades.json", "r") as f:
            data = json.load(f)
    except:
        data = {"buys": {}, "sells": []}
    
    data["buys"][mint] = {
        "price_per_token": actual_price,
        "buy_tx": buy_tx,
        "tp_price": tp,
        "sl_price": sl,
        "tp_percent": 100,
        "sl_percent": 20,
        "total_sol": sol_spent,
        "tokens_received": received,
        "confirmed": verify["confirmed"],
        "time": time.strftime("%Y-%m-%dT%H:%M:%S")
    }
    
    with open("/root/.openclaw/workspace-minimaxbot/trading-bot/data/trades.json", "w") as f:
        json.dump(data, f, indent=2)
    
    print(f"\n   TP 100%: {tp:.10f} SOL")
    print(f"   SL 20%: {sl:.10f} SOL")
    print(f"   ✅ TRACKED & SAVED")
    
    print(f"\n{'='*70}")
    print(f"✅ BUY COMPLETE")
    print(f"   TX: {buy_tx}")
    print(f"   Solscan: https://solscan.io/tx/{buy_tx}")
    print(f"   Tokens: {received:.4f}")
    print(f"   Entry: {actual_price:.10f} SOL")
    print(f"{'='*70}")
    
    return {"tx": buy_tx, "confirmed": verify["confirmed"], "received": received, "entry": actual_price}


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python3 deep_analysis.py <TOKEN_MINT> [buy]")
        exit(1)
    
    mint = sys.argv[1]
    results = deep_analyze(mint)
    
    if len(sys.argv) > 2 and sys.argv[2] == "buy" and results["verdict"] == "PASS":
        print("\n")
        buy_and_track(mint)