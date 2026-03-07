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
        
        sweep_candle = None
        # Tìm nến quét (sau cái swing low đó)
        for i in range(df.index.get_loc(last_swing_low_idx) + 1, len(df)):
            candle = df.iloc[i]
            if candle['low'] < last_swing_low_val and candle['close'] > last_swing_low_val:
                # Có quét thanh khoản kèm RSI quá bán (<= 40 cho phép sai số một chút)
                if candle['rsi'] <= 40:
                    sweep_candle = candle
                    break
                    
        if sweep_candle is None:
            return None
            
        # Tìm MSS (Market Structure Shift) phá vỡ đỉnh dẫn hướng gần nhất trước cú quét
        swing_highs_before_sweep = df.loc[:sweep_candle.name][df['swing_high'] == True]
        if swing_highs_before_sweep.empty:
            return None
            
        target_high_val = swing_highs_before_sweep['high'].iloc[-1]
        
        mss_candle = None
        for i in range(df.index.get_loc(sweep_candle.name) + 1, len(df)):
            candle = df.iloc[i]
            if candle['close'] > target_high_val:
                # Bộ lọc Volume: Khối lượng ở nến phá vỡ phải lớn hơn Volume SMA
                if candle['volume'] > candle['volume_sma_20']:
                    mss_candle = candle
                    break
                    
        if mss_candle is None:
            return None
            
        # Tìm FVG tăng giá hình thành từ lúc Sweep đến MSS
        start_idx_loc = df.index.get_loc(sweep_candle.name)
        end_idx_loc = df.index.get_loc(mss_candle.name)
        
        fvg = None
        for i in range(start_idx_loc, end_idx_loc):
            if i+2 >= len(df):
                continue
            candle1 = df.iloc[i]
            candle3 = df.iloc[i+2]
            
            # FVG Tăng
            if candle3['low'] > candle1['high']:
                fvg = {'top': candle3['low'], 'bottom': candle1['high']}
                break
                
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
        
        sweep_candle = None
        for i in range(df.index.get_loc(last_swing_high_idx) + 1, len(df)):
            candle = df.iloc[i]
            if candle['high'] > last_swing_high_val and candle['close'] < last_swing_high_val:
                if candle['rsi'] >= 60:
                    sweep_candle = candle
                    break
                    
        if sweep_candle is None:
            return None
            
        swing_lows_before_sweep = df.loc[:sweep_candle.name][df['swing_low'] == True]
        if swing_lows_before_sweep.empty:
            return None
            
        target_low_val = swing_lows_before_sweep['low'].iloc[-1]
        
        mss_candle = None
        for i in range(df.index.get_loc(sweep_candle.name) + 1, len(df)):
            candle = df.iloc[i]
            if candle['close'] < target_low_val:
                if candle['volume'] > candle['volume_sma_20']:
                    mss_candle = candle
                    break
                    
        if mss_candle is None:
            return None
            
        start_idx_loc = df.index.get_loc(sweep_candle.name)
        end_idx_loc = df.index.get_loc(mss_candle.name)
        
        fvg = None
        for i in range(start_idx_loc, end_idx_loc):
            if i+2 >= len(df):
                continue
            candle1 = df.iloc[i]
            candle3 = df.iloc[i+2]
            
            # FVG Giảm
            if candle3['high'] < candle1['low']:
                fvg = {'top': candle1['low'], 'bottom': candle3['high']}
                break
                
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
