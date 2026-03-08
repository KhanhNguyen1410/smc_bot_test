import pandas as pd
import numpy as np

def check_pa_setup(df: pd.DataFrame):
    """
    Hàm chính kiểm tra 3 setup Price Action.
    Ưu tiên thứ tự: Breakout & Retest > Pinbar/Engulfing > Inside Bar Breakout
    """
    if len(df) < 20: 
        return None
        
    # Check Breakout & Retest
    br_signal = check_breakout_retest(df)
    if br_signal:
        return br_signal
        
    # Check Pinbar / Engulfing tại Swing points
    pe_signal = check_pinbar_engulfing(df)
    if pe_signal:
        return pe_signal
        
    # Check Inside Bar Breakout
    ib_signal = check_inside_bar(df)
    if ib_signal:
        return ib_signal
        
    return None

def check_pinbar_engulfing(df: pd.DataFrame):
    """
    Tìm Pin Bar hoặc Engulfing tại các vùng hỗ trợ / kháng cự (dựa vào Swing High/Low)
    """
    current_idx = df.index[-1]
    prev_idx = df.index[-2]
    
    current_candle = df.loc[current_idx]
    prev_candle = df.loc[prev_idx]
    
    # Tính toán râu nến và thân nến hiện tại
    body_size = abs(current_candle['open'] - current_candle['close'])
    upper_wick = current_candle['high'] - max(current_candle['open'], current_candle['close'])
    lower_wick = min(current_candle['open'], current_candle['close']) - current_candle['low']
    total_len = current_candle['high'] - current_candle['low']
    
    if total_len == 0:
        return None
        
    is_bullish = current_candle['close'] > current_candle['open']
    is_bearish = current_candle['close'] < current_candle['open']
    
    # --- Định nghĩa nến ---
    # Bullish Pinbar: Râu dưới dài (>= 2 lần thân) và râu trên ngắn
    is_bullish_pinbar = (lower_wick >= 2 * body_size) and (upper_wick <= body_size) and total_len > 0
    
    # Bearish Pinbar: Râu trên dài (>= 2 lần thân) và râu dưới ngắn
    is_bearish_pinbar = (upper_wick >= 2 * body_size) and (lower_wick <= body_size) and total_len > 0
    
    # Bullish Engulfing: Nến trước giảm, nến nay tăng và thân nến nay bao trùm thân nến trước
    prev_body = abs(prev_candle['open'] - prev_candle['close'])
    is_bullish_engulfing = (prev_candle['close'] < prev_candle['open']) and is_bullish and (body_size > prev_body) and (current_candle['close'] > prev_candle['open']) and (current_candle['open'] < prev_candle['close'])
    
    # Bearish Engulfing: Nến trước tăng, nến nay giảm và thân nến nay bao trùm thân nến trước
    is_bearish_engulfing = (prev_candle['close'] > prev_candle['open']) and is_bearish and (body_size > prev_body) and (current_candle['close'] < prev_candle['open']) and (current_candle['open'] > prev_candle['close'])

    # --- Đánh giá vị trí (so với EMA 50 hoặc Swing) ---
    # Đơn giản hoá bằng cách xem xét EMA 50 để thuận Trend
    ema50 = current_candle['ema_50'] if 'ema_50' in current_candle else None
    
    if (is_bullish_pinbar or is_bullish_engulfing):
        # Ưu tiên mua nếu giá đang mấp mé dội lên từ EMA hoặc EMA đang hướng lên
        if ema50 is None or current_candle['low'] <= ema50 * 1.002:
            entry = current_candle['close']
            sl = current_candle['low'] - (current_candle['high'] - current_candle['low']) * 0.1
            tp = entry + (entry - sl) * 2 # RR 1:2
            
            pattern_name = "Bullish Pinbar" if is_bullish_pinbar else "Bullish Engulfing"
            return {
                "type": "PRICE ACTION - LONG (Reversal)",
                "entry": entry,
                "sl": sl,
                "tp": tp,
                "reason": f"Phát hiện mẫu hình nến {pattern_name} bật tăng từ vùng hỗ trợ / EMA."
            }
            
    if (is_bearish_pinbar or is_bearish_engulfing):
        if ema50 is None or current_candle['high'] >= ema50 * 0.998:
            entry = current_candle['close']
            sl = current_candle['high'] + (current_candle['high'] - current_candle['low']) * 0.1
            tp = entry - (sl - entry) * 2 # RR 1:2
            
            pattern_name = "Bearish Pinbar" if is_bearish_pinbar else "Bearish Engulfing"
            return {
                "type": "PRICE ACTION - SHORT (Reversal)",
                "entry": entry,
                "sl": sl,
                "tp": tp,
                "reason": f"Phát hiện mẫu hình nến {pattern_name} bị từ chối giá tại vùng kháng cự / EMA."
            }

    return None

