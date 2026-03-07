import pandas as pd

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

def check_smc_setup(df: pd.DataFrame, htf_trend: str, htf_timeframes: list = None) -> dict:
    """
    Kiểm tra tín hiệu SMC trên DataFrame khung thời gian nhỏ (LTF).
    
    :param df: DataFrame của khung thời gian LTF (15m)
    :param htf_trend: Xu hướng từ khung thời gian cao (HTF) - "up", "down", hoặc "neutral"
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
            
        # Tìm nến Sweep bằng mảng logic (Vectorized)
        sweep_mask = (post_swing_df['low'] < last_swing_low_val) & (post_swing_df['close'] > last_swing_low_val) & (post_swing_df['rsi'] <= 40)
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
        mss_mask = (post_sweep_df['close'] > target_high_val) & (post_sweep_df['volume'] > post_sweep_df['volume_sma_20'])
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
            
            reason = (
                f"{htf_info}. Có Liquidity Sweep kèm RSI quá bán ({sweep_candle['rsi']:.0f}) tại đáy {last_swing_low_val:.2f}"
                f"{sweep_date_str}. Phá vỡ cấu trúc (MSS) kèm Volume đột biến tại {target_high_val:.2f}"
                f"{mss_date_str}. Chạm lại vùng FVG tăng giá ({fvg['bottom']:.2f}-{fvg['top']:.2f})."
            )
            
            signal = {
                'type': 'LONG',
                'entry': entry_price, 'sl': sl, 'tp': tp,
                'reason': reason
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
            
        # Tìm nến Sweep bằng mảng logic (Vectorized)
        sweep_mask = (post_swing_df['high'] > last_swing_high_val) & (post_swing_df['close'] < last_swing_high_val) & (post_swing_df['rsi'] >= 60)
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
        mss_mask = (post_sweep_df['close'] < target_low_val) & (post_sweep_df['volume'] > post_sweep_df['volume_sma_20'])
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
            
            reason = (
                f"{htf_info}. Có Liquidity Sweep kèm RSI quá mua ({sweep_candle['rsi']:.0f}) tại đỉnh {last_swing_high_val:.2f}"
                f"{sweep_date_str}. Phá vỡ cấu trúc (MSS) kèm Volume đột biến tại {target_low_val:.2f}"
                f"{mss_date_str}. Chạm lại vùng FVG giảm giá ({fvg['bottom']:.2f}-{fvg['top']:.2f})."
            )
            
            signal = {
                'type': 'SHORT',
                'entry': entry_price, 'sl': sl, 'tp': tp,
                'reason': reason
            }
            
    return signal
