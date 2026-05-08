import os
from dotenv import load_dotenv
import asyncio
from telethon import TelegramClient, events
from openai import OpenAI
from binance.client import Client as BinanceClient
from binance.enums import *

# .env dosyasını sisteme yükle
load_dotenv()

# .env dan apıleri sıstem ıcıne aldıgım yer
binance_api_key = os.getenv("BINANCE_API_KEY")
binance_api_secret = os.getenv("BINANCE_API_SECRET")
openai_api_key = os.getenv("OPENAI_API_KEY")

# OpenAI başlatma
client_gpt = OpenAI(api_key=openai_api_key)

# Binance başlatma
binance_client = BinanceClient(api_key=binance_api_key, api_secret=binance_api_secret, testnet=True)
# --- AYARLAR BAGLANTI APILERI ---

DRY_RUN = False

# Telegram
api_id = os.getenv("TELEGRAM_API_ID")
api_hash = os.getenv("TELEGRAM_API_HASH")
client = TelegramClient('session_name', int(api_id), api_hash)
channel_username = 'ninjanewstr'

# BORSADAKİ İSLEM HACMİ
symbol = "BTCUSDT"
leverage = 3
dolar_miktari = 100

# --- GLOBAL DURUM ---
current_position = None

# --- TELEGRAM MESAJI GELİNCE ÇALIŞIR ---
@client.on(events.NewMessage(chats=channel_username))
async def news_handler(event):
    global current_position
    news_text = event.message.text
    if not news_text: return

    print(f"\n📨 Gelen haber: {news_text}")

    try:
        # --- GPT değerlendirmesi,GPT gidecek mesaj ---
        response = client_gpt.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": (
                    "Gelen haberi Bitcoin (BTC) açısından değerlendir. "
                    "1'den 10'a kadar bir puan ver: 10 çok olumlu (BTC yükselir), "
                    "1 çok olumsuz (BTC düşer), 5 nötr. "
                    "Sonuç olarak 'puan + boşluk + LONG/SHORT/HOLD' formatında yanıt ver. "
                    "Örnek: '10 Long', '1 Short', '5 Hold'."
                )},
                {"role": "user", "content": news_text}
            ],
            max_tokens=50
        )

        gpt_reply = response.choices[0].message.content.strip()
        print(f"🤖 GPT Kararı: {gpt_reply}")

        # Gelen yanıtı parçalarına ayır
        score, position = gpt_reply.split()
        score = int(score)
        position = position.upper()

        # --- Fiyat çekme ---
        ticker = binance_client.futures_symbol_ticker(symbol=symbol)
        btc_fiyati = float(ticker['price'])



        # stepSize hassasiyeti
        info = binance_client.futures_exchange_info()
        s_info = next(s for s in info['symbols'] if s['symbol'] == symbol)
        step_size = float(next(f['stepSize'] for f in s_info['filters'] if f['filterType'] == 'LOT_SIZE'))

        quantity = round((dolar_miktari * leverage) / btc_fiyati, 3)
        binance_client.futures_change_leverage(symbol=symbol, leverage=leverage)

        # EMİR GÖNDERME FONKSİYONU (Hata yakalamalı)
        def send_order(side):
            try:
                res = binance_client.futures_create_order(symbol=symbol, side=side, type=ORDER_TYPE_MARKET,
                                                          quantity=quantity)
                print(f"✅ Binance Onayı: {res['status']} | OrderID: {res['orderId']}")
                return True
            except Exception as e:
                print(f"❌ BİNANCE EMİR HATASI: {e}")
                return False

        # --- Pozisyon Mantığı ---
        if position == "LONG" and score >= 9 and current_position != "LONG":
            if not DRY_RUN:
                if send_order(SIDE_BUY): current_position = "LONG"

        elif position == "SHORT" and score <= 2 and current_position != "SHORT":
            if not DRY_RUN:
                if send_order(SIDE_SELL): current_position = "SHORT"
        else:
            print("⚖️ İşlem yapılmadı (Nötr).")

    except Exception as e:
        print(f"❌ İşlem Hatası: {e}")


# --- MANUEL TEST FONKSİYONU ---
async def manual_test():
    await asyncio.sleep(5)
    print("\n" + "=" * 45 + "\n🚀 TEST MODU AKTİF\n" + "=" * 45)

    while True:
        try:
            # Kilitlenmeyi önlemek için to_thread kullanıyoruz
            test_news = await asyncio.to_thread(input, "📣 Manuel Haber Gir: ")
            if test_news.lower() == 'exit': break
            if test_news.strip():
                print(f"🧪 İşleniyor: {test_news}")

                class MockMessage:
                    def __init__(self, t): self.text = t

                class MockEvent:
                    def __init__(self, t): self.message = MockMessage(t)

                await news_handler(MockEvent(test_news))
        except Exception as e:
            print(f"⚠️ Test hatası: {e}")


# --- ÇALIŞTIRICI ---
if __name__ == "__main__":
    client.loop.create_task(manual_test())
    try:
        client.start()
        print("✅ Bot Aktif!")
        client.run_until_disconnected()
    except KeyboardInterrupt:
        print("\n🛑 Durduruldu.")