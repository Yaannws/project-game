# XAU Pulse — Bot Telegram

Bot analisa XAU/USD real-time: harga, sinyal teknikal (SMA/RSI/MACD),
alert harga custom, dan pengingat news besar (NFP/FOMC/CPI). Semua
diatur langsung dari chat Telegram, tidak perlu edit kode.

## 1. Buat bot di Telegram

1. Buka chat dengan **@BotFather** di Telegram
2. Ketik `/newbot`, ikuti instruksinya (kasih nama & username)
3. BotFather akan kasih **token** seperti `123456:ABC-def...` — simpan ini

## 2. Jalankan di komputer sendiri (untuk coba dulu)

```bash
pip install -r requirements.txt
export TELEGRAM_BOT_TOKEN="token_dari_botfather"
python xau_telegram_bot.py
```

Buka Telegram, cari bot kamu, ketik `/start`. Bot hanya aktif selama
skrip ini berjalan (matikan terminal = bot berhenti).

## 3. Deploy 24/7 gratis di Railway (disarankan untuk pemula)

1. Buat akun di https://railway.app (bisa login pakai GitHub)
2. Push 3 file ini (`xau_telegram_bot.py`, `requirements.txt`, dan
   file `Procfile` di bawah) ke repo GitHub baru
3. Di Railway: **New Project → Deploy from GitHub repo** → pilih repo ini
4. Di tab **Variables**, tambahkan:
   - `TELEGRAM_BOT_TOKEN` = token dari BotFather
5. Railway otomatis build & jalankan. Bot langsung aktif 24/7.

Buat file `Procfile` (tanpa ekstensi) isinya:
```
worker: python xau_telegram_bot.py
```

Railway free tier ada limit jam pemakaian/bulan — cukup untuk bot
personal, tapi kalau habis, bot berhenti sampai kuota reset atau kamu
upgrade plan.

## 4. Alternatif: VPS murah (kalau mau lebih permanen)

Oracle Cloud Free Tier atau VPS ~$5/bulan (Contabo, DigitalOcean):
```bash
git clone <repo-kamu>
cd <repo-kamu>
pip install -r requirements.txt
export TELEGRAM_BOT_TOKEN="token"
nohup python xau_telegram_bot.py &
```
Atau pakai `systemd`/`pm2` supaya otomatis restart kalau server reboot.

## Perintah bot (semua diatur dari Telegram)

| Perintah | Fungsi |
|---|---|
| `/start` | Aktifkan bot di chat ini |
| `/harga` | Harga XAU/USD sekarang |
| `/sinyal` | Ringkasan sinyal teknikal |
| `/setalert 2650` | Alert saat harga menyentuh $2650 |
| `/alerts` | Lihat semua alert aktif |
| `/delalert 2650` | Hapus alert tertentu |
| `/newson` / `/newsoff` | Aktif/nonaktifkan pengingat news besar |
| `/interval 5` | Atur seberapa sering bot cek harga (menit) |
| `/status` | Lihat semua pengaturan chat ini |
| `/help` | Bantuan |

## Catatan jujur

- Data harga dari xaus.com (gratis, indikatif, delay kecil) — bukan
  kuotasi tradable, jangan dipakai untuk eksekusi settlement.
- Tanggal FOMC 2026 sudah resmi dari Federal Reserve. Tanggal CPI
  masih perkiraan (tanggal 12 tiap bulan) — cek ulang ke bls.gov,
  ganti di kode (`upcoming_events`) kalau ada jadwal pasti.
- Sinyal teknikal bersifat deskriptif (apa yang sedang terjadi),
  bukan prediksi arah harga. Ini bukan nasihat keuangan.
- Config disimpan di file lokal `xau_bot_config.json` — kalau deploy
  di Railway/VPS, file ini reset tiap redeploy kecuali dipasang
  persistent volume. Untuk pemakaian serius, ganti ke database kecil
  (SQLite cukup) supaya alert & pengaturan tidak hilang.
