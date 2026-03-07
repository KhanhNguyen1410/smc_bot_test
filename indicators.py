import pandas as pd
import numpy as np

def add_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """
    Tính toán các chỉ báo cho phân tích SMC: EMA50, EMA200, RSI(14), Volume SMA(20) và Swing High/Low
    """
    if len(df) < 200:
        return df
        
    df = df.copy()
        
    # EMA
    df['ema_50'] = df['close'].ewm(span=50, adjust=False).mean()
    df['ema_200'] = df['close'].ewm(span=200, adjust=False).mean()
    
    # RSI 14 (Sử dụng Wilder's Smoothing)
    delta = df['close'].diff()
    up, down = delta.copy(), delta.copy()
    up[up < 0] = 0
    down[down > 0] = 0
    
    roll_up = up.ewm(alpha=1/14, adjust=False).mean()
    roll_down = down.abs().ewm(alpha=1/14, adjust=False).mean()
    
    rs = roll_up / roll_down
    df['rsi'] = 100.0 - (100.0 / (1.0 + rs))
    
    # Volume SMA 20
    df['volume_sma_20'] = df['volume'].rolling(window=20).mean()
    
    # Swing Highs and Lows (Window = 5: 2 trái, 1 giữa, 2 phải)
    df['swing_high'] = False
    df['swing_low'] = False
    
    highs = df['high'].values
    lows = df['low'].values
    
    for i in range(2, len(df) - 2):
        # Is Swing High?
        if highs[i] > highs[i-1] and highs[i] > highs[i-2] and highs[i] > highs[i+1] and highs[i] > highs[i+2]:
            df.loc[df.index[i], 'swing_high'] = True
            
        # Is Swing Low?
        if lows[i] < lows[i-1] and lows[i] < lows[i-2] and lows[i] < lows[i+1] and lows[i] < lows[i+2]:
            df.loc[df.index[i], 'swing_low'] = True
            
    return df
