"""
XAU Pulse — Telegram Bot
=========================
Bot analisa XAU/USD real-time + alert news besar, semua diatur dari Telegram.

Setup singkat:
  1. Buat bot lewat @BotFather di Telegram -> dapat TELEGRAM_BOT_TOKEN
  2. pip install -r requirements.txt
  3. export TELEGRAM_BOT_TOKEN="xxxx"   (atau taruh di file .env)
  4. python xau_telegram_bot.py
  5. Chat bot kamu di Telegram, ketik /start

Command yang tersedia (semua diatur dari chat, tidak perlu edit kode):
  /start              - mulai & daftar chat ini untuk menerima alert
  /harga              - harga XAU/USD terkini
  /sinyal             - ringkasan sinyal teknikal (SMA/RSI/MACD)
  /setalert <harga>   - alert ketika harga menyentuh level ini
  /alerts             - lihat semua alert aktif
  /delalert <harga>   - hapus alert tertentu
  /newson             - aktifkan pengingat news besar (NFP/FOMC/CPI)
  /newsoff            - matikan pengingat news besar
  /interval <menit>   - atur seberapa sering bot cek harga (default 5 menit)
  /status             - lihat semua pengaturan chat ini
  /help               - tampilkan bantuan ini
"""

import os
import json
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
)

logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s", level=logging.INFO
)
log = logging.getLogger("xau_pulse_bot")

BASE_API = "https://xaus.com/api/v1"
CONFIG_PATH = Path(__file__).parent / "xau_bot_config.json"
TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")

DEFAULT_CHAT_CONFIG = {
    "alerts": [],  # list of {"price": float, "direction": "above"/"below"/"cross"}
    "news_notify": True,
    "interval_minutes": 5,
    "last_price": None,
    "notified_events": [],  # event keys already notified (to avoid duplicate spam)
    "last_trend": None,  # last bullish/bearish/neutral verdict sent
}

# ---------------- persistence ----------------
def load_config():
    if CONFIG_PATH.exists():
        return json.loads(CONFIG_PATH.read_text())
    return {}


def save_config(cfg):
    CONFIG_PATH.write_text(json.dumps(cfg, indent=2))


def get_chat_cfg(cfg, chat_id):
    key = str(chat_id)
    if key not in cfg:
        cfg[key] = dict(DEFAULT_CHAT_CONFIG)
        cfg[key]["alerts"] = []
        cfg[key]["notified_events"] = []
    return cfg[key]


# ---------------- market data + indicators ----------------
def fetch_spot():
    r = requests.get(f"{BASE_API}/spot?compact=1", timeout=10)
    r.raise_for_status()
    return r.json()


def fetch_intraday(hours=24):
    r = requests.get(f"{BASE_API}/intraday", params={"symbol": "xau", "hours": hours}, timeout=10)
    r.raise_for_status()
    return r.json()


def sma(values, period):
    out = [None] * len(values)
    s = 0
    for i, v in enumerate(values):
        s += v
        if i >= period:
            s -= values[i - period]
        if i >= period - 1:
            out[i] = s / period
    return out


def ema(values, period):
    out = [None] * len(values)
    k = 2 / (period + 1)
    prev = None
    for i, v in enumerate(values):
        if v is None:
            continue
        prev = v if prev is None else v * k + prev * (1 - k)
        out[i] = prev
    return out


def rsi(values, period=14):
    out = [None] * len(values)
    if len(values) <= period:
        return out
    gains = losses = 0.0
    avg_g = avg_l = None
    for i in range(1, len(values)):
        diff = values[i] - values[i - 1]
        gain, loss = max(diff, 0), max(-diff, 0)
        if i <= period:
            gains += gain
            losses += loss
            if i == period:
                avg_g, avg_l = gains / period, losses / period
                out[i] = 100 if avg_l == 0 else 100 - 100 / (1 + avg_g / avg_l)
        else:
            avg_g = (avg_g * (period - 1) + gain) / period
            avg_l = (avg_l * (period - 1) + loss) / period
            out[i] = 100 if avg_l == 0 else 100 - 100 / (1 + avg_g / avg_l)
    return out


def macd_hist(values):
    e12, e26 = ema(values, 12), ema(values, 26)
    line = [
        (a - b) if a is not None and b is not None else None
        for a, b in zip(e12, e26)
    ]
    signal = ema([v if v is not None else 0 for v in line], 9)
    return [
        (a - b) if a is not None and b is not None else None
        for a, b in zip(line, signal)
    ]


