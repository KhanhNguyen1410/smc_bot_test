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
    alerted_signals = state.get("alerted_signals", {})
    
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = []
        for symbol in symbols:
            # Submit each symbol to be processed concurrently
            futures.append(executor.submit(process_symbol, symbol, config, alerted_signals))
            
        new_alerts = {}
        for future in concurrent.futures.as_completed(futures):
            sf, na = future.result()
            signals_found += sf
            new_alerts.update(na)
            
    # Cập nhật danh sách tín hiệu đã gửi
    state["alerted_signals"] = alerted_signals
    state["alerted_signals"].update(new_alerts)
            
    print(f"Đã hoàn tất 1 chu kỳ quét. Tổng số tín hiệu mới tìm được: {signals_found}\n")
    
    # Logic kiểm tra Heartbeat (Báo cáo sinh tồn)
    state["run_count"] = state.get("run_count", 0) + 1
    heartbeat_runs = config.get("heartbeat_interval_runs", 10)
    
    if state["run_count"] >= heartbeat_runs:
        send_alert(f"🟢 *BOT HEARTBEAT*\nSMC Scanner vẫn đang chạy bình thường.\nĐã hoàn thành {state['run_count']} chu kỳ quét kể từ lần báo cáo trước.")
        state["run_count"] = 0 # reset biến đếm
        
    save_state(state)

def process_symbol(symbol, config, alerted_signals):
    signals_found = 0
    new_alerts = {}
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
            trigger_time = str(df_15m.iloc[-1]['datetime'])
            sig_key = f"{symbol}_BOLLINGER_15m"
            
            if alerted_signals.get(sig_key) != trigger_time and new_alerts.get(sig_key) != trigger_time:
                signals_found += 1
                new_alerts[sig_key] = trigger_time
                msg2 = (
                    f"🚨 *TÍN HIỆU {signal_bol['type']}*\n"
                    f"Cặp giao dịch: `{symbol}`\n"
                    f"Khung thời gian Entry: `15m` (Setup `1h`)\n"
                    f"Entry: `{signal_bol['entry']:.5f}`\n"
                    f"Stop Loss: `{signal_bol['sl']:.5f}`\n"
                    f"Take Profit: `{signal_bol['tp']:.5f}`\n\n"
                    f"📖 *Lý do vào lệnh:*\n"
                    f"{signal_bol['reason']}"
                )
                send_alert(msg2)
            
    # === C. CHIẾN LƯỢC PRICE ACTION ===
    for ltf in ltfs:
        df_ltf = fetch_ohlcv(symbol, ltf, limit=200)
        if df_ltf.empty:
            continue
            
        df_ltf = add_indicators(df_ltf) # Cần cho EMA của Pinbar
        signal_pa = check_pa_setup(df_ltf)
        
        if signal_pa:
            trigger_time = str(df_ltf.iloc[-1]['datetime'])
            sig_key = f"{symbol}_PA_{ltf}"
            
            if alerted_signals.get(sig_key) != trigger_time and new_alerts.get(sig_key) != trigger_time:
                signals_found += 1
                new_alerts[sig_key] = trigger_time
                msg3 = (
                    f"🚨 *{signal_pa['type']}*\n"
                    f"Cặp giao dịch: `{symbol}`\n"
                    f"Khung thời gian: `{ltf}`\n"
                    f"Entry: `{signal_pa['entry']:.5f}`\n"
                    f"Stop Loss: `{signal_pa['sl']:.5f}`\n"
                    f"Take Profit: `{signal_pa['tp']:.5f}`\n\n"
                    f"📖 *Lý do vào lệnh:*\n"
                    f"{signal_pa['reason']}"
                )
                send_alert(msg3)
            
    # === B. CHIẾN LƯỢC SMC DÀI HẠN (Cần HTF Trend) ===
    htf_trend_main = "neutral"
    htf_confirmed = []
    
    for htf in htfs:
        df_htf = fetch_ohlcv(symbol, htf, limit=200)
        if df_htf.empty:
            continue
            
        df_htf = add_indicators(df_htf)
        trend = get_trend(df_htf)
        
        # Bổ sung logic HTF Support/Resistance Bounce
        signal_htf_pa = check_htf_support_resistance(df_htf)
        if signal_htf_pa:
            trigger_time = str(df_htf.iloc[-1]['datetime'])
            sig_key = f"{symbol}_HTF_PA_{htf}"
            
            if alerted_signals.get(sig_key) != trigger_time and new_alerts.get(sig_key) != trigger_time:
                signals_found += 1
                new_alerts[sig_key] = trigger_time
                msg_htf = (
                    f"🚨 *{signal_htf_pa['type']}*\n"
                    f"Cặp giao dịch: `{symbol}`\n"
                    f"Khung thời gian: `{htf}`\n"
                    f"Entry: `{signal_htf_pa['entry']:.5f}`\n"
                    f"Stop Loss: `{signal_htf_pa['sl']:.5f}`\n"
                    f"Take Profit: `{signal_htf_pa['tp']:.5f}`\n\n"
                    f"📖 *Lý do vào lệnh:*\n"
                    f"{signal_htf_pa['reason']}"
                )
                send_alert(msg_htf)
        
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
        return signals_found, new_alerts
        
    htf_str = ", ".join(htf_confirmed).upper()
    print(f"  -> {symbol}: Trend HTF xác nhận: {htf_trend_main.upper()} ({htf_str}). Đang tìm điểm SMC Entry...")
    
    for ltf in ltfs: # SMC chạy đa khung thời gian như config
        df_ltf = fetch_ohlcv(symbol, ltf, limit=200)
        if df_ltf.empty:
            continue
            
        df_ltf = add_indicators(df_ltf)
        signal_smc = check_smc_setup(df_ltf, htf_trend_main, htf_confirmed)
        
        if signal_smc:
            trigger_time = str(df_ltf.iloc[-1]['datetime'])
            sig_key = f"{symbol}_SMC_{ltf}"
            
            if alerted_signals.get(sig_key) != trigger_time and new_alerts.get(sig_key) != trigger_time:
                signals_found += 1
                new_alerts[sig_key] = trigger_time
                msg = (
                    f"🚨 *TÍN HIỆU {signal_smc['type']} (SMC)*\n"
                    f"Cặp giao dịch: `{symbol}`\n"
                    f"Khung thời gian Entry: `{ltf}`\n"
                    f"Entry: `{signal_smc['entry']:.5f}`\n"
                    f"Stop Loss: `{signal_smc['sl']:.5f}`\n"
                    f"Take Profit: `{signal_smc['tp']:.5f}`\n\n"
                    f"📖 *Lý do vào lệnh:*\n"
                    f"{signal_smc['reason']}"
                )
                send_alert(msg)
            
    return signals_found, new_alerts
if __name__ == "__main__":
    scan_markets()
