import json
import os
import concurrent.futures

from binance_api import fetch_ohlcv
from indicators import add_indicators
from smc_strategy import get_trend, check_smc_setup
from bollinger_strategy import check_bollinger_setup
from price_action_strategy import check_pa_setup, check_htf_support_resistance
from telegram_bot import send_alert
from news_api import get_high_impact_news, check_upcoming_news

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
        
        # Break-even Logic
        break_even_triggered = pos.get('be_triggered', False)
        entry_price = float(entry)
        
        if pos_type == "LONG":
            risk_dist = entry_price - float(sl)
            be_target = entry_price + risk_dist # Mốc 1R
            
            # Check Break Even
            if not break_even_triggered and recent_high >= be_target:
                active_positions[sig_key]['sl'] = entry_price
                active_positions[sig_key]['be_triggered'] = True
                send_alert(f"🛡️ *CẬP NHẬT LỆNH*\nCặp: `{symbol}` (LONG)\nGiá đã chạy được 1R (+{risk_dist/entry_price*100:.2f}%).\n✅ *Đã dời Stop Loss về vùng giá Entry (Hòa vốn).*")
                
            # Check SL/TP
            hit_sl = recent_low <= float(active_positions[sig_key]['sl'])
            hit_tp = recent_high >= tp
            
        else: # SHORT
            risk_dist = float(sl) - entry_price
            be_target = entry_price - risk_dist # Mốc 1R
            
            # Check Break Even
            if not break_even_triggered and recent_low <= be_target:
                active_positions[sig_key]['sl'] = entry_price
                active_positions[sig_key]['be_triggered'] = True
                send_alert(f"🛡️ *CẬP NHẬT LỆNH*\nCặp: `{symbol}` (SHORT)\nGiá đã chạy được 1R (+{risk_dist/entry_price*100:.2f}%).\n✅ *Đã dời Stop Loss về vùng giá Entry (Hòa vốn).*")
                
            # Check SL/TP
            hit_sl = recent_high >= float(active_positions[sig_key]['sl'])
            hit_tp = recent_low <= tp
                
        if hit_tp or hit_sl:
            # Nếu chốt ở Entry (Hòa vốn)
            if hit_sl and active_positions[sig_key]['be_triggered']:
                result = "🛡️ Đóng Lệnh Hòa Vốn (Break-Even)"
                pct = 0.0
            else:
                result = "🟢 Chốt Lời (TP)" if hit_tp else "🔴 Cắt Lỗ (SL)"
                pct = abs(tp - entry)/entry*100 if hit_tp else abs(entry - float(active_positions[sig_key]['sl']))/entry*100
            
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
        
        # Trích xuất điểm tự tin nếu có (dành cho SMC)
        score_str = ""
        if 'score' in signal and 'conf_label' in signal:
            score = signal['score']
            stars = "⭐" * (score // 2 + 1) if score > 0 else "⭐"
            score_str = (
                f"\n🎯 *Điểm Tự Tin:* {stars} ({score}/10)\n"
                f"🏷️ *Phân Loại:* `{signal['conf_label']}`\n"
            )
            
        msg = (
            f"🚨 *{signal['type']}*\n"
            f"Cặp giao dịch: `{symbol}`\n"
            f"Khung thời gian: `{timeframe}`\n"
            f"Entry: `{entry:.5f}`\n"
            f"Stop Loss: `{sl:.5f}` ({sl_pct:.2f}%)\n"
            f"Take Profit: `{tp:.5f}` ({tp_pct:.2f}%)\n"
            f"{score_str}"
            f"\n📖 *Lý do vào lệnh:*\n"
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
            "time": trigger_time,
            "be_triggered": False
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
    
    # 0. Kiểm tra tin tức Vĩ Mô (Macroeconomic News)
    try:
        news_events = get_high_impact_news()
        upcoming = check_upcoming_news(news_events, minutes_ahead=35) # Cảnh báo trước tối đa 35 phút
        
        alerted_news = state.get("alerted_news", [])
        
        for news in upcoming:
            news_id = news['id']
            if news_id not in alerted_news:
                msg = (
                    f"⚠️ *CẢNH BÁO TIN TỨC VĨ MÔ*\n"
                    f"Sắp diễn ra tin ĐỎ (High Impact) tác động mạnh tới USD:\n\n"
                    f"🔴 *{news['event']}*\n"
                    f"⏰ Thời gian: `{news['time_str']}`\n\n"
                    f"👉 *Khuyến nghị:* Hãy cẩn thận rủi ro biến động giật cản (fakeout) hoặc dãn spread. Cân nhắc không vào lệnh mới lúc này."
                )
                send_alert(msg)
                alerted_news.append(news_id)
                
        # Giữ lại tối đa 50 tin để file state không bị quá dài
        state["alerted_news"] = alerted_news[-50:]
    except Exception as e:
        print(f"Lỗi khi check tin tức: {e}")

    # 1. Kiểm tra các lệnh đang mở trước
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
    
    # Giữ lại df khung 4H (hoặc khung lớn nhất) để đưa vào khối Order Block
    df_htf_poi = None
    
    for htf in htfs:
        df_htf = fetch_ohlcv(symbol, htf, limit=200)
        if df_htf.empty:
            continue
            
        df_htf = add_indicators(df_htf)
        trend = get_trend(df_htf)
        
        # Chọn khung lớn nhất (ví dụ 4H) làm HTF POI. Lưu lại DataFrame này.
        if htf == '4h' or df_htf_poi is None:
            df_htf_poi = df_htf
        
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
        
        # Pass df_ltf (15m), trend chính, df_htf_poi (4H) vào SMC
        signal_smc = check_smc_setup(df_ltf, htf_trend_main, df_htf_poi, htf_confirmed)
        
        if signal_smc:
            sig_key = f"{symbol}_SMC_{ltf}"
            sf = handle_signal(symbol, ltf, signal_smc, df_ltf, state, new_alerts, new_positions, sig_key)
            signals_found += sf
            
    return signals_found, new_alerts, new_positions
if __name__ == "__main__":
    scan_markets()
