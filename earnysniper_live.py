#!/usr/bin/env python3
"""
EARNY Sniper - Complete Trading System v5.0
Fixed & Enhanced
"""
import requests
import os
import sys
import json
import base58
import base64
import time
from datetime import datetime
from dotenv import load_dotenv
from solders.keypair import Keypair
from solders.transaction import VersionedTransaction

load_dotenv("/root/.openclaw/workspace-minimaxbot/trading-bot/.env")

# Configuration
QUICKNODE_RPC = os.getenv("QUICKNODE_RPC_URL", "https://empty-hidden-grass.solana-mainnet.quiknode.pro/ca3087fb95c146dab3c3a247aefeecb25a4ad0af/")
ALCH_RPC = os.getenv("SOLANA_RPC_URL", "https://solana-mainnet.g.alchemy.com/v2/koEw2jzP14JkBeAU4Wzw9")
JUPITER_KEY = os.getenv("JUPITER_API_KEY", "491784ae-9799-4ecf-8d18-63bfd5f932dd")
WALLET = os.getenv("WALLET_ADDRESS", "")
PRIVATE_KEY = os.getenv("WALLET_SECRET", "")

# Trading settings
MAX_DEV_HOLDING = 35  # Max 35% dev holding
MIN_LIQUIDITY = 2000  # Min $2000 liquidity
MIN_MCAP = 3000       # Min $3000 mcap
MAX_MCAP = 80000      # Max $80k mcap
BUY_AMOUNT = 0.005    # 0.005 SOL per trade
PROFIT_TARGET = 50    # 50% profit
STOP_LOSS = -20       # 20% stop loss