def compute_signal():
    data = fetch_intraday(24)
    closes = [p["p"] for p in data.get("points", [])]
    if len(closes) < 25:
        return None
    s9, s21 = sma(closes, 9), sma(closes, 21)
    r = rsi(closes, 14)
    m = macd_hist(closes)

    trend = "bullish" if s9[-1] and s21[-1] and s9[-1] > s21[-1] else "bearish"
    momentum = "bullish" if r[-1] and r[-1] > 60 else "bearish" if r[-1] and r[-1] < 40 else "neutral"
    macd_sig = "bullish" if m[-1] and m[-1] > 0 else "bearish" if m[-1] is not None else None

    votes = [v for v in [trend, momentum, macd_sig] if v in ("bullish", "bearish")]
    bulls = votes.count("bullish")
    bears = votes.count("bearish")
    verdict = "netral"
    if bulls >= 2:
        verdict = "condong bullish"
    elif bears >= 2:
        verdict = "condong bearish"

    return {
        "price": closes[-1],
        "trend": trend,
        "momentum": momentum,
        "macd": macd_sig,
        "rsi": r[-1],
        "macd_hist": m[-1],
        "verdict": verdict,
    }


# ---------------- economic calendar (jadwal indikatif) ----------------
FOMC_2026 = [
    datetime(2026, 9, 16, 18, 0, tzinfo=timezone.utc),
    datetime(2026, 10, 28, 18, 0, tzinfo=timezone.utc),
    datetime(2026, 12, 9, 19, 0, tzinfo=timezone.utc),
]


def next_first_friday(now):
    d = datetime(now.year, now.month, 1, 12, 30, tzinfo=timezone.utc)
    while d.weekday() != 4:
        d += timedelta(days=1)
    if d < now:
        nm = now.month + 1 if now.month < 12 else 1
        ny = now.year if now.month < 12 else now.year + 1
        d = datetime(ny, nm, 1, 12, 30, tzinfo=timezone.utc)
        while d.weekday() != 4:
            d += timedelta(days=1)
    return d


def upcoming_events(now):
    events = []
    for d in FOMC_2026:
        if d > now:
            events.append(("FOMC", "FOMC Rate Decision", d))
    events.append(("NFP", "Non-Farm Payrolls", next_first_friday(now)))
    cpi = datetime(now.year, now.month, 12, 12, 30, tzinfo=timezone.utc)
    if cpi < now:
        nm = now.month + 1 if now.month < 12 else 1
        ny = now.year if now.month < 12 else now.year + 1
        cpi = datetime(ny, nm, 12, 12, 30, tzinfo=timezone.utc)
    events.append(("CPI", "US CPI (perkiraan, cek bls.gov)", cpi))
    events.sort(key=lambda e: e[2])
    return events


# ---------------- command handlers ----------------
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    cfg = load_config()
    get_chat_cfg(cfg, update.effective_chat.id)
    save_config(cfg)
    await update.message.reply_text(
        "XAU Pulse aktif di chat ini.\n\n"
        "Perintah cepat:\n"
        "/harga - harga sekarang\n"
        "/sinyal - ringkasan teknikal\n"
        "/setalert 2650 - alert saat harga sentuh level ini\n"
        "/newson /newsoff - pengingat news besar\n"
        "/status - lihat pengaturan\n"
        "/help - semua perintah"
    )


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(__doc__.split("Command yang tersedia")[1])


