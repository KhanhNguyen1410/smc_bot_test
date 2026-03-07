import json
import os
from binance_api import fetch_ohlcv
from indicators import add_indicators
from smc_strategy import get_trend, check_smc_setup
from telegram_bot import send_alert

def load_config():
    with open(os.path.join(os.path.dirname(__file__), 'config.json'), 'r') as f:
        return json.load(f)

def scan_markets():
    print("Bắt đầu quét thị trường...")
    config = load_config()
    symbols = config.get("symbols", [])
    tfs = config.get("timeframes", {})
    
    ltfs = tfs.get("ltf", ["15m"])
    if isinstance(ltfs, str):
        ltfs = [ltfs]
    htfs = tfs.get("htf", ["4h", "1d"])
    
    for symbol in symbols:
        print(f"Đang phân tích {symbol}...")
        
        # 1. Xác định xu hướng HTF (4h, 1d)
        htf_trend_main = "neutral"
        for htf in htfs:
            df_htf = fetch_ohlcv(symbol, htf, limit=200)
            if df_htf.empty:
                continue
                
            df_htf = add_indicators(df_htf)
            trend = get_trend(df_htf)
            
            if htf_trend_main == "neutral":
                htf_trend_main = trend
            elif htf_trend_main != trend and trend != "neutral":
                htf_trend_main = "conflict"
                
        if htf_trend_main in ["neutral", "conflict"]:
            print(f"  -> {symbol}: Xung đột trend HTF hoặc không rõ ràng.")
            continue
            
        print(f"  -> Trend HTF xác nhận: {htf_trend_main.upper()}. Đang tìm điểm Entry ở {', '.join(ltfs)}...")
            
        # 2. Tìm Setup trên các LTF
        for ltf in ltfs:
            df_ltf = fetch_ohlcv(symbol, ltf, limit=200)
            if df_ltf.empty:
                continue
                
            df_ltf = add_indicators(df_ltf)
            signal = check_smc_setup(df_ltf, htf_trend_main)
            
            if signal:
                msg = (
                    f"🚨 *TÍN HIỆU SMC {signal['type']}*\n"
                    f"Cặp giao dịch: `{symbol}`\n"
                    f"Khung thời gian: `{ltf}`\n"
                    f"Entry: `{signal['entry']:.5f}`\n"
                    f"Stop Loss: `{signal['sl']:.5f}`\n"
                    f"Take Profit: `{signal['tp']:.5f}`\n\n"
                    f"📖 *Lý do vào lệnh:*\n"
                    f"{signal['reason']}"
                )
                send_alert(msg)
            
    print("Đã hoàn tất 1 chu kỳ quét.\n")

if __name__ == "__main__":
    scan_markets()
