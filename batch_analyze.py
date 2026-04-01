#!/usr/bin/env python3
"""Quick batch analyzer for multiple tokens"""
import requests
import time
import sys

ALCH_RPC = "https://solana-mainnet.g.alchemy.com/v2/koEw2jzP14JkBeAU4Wzw9"
QUICKNODE = "https://empty-hidden-grass.solana-mainnet.quiknode.pro/ca3087fb95c146dab3c3a247aefeecb25a4ad0af/"
JUPITER_KEY = "491784ae-9799-4ecf-8d18-63bfd5f932dd"
headers = {"x-api-key": JUPITER_KEY}
WALLET = "FRGVy5xEk7tKyeBcWP1Mkj97Tv4aFPWHaQJnNggKe7Cf"
BUY_AMOUNT = 0.005
# STRICTER FILTERS (v2)
MAX_DEV = 20        # was 35 - only low dev tokens
MAX_TOP20 = 50     # was 40 - relaxed to 50%

def rate(s=1.5):
    time.sleep(s)

def get_sol():
    r = requests.post(ALCH_RPC, json={"jsonrpc":"2.0","id":1,"method":"getBalance","params":[WALLET]}, headers={"Content-Type":"application/json"}, timeout=10)
    return r.json().get("result",{}).get("value",0)/1e9

def get_token_supply(mint):
    try:
        r = requests.post(ALCH_RPC, json={
            "jsonrpc": "2.0", "id": 1, "method": "getTokenSupply",
            "params": [mint]
        }, headers={"Content-Type": "application/json"}, timeout=10)
        result = r.json().get("result", {})
        if result:
            return int(result["value"]["amount"]), result["value"].get("decimals", 0)
    except:
        pass
    return 0, 0

def get_token_holders(mint):
    try:
        r = requests.post(ALCH_RPC, json={
            "jsonrpc": "2.0", "id": 1,
            "method": "getTokenLargestAccounts",
            "params": [mint, {"commitment": "processed"}]
        }, headers={"Content-Type": "application/json"}, timeout=15)
        result = r.json().get("result", {})
        if result and result.get("value"):
            accounts = [(acc["address"], int(acc["amount"])) for acc in result["value"]]
            total = sum(amt for _, amt in accounts)
            return accounts, total
    except:
        pass
    return [], 0

def check_jupiter_buy(mint):
    try:
        params = {"inputMint": mint, "outputMint": "So11111111111111111111111111111111111111112", "amount": 1000000, "slippage": 5}
        r = requests.get("https://api.jup.ag/swap/v1/quote", params=params, headers=headers, timeout=15)
        if r.status_code == 200:
            return True, int(r.json().get("outAmount","0")) / 1e9
    except:
        pass
    return False, 0

def check_jupiter_sell(mint, amount):
    try:
        params = {"inputMint": mint, "outputMint": "So11111111111111111111111111111111111111112", "amount": amount, "slippage": 5}
        r = requests.get("https://api.jup.ag/swap/v1/quote", params=params, headers=headers, timeout=15)
        if r.status_code == 200:
            return True, int(r.json().get("outAmount","0")) / 1e9
    except:
        pass
    return False, 0

def get_wallet_tokens():
    tokens = {}
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
                        tokens[mint] = amt
    return tokens

