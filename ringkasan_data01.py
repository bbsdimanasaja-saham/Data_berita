import os
import yfinance as yf
import pandas as pd
import numpy as np
import warnings
import urllib.request
import urllib.parse
import xml.etree.ElementTree as ET
import html
from dotenv import load_dotenv

warnings.filterwarnings('ignore')

# Ambil token dari file .env (jika ada) atau environment variables
load_dotenv()

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "8944012322:AAH9DlK3PQZIz47hpG28gsBewnvLaiXxSjY")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "8789794251")

def escape_html(text):
    """Mengamankan teks dari karakter khusus HTML"""
    return html.escape(str(text))

def kirim_telegram_pretty(pesan_html):
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        for i in range(0, len(pesan_html), 4000):
            chunk = pesan_html[i:i+4000]
            data = urllib.parse.urlencode({
                'chat_id': TELEGRAM_CHAT_ID, 
                'text': chunk,
                'parse_mode': 'HTML'
            }).encode('utf-8')
            req = urllib.request.Request(url, data=data)
            urllib.request.urlopen(req, timeout=10)
        print("✅ Laporan berhasil dikirim ke Telegram!\n")
    except Exception as e:
        print(f"❌ Gagal mengirim ke Telegram: {e}\n")

def safe_int(val):
    try:
        if pd.isna(val) or np.isnan(val):
            return 0
        return int(val)
    except Exception:
        return 0

def ambil_sentimen_berita(kode_saham):
    try:
        kode_bersih = kode_saham.replace(".JK", "").upper()
        query = urllib.parse.quote(f'"{kode_bersih}" saham OR "{kode_bersih}" stock')
        url = f"https://news.google.com/rss/search?q={query}&hl=id&gl=ID&ceid=ID:id"
        
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'})
        xml_data = urllib.request.urlopen(req, timeout=7).read()
        
        root = ET.fromstring(xml_data)
        items = root.findall('.//item')
        
        if not items:
            return "⚪ NETRAL (Berita Tidak Ditemukan)", []
        
        kata_positif = [
            'naik', 'melejit', 'laba', 'untung', 'dividen', 'tumbuh', 'ekspansi', 
            'bullish', 'positif', 'rekor', 'lonjakan', 'terbang', 'cuan', 'surplus', 
            'prospek', 'buy', 'outperform', 'profit', 'gain', 'growth', 'surge', 'soar'
        ]
        kata_negatif = [
            'turun', 'anjlok', 'rugi', 'longsor', 'amblas', 'bearish', 'drop', 
            'pangkas', 'tertekan', 'kasus', 'sanksi', 'negatif', 'gugatan', 'merugi', 
            'defisit', 'meleset', 'sell', 'underperform', 'loss', 'decline', 'slump', 'fall'
        ]
        
        daftar_berita = []
        skor_pos = 0
        skor_neg = 0
        
        for item in items:
            title = item.find('title').text if item.find('title') is not None else ""
            source_elem = item.find('source')
            media_name = source_elem.text if source_elem is not None else "Media Berita"
            
            title_clean = title.split(' - ')[0] if ' - ' in title else title
            title_lower = title_clean.lower()
            
            if kode_bersih.lower() not in title_lower:
                continue
            
            pos_count = sum(1 for w in kata_positif if w in title_lower)
            neg_count = sum(1 for w in kata_negatif if w in title_lower)
            
            if pos_count > 0 or neg_count > 0:
                skor_pos += pos_count
                skor_neg += neg_count
                
                label_dampak = "🟢 POSITIF" if pos_count > neg_count else ("🔴 NEGATIF" if neg_count > pos_count else "⚪ NETRAL")
                daftar_berita.append(f"{label_dampak} [{media_name}] {title_clean}")
            
            if len(daftar_berita) >= 10:
                break
        
        if not daftar_berita:
            return "⚪ NETRAL (Gak Ada Berita Sentimen Berdampak Signifikan)", []
            
        if skor_pos > skor_neg:
            status_sentimen = f"🟢 POSITIF (Skor Positif: {skor_pos} | Negatif: {skor_neg})"
        elif skor_neg > skor_pos:
            status_sentimen = f"🔴 NEGATIF (Skor Negatif: {skor_neg} | Positif: {skor_pos})"
        else:
            status_sentimen = "⚪ NETRAL / SEIMBANG"
            
        return status_sentimen, daftar_berita
    except Exception:
        return "⚪ NETRAL (Gagal Memuat Berita)", []

