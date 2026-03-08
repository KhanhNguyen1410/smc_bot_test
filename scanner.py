import json
import os
import concurrent.futures

from binance_api import fetch_ohlcv
from indicators import add_indicators
from smc_strategy import get_trend, check_smc_setup
from bollinger_strategy import check_bollinger_setup
from price_action_strategy import check_pa_setup, check_htf_support_resistance
from telegram_bot import send_alert

def load_config():
    with open(os.path.join(os.path.dirname(__file__), 'config.json'), 'r') as f:
        return json.load(f)

def load_state():
    state_file = os.path.join(os.path.dirname(__file__), 'state.json')
    if os.path.exists(state_file):
        with open(state_file, 'r') as f:
            return json.load(f)
    return {"run_count": 0}

def save_state(state):
    state_file = os.path.join(os.path.dirname(__file__), 'state.json')
    with open(state_file, 'w') as f:
        json.dump(state, f)

def check_active_positions(state):
    active_positions = state.get("active_positions", {})
    if not active_positions:
        return
        
    print("Kiểm tra trạng thái các lệnh đang mở...")
    positions_to_remove = []
    
    for sig_key, pos in active_positions.items():
        symbol = pos['symbol']
        entry = pos['entry']
        sl = pos['sl']
        tp = pos['tp']
        pos_type = pos['type']
        
        # Chỉ cần lấy 1 cây nến 15m để có High/Low mới nhất
        df = fetch_ohlcv(symbol, "15m", limit=3) # lấy 3 cây mới nhất để quét râu
        if df.empty:
            continue
            
        recent_high = df['high'].max()
        recent_low = df['low'].min()
        
        hit_tp = False
        hit_sl = False
        
        if pos_type == "LONG":
            if recent_low <= sl:
                hit_sl = True
            elif recent_high >= tp:
                hit_tp = True
        else: # SHORT
            if recent_high >= sl:
                hit_sl = True
            elif recent_low <= tp:
                hit_tp = True
                
        if hit_tp or hit_sl:
            result = "🟢 Chốt Lời (TP)" if hit_tp else "🔴 Cắt Lỗ (SL)"
            pct = abs(tp - entry)/entry*100 if hit_tp else abs(entry - sl)/entry*100
            
            msg = (
                f"Lệnh *{pos_type}* `{symbol}` đã có kết quả:\n"
                f"{result}: `{pct:.2f}%`\n"
                f"Entry: `{entry:.5f}`\n"
                f"Key: `{sig_key}`"
            )
            send_alert(msg)
            positions_to_remove.append(sig_key)
            
    for key in positions_to_remove:
        del active_positions[key]
        
    state["active_positions"] = active_positions

def handle_signal(symbol, timeframe, signal, df_trigger, state, new_alerts, new_positions, sig_key):
    trigger_time = str(df_trigger.iloc[-1]['datetime'])
    alerted_signals = state.get("alerted_signals", {})
    
    if alerted_signals.get(sig_key) != trigger_time and new_alerts.get(sig_key) != trigger_time:
        new_alerts[sig_key] = trigger_time
        
        entry = signal['entry']
        sl = signal['sl']
        tp = signal['tp']
        
        tp_pct = abs(tp - entry) / entry * 100
        sl_pct = abs(entry - sl) / entry * 100
        
        msg = (
            f"🚨 *{signal['type']}*\n"
            f"Cặp giao dịch: `{symbol}`\n"
            f"Khung thời gian: `{timeframe}`\n"
            f"Entry: `{entry:.5f}`\n"
            f"Stop Loss: `{sl:.5f}` ({sl_pct:.2f}%)\n"
            f"Take Profit: `{tp:.5f}` ({tp_pct:.2f}%)\n\n"
            f"📖 *Lý do vào lệnh:*\n"
            f"{signal['reason']}"
        )
        send_alert(msg)
        
        # Lưu vào active positions
        is_long = "LONG" in signal['type'].upper() or "UP" in signal['type'].upper() or "SUPPORT" in signal['type'].upper()
        pos_type = "LONG" if is_long else "SHORT"
        
        new_positions[sig_key] = {
            "symbol": symbol,
            "entry": entry,
            "sl": sl,
            "tp": tp,
            "type": pos_type,
            "time": trigger_time
        }
        return 1
    return 0

