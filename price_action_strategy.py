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
            
            # Đảm bảo TP lớn hơn hoặc bằng 2.0%
            min_tp_price = entry * 1.02
            if tp < min_tp_price:
                tp = min_tp_price
                sl = entry - ((tp - entry) / 2) # Nới SL để giữ nguyên RR 1:2
            
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
            
            # Đảm bảo TP lớn hơn hoặc bằng 2.0%
            min_tp_price = entry * 0.98
            if tp > min_tp_price:
                tp = min_tp_price
                sl = entry + ((entry - tp) / 2) # Nới SL để giữ nguyên RR 1:2
            
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
        
    # Điều kiện Breakout Up kèm Volume nổ
    if bo['close'] > mb['high']:
        # Lọc nhiễu: Volume cây breakout phải lớn hơn volume trung bình 20 phiên x 1.2
        if 'volume_sma_20' in bo and bo['volume'] < bo['volume_sma_20'] * 1.2:
            return None
            
        entry = bo['close']
        sl = mb['low'] # SL dưới nến mẹ cho an toàn
        tp = entry + (entry - sl) * 1.5 # RR 1:1.5 vì mô hình này thường SL khá dài
        
        min_tp_price = entry * 1.02 # Tối thiểu 2%
        if tp < min_tp_price:
            tp = min_tp_price
            sl = entry - ((tp - entry) / 1.5)
        return {
            "type": "PRICE ACTION - LONG (Inside Bar Breakout)",
            "entry": entry,
            "sl": sl,
            "tp": tp,
            "reason": f"Giá phá vỡ lên cụm nến nén chặt (Inside Bar) với Volume đột biến."
        }
        
    # Điều kiện Breakout Down kèm Volume nổ
    if bo['close'] < mb['low']:
        if 'volume_sma_20' in bo and bo['volume'] < bo['volume_sma_20'] * 1.2:
            return None
            
        entry = bo['close']
        sl = mb['high']
        tp = entry - (sl - entry) * 1.5
        
        min_tp_price = entry * 0.98 # Tối thiểu 2%
        if tp > min_tp_price:
            tp = min_tp_price
            sl = entry + ((entry - tp) / 1.5)
        return {
            "type": "PRICE ACTION - SHORT (Inside Bar Breakout)",
            "entry": entry,
            "sl": sl,
            "tp": tp,
            "reason": f"Giá phá vỡ xuống cụm nến nén chặt (Inside Bar) với Volume đột biến."
        }
        
    return None

def check_breakout_retest(df: pd.DataFrame):
    """
    Tìm setup Phá vỡ đỉnh/đáy rồi quay lại test (Retest).
    Đã nâng cấp 4 màng lọc nhiễu: Volume Breakout, Momentum Body, Pinbar Retest và thuận EMA.
    """
    if len(df) < 30:
        return None
        
    past_df = df.iloc[-30:-5]
    recent_df = df.iloc[-5:-1] # Các nến gần nhất (chứa nến Breakout)
    current_candle = df.iloc[-1] # Nến Retest
    
    res_level = past_df['high'].max()
    sup_level = past_df['low'].min()
    ema50 = current_candle['ema_50'] if 'ema_50' in current_candle else None
    
    # 1. Long B&R
    bo_up_candles = recent_df[recent_df['close'] > res_level]
    valid_bo_up = False
    
    # Filter 1 & 2: Xác nhận Breakout bằng Volume (>1.2x SMA20) và Lực Nến (Thân > 60%)
    if not bo_up_candles.empty:
        for _, bo_candle in bo_up_candles.iterrows():
            body = abs(bo_candle['close'] - bo_candle['open'])
            total = bo_candle['high'] - bo_candle['low']
            
            vol_ok = 'volume_sma_20' not in bo_candle or pd.isna(bo_candle['volume_sma_20']) or bo_candle['volume'] > bo_candle['volume_sma_20'] * 1.2
            mom_ok = total > 0 and (body / total) > 0.6
            if vol_ok and mom_ok:
                valid_bo_up = True
                break
                
    # Filter 3 & 4: Nến Retest chạm cản tạo mô hình Pinbar và thuận EMA50
    retesting_res = (current_candle['low'] <= res_level) and (current_candle['close'] > res_level)
    
    if valid_bo_up and retesting_res:
        trend_ok = ema50 is None or pd.isna(ema50) or current_candle['close'] > ema50
        
        body_size = abs(current_candle['open'] - current_candle['close'])
        lower_wick = min(current_candle['open'], current_candle['close']) - current_candle['low']
        rejection_ok = lower_wick >= 1.5 * body_size and lower_wick > 0 # Rút râu mạnh
        
        if trend_ok and rejection_ok:
            entry = current_candle['close']
            sl = current_candle['low'] - (current_candle['high'] - current_candle['low']) * 0.5
            tp = entry + (entry - sl) * 2
            
            min_tp_price = entry * 1.02 # Tối thiểu 2%
            if tp < min_tp_price:
                tp = min_tp_price
                sl = entry - ((tp - entry) / 2)
            
            return {
                "type": "PRICE ACTION - LONG (Breakout & Retest)",
                "entry": entry,
                "sl": sl,
                "tp": tp,
                "reason": f"Phá vỡ đỉnh {res_level:.4f} với Volume & Lực nến tốt. Retest thành công tạo Pinbar thuận xu hướng."
            }

    # 2. Short B&R
    bo_down_candles = recent_df[recent_df['close'] < sup_level]
    valid_bo_down = False
    
    if not bo_down_candles.empty:
        for _, bo_candle in bo_down_candles.iterrows():
            body = abs(bo_candle['close'] - bo_candle['open'])
            total = bo_candle['high'] - bo_candle['low']
            
            vol_ok = 'volume_sma_20' not in bo_candle or pd.isna(bo_candle['volume_sma_20']) or bo_candle['volume'] > bo_candle['volume_sma_20'] * 1.2
            mom_ok = total > 0 and (body / total) > 0.6
            if vol_ok and mom_ok:
                valid_bo_down = True
                break
                
    retesting_sup = (current_candle['high'] >= sup_level) and (current_candle['close'] < sup_level)
    
    if valid_bo_down and retesting_sup:
        trend_ok = ema50 is None or pd.isna(ema50) or current_candle['close'] < ema50
        
        body_size = abs(current_candle['open'] - current_candle['close'])
        upper_wick = current_candle['high'] - max(current_candle['open'], current_candle['close'])
        rejection_ok = upper_wick >= 1.5 * body_size and upper_wick > 0
        
        if trend_ok and rejection_ok:
            entry = current_candle['close']
            sl = current_candle['high'] + (current_candle['high'] - current_candle['low']) * 0.5
            tp = entry - (sl - entry) * 2
            
            min_tp_price = entry * 0.98 # Tối thiểu 2%
            if tp > min_tp_price:
                tp = min_tp_price
                sl = entry + ((entry - tp) / 2)
            
            return {
                "type": "PRICE ACTION - SHORT (Breakout & Retest)",
                "entry": entry,
                "sl": sl,
                "tp": tp,
                "reason": f"Phá vỡ đáy {sup_level:.4f} với Volume & Lực nến tốt. Retest thành công tạo Pinbar thuận xu hướng."
            }

    return None