def check_inside_bar(df: pd.DataFrame):
    """
    Tìm Inside Bar Breakout.
    Mô hình cần ít nhất 3 nến: Nến -2 (Mẹ), Nến -1 (Inside - Nằm gọn trong Mẹ), Nến hiện tại (Phá vỡ)
    """
    if len(df) < 4:
        return None
        
    mother_idx = df.index[-3]
    inside_idx = df.index[-2]
    breakout_idx = df.index[-1]
    
    mb = df.loc[mother_idx]
    ib = df.loc[inside_idx]
    bo = df.loc[breakout_idx]
    
    # Điều kiện Inside Bar: High của nến trong thấp hơn High nến mẹ, Low nến trong cao hơn Low nến mẹ
    is_inside_bar = (ib['high'] <= mb['high']) and (ib['low'] >= mb['low'])
    
    if not is_inside_bar:
        return None
        
    # Điều kiện Breakout Up
    if bo['close'] > mb['high']:
        entry = bo['close']
        sl = mb['low'] # SL dưới nến mẹ cho an toàn
        tp = entry + (entry - sl) * 1.5 # RR 1:1.5 vì mô hình này thường SL khá dài
        return {
            "type": "PRICE ACTION - LONG (Inside Bar Breakout)",
            "entry": entry,
            "sl": sl,
            "tp": tp,
            "reason": f"Giá phá vỡ lên trên cụm nến nén chặt (Inside Bar)."
        }
        
    # Điều kiện Breakout Down
    if bo['close'] < mb['low']:
        entry = bo['close']
        sl = mb['high']
        tp = entry - (sl - entry) * 1.5
        return {
            "type": "PRICE ACTION - SHORT (Inside Bar Breakout)",
            "entry": entry,
            "sl": sl,
            "tp": tp,
            "reason": f"Giá phá vỡ xuống dưới cụm nến nén chặt (Inside Bar)."
        }
        
    return None

def check_breakout_retest(df: pd.DataFrame):
    """
    Tìm setup Phá vỡ đỉnh/đáy rồi quay lại test (Retest).
    Logic thu gọn: Nhìn lại N cây nến trước để kiếm đỉnh cao nhất (Kháng cự).
    Nếu giá từng phá vỡ Kháng cự này, rồi bây giờ Nến hiện tại đang chạm lại Kháng cự cũ (trở thành Hỗ trợ) từ trên xuống và rút râu.
    """
    if len(df) < 30:
        return None
        
    # Tìm mức cản cao nhất và thấp nhất trong vùng quá khứ [30 nến đến 5 nến trước]
    past_df = df.iloc[-30:-5]
    recent_df = df.iloc[-5:-1] # Các nến gần nhất (phá vỡ và quay lại)
    current_candle = df.iloc[-1]
    
    res_level = past_df['high'].max()
    sup_level = past_df['low'].min()
    
    # 1. Long B&R
    # Điều kiện: Đã có nến Breakout đóng cửa trên cản (res_level) trong 4 nến gần nhất
    has_breakout_up = any(recent_df['close'] > res_level)
    # Và hiện tại giá thoái lui về chạm lại vùng cản cũ (bây giờ là Hỗ trợ) và đang giữ giá trên đó
    retesting_res = (current_candle['low'] <= res_level) and (current_candle['close'] > res_level)
    
    if has_breakout_up and retesting_res:
        # Check xem thân nến hoặc râu dưới có dội lên không (Rút châm)
        lower_wick = min(current_candle['open'], current_candle['close']) - current_candle['low']
        if lower_wick > 0: # Có phản ứng dội
            entry = current_candle['close']
            sl = current_candle['low'] - (current_candle['high'] - current_candle['low']) * 0.5
            tp = entry + (entry - sl) * 2
            
            return {
                "type": "PRICE ACTION - LONG (Breakout & Retest)",
                "entry": entry,
                "sl": sl,
                "tp": tp,
                "reason": f"Giá phá vỡ đỉnh cũ tại {res_level:.4f} sau đó quay lại Retest thành công."
            }

    # 2. Short B&R
    has_breakout_down = any(recent_df['close'] < sup_level)
    retesting_sup = (current_candle['high'] >= sup_level) and (current_candle['close'] < sup_level)
    
    if has_breakout_down and retesting_sup:
        upper_wick = current_candle['high'] - max(current_candle['open'], current_candle['close'])
        if upper_wick > 0:
            entry = current_candle['close']
            sl = current_candle['high'] + (current_candle['high'] - current_candle['low']) * 0.5
            tp = entry - (sl - entry) * 2
            
            return {
                "type": "PRICE ACTION - SHORT (Breakout & Retest)",
                "entry": entry,
                "sl": sl,
                "tp": tp,
                "reason": f"Giá phá vỡ đáy cũ tại {sup_level:.4f} sau đó quay lại Retest thành công."
            }

    return None
