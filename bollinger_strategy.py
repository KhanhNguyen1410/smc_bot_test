import pandas as pd

def check_bollinger_setup(df_1h: pd.DataFrame, df_15m: pd.DataFrame) -> dict:
    """
    Chiến lược Bollinger Scalp Đa Khung Thời Gian (1H Setup, 15M Entry) - Cố định bảo vệ lợi nhuận TP 1%.
    """
    if len(df_1h) < 3 or len(df_15m) < 3:
        return None
        
    last_1h = df_1h.iloc[-1]
    prev_1h = df_1h.iloc[-2]
    
    last_15m = df_15m.iloc[-1] # Nến 15m vừa đóng
    prev_15m = df_15m.iloc[-2] # Nến 15m liền trước
    setup_15m = df_15m.iloc[-3]
    
    signal = None
    
    # === KIỂM TRA LONG SCALP (BẮT ĐÁY ĐẢO CHIỀU) ===
    # 1. Khung 1H: Giá chạm hoặc đâm thủng cực dưới Bollinger, RSI <= 30
    if (prev_1h['low'] < prev_1h['bb_lower'] or last_1h['low'] < last_1h['bb_lower']) and min(prev_1h['rsi'], last_1h['rsi']) <= 30:
        
        # 2. Khung 15M: Tìm sự đảo chiều (Nến 15m hiện tại xanh và bẻ gãy thân nến đỏ trước)
        if prev_15m['close'] < prev_15m['open']: # Nến 15m liền trước là nến giảm
            if last_15m['close'] > last_15m['open'] and last_15m['close'] > prev_15m['high']: # Nến xanh hiện tại phá đỉnh (râu) nến đỏ trước
                
                # Setup LONG chuẩn
                entry_price = last_15m['close']
                
                # SL: Cắt lỗ dưới cái râu sâu nhất của cụm 15m này 1 chút xíu
                sl = min(last_15m['low'], prev_15m['low'], setup_15m['low']) * 0.999 
                
                # TP: Lướt sóng cố định 1.5% từ entry
                tp = entry_price * 1.015
                
                # Tính Risk (Rủi ro %): Nới SL tối đa 2.0% cho biên TP 1.5%.
                risk_pct = (entry_price - sl) / entry_price
                if risk_pct > 0 and risk_pct <= 0.02:
                    signal = {
                        'type': 'SCALP BOLLINGER LONG (1H/15M)',
                        'entry': entry_price, 'sl': sl, 'tp': tp,
                        'reason': f"Khung 1H kiệt sức ngoài BB Lower ({last_1h['bb_lower']:.2f}) & RSI quá bán ({last_1h['rsi']:.0f}). Khung 15M xuất hiện nến xanh đảo chiều phá đỉnh nến trước ({prev_15m['high']:.2f}). Đặt mục tiêu chốt nhanh 1.5%."
                    }
                    return signal

    # === KIỂM TRA SHORT SCALP (BẮT ĐỈNH ĐẢO CHIỀU) ===
    # 1. Khung 1H: Giá chạm hoặc đâm thủng cực trên Bollinger, RSI >= 70
    if (prev_1h['high'] > prev_1h['bb_upper'] or last_1h['high'] > last_1h['bb_upper']) and max(prev_1h['rsi'], last_1h['rsi']) >= 70:
        
        # 2. Khung 15M: Tìm sự đảo chiều (Nến 15m hiện tại đỏ và xả gãy thân nến tăng trước)
        if prev_15m['close'] > prev_15m['open']: # Nến 15m liền trước là nến tăng
            if last_15m['close'] < last_15m['open'] and last_15m['close'] < prev_15m['low']: # Nến đỏ hiện tại xả phá đáy (râu) nến xanh trước
                
                # Setup SHORT chuẩn
                entry_price = last_15m['close']
                
                # SL: Cắt lỗ trên cụm râu cao nhất của cụm 15m xíu xiu
                sl = max(last_15m['high'], prev_15m['high'], setup_15m['high']) * 1.001
                
                # TP: Lướt sóng cố định 1.5% từ entry
                tp = entry_price * 0.985
                
                # Tính Risk (Rủi ro %)
                risk_pct = (sl - entry_price) / entry_price
                if risk_pct > 0 and risk_pct <= 0.02:
                    signal = {
                        'type': 'SCALP BOLLINGER SHORT (1H/15M)',
                        'entry': entry_price, 'sl': sl, 'tp': tp,
                        'reason': f"Khung 1H đẩy vượt BB Upper ({last_1h['bb_upper']:.2f}) & RSI quá mua ({last_1h['rsi']:.0f}). Khung 15M xuất hiện nến xả đảo chiều phá đáy nến trước ({prev_15m['low']:.2f}). Đặt mục tiêu chốt nhanh 1.5%."
                    }
                    return signal
                    
    return signal
