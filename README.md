# 🤖 EARNY Sniper — Solana Pump.fun Trading Bot

> Fully automated sniper bot for pump.fun tokens on Solana. Deep analysis → buy → auto TP/SL monitoring.

![Python](https://img.shields.io/badge/Python-3.10+-blue)
![Solana](https://img.shields.io/badge/Solana-SVM-purple)
![License](https://img.shields.io/badge/License-MIT-green)

## 📋 Overview

EARNY is a Python-based trading bot that:
1. **Scans** pump.fun for new tokens
2. **Deep analyzes** tokens (dev holding, rugcheck, liquidity, sellability)
3. **Buys** top candidates automatically
4. **Monitors** positions with TP/SL triggers
5. **Sells** when targets hit

## ⚙️ Requirements

### External Services (FREE Tiers Available)

| Service | Required | Purpose | Sign Up |
|---------|----------|---------|---------|
| **Alchemy** | ✅ Yes | Solana RPC (faster than QuickNode) | [alchemy.com](https://www.alchemy.com) — free tier: 100M compute units/month |
| **Jupiter** | ✅ Yes | Price quotes & swap routing | [jup.ag](https://jup.ag) — FREE, no API key needed |
| **RugCheck** | ✅ Yes | Rugpull detection | [rugcheck.xyz](https://rugcheck.xyz) — FREE, no API key |
| **GeckoTerminal** | ✅ Yes | Market cap & FDV data | [geckoterminal.com](https://www.geckoterminal.com) — FREE, no API key |
| **DexScreener** | ⚠️ Optional | Additional market data | [dexscreener.com](https://dexscreener.com) — FREE |

### Python Dependencies

```bash
pip install requests solders base58 base64 python-dotenv
```

**Optional (for advanced features):**
```bash
pip install vectorbt ccxt pandas-ta backtesting
```

## 🔧 Setup

### 1. Clone or Copy This Repo

```bash
git clone https://github.com/papatorra/Deep-Analysis.git
cd Deep-Analysis
```

### 2. Configure Environment

Create a `.env` file:

```env
# REQUIRED - Solana RPC (Alchemy FREE tier)
ALCH_RPC=https://solana-mainnet.g.alchemy.com/v2/YOUR_API_KEY

# REQUIRED - Jupiter API (FREE, get from jup.ag)
JUPITER_KEY=your_jupiter_api_key

# REQUIRED - Your Solana wallet
WALLET_ADDRESS=YourPublicKeyHere
PRIVATE_KEY=YourPrivateKeyHere  # ⚠️ KEEP SECRET!

# Trading Settings
BUY_AMOUNT=0.005              # SOL per trade
MAX_DEV_HOLDING=20            # Max dev % (default: 20%)
MAX_TOP20=50                 # Max top 20 holders % (default: 50%)
TP_PERCENT=100               # Take profit % (default: 100%)
SL_PERCENT=20               # Stop loss % (default: 20%)
CHECK_INTERVAL=15            # Monitor check interval in seconds (default: 15)
```

### 3. Get Alchemy API Key (FREE)

1. Go to [alchemy.com](https://www.alchemy.com)
2. Sign up for free tier
3. Create new app → Select **Solana** → **Mainnet**
4. Copy the **HTTPS endpoint** (looks like `https://solana-mainnet.g.alchemy.com/v2/...`)
5. Paste into `.env` as `ALCH_RPC`

### 4. Get Jupiter API Key (FREE)

1. Go to [jup.ag](https://jup.ag/api)
2. Get the free API key (or use the public endpoint without key for limited usage)
3. Paste into `.env` as `JUPITER_KEY`

### 5. Verify Setup

```bash
python3 -c "from dotenv import load_dotenv; load_dotenv('.env'); import os; print('ALCH_RPC:', os.getenv('ALCH_RPC')[:50]+'...' if os.getenv('ALCH_RPC') else 'NOT SET')"
```

## 📁 File Structure

```
trading-bot/
├── deep_analysis.py       # 🔬 Full analysis: dev%, rugcheck, liquidity, sellability, TP/SL
├── batch_analyze.py      # ⚡ Quick batch scan of multiple tokens
├── monitor_v5.py         # 👁️ Auto-monitor positions: TP/SL triggers & execution
├── earnysniper_live.py   # 🚀 Live scanner: scans pump.fun, analyzes, buys top tokens
├── data/
│   └── trades.json       # 📊 Trade history (auto-updated by monitor)
├── .env                  # 🔐 API keys & wallet (NOT committed to git)
├── .gitignore            # Files to exclude
└── README.md             # This file
```

## 🎯 How It Works

### Token Selection Criteria

| Filter | Threshold | Purpose |
|--------|-----------|---------|
| Dev Holding | < 20% | Low dev = lower rug risk |
| Top 20 Holders | < 50% | Distributed = safer |
| RugCheck Score | ≥ 1 | Not rugged |
| Mint Auth | Revoked | Can't mint more |
| Freeze Auth | Revoked | Can't freeze |
| Jupiter Buy | Available | Can enter |
| Jupiter Sell | Available | Can exit |

### Trading Strategy

```
Entry:     Market buy at current price
TP:        +100% (2x entry price)
SL:        -20% (80% of entry price)
Emergency: -25% triggers immediate sell
Check:     Every 15 seconds
```

### TP/SL Calculation (Example)

```
Buy:  0.001 SOL per token
TP:   0.002 SOL (+100%)  → Sell target
SL:   0.0008 SOL (-20%)  → Stop loss
```

## 🚀 Usage

### Quick Scan (Batch Analyze)

Analyze multiple tokens at once:

```bash
python3 batch_analyze.py <TOKEN1_MINT> <TOKEN2_MINT> ...

# Example:
python3 batch_analyze.py TokenA TokenB TokenC
```

Output:
```
============================================================
🔍 TokenA
============================================================
✅ Supply: 999,999,999,999 (6 decimals)
   Dev: 5.23% | Top5: 12.34% | Top20: 25.67%
✅ Jupiter buy: 0.00005000 SOL/token
✅ Jupiter sell: YES
✅ SOL balance: 0.0500 SOL

============================================================
✅ PASSED — READY TO BUY
============================================================
```

### Deep Analysis (Single Token)

Full analysis with all checks:

```bash
python3 deep_analysis.py <TOKEN_MINT>

# Example:
python3 deep_analysis.py 7nEwdPgSXvW4heqjSsN3Fo7y7TdvMhqwZ5qQJKXbpump
```

Output:
```
[1/10] TOKEN SUPPLY
--------------------------------------------------
✅ Supply: 999,999,999,999 (6 decimals)

[2/10] HOLDER ANALYSIS
--------------------------------------------------
   📊 Dev: 3.45% | Top5: 10.23% | Top20: 22.45%
✅ PASSED: Dev 3.45% < 20% | Top20 22.45% < 50%

[3/10] JUPITER BUY PRICE
--------------------------------------------------
✅ Route: Pump.fun Amm
✅ 0.005 SOL → 100,000 tokens @ 0.00005000 SOL

[4/10] JUPITER SELL CHECK (Can Exit?)
--------------------------------------------------
✅ CAN SELL: YES (Pump.fun Amm)

[5/10] DEXSCREENER
--------------------------------------------------
✅ FDV: $500,000

[6/10] GECKOTERMINAL
--------------------------------------------------
✅ FDV: $499,999

[7/10] RUGCHECK
--------------------------------------------------
✅ Score: 2501 (normalized: 73)
✅ Rugged: False
✅ Mint Auth: REVOKED ✅
✅ Freeze Auth: REVOKED ✅

[8/10] EXISTING WALLET POSITION
--------------------------------------------------
✅ No existing position

[9/10] SOL BALANCE
--------------------------------------------------
✅ Balance: 0.0500 SOL | Can afford 0.005 SOL? YES ✅

[10/10] TP/SL SETTINGS
--------------------------------------------------
   Entry: 0.00005000 SOL
   TP 100%: 0.00010000 SOL
   SL 20%: 0.00004000 SOL
   R:R: 5.0:1

======================================================================
✅ STATUS: PASSED - READY TO BUY
   Entry: 0.00005000 | TP: 0.00010000 | SL: 0.00004000
   SOL: 0.0500 | Can buy: YES
======================================================================
```

### Auto Buy + Monitor (Full Workflow)

```bash
# From your code:
from deep_analysis import buy_and_track

# Buy and auto-monitor
result = buy_and_track("TOKEN_MINT_HERE", 0.005)
print(f"TX: {result['tx']}")
```

### Monitor Running Positions

```bash
# Start monitor (runs in background)
python3 monitor_v5.py

# Monitor will:
# - Check prices every 15 seconds
# - Execute TP sell when +100% reached
# - Execute SL sell when -20% reached
# - Emergency sell when -25% (fast drop protection)
# - Log all trades to data/trades.json
```

### Live Scanner Mode

```bash
python3 earnysniper_live.py scan
```

This scans pump.fun, filters tokens, and prints candidates ready for analysis.

## 🔧 Configuration Options

| Variable | Default | Description |
|----------|---------|-------------|
| `BUY_AMOUNT` | 0.005 | SOL amount per trade |
| `MAX_DEV_HOLDING` | 20 | Max dev wallet % |
| `MAX_TOP20` | 50 | Max top 20 holders % |
| `TP_PERCENT` | 100 | Take profit % |
| `SL_PERCENT` | 20 | Stop loss % |
| `CHECK_INTERVAL` | 15 | Monitor check interval (seconds) |
| `EMERGENCY_PCT` | 25 | Emergency sell trigger % |

## ⚠️ Risk Warnings

1. **NOT Financial Advice** — This is experimental software. Use at your own risk.
2. **Pump.fun is HIGH RISK** — Tokens can dump 50%+ in seconds
3. **Slippage** — Large orders may experience significant slippage
4. **Liquidity** — Low liquidity tokens are harder to exit
5. **Monitor Failure** — Bot may miss fast price moves. Consider manual oversight

## 🛠️ Troubleshooting

### "No module named 'solders'"

```bash
pip install solders
```

### "Jupiter API rate limited"

Wait a few minutes or get a Jupiter API key from jup.ag

### "Transaction failed"

- Check wallet balance
- Verify RPC is working
- Try with `skipPreflight: true` in transaction params

### "Tokens not appearing in wallet"

Verify transaction on [solscan.io](https://solscan.io) with your TX hash

### Monitor not executing sells

- Check monitor.log for errors
- Verify RPC is responding
- Ensure wallet has enough SOL for fees (~0.000005 SOL per tx)

## 📊 Analyzing Results

Check `data/trades.json` for trade history:

```json
{
  "buys": {
    "TOKEN_MINT": {
      "price_per_token": 0.00005000,
      "buy_tx": "TX_HASH",
      "tp_price": 0.00010000,
      "sl_price": 0.00004000,
      "sol_spent": 0.005,
      "confirmed": true
    }
  },
  "sells": [
    {
      "token": "TOKEN_MINT",
      "buy_amount_sol": 0.005,
      "sell_amount_sol": 0.010,
      "pnl_sol": 0.005,
      "pnl_percent": 100,
      "sell_tx": "TX_HASH"
    }
  ]
}
```

## 🔗 Useful Links

- [Solana Docs](https://docs.solana.com)
- [Pump.fun](https://pump.fun)
- [Jupiter Docs](https://docs.jup.ag)
- [Alchemy Solana](https://docs.alchemy.com/reference/solana-api-quickstart)
- [RugCheck](https://rugcheck.xyz)

## 📝 License

MIT License — Use freely, but at your own risk.

---

Built with 💧 by Rem | Powered by Solana
