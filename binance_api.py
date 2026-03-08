import requests
import pandas as pd

def fetch_ohlcv(symbol: str, interval: str, limit: int = 500) -> pd.DataFrame:
    """
    Lấy dữ liệu OHLCV từ Binance API.
    
    :param symbol: Tên cặp tiền giao dịch (VD: 'BTCUSDT')
    :param interval: Khung thời gian (VD: '15m', '1h', '4h', '1d')
    :param limit: Số lượng nến (Mặc định 500)
    :return: pd.DataFrame chứa OHLCV
    """
    url = "https://api.binance.com/api/v3/klines"
    params = {
        "symbol": symbol,
        "interval": interval,
        "limit": limit
    }
    
    try:
        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()
        
        if not data:
            return pd.DataFrame()
            
        columns = ['timestamp', 'open', 'high', 'low', 'close', 'volume', 'close_time', 'qav', 'num_trades', 'taker_base_vol', 'taker_quote_vol', 'ignore']
        df = pd.DataFrame(data, columns=columns)
        
        # Chuyển đổi định dạng thời gian
        df['datetime'] = pd.to_datetime(df['timestamp'], unit='ms')
        
        # Ép kiểu dữ liệu sang float
        numeric_cols = ['open', 'high', 'low', 'close', 'volume']
        df[numeric_cols] = df[numeric_cols].apply(pd.to_numeric)
        
        # Lọc bỏ cây nến cuối cùng (nến đang chạy chưa đóng cửa) để tránh tín hiệu fake
        df = df.iloc[:-1]
        
        return df[['datetime', 'open', 'high', 'low', 'close', 'volume']]
        
    except Exception as e:
        print(f"Lỗi khi lấy dữ liệu cho cặp {symbol} khung {interval}: {e}")
        return pd.DataFrame()
