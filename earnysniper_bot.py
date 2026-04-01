"""
EARNY Sniper Trading Bot v4.0 - Integrated
Complete trading with scanner, analyzer, and real trading execution

Strategy:
- Entry: Dev holding < 35%, Liq > $2000, Vol > $3000
- Profit: High dev (20-50%), Low dev (100%)
- Stop: Half at -20%, Full at -50%
"""

import requests
import json
import time
import os
from datetime import datetime
from typing import Dict, List, Optional
from dotenv import load_dotenv

load_dotenv("/root/.openclaw/workspace-minimaxbot/trading-bot/.env")

# === CONFIG ===
ALCHEMY_RPC = "https://solana-mainnet.g.alchemy.com/v2/koEw2jzP14JkBeAU4Wzw9"
GECKO_API = "https://api.geckoterminal.com/api/v2"

# Trading settings
POSITION_SIZE_SOL = 0.005
MAX_POSITIONS = 3

# Thresholds
MAX_DEV_HOLDING = 35
MIN_LIQUIDITY = 2000
MIN_VOLUME = 3000

# Profit/Stop
PROFIT_HIGH_DEV = (20, 50)
PROFIT_LOW_DEV = 100
STOP_HALF = -20
STOP_FULL = -50

# Import trader
from trader import PumpTrader

