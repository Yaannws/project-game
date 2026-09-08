import os
import sys
import asyncio
from datetime import datetime
import logging
from typing import Dict, List, Tuple, Optional
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
        logging.FileHandler('bot_multi_exchange.log'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

class MultiExchangeBot:
    """Trading Signal Bot - Multi-Exchange Support (Binance, Kraken, ByBit, KuCoin, OKX, Deribit)"""
    
    def __init__(self):
        self.telegram_token = os.getenv('TELEGRAM_TOKEN', '')
        self.telegram_chat_id = os.getenv('TELEGRAM_CHAT_ID', '')
        
        # Multi-exchange initialization
        self.exchanges = {}
        self._init_all_exchanges()
        
        # Pair mapping to best exchange
        self.pair_to_exchange = self._create_pair_routing()
        
        self.timeframes = ['5m', '15m', '1h', '4h']
        self.pairs = self._get_pairs()
        self.webhook_url = os.getenv('WEBHOOK_URL', '')
        
        logger.info(f"🚀 Multi-Exchange Bot Starting...")
        logger.info(f"📱 Telegram Bot Configured: {bool(self.telegram_token)}")
        logger.info(f"💱 Exchanges Available: {list(self.exchanges.keys())}")
        asyncio.run(self._test_telegram_connection())
    
    def _init_all_exchanges(self):
        """Initialize all configured exchanges"""
        
        # BINANCE - Best for Forex, Metals, Crypto
        try:
            if os.getenv('BINANCE_API_KEY'):
                self.exchanges['binance'] = ccxt.binance({
                    'apiKey': os.getenv('BINANCE_API_KEY', ''),
                    'secret': os.getenv('BINANCE_API_SECRET', ''),
                    'enableRateLimit': True
                })
                logger.info("✅ Binance initialized")
        except Exception as e:
            logger.warning(f"⚠️  Binance init error: {str(e)}")
        
        # KRAKEN - Best for Crypto (no Forex/Metals)
        try:
            if os.getenv('KRAKEN_API_KEY'):
                self.exchanges['kraken'] = ccxt.kraken({
                    'apiKey': os.getenv('KRAKEN_API_KEY', ''),
                    'secret': os.getenv('KRAKEN_API_SECRET', ''),
                    'enableRateLimit': True
                })
                logger.info("✅ Kraken initialized")
        except Exception as e:
            logger.warning(f"⚠️  Kraken init error: {str(e)}")
        
        # BYBIT - Best for Crypto Futures
        try:
            if os.getenv('BYBIT_API_KEY'):
                self.exchanges['bybit'] = ccxt.bybit({
                    'apiKey': os.getenv('BYBIT_API_KEY', ''),
                    'secret': os.getenv('BYBIT_API_SECRET', ''),
                    'enableRateLimit': True
                })
                logger.info("✅ ByBit initialized")
        except Exception as e:
            logger.warning(f"⚠️  ByBit init error: {str(e)}")
        
        # KUCOIN - Best for Crypto
        try:
            if os.getenv('KUCOIN_API_KEY'):
                self.exchanges['kucoin'] = ccxt.kucoin({
                    'apiKey': os.getenv('KUCOIN_API_KEY', ''),
                    'secret': os.getenv('KUCOIN_API_SECRET', ''),
                    'enableRateLimit': True
                })
                logger.info("✅ KuCoin initialized")
        except Exception as e:
            logger.warning(f"⚠️  KuCoin init error: {str(e)}")
        
        # OKX - Best for Crypto
        try:
            if os.getenv('OKX_API_KEY'):
                self.exchanges['okx'] = ccxt.okx({
                    'apiKey': os.getenv('OKX_API_KEY', ''),
                    'secret': os.getenv('OKX_API_SECRET', ''),
                    'enableRateLimit': True
                })
                logger.info("✅ OKX initialized")
        except Exception as e:
            logger.warning(f"⚠️  OKX init error: {str(e)}")
        
        # DERIBIT - Best for Crypto Futures
        try:
            if os.getenv('DERIBIT_API_KEY'):
                self.exchanges['deribit'] = ccxt.deribit({
                    'apiKey': os.getenv('DERIBIT_API_KEY', ''),
                    'secret': os.getenv('DERIBIT_API_SECRET', ''),
                    'enableRateLimit': True
                })
                logger.info("✅ Deribit initialized")
        except Exception as e:
            logger.warning(f"⚠️  Deribit init error: {str(e)}")
        
        # Fallback: Initialize public (read-only) exchange jika tidak ada API key
        if not self.exchanges:
            logger.warning("⚠️  No API keys found, using public exchanges")
            self.exchanges['binance_public'] = ccxt.binance()
            logger.info("✅ Binance (public) initialized")
    
    def _create_pair_routing(self) -> Dict[str, str]:
        """Smart routing: Pair ke best exchange"""
        routing = {}
        
        # Forex & Metals -> Binance only
        forex_metals = [
            'EURUSD/USD', 'GBPUSD/USD', 'USDJPY/USD', 'AUDUSD/USD',
            'XAUUSD/USD', 'XAGUSD/USD'
        ]
        for pair in forex_metals:
            routing[pair] = 'binance'
        
        # Crypto -> Multiple exchanges (for redundancy)
        crypto_binance = ['BTC/USDT', 'ETH/USDT', 'XRP/USDT', 'ADA/USDT', 'BNB/USDT', 'SOL/USDT']
        crypto_kraken = ['BTC/USD', 'ETH/USD', 'XRP/USD', 'ADA/USD']
        crypto_bybit = ['BTC/USDT', 'ETH/USDT', 'XRP/USDT']
        
        # Primary: Binance untuk crypto
        for pair in crypto_binance:
            routing[pair] = 'binance'
        
        return routing
    
    def _get_best_exchange(self, pair: str) -> str:
        """Get best exchange untuk specific pair"""
        
        # Check routing table
        if pair in self.pair_to_exchange:
            exchange = self.pair_to_exchange[pair]
            if exchange in self.exchanges:
                return exchange
        
        # Smart fallback: Cari exchange yang punya pair ini
        for exchange_name, exchange in self.exchanges.items():
            try:
                # Try to get recent data
                test_data = exchange.fetch_ohlcv(pair, '1h', limit=1)
                if test_data:
                    return exchange_name
            except:
                continue
        
        # Default fallback ke exchange pertama yang ada
        if self.exchanges:
            return list(self.exchanges.keys())[0]
        
        return None
    
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
    
    async def fetch_candles(self, pair: str, timeframe: str, exchange_name: str, limit: int = 100):
        """Fetch OHLCV data dari specific exchange"""
        try:
            exchange = self.exchanges.get(exchange_name)
            if not exchange:
                return None
            
            ohlcv = exchange.fetch_ohlcv(pair, timeframe, limit=limit)
            return ohlcv
        except Exception as e:
            logger.error(f"Error fetching {pair} {timeframe} from {exchange_name}: {str(e)}")
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
        """Send to Telegram"""
        if signal_data['signal'] == 'HOLD':
            return
        
        try:
            message = f"""
🔔 TRADING SIGNAL
━━━━━━━━━━━━━━━━
📊 Pair: {signal_data.get('pair')}
💱 Exchange: {signal_data.get('exchange', 'N/A')}
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
                        logger.info(f"✅ Telegram sent: {signal_data['pair']} {signal_data['timeframe']} {signal_data['signal']} ({signal_data.get('exchange', 'N/A')})")
                    else:
                        logger.error(f"❌ Telegram error: {resp.status}")
        except Exception as e:
            logger.error(f"❌ Telegram send failed: {str(e)}")
    
    async def scan_pair(self, pair: str) -> List[Dict]:
        """Scan one pair across all timeframes"""
        signals = []
        
        # Get best exchange untuk pair ini
        exchange_name = self._get_best_exchange(pair)
        if not exchange_name:
            logger.warning(f"⚠️  No exchange available for {pair}")
            return signals
        
        for timeframe in self.timeframes:
            try:
                ohlcv = await self.fetch_candles(pair, timeframe, exchange_name)
                if ohlcv is None:
                    continue
                
                signal = self._detect_signal(ohlcv)
                
                if signal['signal'] != 'HOLD':
                    signal_data = {
                        'pair': pair,
                        'exchange': exchange_name.upper(),
                        'timeframe': timeframe,
                        'timestamp': datetime.now().isoformat(),
                        **signal
                    }
                    
                    signals.append(signal_data)
                    await self.send_signal(signal_data)
                    logger.info(f"🎯 [{exchange_name.upper()}] {pair} {timeframe}: {signal['signal']}")
                
                await asyncio.sleep(0.5)
            except Exception as e:
                logger.error(f"Error scanning {pair} {timeframe} on {exchange_name}: {str(e)}")
        
        return signals
    
    async def run_scanner(self):
        """Main scanner loop"""
        logger.info("=" * 70)
        logger.info("🤖 MULTI-EXCHANGE TRADING SIGNAL BOT")
        logger.info("=" * 70)
        logger.info(f"Exchanges: {', '.join([e.upper() for e in self.exchanges.keys()])}")
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
                    exchange_name = self._get_best_exchange(pair)
                    if exchange_name:
                        logger.info(f"Scanning {i}/{len(self.pairs)}: {pair} ({exchange_name.upper()})...")
                    else:
                        logger.warning(f"Scanning {i}/{len(self.pairs)}: {pair} (NO EXCHANGE)")
                        continue
                    
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
    
    def _get_pairs(self) -> List[str]:
        """Get trading pairs"""
        pairs_env = os.getenv('TRADING_PAIRS', '')
        if pairs_env:
            pairs = [p.strip() for p in pairs_env.split(',')]
            logger.info(f"📊 Custom Pairs ({len(pairs)}): {', '.join(pairs[:3])}...")
            return pairs
        
        # Default pairs - optimized untuk multi-exchange
        default_pairs = [
            # Forex & Metals (Binance only)
            'EURUSD/USD', 'GBPUSD/USD', 'USDJPY/USD', 'AUDUSD/USD',
            'XAUUSD/USD', 'XAGUSD/USD',
            # Crypto (Multi-exchange)
            'BTC/USDT', 'ETH/USDT', 'XRP/USDT', 'ADA/USDT',
            'BNB/USDT', 'SOL/USDT'
        ]
        logger.info(f"📊 Using Default Pairs ({len(default_pairs)})")
        return default_pairs

async def main():
    bot = MultiExchangeBot()
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
