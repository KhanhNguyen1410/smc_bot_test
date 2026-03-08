import json
import os
import time
from datetime import datetime
import pandas as pd
from binance.client import Client
from indicators import add_indicators
from smc_strategy import get_trend, identify_order_blocks, check_smc_setup

def load_config():
    with open('config.json', 'r') as f:
        return json.load(f)

config = load_config()
client = Client()

def fetch_historical_data(symbol, interval, days=30):
    """Lấy dữ liệu nến trong quá khứ"""
    try:
        klines = client.get_historical_klines(symbol, interval, f"{days} day ago UTC")
        if not klines:
            return pd.DataFrame()
            
        df = pd.DataFrame(klines, columns=[
            'timestamp', 'open', 'high', 'low', 'close', 'volume',
            'close_time', 'quote_asset_volume', 'number_of_trades',
            'taker_buy_base_asset_volume', 'taker_buy_quote_asset_volume', 'ignore'
        ])
        df['datetime'] = pd.to_datetime(df['timestamp'], unit='ms')
        for col in ['open', 'high', 'low', 'close', 'volume']:
            df[col] = df[col].astype(float)
        return df[['datetime', 'open', 'high', 'low', 'close', 'volume']]
    except Exception as e:
        print(f"Lỗi lấy dữ liệu {symbol}: {e}")
        return pd.DataFrame()

def run_simulation():
    symbols = config.get("symbols", [])
    print(f"Bắt đầu Backtest Tần Suất Kèo (Khoảng 30 ngày) cho {len(symbols)} cặp...")
    
    total_signals = 0
    high_conf_signals = 0
    signals_by_symbol = {}
    
    for symbol in symbols:
        print(f"Đang quét {symbol}...")
        df_15m = fetch_historical_data(symbol, "15m", 30)
        df_4h = fetch_historical_data(symbol, "4h", 45) # Lấy 45 ngày để có đủ data MA200 cho 4H
        
        if df_15m.empty or df_4h.empty:
            continue
            
        # Thêm indicator trước để tính toán trượt
        df_15m = add_indicators(df_15m)
        df_4h = add_indicators(df_4h)
        
        signals_found_for_symbol = 0
        
        # Mô phỏng thời gian thực (trượt cửa sổ dữ liệu tịnh tiến)
        # Bắt đầu từ cây nến thứ 200 (để có đủ MA) đến hiện tại
        i = 200
        while i < len(df_15m):
            # Cắt data tại thời điểm i
            current_15m = df_15m.iloc[:i+1].copy()
            current_time = current_15m.iloc[-1]['datetime']
            
            # Cắt data 4H tính đến thời điểm current_time
            current_4h = df_4h[df_4h['datetime'] <= current_time]
            if len(current_4h) < 200:
                i += 1
                continue
                
            # Phân tích HTF
            htf_trend_main = get_trend(current_4h)
            if htf_trend_main == "neutral":
                i += 1
                continue
                
            # Phân tích SMC
            signal = check_smc_setup(current_15m, htf_trend_main, df_4h=current_4h, htf_timeframes=["4h"])
            
            if signal:
                total_signals += 1
                signals_found_for_symbol += 1
                if signal.get('score', 0) >= 7:
                    high_conf_signals += 1
                    
                # Nhảy một đoạn (vd: 12 nến = 3 tiếng) để tránh bắt trùng 1 tín hiệu nhiều lần trên cây nến bên cạnh
                i += 12
            else:
                i += 1
                
        signals_by_symbol[symbol] = signals_found_for_symbol
        print(f"  -> {symbol}: Tìm thấy {signals_found_for_symbol} kèo.")
        
    print("\n" + "="*40)
    print("📈 KẾT QUẢ MÔ PHỎNG (30 NGÀY QUA) 📈")
    print(f"Tổng số cặp giao dịch quét: {len(symbols)}")
    print(f"Tổng số tín hiệu tìm thấy: {total_signals} lệnh")
    print(f"Trung bình: {total_signals / 30:.1f} lệnh / ngày")
    print(f"Số kèo LỬA (High Confidence >= 7đ): {high_conf_signals} lệnh")
    print(f"Trung bình kèo LỬA: {high_conf_signals / 30:.2f} lệnh / ngày")
    print("Chi tiết:")
    for sym, count in signals_by_symbol.items():
        print(f" - {sym}: {count} lệnh")

if __name__ == "__main__":
    run_simulation()