def hitung_supertrend(df, period=10, multiplier=3):
    hl2 = (df['High'] + df['Low']) / 2
    tr = pd.concat([
        df['High'] - df['Low'],
        (df['High'] - df['Close'].shift()).abs(),
        (df['Low'] - df['Close'].shift()).abs()
    ], axis=1).max(axis=1)
    
    atr = tr.ewm(span=period, adjust=False).mean()
    basic_ub = hl2 + (multiplier * atr)
    basic_lb = hl2 - (multiplier * atr)
    
    final_ub = pd.Series(0.0, index=df.index)
    final_lb = pd.Series(0.0, index=df.index)
    supertrend = pd.Series(0.0, index=df.index)
    st_dir = pd.Series(1, index=df.index)
    
    for i in range(1, len(df)):
        if basic_ub.iloc[i] < final_ub.iloc[i-1] or df['Close'].iloc[i-1] > final_ub.iloc[i-1]:
            final_ub.iloc[i] = basic_ub.iloc[i]
        else:
            final_ub.iloc[i] = final_ub.iloc[i-1]
            
        if basic_lb.iloc[i] > final_lb.iloc[i-1] or df['Close'].iloc[i-1] < final_lb.iloc[i-1]:
            final_lb.iloc[i] = basic_lb.iloc[i]
        else:
            final_lb.iloc[i] = final_lb.iloc[i-1]
            
        if st_dir.iloc[i-1] == 1:
            if df['Close'].iloc[i] < final_lb.iloc[i]:
                st_dir.iloc[i] = -1
                supertrend.iloc[i] = final_ub.iloc[i]
            else:
                st_dir.iloc[i] = 1
                supertrend.iloc[i] = final_lb.iloc[i]
        else:
            if df['Close'].iloc[i] > final_ub.iloc[i]:
                st_dir.iloc[i] = 1
                supertrend.iloc[i] = final_lb.iloc[i]
            else:
                st_dir.iloc[i] = -1
                supertrend.iloc[i] = final_ub.iloc[i]
                
    return supertrend, st_dir