class EARNYSniper:
    def __init__(self):
        self.headers = {"x-api-key": JUPITER_KEY}
        self.wallet = WALLET
        self.keypair = Keypair.from_bytes(base58.b58decode(PRIVATE_KEY))
        
        # Load entry prices
        self.entry_prices = self.load_entry_prices()
    
    def load_entry_prices(self):
        """Load entry prices from trades file"""
        try:
            with open("/root/.openclaw/workspace-minimaxbot/trading-bot/data/trades.json", "r") as f:
                data = json.load(f)
                return data.get("buys", {})
        except:
            return {}
    
    def save_entry_price(self, mint, price, amount_sol):
        """Save entry price for TP/SL tracking"""
        try:
            os.makedirs("/root/.openclaw/workspace-minimaxbot/trading-bot/data", exist_ok=True)
            try:
                with open("/root/.openclaw/workspace-minimaxbot/trading-bot/data/trades.json", "r") as f:
                    data = json.load(f)
            except:
                data = {"buys": {}, "sells": []}
            
            data["buys"][mint] = {
                "price_per_token": price,
                "total_sol": amount_sol,
                "time": datetime.now().isoformat()
            }
            
            with open("/root/.openclaw/workspace-minimaxbot/trading-bot/data/trades.json", "w") as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            print(f"Error saving entry: {e}")
    
    def get_wallet_tokens(self):
        """Get all token holdings"""
        tokens = {}
        
        for program in ["TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA", "TokenzQdBNbLqP5VEhdkAS6EPFLC1PHnBqCXEpPxuEb"]:
            try:
                payload = {
                    "jsonrpc": "2.0", "id": 1, "method": "getTokenAccountsByOwner",
                    "params": [self.wallet, {"programId": program}, {"encoding": "jsonParsed"}]
                }
                resp = requests.post(QUICKNODE_RPC, json=payload, headers={"Content-Type": "application/json"}, timeout=15)
                data = resp.json()
                
                if data.get("result", {}).get("value"):
                    for acc in data["result"]["value"]:
                        info = acc["account"]["data"]["parsed"]["info"]
                        mint = info["mint"]
                        amount = int(info["tokenAmount"]["amount"])
                        decimals = info["tokenAmount"]["decimals"]
                        
                        if amount > 0:
                            tokens[mint] = {
                                "amount": amount / (10 ** decimals),
                                "amount_raw": amount,
                                "decimals": decimals
                            }
            except:
                pass
        
        return tokens
    
    def get_sol_balance(self):
        """Get SOL balance"""
        try:
            payload = {"jsonrpc": "2.0", "id": 1, "method": "getBalance", "params": [self.wallet]}
            resp = requests.post(QUICKNODE_RPC, json=payload, headers={"Content-Type": "application/json"}, timeout=10)
            return resp.json().get("result", {}).get("value", 0) / 1e9
        except:
            return 0
    
    def check_dev_holding(self, mint):
        """Check dev holding percentage"""
        try:
            # Get largest accounts
            r1 = requests.post(ALCH_RPC, json={
                "jsonrpc": "2.0", "id": 1, "method": "getTokenLargestAccounts",
                "params": [mint]
            }, timeout=15)
            
            # Get total supply
            r2 = requests.post(ALCH_RPC, json={
                "jsonrpc": "2.0", "id": 2, "method": "getTokenSupply",
                "params": [mint]
            }, timeout=15)
            
            if r1.status_code == 200 and r2.status_code == 200:
                holders = r1.json().get("result", {}).get("value", [])
                total = int(r2.json().get("result", {}).get("value", {}).get("amount", 1))
                
                if holders and total > 0:
                    dev_pct = (int(holders[0]["amount"]) / total) * 100
                    return dev_pct
            
            return 100  # Assume high if error
        except:
            return 100
    
    def check_jupiter_sell(self, mint, amount=1000000):
        """Check if token can be sold via Jupiter"""
        try:
            params = {
                "inputMint": mint,
                "outputMint": "So11111111111111111111111111111111111111112",
                "amount": amount,
                "slippage": 10
            }
            resp = requests.get("https://api.jup.ag/swap/v1/quote", params=params, headers=self.headers, timeout=15)
            
            if resp.status_code == 200:
                out = resp.json().get("outAmount", "0")
                return int(out) > 0
            return False
        except:
            return False
    
    def get_token_price(self, mint):
        """Get current token price in SOL"""
        try:
            params = {
                "inputMint": mint,
                "outputMint": "So11111111111111111111111111111111111111112",
                "amount": 1000000,
                "slippage": 1
            }
            resp = requests.get("https://api.jup.ag/swap/v1/quote", params=params, headers=self.headers, timeout=10)
            if resp.status_code == 200:
                quote = resp.json()
                out = quote.get("outAmount")
                if out and float(out) > 0:
                    return float(out) / 1000000
        except:
            pass
        return 0
    
    def scan_tokens(self, max_pages=2):
        """Scan for tokens that pass all checks"""
        print("=" * 60)
        print("🚀 EARNY SCANNER v5.0")
        print("=" * 60)
        
        dexs = ["pump", "meteora", "raydium"]
        all_tokens = []
        
        for dex in dexs:
            print(f"\n📡 Scanning {dex}...")
            
            for page in range(1, max_pages + 1):
                try:
                    r = requests.get(
                        "https://api.geckoterminal.com/api/v2/networks/solana/pools",
                        params={"dex": dex, "page": page, "limit": 50},
                        timeout=20
                    )
                    
                    if r.status_code != 200:
                        break
                    
                    pools = r.json().get("data", [])
                    
                    for pool in pools:
                        attrs = pool.get("attributes", {})
                        rels = pool.get("relationships", {})
                        
                        mcap = float(attrs.get("market_cap_usd") or attrs.get("fdv_usd") or 0)
                        
                        base = rels.get("base_token", {}).get("data", {})
                        quote = rels.get("quote_token", {}).get("data", {})
                        
                        base_addr = base.get("id", "").replace("solana_", "")
                        quote_addr = quote.get("id", "").replace("solana_", "")
                        
                        # Filter
                        if not base_addr:
                            continue
                        if mcap and MIN_MCAP <= mcap <= MAX_MCAP:
                            if quote_addr == "So11111111111111111111111111111111111111112":
                                all_tokens.append({
                                    "token": base_addr,
                                    "symbol": base.get("symbol", "?"),
                                    "mcap": mcap,
                                    "dex": dex
                                })
                    
                    time.sleep(1)  # Rate limit
                    
                except Exception as e:
                    print(f"   Error: {e}")
                    break
        
        # Dedupe
        seen = set()
        tokens = []
        for t in all_tokens:
            if t["token"] not in seen:
                seen.add(t["token"])
                tokens.append(t)
        
        tokens.sort(key=lambda x: x["mcap"])
        
        print(f"\n📊 Found {len(tokens)} unique tokens")
        
        # Check each token
        print("\n" + "=" * 60)
        print("🔍 ANALYSIS")
        print("=" * 60)
        
        passed = []
        
        for t in tokens[:10]:  # Check first 10
            addr = t["token"]
            sym = t["symbol"]
            mcap = t["mcap"]
            dex = t["dex"]
            
            print(f"\n📦 {sym} (${mcap:,.0f}) [{dex}]")
            
            # Dev check
            dev_pct = self.check_dev_holding(addr)
            print(f"   Dev: {dev_pct:.1f}%")
            
            if dev_pct > MAX_DEV_HOLDING:
                print(f"   ❌ HIGH DEV - SKIP")
                continue
            
            # Jupiter sell check
            time.sleep(1.2)
            can_sell = self.check_jupiter_sell(addr)
            
            if not can_sell:
                print(f"   ❌ CANNOT SELL - SKIP")
                continue
            
            print(f"   ✅ PASSED!")
            passed.append(t)
            
            # Stop after 1 good candidate
            break
        
        return passed
    
    def buy_token(self, mint, amount_sol=BUY_AMOUNT):
        """Buy token via Jupiter"""
        sol = "So11111111111111111111111111111111111111112"
        amount_lamports = int(amount_sol * 1e9)
        
        print(f"\n🔴 BUYING {mint[:30]}... ({amount_sol} SOL)")
        
        # Get quote
        params = {"inputMint": sol, "outputMint": mint, "amount": amount_lamports, "slippage": 10}
        resp = requests.get("https://api.jup.ag/swap/v1/quote", params=params, headers=self.headers, timeout=15)
        
        if resp.status_code != 200:
            return {"success": False, "error": f"Quote failed: {resp.status_code}"}
        
        quote = resp.json()
        token_amount = int(quote.get("outAmount", 0))
        
        if token_amount == 0:
            return {"success": False, "error": "No output"}
        
        # Get swap tx
        swap_resp = requests.post("https://api.jup.ag/swap/v1/swap", json={
            "userPublicKey": self.wallet,
            "quoteResponse": quote,
            "wrapAndUnwrapSol": True
        }, headers=self.headers, timeout=30).json()
        
        if "swapTransaction" not in swap_resp:
            return {"success": False, "error": "No swap transaction"}
        
        # Sign and send
        try:
            unsigned = VersionedTransaction.from_bytes(base64.b64decode(swap_resp["swapTransaction"]))
            signed = VersionedTransaction(unsigned.message, [self.keypair])
            signed_b64 = base64.b64encode(bytes(signed)).decode()
            
            send_resp = requests.post(QUICKNODE_RPC, json={
                "jsonrpc": "2.0", "id": 1, "method": "sendTransaction",
                "params": [signed_b64, {"encoding": "base64", "skipPreflight": True}]
            }, timeout=60).json()
            
            if "result" in send_resp:
                # Save entry price
                price_per_token = amount_sol / (token_amount / 1e6)
                self.save_entry_price(mint, price_per_token, amount_sol)
                
                print(f"✅ BUY SUCCESS! TX: {send_resp['result'][:40]}...")
                return {"success": True, "tx_hash": send_resp["result"]}
            
            return {"success": False, "error": str(send_resp)}
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    def sell_token(self, mint, percentage=100):
        """Sell token via Jupiter"""
        sol = "So11111111111111111111111111111111111111112"
        
        positions = self.get_wallet_tokens()
        if mint not in positions:
            return {"success": False, "error": "No position"}
        
        amount_raw = positions[mint]["amount_raw"]
        sell_amount = int(amount_raw * (percentage / 100))
        
        print(f"\n🔴 SELLING {mint[:30]}... ({percentage}%)")
        
        # Get quote
        params = {"inputMint": mint, "outputMint": sol, "amount": sell_amount, "slippage": 5}
        resp = requests.get("https://api.jup.ag/swap/v1/quote", params=params, headers=self.headers, timeout=15)
        
        if resp.status_code != 200:
            return {"success": False, "error": f"Quote failed: {resp.status_code}"}
        
        quote = resp.json()
        
        # Get swap tx
        swap_resp = requests.post("https://api.jup.ag/swap/v1/swap", json={
            "userPublicKey": self.wallet,
            "quoteResponse": quote,
            "wrapAndUnwrapSol": True
        }, headers=self.headers, timeout=30).json()
        
        if "swapTransaction" not in swap_resp:
            return {"success": False, "error": "No swap transaction"}
        
        # Sign and send
        try:
            unsigned = VersionedTransaction.from_bytes(base64.b64decode(swap_resp["swapTransaction"]))
            signed = VersionedTransaction(unsigned.message, [self.keypair])
            signed_b64 = base64.b64encode(bytes(signed)).decode()
            
            send_resp = requests.post(QUICKNODE_RPC, json={
                "jsonrpc": "2.0", "id": 1, "method": "sendTransaction",
                "params": [signed_b64, {"encoding": "base64", "skipPreflight": True}]
            }, timeout=60).json()
            
            if "result" in send_resp:
                print(f"✅ SELL SUCCESS! TX: {send_resp['result'][:40]}...")
                return {"success": True, "tx_hash": send_resp["result"]}
            
            return {"success": False, "error": str(send_resp)}
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    def check_tp_sl(self):
        """Check and execute TP/SL for all positions"""
        print("\n" + "=" * 60)
        print("🎯 AUTO TP/SL CHECK")
        print("=" * 60)
        
        positions = self.get_wallet_tokens()
        sol_balance = self.get_sol_balance()
        
        print(f"\n💰 SOL: {sol_balance:.4f}")
        print(f"📊 Positions: {len(positions)}")
        
        for mint, info in positions.items():
            current_price = self.get_token_price(mint)
            
            if current_price == 0:
                continue
            
            entry_data = self.entry_prices.get(mint, {})
            entry_price = entry_data.get("price_per_token", 0)
            
            if entry_price > 0:
                pnl_pct = ((current_price - entry_price) / entry_price) * 100
            else:
                pnl_pct = 0
            
            print(f"\n📍 {mint[:30]}...")
            print(f"   Amount: {info['amount']:.2f}")
            print(f"   Entry: {entry_price:.8f}")
            print(f"   Current: {current_price:.8f}")
            print(f"   P&L: {pnl_pct:+.2f}%")
            
            # TP
            if pnl_pct >= PROFIT_TARGET:
                print(f"   🎯 TP TRIGGERED!")
                result = self.sell_token(mint, 100)
                print(f"   {'✅ SOLD' if result.get('success') else '❌ FAILED'}")
            
            # SL
            elif pnl_pct <= STOP_LOSS:
                print(f"   🛡️ SL TRIGGERED!")
                result = self.sell_token(mint, 100)
                print(f"   {'✅ SOLD' if result.get('success') else '❌ FAILED'}")
    
    def status(self):
        """Show current status"""
        positions = self.get_wallet_tokens()
        sol_balance = self.get_sol_balance()
        
        print("\n" + "=" * 60)
        print("📊 EARNY STATUS")
        print("=" * 60)
        print(f"\n💰 SOL: {sol_balance:.4f}")
        print(f"📊 Positions: {len(positions)}")
        
        for mint, info in positions.items():
            current = self.get_token_price(mint)
            entry = self.entry_prices.get(mint, {}).get("price_per_token", 0)
            
            pnl = 0
            if entry > 0 and current > 0:
                pnl = ((current - entry) / entry) * 100
            
            print(f"\n{mint[:30]}...")
            print(f"   Amount: {info['amount']:.2f}")
            print(f"   Entry: {entry:.8f}")
            print(f"   Current: {current:.8f}")
            print(f"   P&L: {pnl:+.2f}%")
        
        print("\n" + "=" * 60)

def main():
    bot = EARNYSniper()
    
    if len(sys.argv) > 1:
        cmd = sys.argv[1].lower()
        
        if cmd == "scan":
            bots = bot.scan_tokens()
            if bots:
                for b in bots:
                    print(f"\n🎯 {b['symbol']}: {b['token']}")
            else:
                print("\n❌ No tokens passed")
        
        elif cmd == "buy":
            token = sys.argv[2] if len(sys.argv) > 2 else ""
            if token:
                result = bot.buy_token(token)
                print(result)
            else:
                print("Usage: earnysniper_live.py buy <TOKEN_ADDRESS>")
        
        elif cmd == "sell":
            token = sys.argv[2] if len(sys.argv) > 2 else ""
            if token:
                result = bot.sell_token(token)
                print(result)
            else:
                print("Usage: earnysniper_live.py sell <TOKEN_ADDRESS>")
        
        elif cmd == "check":
            bot.check_tp_sl()
        
        elif cmd == "status":
            bot.status()
        
        else:
            print("Commands: scan, buy <token>, sell <token>, check, status")
    else:
        bot.status()

if __name__ == "__main__":
    main()
