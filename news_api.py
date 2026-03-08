import requests
import datetime
from dateutil import parser
from dateutil.tz import tzutc, tzlocal

def get_high_impact_news():
    """
    Lấy tin tức Đỏ (High Impact) từ nfs.faireconomy.media (Dữ liệu của ForexFactory).
    Trả về danh sách event Đỏ (High) của hệ USD.
    """
    url = "https://nfs.faireconomy.media/ff_calendar_thisweek.json"
    
    headers = {
        'User-Agent': 'Mozilla/5.0'
    }
    
    events = []
    try:
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        data = response.json()
    except Exception as e:
        print(f"Lỗi khi tải lịch kinh tế: {e}")
        return []

    now_local = datetime.datetime.now(tzlocal())
    
    for item in data:
        # Lọc tin USD và High impact
        if item.get("country") == "USD" and item.get("impact") == "High":
            # API trả về time dạng ISO "2023-10-12T08:30:00-04:00" (đã có múi giờ Mỹ chuẩn r)
            time_str = item.get("date")
            title = item.get("title")
            
            try:
                # Parse ra object timezone-aware
                dt_obj_utc = parser.parse(time_str)
                # Chuyển về Local time (Giờ VN nếu máy chạy ở VN)
                dt_obj_local = dt_obj_utc.astimezone(tzlocal())
                
                # Chỉ lấy các sự kiện của ngày hôm nay và tương lai gần (để tránh xử lý lại tin cũ đầu tuần)
                if dt_obj_local >= now_local - datetime.timedelta(hours=2):
                    events.append({
                        "id": f"news_usd_{dt_obj_local.timestamp()}",
                        "event": title,
                        "time": dt_obj_local,
                        "time_str": dt_obj_local.strftime("%Y-%m-%d %H:%M")
                    })
            except Exception as e:
                pass
                
    return events


def check_upcoming_news(events, minutes_ahead=30):
    """
    Kiểm tra xem có tin tức nào sắp diễn ra trong vòng `minutes_ahead` phút không.
    Trả về danh sách các tin sắp ra.
    """
    upcoming = []
    now = datetime.datetime.now(tzlocal())
    
    for ev in events:
        time_diff = (ev['time'] - now).total_seconds() / 60.0
        
        # Nếu sự kiện sẽ diễn ra trong vòng m phút tới (lớn hơn 0 và nhỏ hơn or bằng minutes_ahead)
        if 0 < time_diff <= minutes_ahead:
            upcoming.append(ev)
            
    return upcoming

if __name__ == "__main__":
    print("Fetching High Impact USD News (Faireconomy API)...")
    news = get_high_impact_news()
    for n in news:
        print(f"[{n['time_str']}] 🔴 {n['event']} (ID: {n['id']})")
    
    if not news:
        print("Không có tin Đỏ USD nào sắp tới trong tuần này.")
