import pandas as pd
import numpy as np

def get_trend(df: pd.DataFrame) -> str:
    """Trả về xu hướng hiện tại dựa trên EMA50 và EMA200"""
    if len(df) < 200:
        return "neutral"
    last_candle = df.iloc[-1]
    if last_candle['ema_50'] > last_candle['ema_200']:
        return "up"
    elif last_candle['ema_50'] < last_candle['ema_200']:
        return "down"
    return "neutral"

def identify_order_blocks(df: pd.DataFrame, trend: str) -> list:
    """
    Xác định các vùng Order Block (OB) chưa bị mitigate.
    - OB Tăng (Demand): Cây nến giảm cuối cùng trước đợt sóng tăng phá vỡ đỉnh (Swing High).
    - OB Giảm (Supply): Cây nến tăng cuối cùng trước đợt sóng giảm phá vỡ đáy (Swing Low).
    """
    obs = []
    if len(df) < 50:
        return obs
        
    # Lấy 50 nến gần nhất để tối ưu hiệu suất quét OB
    recent_df = df.iloc[-50:]
    
    if trend == "up":
        # Tìm Demand OB: Quá trình giá tạo Sweep/MSS rồi đi lên
        swing_highs = recent_df[recent_df['swing_high'] == True]
        for idx in swing_highs.index:
            # Tìm đoạn giảm trước khi phá vỡ cái đỉnh này
            pre_break_df = recent_df.loc[:idx].iloc[:-1]
            if not pre_break_df.empty:
                # Tìm cây nến đỏ cuối cùng (Bearish candle)
                bear_candles = pre_break_df[pre_break_df['close'] < pre_break_df['open']]
                if not bear_candles.empty:
                    ob_candle = bear_candles.iloc[-1]
                    # Vùng OB là râu trên và râu dưới của cây nến này
                    top_ob = max(ob_candle['open'], ob_candle['close'])
                    bottom_ob = ob_candle['low']
                    
                    # Kiểm tra xem từ đó tới nay giá đã mitigate (chạm lại) chưa
                    post_ob_df = recent_df.loc[idx:]
                    mitigated = (post_ob_df['low'] <= top_ob).any()
                    
                    if not mitigated:
                        obs.append({'top': top_ob, 'bottom': bottom_ob, 'type': 'demand', 'time': ob_candle.name})
                        
    elif trend == "down":
        # Tìm Supply OB
        swing_lows = recent_df[recent_df['swing_low'] == True]
        for idx in swing_lows.index:
            pre_break_df = recent_df.loc[:idx].iloc[:-1]
            if not pre_break_df.empty:
                # Tìm cây nến xanh cuối cùng (Bullish candle)
                bull_candles = pre_break_df[pre_break_df['close'] > pre_break_df['open']]
                if not bull_candles.empty:
                    ob_candle = bull_candles.iloc[-1]
                    top_ob = ob_candle['high']
                    bottom_ob = min(ob_candle['open'], ob_candle['close'])
                    
                    post_ob_df = recent_df.loc[idx:]
                    mitigated = (post_ob_df['high'] >= bottom_ob).any()
                    
                    if not mitigated:
                        obs.append({'top': top_ob, 'bottom': bottom_ob, 'type': 'supply', 'time': ob_candle.name})
                        
    return obs