def analyze_token(mint):
    print(f"\n{'='*60}")
    print(f"🔍 {mint}")
    print(f"{'='*60}")
    
    reasons = []
    passed = True
    
    # 1. Supply
    supply, dec = get_token_supply(mint)
    rate(1)
    if supply == 0:
        reasons.append("❌ Supply error")
        passed = False
    else:
        print(f"✅ Supply: {supply:,} ({dec} decimals)")
    
    # 2. Dev holding + Top 20 check
    holders, total = get_token_holders(mint)
    rate(1)
    if holders:
        dev_pct = (holders[0][1] / total * 100) if total > 0 else 100
        top5_pct = sum(h[1] for h in holders[:5]) / total * 100 if total > 0 else 100
        top20_pct = sum(h[1] for h in holders[:20]) / total * 100 if total > 0 else 100
        print(f"   Dev: {dev_pct:.2f}% | Top5: {top5_pct:.2f}% | Top20: {top20_pct:.2f}%")
        if dev_pct > MAX_DEV:
            reasons.append(f"❌ Dev {dev_pct:.2f}% > {MAX_DEV}%")
            passed = False
        elif top20_pct > MAX_TOP20:
            reasons.append(f"❌ Top20 {top20_pct:.2f}% > {MAX_TOP20}%")
            passed = False
        else:
            print(f"✅ Dev {dev_pct:.2f}% < {MAX_DEV}% | Top20 {top20_pct:.2f}% < {MAX_TOP20}%")
    else:
        reasons.append("❌ No holder data")
        passed = False
    
    # 3. Jupiter buy price
    can_buy, buy_price = check_jupiter_buy(mint)
    rate(1.5)
    if not can_buy:
        reasons.append("❌ Cannot buy on Jupiter")
        passed = False
    else:
        print(f"✅ Jupiter buy: {buy_price:.10f} SOL/token")
    
    # 5. Jupiter sell check
    wallet_tokens = get_wallet_tokens()
    test_amount = max(wallet_tokens.get(mint, 1000000), 1000000)
    can_sell, sell_price = check_jupiter_sell(mint, test_amount)
    rate(1.5)
    if not can_sell:
        reasons.append("❌ Cannot sell on Jupiter (no route)")
        passed = False
    else:
        print(f"✅ Jupiter sell: {sell_price:.10f} SOL/token")
    
    # 6. SOL balance
    sol = get_sol()
    print(f"   SOL balance: {sol:.6f}")
    if sol < BUY_AMOUNT:
        reasons.append(f"❌ SOL {sol:.4f} < {BUY_AMOUNT}")
        passed = False
    
    print(f"\n{'='*60}")
    if passed:
        print(f"✅ PASSED — READY TO BUY")
        print(f"   Entry: {buy_price:.10f} SOL")
        print(f"   Dev: {dev_pct:.2f}% | Sellable: YES")
    else:
        print(f"🔴 REJECTED:")
        for r in reasons:
            print(f"   {r}")
    print(f"{'='*60}")
    
    return {
        "mint": mint,
        "passed": passed,
        "dev_pct": dev_pct if holders else 100,
        "buy_price": buy_price,
        "reasons": reasons
    }

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python3 batch_analyze.py <TOKEN1> <TOKEN2> ...")
        exit(1)
    
    tokens = sys.argv[1:]
    print(f"\n{'#'*60}")
    print(f"# BATCH ANALYZER — {len(tokens)} TOKENS")
    print(f"# SOL Balance: {get_sol():.6f}")
    print(f"{'#'*60}")
    
    results = []
    for i, token in enumerate(tokens):
        print(f"\n[{i+1}/{len(tokens)}] Analyzing...")
        result = analyze_token(token)
        results.append(result)
    
    # Summary
    print(f"\n{'#'*60}")
    print(f"# SUMMARY")
    print(f"{'#'*60}")
    passed_list = [r for r in results if r["passed"]]
    rejected_list = [r for r in results if not r["passed"]]
    
    print(f"\n✅ PASSED ({len(passed_list)}):")
    for r in passed_list:
        print(f"   • {r['mint']}")
        print(f"     Dev: {r['dev_pct']:.2f}% | Price: {r['buy_price']:.10f}")
    
    print(f"\n🔴 REJECTED ({len(rejected_list)}):")
    for r in rejected_list:
        print(f"   • {r['mint'][:30]}...")
        for reason in r['reasons']:
            print(f"     {reason}")
    
    print(f"\n{'#'*60}")
