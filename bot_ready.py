import os
import sys
import asyncio
from datetime import datetime
import logging
from typing import Dict, List, Tuple
import ccxt
import pandas as pd
import numpy as np
from dotenv import load_dotenv
import aiohttp

# Load environment variables
load_dotenv()

# Logging setup
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('bot.log'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

class TradingSignalBot:
    """Bot Signal Trading - Real Telegram Credentials"""
    
    def __init__(self):
        # Get credentials dari .env
        self.telegram_token = os.getenv('TELEGRAM_TOKEN', '')
        self.telegram_chat_id = os.getenv('TELEGRAM_CHAT_ID', '')
        
        logger.info(f"🚀 Bot Starting...")
        logger.info(f"📱 Telegram Bot Configured: {bool(self.telegram_token)}")
        logger.info(f"💬 Chat ID: {self.telegram_chat_id}")
        
        # Exchange setup
        self.exchange = self._init_exchange()
        self.timeframes = ['5m', '15m', '1h', '4h']
        self.pairs = self._get_pairs()
        self.webhook_url = os.getenv('WEBHOOK_URL', '')
        
        # Test Telegram connection
        asyncio.run(self._test_telegram_connection())
    
    def _init_exchange(self):
        """Initialize Binance exchange"""
        exchange_name = os.getenv('EXCHANGE', 'binance').lower()
        api_key = os.getenv('API_KEY', '')
        api_secret = os.getenv('API_SECRET', '')
        
        if not api_key or api_key == 'your_binance_api_key_here':
            logger.warning("⚠️  BINANCE API KEY NOT SET!")
            logger.warning("   Please set API_KEY in .env file")
            logger.warning("   You can still test Telegram notifications")
            return ccxt.binance({'enableRateLimit': True})
        
        try:
            return ccxt.binance({
                'apiKey': api_key,
                'secret': api_secret,
                'enableRateLimit': True
            })
        except Exception as e:
            logger.error(f"Exchange init error: {str(e)}")
            return ccxt.binance({'enableRateLimit': True})
    
    def _get_pairs(self) -> List[str]:
        """Get trading pairs"""
        pairs_env = os.getenv('TRADING_PAIRS', '')
        if pairs_env:
            pairs = [p.strip() for p in pairs_env.split(',')]
            logger.info(f"📊 Trading Pairs ({len(pairs)}): {', '.join(pairs[:3])}...")
            return pairs
        
        default_pairs = [
            'EURUSD/USD', 'GBPUSD/USD', 'USDJPY/USD', 'AUDUSD/USD',
            'XAUUSD/USD', 'XAGUSD/USD',
            'BTC/USDT', 'ETH/USDT', 'XRP/USDT', 'ADA/USDT',
            'BNBUSD/USD', 'SOL/USDT'
        ]
        logger.info(f"📊 Using Default Pairs ({len(default_pairs)})")
        return default_pairs
    
    def _calculate_ma(self, closes: np.ndarray, period: int) -> np.ndarray:
        """Calculate Moving Average"""
        return pd.Series(closes).rolling(window=period).mean().values
    
    def _calculate_bollinger_bands(self, closes: np.ndarray, period: int = 20, std_dev: int = 2) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
        """Calculate Bollinger Bands"""
        ma = pd.Series(closes).rolling(window=period).mean()
        std = pd.Series(closes).rolling(window=period).std()
        upper_band = ma + (std * std_dev)
        lower_band = ma - (std * std_dev)
        return upper_band.values, ma.values, lower_band.values
    
    def _calculate_support_resistance(self, closes: np.ndarray, lookback: int = 20) -> Tuple[float, float]:
        """Detect Support & Resistance"""
        high = np.max(closes[-lookback:])
        low = np.min(closes[-lookback:])
        return low, high
    
    def _detect_signal(self, ohlcv: List) -> Dict:
        """Detect trading signal"""
        if len(ohlcv) < 30:
            return {'signal': 'WAIT', 'reason': 'Insufficient data'}
        
        closes = np.array([x[4] for x in ohlcv])
        
        # Moving Averages
        ma20 = self._calculate_ma(closes, 20)
        ma50 = self._calculate_ma(closes, 50)
        
        # Bollinger Bands
        upper_bb, middle_bb, lower_bb = self._calculate_bollinger_bands(closes, 20, 2)
        
        # Support & Resistance
        support, resistance = self._calculate_support_resistance(closes)
        
        current_price = closes[-1]
        current_ma20 = ma20[-1]
        current_ma50 = ma50[-1]
        current_upper = upper_bb[-1]
        current_lower = lower_bb[-1]
        
        # BUY Signal
        if (current_price > current_ma20 > current_ma50 and
            current_price > support and
            current_price < current_upper and
            closes[-1] > closes[-2]):
            return {
                'signal': 'BUY',
                'price': float(current_price),
                'ma20': float(current_ma20),
                'ma50': float(current_ma50),
                'support': float(support),
                'resistance': float(resistance),
                'reason': 'MA Uptrend + Support Hold + Price Action'
            }
        
        # SELL Signal
        if (current_price < current_ma20 < current_ma50 and
            current_price < resistance and
            current_price > current_lower and
            closes[-1] < closes[-2]):
            return {
                'signal': 'SELL',
                'price': float(current_price),
                'ma20': float(current_ma20),
                'ma50': float(current_ma50),
                'support': float(support),
                'resistance': float(resistance),
                'reason': 'MA Downtrend + Resistance Hold + Price Action'
            }
        
        return {
            'signal': 'HOLD',
            'price': float(current_price),
            'ma20': float(current_ma20),
            'reason': 'No clear signal'
        }
    
    async def fetch_candles(self, symbol: str, timeframe: str, limit: int = 100):
        """Fetch OHLCV data"""
        try:
            ohlcv = self.exchange.fetch_ohlcv(symbol, timeframe, limit=limit)
            return ohlcv
        except Exception as e:
            logger.error(f"Error fetching {symbol} {timeframe}: {str(e)}")
            return None
    
    async def _test_telegram_connection(self):
        """Test Telegram connection"""
        if not self.telegram_token or self.telegram_token == 'your_telegram_token':
            logger.warning("⚠️  TELEGRAM TOKEN NOT SET!")
            return
        
        try:
            url = f"https://api.telegram.org/bot{self.telegram_token}/getMe"
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=5)) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        if data['ok']:
                            bot_info = data['result']
                            logger.info(f"✅ Telegram Bot Connected: @{bot_info['username']}")
                            return
        except Exception as e:
            logger.warning(f"⚠️  Telegram connection test failed: {str(e)}")
    
    async def send_signal(self, signal_data: Dict):
        """Send signal notification"""
        if self.telegram_token and self.telegram_chat_id:
            await self._send_telegram(signal_data)
    
    async def _send_telegram(self, signal_data: Dict):
        """Send to Telegram (REAL)"""
        if signal_data['signal'] == 'HOLD':
            return
        
        try:
            message = f"""
🔔 TRADING SIGNAL
━━━━━━━━━━━━━━━━
📊 Pair: {signal_data.get('pair')}
⏰ Timeframe: {signal_data.get('timeframe')}
📈 Signal: {signal_data.get('signal')}
💰 Price: {signal_data.get('price')}
📍 Support: {signal_data.get('support')}
📍 Resistance: {signal_data.get('resistance')}
💡 Reason: {signal_data.get('reason')}
━━━━━━━━━━━━━━━━
🕐 Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
"""
            url = f"https://api.telegram.org/bot{self.telegram_token}/sendMessage"
            async with aiohttp.ClientSession() as session:
                async with session.post(url, json={
                    'chat_id': self.telegram_chat_id,
                    'text': message
                }, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                    if resp.status == 200:
                        logger.info(f"✅ Telegram sent: {signal_data['pair']} {signal_data['timeframe']} {signal_data['signal']}")
                    else:
                        logger.error(f"❌ Telegram error: {resp.status}")
        except Exception as e:
            logger.error(f"❌ Telegram send failed: {str(e)}")
    
    async def scan_pair(self, pair: str) -> List[Dict]:
        """Scan one pair across all timeframes"""
        signals = []
        
        for timeframe in self.timeframes:
            try:
                ohlcv = await self.fetch_candles(pair, timeframe)
                if ohlcv is None:
                    continue
                
                signal = self._detect_signal(ohlcv)
                
                if signal['signal'] != 'HOLD':
                    signal_data = {
                        'pair': pair,
                        'timeframe': timeframe,
                        'timestamp': datetime.now().isoformat(),
                        **signal
                    }
                    
                    signals.append(signal_data)
                    await self.send_signal(signal_data)
                    logger.info(f"🎯 {pair} {timeframe}: {signal['signal']}")
                
                await asyncio.sleep(0.5)
            except Exception as e:
                logger.error(f"Error scanning {pair} {timeframe}: {str(e)}")
        
        return signals
    
    async def run_scanner(self):
        """Main scanner loop"""
        logger.info("=" * 70)
        logger.info("🤖 TRADING SIGNAL BOT - ALL PAIRS ALL TIMEFRAMES")
        logger.info("=" * 70)
        logger.info(f"Timeframes: {', '.join(self.timeframes)}")
        logger.info(f"Total Pairs: {len(self.pairs)}")
        logger.info("Starting scanner...")
        logger.info("=" * 70)
        
        scan_count = 0
        
        while True:
            try:
                scan_count += 1
                all_signals = []
                
                logger.info(f"\n📍 Scan #{scan_count} - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
                logger.info("-" * 70)
                
                for i, pair in enumerate(self.pairs, 1):
                    logger.info(f"Scanning {i}/{len(self.pairs)}: {pair}...")
                    pair_signals = await self.scan_pair(pair)
                    all_signals.extend(pair_signals)
                    await asyncio.sleep(1)
                
                if all_signals:
                    logger.info(f"\n✅ Scan Complete: {len(all_signals)} signal(s) generated")
                else:
                    logger.info(f"\n✅ Scan Complete: No signals")
                
                logger.info(f"⏰ Next scan in 5 minutes...")
                await asyncio.sleep(300)
            
            except Exception as e:
                logger.error(f"❌ Scanner error: {str(e)}")
                await asyncio.sleep(60)

async def main():
    bot = TradingSignalBot()
    await bot.run_scanner()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("\n✋ Bot stopped by user")
        sys.exit(0)
    except Exception as e:
        logger.error(f"Fatal error: {str(e)}")
        sys.exit(1)