def check_smc_setup(df: pd.DataFrame, htf_trend: str, df_4h: pd.DataFrame = None, htf_timeframes: list = None) -> dict:
    """
    Kiểm tra tín hiệu SMC trên DataFrame khung thời gian nhỏ (LTF).
    
    :param df: DataFrame của khung thời gian LTF (15m)
    :param htf_trend: Xu hướng từ khung thời gian cao (HTF) - "up", "down", hoặc "neutral"
    :param df_4h: Dữ liệu nến 4H để tìm Order Block HTF POI (nâng cao winrate)
    :param htf_timeframes: Danh sách các khung HTF đã xác nhận trend (ví dụ: ["4h", "1d"])
    """
    if len(df) < 50:
        return None
        
    last_candle = df.iloc[-1]
    ltf_trend = get_trend(df)
        
    # Lọc đồng thuận xu hướng (Trend Alignment)
    if htf_trend != "neutral" and htf_trend != ltf_trend:
        return None
        
    signal = None
    
    # === HỢP LƯU HTF POI (Order Block) ===
    in_htf_poi = False
    htf_poi_info = ""
    # Nếu có truyền df_4h vào, bot ưu tiên tìm Order Block HTF để lọc lệnh nhiễu.
    if df_4h is not None and not df_4h.empty:
        htf_obs = identify_order_blocks(df_4h, htf_trend)
        current_price = last_candle['close']
        
        for ob in htf_obs:
            if ob['type'] == 'demand' and ltf_trend == 'up':
                if ob['bottom'] * 0.99 <= current_price <= ob['top'] * 1.01: # Cho phép sai số 1% quanh vùng OB
                    in_htf_poi = True
                    htf_poi_info = f" (Giá chạm HTF Demand OB: {ob['bottom']:.2f}-{ob['top']:.2f})"
                    break
            elif ob['type'] == 'supply' and ltf_trend == 'down':
                if ob['bottom'] * 0.99 <= current_price <= ob['top'] * 1.01:
                    in_htf_poi = True
                    htf_poi_info = f" (Giá chạm HTF Supply OB: {ob['bottom']:.2f}-{ob['top']:.2f})"
                    break
                    
    # === KIỂM TRA LONG SETUP ===
    if ltf_trend == "up":
        recent_swing_lows = df[df['swing_low'] == True]
        if recent_swing_lows.empty:
            return None
            
        last_swing_low_val = recent_swing_lows['low'].iloc[-1]
        last_swing_low_idx = recent_swing_lows.index[-1]
        
        # Lấy mảng dữ liệu từ sau cái swing low
        post_swing_df = df.loc[last_swing_low_idx:].iloc[1:]
        if post_swing_df.empty:
            return None
            
        # Tính toán Body và Lower Wick để check Wick Rejection
        body = (post_swing_df['close'] - post_swing_df['open']).abs()
        lower_wick = np.minimum(post_swing_df['open'], post_swing_df['close']) - post_swing_df['low']
        
        # Tìm nến Sweep bằng mảng logic (Vectorized)
        sweep_mask = (post_swing_df['low'] < last_swing_low_val) & (post_swing_df['close'] > last_swing_low_val) & (post_swing_df['rsi'] <= 40) & (lower_wick > body * 2)
        valid_sweeps = post_swing_df[sweep_mask]
        if valid_sweeps.empty:
            return None
            
        sweep_candle = valid_sweeps.iloc[0] # Lấy cây quét đầu tiên xảy ra
        
        # Tìm MSS (Market Structure Shift) phá vỡ đỉnh dẫn hướng gần nhất trước cú quét
        swing_highs_before_sweep = df.loc[:sweep_candle.name][df['swing_high'] == True]
        if swing_highs_before_sweep.empty:
            return None
            
        target_high_val = swing_highs_before_sweep['high'].iloc[-1]
        
        # Lấy mảng dữ liệu từ sau nến Sweep
        post_sweep_df = df.loc[sweep_candle.name:].iloc[1:]
        if post_sweep_df.empty:
            return None
            
        # Tìm nến MSS bằng mảng logic (Vectorized)
        mss_mask = (post_sweep_df['close'] > target_high_val) & (post_sweep_df['volume'] > post_sweep_df['volume_sma_20'] * 1.5)
        valid_mss = post_sweep_df[mss_mask]
        
        if valid_mss.empty:
            return None
            
        mss_candle = valid_mss.iloc[0] # Lấy cây phá ngưỡng đầu tiên
            
        # Tìm FVG tăng giá hình thành từ lúc Sweep đến MSS
        fvg_df = df.loc[sweep_candle.name:mss_candle.name]
        
        fvg = None
        # Mảng shift nến để tìm FVG (Vectorized shift)
        if len(fvg_df) >= 3:
            fvg_mask = fvg_df['low'].shift(-2) > fvg_df['high']
            # Cây nến số 1 (i) thoả mãn điều kiện fvg_mask = True
            valid_fvgs = fvg_df[fvg_mask]
            
            if not valid_fvgs.empty:
                fvg_idx = valid_fvgs.index[0]
                candle1_high = fvg_df.loc[fvg_idx, 'high']
                candle3_idx = fvg_df.index[fvg_df.index.get_loc(fvg_idx) + 2]
                candle3_low = fvg_df.loc[candle3_idx, 'low']
                fvg = {'top': candle3_low, 'bottom': candle1_high}
                
        if fvg is None:
            return None
            
        # Entry: Giá hiện tại đi vào lại vùng FVG
        if last_candle['low'] <= fvg['top'] and last_candle['close'] >= fvg['bottom']:
            entry_price = (fvg['top'] + fvg['bottom']) / 2
            sl = sweep_candle['low'] * 0.999
            tp = entry_price + ((entry_price - sl) * 2)
            
            # Đảm bảo TP lớn hơn hoặc bằng 2.0%
            min_tp_price = entry_price * 1.02
            if tp < min_tp_price:
                tp = min_tp_price
                sl = entry_price - ((tp - entry_price) / 2) # Nới SL để giữ nguyên RR 1:2
            
            # Xây dựng lý do chi tiết
            htf_info = f"Xu hướng HTF ({', '.join(htf_timeframes).upper() if htf_timeframes else 'HTF'}) tăng" if htf_timeframes else "Xu hướng HTF tăng"
            
            # Lấy datetime nếu có
            sweep_date_str = ""
            mss_date_str = ""
            try:
                if 'datetime' in df.columns and hasattr(sweep_candle, 'name'):
                    sweep_dt = df.loc[sweep_candle.name, 'datetime']
                    if pd.notna(sweep_dt):
                        sweep_date_str = f" ({sweep_dt.strftime('%Y-%m-%d %H:%M')})"
            except:
                pass
            try:
                if 'datetime' in df.columns and hasattr(mss_candle, 'name'):
                    mss_dt = df.loc[mss_candle.name, 'datetime']
                    if pd.notna(mss_dt):
                        mss_date_str = f" ({mss_dt.strftime('%Y-%m-%d %H:%M')})"
            except:
                pass
            
            # --- TÍNH ĐIỂM CONFIDENCE SCORE (Max 10đ) ---
            score = 0
            # 1. HTF Confluence (Max 4đ)
            if in_htf_poi:
                score += 4
            elif htf_trend == ltf_trend: # Đồng thuận xu hướng
                score += 2
                
            # 2. Động lượng & Dòng tiền (Max 3đ)
            vol_ratio = mss_candle['volume'] / mss_candle['volume_sma_20']
            if vol_ratio > 2.0:
                score += 2
            elif vol_ratio > 1.5:
                score += 1
                
            if sweep_candle['rsi'] < 30: # Quá bán cực đại
                score += 1
                
            # 3. Hành vi giá & R:R (Max 3đ)
            sweep_body = abs(sweep_candle['close'] - sweep_candle['open'])
            sweep_lower_wick = min(sweep_candle['open'], sweep_candle['close']) - sweep_candle['low']
            if sweep_body > 0:
                if sweep_lower_wick / sweep_body > 3.0:
                    score += 2
                elif sweep_lower_wick / sweep_body > 2.0:
                    score += 1
                    
            rr_ratio = abs(tp - entry_price) / abs(entry_price - sl)
            if rr_ratio >= 3.0:
                score += 1
                
            # Phân loại độ tin cậy
            if score >= 7:
                conf_label = "🔥 HIGH CONFIDENCE"
            elif score >= 4:
                conf_label = "⚡ MEDIUM CONFIDENCE"
            else:
                conf_label = "❄️ LOW CONFIDENCE"
            # --------------------------------------------
            
            reason = (
                f"{htf_info}{htf_poi_info}. Có Liquidity Sweep kèm RSI quá bán ({sweep_candle['rsi']:.0f}) tại đáy {last_swing_low_val:.2f}"
                f"{sweep_date_str}. Phá vỡ cấu trúc (MSS) kèm Volume đột biến tại {target_high_val:.2f}"
                f"{mss_date_str}. Chạm lại vùng FVG tăng giá ({fvg['top']:.2f}-{fvg['bottom']:.2f})."
            )
            
            signal = {
                'type': 'LONG',
                'entry': entry_price, 'sl': sl, 'tp': tp,
                'reason': reason,
                'score': score,
                'conf_label': conf_label
            }
            
    # === KIỂM TRA SHORT SETUP ===
    elif ltf_trend == "down":
        recent_swing_highs = df[df['swing_high'] == True]
        if recent_swing_highs.empty:
            return None
            
        last_swing_high_val = recent_swing_highs['high'].iloc[-1]
        last_swing_high_idx = recent_swing_highs.index[-1]
        
        # Lấy mảng dữ liệu từ sau cái swing high
        post_swing_df = df.loc[last_swing_high_idx:].iloc[1:]
        if post_swing_df.empty:
            return None
            
        # Tính toán Body và Upper Wick để check Wick Rejection
        body = (post_swing_df['close'] - post_swing_df['open']).abs()
        upper_wick = post_swing_df['high'] - np.maximum(post_swing_df['open'], post_swing_df['close'])
        
        # Tìm nến Sweep bằng mảng logic (Vectorized)
        sweep_mask = (post_swing_df['high'] > last_swing_high_val) & (post_swing_df['close'] < last_swing_high_val) & (post_swing_df['rsi'] >= 60) & (upper_wick > body * 2)
        valid_sweeps = post_swing_df[sweep_mask]
        
        if valid_sweeps.empty:
            return None
            
        sweep_candle = valid_sweeps.iloc[0]
            
        swing_lows_before_sweep = df.loc[:sweep_candle.name][df['swing_low'] == True]
        if swing_lows_before_sweep.empty:
            return None
            
        target_low_val = swing_lows_before_sweep['low'].iloc[-1]
        
        # Lấy mảng dữ liệu từ sau nến Sweep
        post_sweep_df = df.loc[sweep_candle.name:].iloc[1:]
        if post_sweep_df.empty:
            return None
            
        # Tìm nến MSS bằng mảng logic (Vectorized)
        mss_mask = (post_sweep_df['close'] < target_low_val) & (post_sweep_df['volume'] > post_sweep_df['volume_sma_20'] * 1.5)
        valid_mss = post_sweep_df[mss_mask]
        
        if valid_mss.empty:
            return None
            
        mss_candle = valid_mss.iloc[0]
            
        fvg_df = df.loc[sweep_candle.name:mss_candle.name]
        fvg = None
        
        # Mảng shift nến để tìm FVG (Vectorized shift)
        if len(fvg_df) >= 3:
            fvg_mask = fvg_df['high'].shift(-2) < fvg_df['low']
            valid_fvgs = fvg_df[fvg_mask]
            
            if not valid_fvgs.empty:
                fvg_idx = valid_fvgs.index[0]
                candle1_low = fvg_df.loc[fvg_idx, 'low']
                candle3_idx = fvg_df.index[fvg_df.index.get_loc(fvg_idx) + 2]
                candle3_high = fvg_df.loc[candle3_idx, 'high']
                fvg = {'top': candle1_low, 'bottom': candle3_high}
                
        if fvg is None:
            return None
            
        # Entry: Giá hiện tại đi vào lại vùng FVG
        if last_candle['high'] >= fvg['bottom'] and last_candle['close'] <= fvg['top']:
            entry_price = (fvg['top'] + fvg['bottom']) / 2
            sl = sweep_candle['high'] * 1.001
            tp = entry_price - ((sl - entry_price) * 2)
            
            # Đảm bảo TP lớn hơn hoặc bằng 2.0%
            min_tp_price = entry_price * 0.98
            if tp > min_tp_price:
                tp = min_tp_price
                sl = entry_price + ((entry_price - tp) / 2) # Nới SL để giữ nguyên RR 1:2
            
            # Xây dựng lý do chi tiết
            htf_info = f"Xu hướng HTF ({', '.join(htf_timeframes).upper() if htf_timeframes else 'HTF'}) giảm" if htf_timeframes else "Xu hướng HTF giảm"
            
            # Lấy datetime nếu có
            sweep_date_str = ""
            mss_date_str = ""
            try:
                if 'datetime' in df.columns and hasattr(sweep_candle, 'name'):
                    sweep_dt = df.loc[sweep_candle.name, 'datetime']
                    if pd.notna(sweep_dt):
                        sweep_date_str = f" ({sweep_dt.strftime('%Y-%m-%d %H:%M')})"
            except:
                pass
            try:
                if 'datetime' in df.columns and hasattr(mss_candle, 'name'):
                    mss_dt = df.loc[mss_candle.name, 'datetime']
                    if pd.notna(mss_dt):
                        mss_date_str = f" ({mss_dt.strftime('%Y-%m-%d %H:%M')})"
            except:
                pass
            
            # --- TÍNH ĐIỂM CONFIDENCE SCORE (Max 10đ) ---
            score = 0
            # 1. HTF Confluence (Max 4đ)
            if in_htf_poi:
                score += 4
            elif htf_trend == ltf_trend: # Đồng thuận xu hướng
                score += 2
                
            # 2. Động lượng & Dòng tiền (Max 3đ)
            vol_ratio = mss_candle['volume'] / mss_candle['volume_sma_20']
            if vol_ratio > 2.0:
                score += 2
            elif vol_ratio > 1.5:
                score += 1
                
            if sweep_candle['rsi'] > 70: # Quá mua cực đại
                score += 1
                
            # 3. Hành vi giá & R:R (Max 3đ)
            sweep_body = abs(sweep_candle['close'] - sweep_candle['open'])
            sweep_upper_wick = sweep_candle['high'] - max(sweep_candle['open'], sweep_candle['close'])
            if sweep_body > 0:
                if sweep_upper_wick / sweep_body > 3.0:
                    score += 2
                elif sweep_upper_wick / sweep_body > 2.0:
                    score += 1
                    
            rr_ratio = abs(entry_price - tp) / abs(sl - entry_price)
            if rr_ratio >= 3.0:
                score += 1
                
            # Phân loại độ tin cậy
            if score >= 7:
                conf_label = "🔥 HIGH CONFIDENCE"
            elif score >= 4:
                conf_label = "⚡ MEDIUM CONFIDENCE"
            else:
                conf_label = "❄️ LOW CONFIDENCE"
            # --------------------------------------------
            
            reason = (
                f"{htf_info}{htf_poi_info}. Có Liquidity Sweep kèm RSI quá mua ({sweep_candle['rsi']:.0f}) tại đỉnh {last_swing_high_val:.2f}"
                f"{sweep_date_str}. Phá vỡ cấu trúc (MSS) kèm Volume đột biến tại {target_low_val:.2f}"
                f"{mss_date_str}. Chạm lại vùng FVG giảm giá ({fvg['bottom']:.2f}-{fvg['top']:.2f})."
            )
            
            signal = {
                'type': 'SHORT',
                'entry': entry_price, 'sl': sl, 'tp': tp,
                'reason': reason,
                'score': score,
                'conf_label': conf_label
            }
            
    return signal