async def cmd_harga(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        d = fetch_spot()
        price = d.get("xau", {}).get("price") or d.get("spot_usd_oz")
        await update.message.reply_text(f"XAU/USD: ${price:,.2f}")
    except Exception as e:
        await update.message.reply_text(f"Gagal ambil harga: {e}")


async def cmd_sinyal(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        s = compute_signal()
        if not s:
            await update.message.reply_text("Data belum cukup, coba lagi sebentar.")
            return
        await update.message.reply_text(
            f"XAU/USD: ${s['price']:,.2f}\n"
            f"Verdict: {s['verdict'].upper()}\n"
            f"Trend (SMA9/21): {s['trend']}\n"
            f"Momentum (RSI {s['rsi']:.1f}): {s['momentum']}\n"
            f"MACD: {s['macd']}\n\n"
            "Ini deskriptif, bukan sinyal pasti — tetap pakai manajemen risiko."
        )
    except Exception as e:
        await update.message.reply_text(f"Gagal hitung sinyal: {e}")


async def cmd_setalert(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Format: /setalert 2650")
        return
    try:
        price = float(context.args[0])
    except ValueError:
        await update.message.reply_text("Harga tidak valid. Contoh: /setalert 2650")
        return
    cfg = load_config()
    chat_cfg = get_chat_cfg(cfg, update.effective_chat.id)
    chat_cfg["alerts"].append({"price": price, "triggered": False})
    save_config(cfg)
    await update.message.reply_text(f"Alert dipasang di ${price:,.2f}")


async def cmd_alerts(update: Update, context: ContextTypes.DEFAULT_TYPE):
    cfg = load_config()
    chat_cfg = get_chat_cfg(cfg, update.effective_chat.id)
    if not chat_cfg["alerts"]:
        await update.message.reply_text("Belum ada alert aktif.")
        return
    lines = [f"${a['price']:,.2f}" for a in chat_cfg["alerts"]]
    await update.message.reply_text("Alert aktif:\n" + "\n".join(lines))


async def cmd_delalert(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Format: /delalert 2650")
        return
    try:
        price = float(context.args[0])
    except ValueError:
        await update.message.reply_text("Harga tidak valid.")
        return
    cfg = load_config()
    chat_cfg = get_chat_cfg(cfg, update.effective_chat.id)
    before = len(chat_cfg["alerts"])
    chat_cfg["alerts"] = [a for a in chat_cfg["alerts"] if a["price"] != price]
    save_config(cfg)
    msg = "Alert dihapus." if len(chat_cfg["alerts"]) < before else "Alert tidak ditemukan."
    await update.message.reply_text(msg)


async def cmd_newson(update: Update, context: ContextTypes.DEFAULT_TYPE):
    cfg = load_config()
    chat_cfg = get_chat_cfg(cfg, update.effective_chat.id)
    chat_cfg["news_notify"] = True
    save_config(cfg)
    await update.message.reply_text("Pengingat news besar diaktifkan.")


async def cmd_newsoff(update: Update, context: ContextTypes.DEFAULT_TYPE):
    cfg = load_config()
    chat_cfg = get_chat_cfg(cfg, update.effective_chat.id)
    chat_cfg["news_notify"] = False
    save_config(cfg)
    await update.message.reply_text("Pengingat news besar dimatikan.")


async def cmd_interval(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Format: /interval 5  (dalam menit)")
        return
    try:
        minutes = max(1, int(context.args[0]))
    except ValueError:
        await update.message.reply_text("Angka tidak valid.")
        return
    cfg = load_config()
    chat_cfg = get_chat_cfg(cfg, update.effective_chat.id)
    chat_cfg["interval_minutes"] = minutes
    save_config(cfg)
    await update.message.reply_text(
        f"Interval cek harga diatur ke {minutes} menit. "
        "(perubahan penuh berlaku setelah bot direstart, cek job berikutnya tetap pakai interval lama sekali)"
    )


async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    cfg = load_config()
    chat_cfg = get_chat_cfg(cfg, update.effective_chat.id)
    await update.message.reply_text(
        f"News alert: {'ON' if chat_cfg['news_notify'] else 'OFF'}\n"
        f"Interval cek: {chat_cfg['interval_minutes']} menit\n"
        f"Jumlah alert harga aktif: {len(chat_cfg['alerts'])}"
    )


# ---------------- background job: cek harga, alert, news ----------------
async def poll_job(context: ContextTypes.DEFAULT_TYPE):
    cfg = load_config()
    if not cfg:
        return
    try:
        spot = fetch_spot()
        price = spot.get("xau", {}).get("price") or spot.get("spot_usd_oz")
    except Exception as e:
        log.warning("fetch_spot failed: %s", e)
        return

    now = datetime.now(timezone.utc)
    events = upcoming_events(now)

    for chat_id, chat_cfg in cfg.items():
        # price alerts
        remaining = []
        for a in chat_cfg.get("alerts", []):
            last_price = chat_cfg.get("last_price")
            crossed = (
                last_price is not None
                and (
                    (last_price < a["price"] <= price)
                    or (last_price > a["price"] >= price)
                )
            )
            if crossed:
                await context.bot.send_message(
                    chat_id=int(chat_id),
                    text=f"⚡ XAU menyentuh level alert ${a['price']:,.2f} (harga sekarang ${price:,.2f})",
                )
            else:
                remaining.append(a)
        chat_cfg["alerts"] = remaining
        chat_cfg["last_price"] = price

        # news reminders: notify once at ~60 min and ~15 min before
        if chat_cfg.get("news_notify", True):
            for tag, label, ev_time in events:
                mins_left = (ev_time - now).total_seconds() / 60
                for threshold, key_suffix in [(60, "60m"), (15, "15m")]:
                    key = f"{tag}-{ev_time.isoformat()}-{key_suffix}"
                    if (
                        threshold - 3 <= mins_left <= threshold
                        and key not in chat_cfg.get("notified_events", [])
                    ):
                        await context.bot.send_message(
                            chat_id=int(chat_id),
                            text=f"🔔 {label} rilis {int(mins_left)} menit lagi. Waspada spread melebar & volatilitas tinggi.",
                        )
                        chat_cfg.setdefault("notified_events", []).append(key)

    save_config(cfg)


def main():
    if not TOKEN:
        raise SystemExit(
            "TELEGRAM_BOT_TOKEN belum diset. export TELEGRAM_BOT_TOKEN='token_dari_botfather'"
        )
    app = Application.builder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(CommandHandler("harga", cmd_harga))
    app.add_handler(CommandHandler("sinyal", cmd_sinyal))
    app.add_handler(CommandHandler("setalert", cmd_setalert))
    app.add_handler(CommandHandler("alerts", cmd_alerts))
    app.add_handler(CommandHandler("delalert", cmd_delalert))
    app.add_handler(CommandHandler("newson", cmd_newson))
    app.add_handler(CommandHandler("newsoff", cmd_newsoff))
    app.add_handler(CommandHandler("interval", cmd_interval))
    app.add_handler(CommandHandler("status", cmd_status))

    app.job_queue.run_repeating(poll_job, interval=300, first=15)  # default 5 menit

    log.info("Bot berjalan...")
    app.run_polling()


if __name__ == "__main__":
    main()
