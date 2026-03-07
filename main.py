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
    print(f" Khởi động Bot SMC Scanner")
    print(f" Tự động chạy quét mỗi {interval} phút.")
    print(f"======================================\n")
    
    scan_markets() # Chạy lần đầu ngay lập tức
    
    schedule.every(interval).minutes.do(scan_markets)
    
    while True:
        schedule.run_pending()
        time.sleep(1)

if __name__ == "__main__":
    main()