def scan_markets():
    print("Bắt đầu quét thị trường...")
    config = load_config()
    symbols = config.get("symbols", [])
    tfs = config.get("timeframes", {})
    
    ltfs = tfs.get("ltf", ["15m"])
    if isinstance(ltfs, str):
        ltfs = [ltfs]
    htfs = tfs.get("htf", ["4h", "1d"])
    
    signals_found = 0
    
    # Sử dụng ThreadPoolExecutor để quét song song nhiều cặp coin cùng lúc
    max_workers = min(10, len(symbols)) # tối đa 10 luồng
    
    state = load_state()
    # Kiểm tra các lệnh đang mở trước
    check_active_positions(state)
    
    alerted_signals = state.get("alerted_signals", {})
    
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = []
        for symbol in symbols:
            # Submit each symbol to be processed concurrently
            futures.append(executor.submit(process_symbol, symbol, config, state))
            
        new_alerts = {}
        new_positions = {}
        for future in concurrent.futures.as_completed(futures):
            sf, na, nap = future.result()
            signals_found += sf
            new_alerts.update(na)
            new_positions.update(nap)
            
    # Cập nhật danh sách tín hiệu đã gửi
    state["alerted_signals"] = alerted_signals
    state["alerted_signals"].update(new_alerts)
    
    active_positions = state.get("active_positions", {})
    active_positions.update(new_positions)
    state["active_positions"] = active_positions
            
    print(f"Đã hoàn tất 1 chu kỳ quét. Tổng số tín hiệu mới tìm được: {signals_found}\n")
    
    # Logic kiểm tra Heartbeat (Báo cáo sinh tồn)
    state["run_count"] = state.get("run_count", 0) + 1
    heartbeat_runs = config.get("heartbeat_interval_runs", 10)
    
    if state["run_count"] >= heartbeat_runs:
        send_alert(f"🟢 *BOT HEARTBEAT*\nSMC Scanner vẫn đang chạy bình thường.\nĐã hoàn thành {state['run_count']} chu kỳ quét kể từ lần báo cáo trước.")
        state["run_count"] = 0 # reset biến đếm
        
    save_state(state)

def process_symbol(symbol, config, state):
    signals_found = 0
    new_alerts = {}
    new_positions = {}
    tfs = config.get("timeframes", {})
    ltfs = tfs.get("ltf", ["15m"])
    if isinstance(ltfs, str):
        ltfs = [ltfs]
    htfs = tfs.get("htf", ["4h", "1d"])
    
    print(f"Đang phân tích {symbol}...")
    
    # === A. CHIẾN LƯỢC BOLLINGER SCALP ĐA KHUNG (1H/15M) ===
    # Lấy dữ liệu đồng thời 2 khung
    df_1h = fetch_ohlcv(symbol, "1h", limit=200)
    df_15m = fetch_ohlcv(symbol, "15m", limit=200)
    
    if not df_1h.empty and not df_15m.empty:
        df_1h = add_indicators(df_1h)
        df_15m = add_indicators(df_15m)
        
        signal_bol = check_bollinger_setup(df_1h, df_15m)
        
        if signal_bol:
            sig_key = f"{symbol}_BOLLINGER_15m"
            sf = handle_signal(symbol, "15m", signal_bol, df_15m, state, new_alerts, new_positions, sig_key)
            signals_found += sf
            
    # === C. CHIẾN LƯỢC PRICE ACTION ===
    for ltf in ltfs:
        df_ltf = fetch_ohlcv(symbol, ltf, limit=200)
        if df_ltf.empty:
            continue
            
        df_ltf = add_indicators(df_ltf) # Cần cho EMA của Pinbar
        signal_pa = check_pa_setup(df_ltf)
        
        if signal_pa:
            sig_key = f"{symbol}_PA_{ltf}"
            sf = handle_signal(symbol, ltf, signal_pa, df_ltf, state, new_alerts, new_positions, sig_key)
            signals_found += sf
            
    # === B. CHIẾN LƯỢC SMC DÀI HẠN (Cần HTF Trend) ===
    htf_trend_main = "neutral"
    htf_confirmed = []
    
    for htf in htfs:
        df_htf = fetch_ohlcv(symbol, htf, limit=200)
        if df_htf.empty:
            continue
            
        df_htf = add_indicators(df_htf)
        trend = get_trend(df_htf)
        
        signal_htf_pa = check_htf_support_resistance(df_htf)
        if signal_htf_pa:
            sig_key = f"{symbol}_HTF_PA_{htf}"
            sf = handle_signal(symbol, htf, signal_htf_pa, df_htf, state, new_alerts, new_positions, sig_key)
            signals_found += sf
        
        if trend != "neutral":
            if htf_trend_main == "neutral":
                htf_trend_main = trend
                htf_confirmed.append(htf)
            elif htf_trend_main == trend:
                htf_confirmed.append(htf)
            elif htf_trend_main != trend:
                htf_trend_main = "conflict"
                break
                
    if htf_trend_main in ["neutral", "conflict"]:
        print(f"  -> {symbol}: Xung đột trend HTF hoặc không rõ ràng (SMC Strategy bị bỏ qua).")
        return signals_found, new_alerts, new_positions
        
    htf_str = ", ".join(htf_confirmed).upper()
    print(f"  -> {symbol}: Trend HTF xác nhận: {htf_trend_main.upper()} ({htf_str}). Đang tìm điểm SMC Entry...")
    
    for ltf in ltfs: # SMC chạy đa khung thời gian như config
        df_ltf = fetch_ohlcv(symbol, ltf, limit=200)
        if df_ltf.empty:
            continue
            
        df_ltf = add_indicators(df_ltf)
        signal_smc = check_smc_setup(df_ltf, htf_trend_main, htf_confirmed)
        
        if signal_smc:
            sig_key = f"{symbol}_SMC_{ltf}"
            sf = handle_signal(symbol, ltf, signal_smc, df_ltf, state, new_alerts, new_positions, sig_key)
            signals_found += sf
            
    return signals_found, new_alerts, new_positions
if __name__ == "__main__":
    scan_markets()