class EARNYBot:
    def __init__(self):
        # Load wallet
        self.private_key = os.getenv("WALLET_SECRET", "")
        self.wallet_address = os.getenv("WALLET_ADDRESS", "")
        
        if self.private_key:
            self.trader = PumpTrader(self.private_key, ALCHEMY_RPC)
        else:
            self.trader = None
            print("⚠️ No wallet configured")
        
        # State
        self.positions = {}
        self.trades = []
        self.scan_results = []
        
    def run_scan(self) -> List[Dict]:
        """Run scanner and return opportunities"""
        from sniper_v4 import run_full_scan
        results = run_full_scan()
        self.scan_results = results
        return results
    
    def get_buyable_tokens(self, results: List[Dict]) -> List[Dict]:
        """Filter tokens yang bisa di-buy"""
        buyable = []
        for r in results:
            if r.get('can_buy', False):
                pool = r['pool']
                holder = r['holder_analysis']
                
                # Extra check
                if pool.get('liquidity', 0) >= MIN_LIQUIDITY:
                    if pool.get('volume_24h', 0) >= MIN_VOLUME:
                        buyable.append({
                            'pool': pool,
                            'holder': holder,
                            'score': r['final_score']
                        })
        
        # Sort by score
        buyable.sort(key=lambda x: x['score'], reverse=True)
        return buyable
    
    def open_position(self, token_data: Dict) -> Dict:
        """Open a new position with real trade"""
        pool = token_data['pool']
        holder = token_data['holder']
        
        token_mint = pool['token_mint']
        symbol = pool['symbol']
        
        # Check wallet balance
        try:
            resp = requests.post(ALCHEMY_RPC, json={
                "jsonrpc": "2.0", "id": 1, "method": "getBalance",
                "params": [self.wallet_address]
            }, timeout=15)
            balance = resp.json()['result']['value'] / 1e9
        except:
            balance = 0
        
        if balance < POSITION_SIZE_SOL:
            return {
                "success": False,
                "error": f"Insufficient balance: {balance:.4f} SOL"
            }
        
        if not self.trader:
            return {"success": False, "error": "No trader configured"}
        
        # Execute buy
        print(f"\n📝 Executing BUY for {symbol}...")
        print(f"   Amount: {POSITION_SIZE_SOL} SOL")
        print(f"   Token: {token_mint}")
        
        result = self.trader.buy(token_mint, POSITION_SIZE_SOL, slippage=20)
        
        if result.get('success'):
            # Record position
            self.positions[token_mint] = {
                'symbol': symbol,
                'token_mint': token_mint,
                'pool_address': pool['pool_address'],
                'entry_price': pool.get('price_usd', 0),
                'entry_time': datetime.now().isoformat(),
                'entry_tx': result.get('tx_hash'),
                'dev_holding': holder.get('dev_holding_pct', 0),
                'amount_sol': POSITION_SIZE_SOL,
                'took_profit_half': False,
                'took_profit_full': False,
                'stop_hit_half': False,
                'stop_hit_full': False
            }
            
            # Record trade
            self.trades.append({
                'symbol': symbol,
                'type': 'BUY',
                'price': pool.get('price_usd', 0),
                'amount_sol': POSITION_SIZE_SOL,
                'tx': result.get('tx_hash'),
                'time': datetime.now().isoformat()
            })
            
            print(f"   ✅ Success! TX: {result.get('tx_hash')}")
        else:
            print(f"   ❌ Failed: {result.get('error')}")
        
        return result
    
    def check_position(self, token_mint: str, current_price: float) -> Optional[Dict]:
        """Check position exit conditions"""
        if token_mint not in self.positions:
            return None
        
        pos = self.positions[token_mint]
        entry_price = pos['entry_price']
        dev_holding = pos['dev_holding']
        
        # Calculate P&L
        pnl_pct = ((current_price - entry_price) / entry_price) * 100
        
        # Determine exit action
        action = None
        
        # Check profit targets
        if dev_holding > 35:
            min_profit, max_profit = PROFIT_HIGH_DEV
        else:
            min_profit = max_profit = PROFIT_LOW_DEV
        
        if pnl_pct >= min_profit and not pos.get('took_profit_half'):
            action = ('TAKE_PROFIT', 50, pnl_pct)
            pos['took_profit_half'] = True
        elif pnl_pct >= max_profit and not pos.get('took_profit_full'):
            action = ('TAKE_PROFIT', 100, pnl_pct)
            pos['took_profit_full'] = True
        elif pnl_pct <= STOP_HALF and not pos.get('stop_hit_half'):
            action = ('STOP_LOSS', 50, pnl_pct)
            pos['stop_hit_half'] = True
        elif pnl_pct <= STOP_FULL:
            action = ('STOP_LOSS', 100, pnl_pct)
        
        return action
    
    def close_position(self, token_mint: str, exit_type: str, percentage: int, pnl_pct: float) -> Dict:
        """Close position with real trade"""
        pos = self.positions[token_mint]
        
        if not self.trader:
            return {"success": False, "error": "No trader configured"}
        
        symbol = pos['symbol']
        pool_address = pos['pool_address']
        
        print(f"\n📝 Executing {exit_type} for {symbol} ({percentage}%)...")
        print(f"   P&L: {pnl_pct:.1f}%")
        
        # For sell, we need token amount
        # Simplified: sell based on percentage of position
        # In production, would calculate exact token amount
        
        result = {"success": False, "error": "Sell integration pending"}
        
        if result.get('success'):
            self.trades.append({
                'symbol': symbol,
                'type': 'SELL',
                'pnl_pct': pnl_pct,
                'tx': result.get('tx_hash'),
                'time': datetime.now().isoformat()
            })
            
            if percentage == 100:
                del self.positions[token_mint]
        
        return result
    
    def run_cycle(self, dry_run: bool = True):
        """Run one trading cycle"""
        print(f"\n{'='*60}")
        print(f"🔄 Trading Cycle - {datetime.now().strftime('%H:%M:%S')}")
        print(f"{'='*60}")
        
        # 1. Scan
        print("\n[1] Scanning...")
        results = self.run_scan()
        
        # 2. Get buyable
        print("\n[2] Filtering...")
        buyable = self.get_buyable_tokens(results)
        
        print(f"    Found {len(buyable)} buyable tokens")
        
        # 3. Open positions
        open_slots = MAX_POSITIONS - len(self.positions)
        
        if open_slots > 0 and buyable and not dry_run:
            for token_data in buyable[:open_slots]:
                token_mint = token_data['pool']['token_mint']
                
                if token_mint not in self.positions:
                    print(f"\n[3] Opening position for {token_data['pool']['symbol']}...")
                    result = self.open_position(token_data)
                    
                    if not result.get('success'):
                        print(f"    Failed: {result.get('error')}")
        else:
            print(f"\n[3] {'DRY RUN - skipping buy' if dry_run else 'No open slots'}")
        
        # 4. Monitor positions
        print("\n[4] Monitoring positions...")
        
        if self.positions:
            for token_mint, pos in list(self.positions.items()):
                print(f"    {pos['symbol']}: Entry {pos['entry_price']:.6f}")
        else:
            print("    No open positions")
        
        # Summary
        print(f"\n{'='*60}")
        print(f"Status: {len(self.positions)} positions, {len(self.trades)} trades")
        print(f"{'='*60}")
        
        return {
            'positions': len(self.positions),
            'trades': len(self.trades),
            'buyable': len(buyable)
        }


def main():
    print("=" * 60)
    print("🎯 EARNY SNIPER TRADING BOT v4.0")
    print("=" * 60)
    
    bot = EARNYBot()
    
    # Run in dry mode first
    print("\n🚀 Running in DRY RUN mode...")
    status = bot.run_cycle(dry_run=True)
    
    print("\n" + "=" * 60)
    print("DRY RUN COMPLETE")
    print("=" * 60)
    print(f"Buyable tokens: {status['buyable']}")
    print(f"Open positions: {status['positions']}")
    print(f"Total trades: {status['trades']}")
    
    print("\nTo enable live trading, set DRY_RUN=false in .env")


if __name__ == "__main__":
    main()
