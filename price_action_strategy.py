import pandas as pd
import numpy as np

def check_pa_setup(df: pd.DataFrame):
    """
    Hàm chính kiểm tra các setup Price Action.
    Ưu tiên thứ tự: Breakout & Retest > Inside Bar Breakout
    """
    if len(df) < 20: 
        return None
        
    # Check Breakout & Retest
    br_signal = check_breakout_retest(df)
    if br_signal:
        return br_signal
        
    # Check Inside Bar Breakout
    ib_signal = check_inside_bar(df)
    if ib_signal:
        return ib_signal
        
    return None

def check_htf_support_resistance(df_4h: pd.DataFrame):
    """
    Tìm tín hiệu đảo chiều (Bounce) tại các vùng Hỗ Trợ/Kháng Cự cứng trên khung 4H.
    Sử dụng thuật toán Cluster (gom cụm) Swing High/Low để tạo vùng cản vĩ mô.
    """
    if len(df_4h) < 100:
        return None
        
    last_candle = df_4h.iloc[-1]
    
    # 1. Tìm các vùng cản cứng (Clustering Swing Highs/Lows)
    swing_highs = df_4h[df_4h['swing_high'] == True]['high'].values
    swing_lows = df_4h[df_4h['swing_low'] == True]['low'].values
    
    # Hàm con để gom cụm (Clustering) các mức giá gần nhau (độ lệch <= 1%)
    def get_clusters(prices, threshold_pct=0.01):
        if len(prices) == 0: return []
        sorted_prices = np.sort(prices)
        clusters = []
        current_cluster = [sorted_prices[0]]
        
        for price in sorted_prices[1:]:
            if (price - np.mean(current_cluster)) / np.mean(current_cluster) <= threshold_pct:
                current_cluster.append(price)
            else:
                clusters.append(np.mean(current_cluster))
                current_cluster = [price]
        if current_cluster:
            clusters.append(np.mean(current_cluster))
        return clusters

    resistance_zones = get_clusters(swing_highs)
    support_zones = get_clusters(swing_lows)
    
    # Chiều dài và Râu nến
    body_size = abs(last_candle['open'] - last_candle['close'])
    upper_wick = last_candle['high'] - max(last_candle['open'], last_candle['close'])
    lower_wick = min(last_candle['open'], last_candle['close']) - last_candle['low']
    total_len = last_candle['high'] - last_candle['low']
    
    if total_len == 0:
        return None
        
    # Điều kiện Volume: Volume nến này phải > 1.2 lần trung bình 20 phiên
    has_high_volume = 'volume_sma_20' in last_candle and last_candle['volume'] > last_candle['volume_sma_20'] * 1.2
    
    # 2. LONG SETUP: Chạm Support cứng và Rút chân dưới cực mạnh (Râu >= 1.5 thân) + Volume khủng
    if has_high_volume and lower_wick >= 1.5 * body_size and lower_wick > upper_wick:
        # Kiểm tra xem mức giá Low có quét qua hoặc chạm Support nào không (sai số 0.5%)
        for sz in support_zones:
            if abs(last_candle['low'] - sz) / sz <= 0.005:
                entry = last_candle['close']
                sl = last_candle['low'] * 0.998 # Đặt sl dưới điểm thấp nhất xíu
                tp = entry * 1.02 # Cố định lợi nhuận 2%
                
                # Check RR (Chấp nhận mạo hiểm tới SL ~ 3-4% cho bắt đỉnh do biên TP lớn, điều chỉnh RR cho phù hợp thực tế)
                if (entry - sl) > 0 and (entry - sl)/entry <= 0.04: 
                    return {
                        "type": "HTF SUPPORT BOUNCE",
                        "entry": entry,
                        "sl": sl,
                        "tp": tp,
                        "reason": f"Khung lớn chạm hỗ trợ cứng khu vực ({sz:.4f}) rồi rút chân mạnh, kèm Volume đột biến xác nhận dòng tiền gom hàng. Chốt tối thiểu 2.0%."
                    }

    # 3. SHORT SETUP: Chạm Resistance cứng và Rút râu trên cực mạnh (Râu >= 1.5 thân) + Volume khủng
    if has_high_volume and upper_wick >= 1.5 * body_size and upper_wick > lower_wick:
        for rz in resistance_zones:
            if abs(last_candle['high'] - rz) / rz <= 0.005:
                entry = last_candle['close']
                sl = last_candle['high'] * 1.002
                tp = entry * 0.98
                
                if (sl - entry) > 0 and (sl - entry)/entry <= 0.04:
                    return {
                        "type": "HTF RESISTANCE BOUNCE",
                        "entry": entry,
                        "sl": sl,
                        "tp": tp,
                        "reason": f"Khung lớn chạm kháng cự cứng khu vực ({rz:.4f}) bị từ chối giá kịch liệt, kèm Volume xả lớn. Chốt tối thiểu 2.0%."
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
