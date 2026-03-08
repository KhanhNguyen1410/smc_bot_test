import schedule
import time
import json
import os
from scanner import scan_markets

def main():
    with open(os.path.join(os.path.dirname(__file__), 'config.json'), 'r') as f:
        config = json.load(f)
        
    interval = config.get("interval_minutes", 10)
    
    print(f"======================================")
    print(f" Khởi động Bot SMC Scanner (Local Mode)")
    print(f" Tự động chạy quét vào các phút 01, 16, 31, 46 của mỗi giờ.")
    print(f"======================================\n")
    
    # Lên lịch chạy vào đúng mốc 01, 16, 31, 46 mỗi giờ
    # Chạy trễ 1 phút để nến bên Binance đóng cửa hoàn toàn
    schedule.every().hour.at(":01").do(scan_markets)
    schedule.every().hour.at(":16").do(scan_markets)
    schedule.every().hour.at(":31").do(scan_markets)
    schedule.every().hour.at(":46").do(scan_markets)
    
    # Chạy lần đầu ngay lập tức để lấy tín hiệu (tùy chọn, bạn có thể comment dòng này nếu muốn đợi đúng giờ)
    scan_markets() 
    
    while True:
        schedule.run_pending()
        time.sleep(1)

if __name__ == "__main__":
    main()