def panggil_saham(kode_input):
    kode = kode_input.upper().strip()
    ticker = kode if kode.endswith(".JK") else f"{kode}.JK"
    
    print(f"\n🔍 Mengambil data & berita {ticker}...\n")
    
    try:
        t_obj = yf.Ticker(ticker)
        df = t_obj.history(period="1y")
        
        if df.empty or len(df) < 50:
            print(f"❌ Saham '{kode}' gak ditemukan atau datanya kurang.\n")
            return

        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)

        df = df.ffill().bfill().fillna(0)

        df['EMA20'] = df['Close'].ewm(span=20, adjust=False).mean()
        df['EMA50'] = df['Close'].ewm(span=50, adjust=False).mean()
        
        delta = df['Close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
        rs = gain / (loss + 1e-9)
        df['RSI'] = 100 - (100 / (1 + rs))

        ema12 = df['Close'].ewm(span=12, adjust=False).mean()
        ema26 = df['Close'].ewm(span=26, adjust=False).mean()
        df['MACD'] = ema12 - ema26
        df['MACD_Signal'] = df['MACD'].ewm(span=9, adjust=False).mean()

        low14 = df['Low'].rolling(14).min()
        high14 = df['High'].rolling(14).max()
        df['Stoch_K'] = 100 * ((df['Close'] - low14) / (high14 - low14 + 1e-9))
        df['Stoch_D'] = df['Stoch_K'].rolling(3).mean()

        df['BB_Mid'] = df['Close'].rolling(20).mean()
        std20 = df['Close'].rolling(20).std()
        df['BB_Upper'] = df['BB_Mid'] + (2 * std20)
        df['BB_Lower'] = df['BB_Mid'] - (2 * std20)

        df['TR'] = pd.concat([
            df['High'] - df['Low'],
            (df['High'] - df['Close'].shift()).abs(),
            (df['Low'] - df['Close'].shift()).abs()
        ], axis=1).max(axis=1)
        df['ATR'] = df['TR'].rolling(14).mean()
        
        daily_returns = df['Close'].pct_change()
        volatilitas_30d = daily_returns.iloc[-30:].std() * np.sqrt(252) * 100

        df['Supertrend'], df['ST_Dir'] = hitung_supertrend(df, period=10, multiplier=3)

        df['Vol_MA20'] = df['Volume'].rolling(20).mean()
        mf_multiplier = ((df['Close'] - df['Low']) - (df['High'] - df['Close'])) / (df['High'] - df['Low'] + 1e-9)
        mf_volume = mf_multiplier * df['Volume']
        df['CMF'] = mf_volume.rolling(20).sum() / (df['Volume'].rolling(20).sum() + 1e-9)

        df = df.ffill().bfill().fillna(0)

        status_sentimen, list_berita = ambil_sentimen_berita(kode)

        today = df.iloc[-1]
        prev = df.iloc[-2]

        close = safe_int(today['Close'])
        open_price = safe_int(today['Open'])
        high = safe_int(today['High'])
        low = safe_int(today['Low'])
        prev_close = safe_int(prev['Close'])
        
        change = close - prev_close
        pct_change = (change / prev_close * 100) if prev_close > 0 else 0
        status = "🟢 NAIK" if change > 0 else ("🔴 TURUN" if change < 0 else "⚪ FLAT")

        vol_today = safe_int(today['Volume'])
        vol_prev = safe_int(prev['Volume'])
        vol_change_pct = ((vol_today - vol_prev) / vol_prev * 100) if vol_prev > 0 else 0

        pivot = (high + low + close) / 3
        r1 = safe_int((2 * pivot) - low)
        s1 = safe_int((2 * pivot) - high)

        body_bottom = min(open_price, close)
        ekor_bawah_rp = body_bottom - low
        candle_range = high - low
        ekor_bawah_pct = (ekor_bawah_rp / candle_range * 100) if candle_range > 0 else 0
        
        len_df = len(df)
        idx_1w = -5 if len_df >= 5 else 0
        idx_1m = -20 if len_df >= 20 else 0
        idx_3m = -60 if len_df >= 60 else 0

        hl_1w = f"{safe_int(df['Low'].iloc[idx_1w:].min()):,} - {safe_int(df['High'].iloc[idx_1w:].max()):,}"
        hl_1m = f"{safe_int(df['Low'].iloc[idx_1m:].min()):,} - {safe_int(df['High'].iloc[idx_1m:].max()):,}"
        hl_3m = f"{safe_int(df['Low'].iloc[idx_3m:].min()):,} - {safe_int(df['High'].iloc[idx_3m:].max()):,}"

        ret_1w = ((close - df['Close'].iloc[idx_1w]) / df['Close'].iloc[idx_1w] * 100) if df['Close'].iloc[idx_1w] > 0 else 0
        ret_1m = ((close - df['Close'].iloc[idx_1m]) / df['Close'].iloc[idx_1m] * 100) if df['Close'].iloc[idx_1m] > 0 else 0
        ret_3m = ((close - df['Close'].iloc[idx_3m]) / df['Close'].iloc[idx_3m] * 100) if df['Close'].iloc[idx_3m] > 0 else 0
        ret_1y = ((close - df['Close'].iloc[0]) / df['Close'].iloc[0] * 100) if df['Close'].iloc[0] > 0 else 0
        
        current_year = df.index[-1].year
        df_ytd = df[df.index.year == current_year]
        ret_ytd = ((close - df_ytd['Close'].iloc[0]) / df_ytd['Close'].iloc[0] * 100) if not df_ytd.empty and df_ytd['Close'].iloc[0] > 0 else 0.0

        txt_harga_wajar = "Tidak Tersedia"
        txt_val_status = "-"
        pe_txt = pbv_txt = roe_txt = dy_txt = "-"

        try:
            info = t_obj.info
            eps = info.get('trailingEps', 0) or 0
            bvps = info.get('bookValue', 0) or 0
            
            pe = info.get('trailingPE', None)
            pbv = info.get('priceToBook', None)
            roe = info.get('returnOnEquity', None)
            dy = info.get('dividendYield', None)

            pe_txt = f"{pe:.2f}x" if pe else "-"
            pbv_txt = f"{pbv:.2f}x" if pbv else "-"
            roe_txt = f"{roe*100:.2f}%" if roe else "-"
            dy_txt = f"{dy*100:.2f}%" if dy else "-"

            if eps > 0 and bvps > 0:
                graham_num = safe_int((22.5 * eps * bvps) ** 0.5)
                if graham_num > 0:
                    mos = round(((graham_num - close) / graham_num) * 100, 1)
                    txt_harga_wajar = f"Rp {graham_num:,}"
                    if mos > 0:
                        txt_val_status = f"🟢 Undervalued (Diskon {mos}%)"
                    else:
                        txt_val_status = f"🔴 Overvalued (Mahal {abs(mos)}%)"
            elif eps <= 0:
                txt_val_status = "⚠ EPS Negatif (Rugi)"
        except Exception:
            pass

        ema20 = safe_int(today['EMA20'])
        ema50 = safe_int(today['EMA50'])
        rsi = round(float(today['RSI']), 1) if not pd.isna(today['RSI']) else 0.0
        stoch_k = round(float(today['Stoch_K']), 1) if not pd.isna(today['Stoch_K']) else 0.0
        stoch_d = round(float(today['Stoch_D']), 1) if not pd.isna(today['Stoch_D']) else 0.0
        macd_val = round(float(today['MACD']), 2) if not pd.isna(today['MACD']) else 0.0
        macd_sig = round(float(today['MACD_Signal']), 2) if not pd.isna(today['MACD_Signal']) else 0.0
        bb_upper = safe_int(today['BB_Upper'])
        bb_lower = safe_int(today['BB_Lower'])
        
        st_val = safe_int(today['Supertrend'])
        st_dir = today['ST_Dir']
        st_status = "🟢 BUY (Uptrend)" if st_dir == 1 else "🔴 SELL (Downtrend)"

        cmf_val = round(float(today['CMF']), 2) if not pd.isna(today['CMF']) else 0.0
        atr_val = safe_int(today['ATR'])
        
        vol_ma20 = safe_int(today['Vol_MA20'])
        vol_ratio = round(vol_today / vol_ma20, 2) if vol_ma20 > 0 else 0
        
        high_52w = safe_int(df['High'].max())
        low_52w = safe_int(df['Low'].min())

        if cmf_val > 0.10:
            status_akum = "🔥 AKUMULASI KUAT"
        elif 0.02 <= cmf_val <= 0.10:
            status_akum = "🟢 AKUMULASI HALUS"
        elif -0.10 <= cmf_val < -0.02:
            status_akum = "🔴 DISTRIBUSI HALUS"
        elif cmf_val < -0.10:
            status_akum = "💥 DISTRIBUSI BESAR"
        else:
            status_akum = "⚪ NETRAL"

        if close > ema20 > ema50:
            tren = "Uptrend"
        elif close < ema20 < ema50:
            tren = "Downtrend"
        else:
            tren = "Sideways"

        macd_status = "🟢 Bullish Cross" if macd_val > macd_sig else "🔴 Bearish Cross"

        # --- LOGIKA TRADING PLAN ---
        if st_dir == 1:
            rekomendasi = "BUY ON WEAKNESS / HOLD"
            buy_area = f"Rp {s1:,} - Rp {close:,}"
            sl_price = safe_int(st_val - (0.5 * atr_val)) if st_val > 0 else safe_int(s1 * 0.97)
            tp1_price = safe_int(r1)
            tp2_price = safe_int(r1 + (1.5 * atr_val))
        else:
            rekomendasi = "WAIT AND SEE / BREAKOUT BUY"
            buy_area = f"Rp {s1:,} (Tunggu Rebound) atau Breakout > Rp {st_val:,}"
            sl_price = safe_int(s1 * 0.95)
            tp1_price = safe_int(st_val)
            tp2_price = safe_int(r1)

        potensi_gain = round(((tp1_price - close) / close) * 100, 1) if close > 0 else 0
        potensi_risk = round(((close - sl_price) / close) * 100, 1) if close > 0 and close > sl_price else 0
        rr_ratio = round(potensi_gain / potensi_risk, 2) if potensi_risk > 0 else 0.0

        kode_clean = kode.replace('.JK', '')

        # --- TELEGRAM BAGIAN 1: Harga, Sentimen, Berita & Valuasi ---
        box_1 = (
            f"=== 📌 HARGA & SENTIMEN PASAR ===\n"
            f"Harga Terakhir : Rp {close:,} ({pct_change:+.2f}%) {status}\n"
            f"Perubahan      : Rp {change:+,}\n"
            f"Open Price     : Rp {open_price:,}\n"
            f"Sentimen Pasar : {status_sentimen}\n\n"
            f"📰 BERITA UTAMA ({len(list_berita)}):\n"
        )
        if list_berita:
            for idx, b in enumerate(list_berita, 1):
                box_1 += f"{idx}. {b}\n"
        else:
            box_1 += "Tidak ada berita berdampak signifikan.\n"

        box_1 += (
            f"\n=== 💎 VALUASI & KINERJA RETURN ===\n"
            f"PER / PBV      : {pe_txt} / {pbv_txt}\n"
            f"ROE / Div Yield: {roe_txt} / {dy_txt}\n"
            f"Harga Wajar    : {txt_harga_wajar}\n"
            f"Status Valuasi : {txt_val_status}\n"
            f"Return 1W / 1M : {ret_1w:+.2f}% / {ret_1m:+.2f}%\n"
            f"Return 3M / YTD: {ret_3m:+.2f}% / {ret_ytd:+.2f}%\n"
            f"Return 1Y      : {ret_1y:+.2f}%\n"
            f"1 Wg / 1 Bln   : Rp {hl_1w} / {hl_1m}\n"
            f"1 Tahun (52W)  : Rp {low_52w:,} - {high_52w:,}\n"
        )

        # --- TELEGRAM BAGIAN 2: Bandar, Teknikal & Trading Plan ---
        box_2 = (
            f"=== 🐋 BANDARMOLOGI & VOLUME ===\n"
            f"Status Bandar  : {status_akum}\n"
            f"Vol Hari Ini   : {vol_today:,} lembar\n"
            f"Vol Kemarin    : {vol_prev:,} ({vol_change_pct:+.2f}%)\n"
            f"Rasio Volume   : {vol_ratio}x (vs MA20)\n\n"
            f"=== 🕯 CANDLESTICK & PIVOT ===\n"
            f"Ekor Bawah     : Rp {ekor_bawah_rp:,} ({ekor_bawah_pct:.1f}%)\n"
            f"Rentang Hari   : Rp {low:,} - {high:,}\n"
            f"Support/Resist : Rp {s1:,} / Rp {r1:,}\n"
            f"Fluktuasi (ATR): Rp {atr_val:,}\n\n"
            f"=== 📊 INDIKATOR TEKNIKAL ===\n"
            f"Supertrend     : Rp {st_val:,} ({st_status})\n"
            f"Kondisi Tren   : {tren}\n"
            f"EMA 20 / 50    : Rp {ema20:,} / Rp {ema50:,}\n"
            f"RSI (14)       : {rsi}\n"
            f"Stoch %K/%D    : {stoch_k} / {stoch_d}\n"
            f"MACD / Signal  : {macd_val} / {macd_sig} ({macd_status})\n"
            f"Bollinger Bands: Rp {bb_lower:,} - Rp {bb_upper:,}\n\n"
            f"=== 🎯 TRADING PLAN OTOMATIS ===\n"
            f"Sinyal / Aksi  : {rekomendasi}\n"
            f"Area Beli      : {buy_area}\n"
            f"Target TP 1    : Rp {tp1_price:,} (+{potensi_gain}%)\n"
            f"Target TP 2    : Rp {tp2_price:,}\n"
            f"Stop Loss (SL) : Rp {sl_price:,} (-{potensi_risk}%)\n"
            f"Risk/Reward    : 1 : {rr_ratio}"
        )

        # --- OUTPUT FULL LENGKAP PADA TERMINAL TERMUX ---
        print("=" * 60)
        print(f"📌 DETAIL SAHAM LENGKAP: {kode_clean}")
        print("=" * 60)
        print(box_1)
        print(box_2)
        print("=" * 60)

        # Kirim Bagian 1 ke Telegram
        msg1 = f"📊 <b>HASIL ANALISIS SAHAM {escape_html(kode_clean)} (1/2)</b>\n\n<pre><code>{escape_html(box_1)}</code></pre>"
        kirim_telegram_pretty(msg1)

        # Kirim Bagian 2 ke Telegram
        msg2 = f"📊 <b>HASIL ANALISIS SAHAM {escape_html(kode_clean)} (2/2)</b>\n\n<pre><code>{escape_html(box_2)}</code></pre>"
        kirim_telegram_pretty(msg2)

    except Exception as e:
        print(f"❌ Terjadi kesalahan: {e}\n")

if __name__ == "__main__":
    print("\n=== PROGRAM CEK DETAIL SAHAM LENGKAP ===")
    while True:
        saham = input("Masukkan kode saham (ketik 'exit' buat keluar): ")
        if saham.lower().strip() == 'exit':
            print("Selesai!")
            break
        if saham.strip():
            panggil_saham(saham)
