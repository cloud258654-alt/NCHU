import re
import logging
from datetime import datetime, timedelta, timezone

logger = logging.getLogger("core.time_filter")

def parse_date_range(args) -> tuple[datetime | None, datetime | None]:
    """
    計算日期範圍過濾的起止邊界。
    優先順序：start-date/end-date > since-days > date-range > all
    """
    now = datetime.now(timezone.utc)
    
    # 1. start-date / end-date
    if getattr(args, "start_date", None) or getattr(args, "end_date", None):
        start_at = None
        end_at = None
        if args.start_date:
            try:
                # 支援 YYYY-MM-DD
                start_at = datetime.strptime(args.start_date.strip(), "%Y-%m-%d").replace(tzinfo=timezone.utc)
            except Exception as e:
                logger.error(f"解析 start-date 失敗: {e}")
        if args.end_date:
            try:
                # 支援 YYYY-MM-DD，結束日設為當天 23:59:59.999
                end_at = datetime.strptime(args.end_date.strip(), "%Y-%m-%d").replace(hour=23, minute=59, second=59, tzinfo=timezone.utc)
            except Exception as e:
                logger.error(f"解析 end-date 失敗: {e}")
        return start_at, end_at

    # 2. since-days
    if getattr(args, "since_days", None) is not None:
        start_at = now - timedelta(days=args.since_days)
        return start_at, None

    # 3. date-range
    date_range = getattr(args, "date_range", "all")
    if date_range == "week":
        return now - timedelta(days=7), None
    elif date_range == "month":
        return now - timedelta(days=30), None
    elif date_range == "year":
        return now - timedelta(days=365), None
    
    return None, None


def parse_platform_time(raw_time: str, platform: str) -> datetime | None:
    """
    將不同平台的多種相對或絕對時間格式，轉換成時區感知 (timezone-aware) 的 UTC datetime。
    """
    if not raw_time:
        return None
        
    raw_str = raw_time.strip()
    # 清除前綴 (例如小紅書 "发布于 06-18")
    raw_str = re.sub(r'^(发布于|發佈於|Posted on)\s*', '', raw_str)
    
    # 清除時間字尾與上下午字樣 (例如 "6月17日上午11:46" -> "6月17日", "2026年6月17日 18:30" -> "2026年6月17日")
    raw_str = re.sub(r'\s*(?:上午|下午)?\s*\d{1,2}:\d{2}(?::\d{2})?', '', raw_str)
    raw_str = raw_str.strip()
    
    now = datetime.now(timezone.utc)
    
    try:
        # --- 絕對日期格式 ---
        
        # Format 1: YYYY-MM-DD 或 YYYY/MM/DD
        match = re.match(r'^(\d{4})[-/](\d{1,2})[-/](\d{1,2})$', raw_str)
        if match:
            return datetime(int(match.group(1)), int(match.group(2)), int(match.group(3)), tzinfo=timezone.utc)
            
        # Format 2: YYYY年MM月DD日 (例如 "2026年7月1日")
        match = re.match(r'^(\d{4})年(\d{1,2})月(\d{1,2})日$', raw_str)
        if match:
            return datetime(int(match.group(1)), int(match.group(2)), int(match.group(3)), tzinfo=timezone.utc)
            
        # Format 3: MM-DD 或 MM/DD (預設今年)
        match = re.match(r'^(\d{1,2})[-/](\d{1,2})$', raw_str)
        if match:
            return datetime(now.year, int(match.group(1)), int(match.group(2)), tzinfo=timezone.utc)
            
        # Format 4: MM月DD日 (例如 "7月1日" 預設今年)
        match = re.match(r'^(\d{1,2})月(\d{1,2})日$', raw_str)
        if match:
            return datetime(now.year, int(match.group(1)), int(match.group(2)), tzinfo=timezone.utc)

        # --- 相對時間格式 (中文/英文) ---
        
        # 1. 剛剛 / 刚刚 / just now
        if raw_str in ["剛剛", "刚刚", "just now", "now"]:
            return now
            
        # 2. 昨天 / yesterday
        if "昨天" in raw_str or "yesterday" in raw_str.lower():
            dt = now - timedelta(days=1)
            time_match = re.search(r'(\d{1,2}):(\d{2})', raw_str)
            if time_match:
                return datetime(dt.year, dt.month, dt.day, int(time_match.group(1)), int(time_match.group(2)), tzinfo=timezone.utc)
            return dt
            
        # 3. 前天
        if "前天" in raw_str:
            dt = now - timedelta(days=2)
            time_match = re.search(r'(\d{1,2}):(\d{2})', raw_str)
            if time_match:
                return datetime(dt.year, dt.month, dt.day, int(time_match.group(1)), int(time_match.group(2)), tzinfo=timezone.utc)
            return dt

        # 4. x分鐘前 / x分钟前 / x minutes ago
        match = re.search(r'(\d+)\s*(?:分鐘前|分钟前|minutes? ago|min)', raw_str, re.IGNORECASE)
        if match:
            return now - timedelta(minutes=int(match.group(1)))
            
        # 5. x小時前 / x小时前 / x hours ago
        match = re.search(r'(\d+)\s*(?:小時前|小时前|hours? ago|hr)', raw_str, re.IGNORECASE)
        if match:
            return now - timedelta(hours=int(match.group(1)))
            
        # 6. x天前 / x days ago
        match = re.search(r'(\d+)\s*(?:天前|days? ago)', raw_str, re.IGNORECASE)
        if match:
            return now - timedelta(days=int(match.group(1)))

        # 7. x週前 / x周前 / x weeks ago / 1 week ago
        match = re.search(r'(\d+)\s*(?:週前|周前|weeks? ago)', raw_str, re.IGNORECASE)
        if match:
            return now - timedelta(weeks=int(match.group(1)))
            
        # 8. x個月前 / x个月前 / x months ago
        match = re.search(r'(\d+)\s*(?:個月前|个月前|months? ago)', raw_str, re.IGNORECASE)
        if match:
            # 概算，以每月 30 天計算
            return now - timedelta(days=int(match.group(1)) * 30)
            
        # 9. x年前 / x years ago
        match = re.search(r'(\d+)\s*(?:年前|years? ago)', raw_str, re.IGNORECASE)
        if match:
            # 概算，以每年 365 天計算
            return now - timedelta(days=int(match.group(1)) * 365)
            
    except Exception as e:
        logger.debug(f"解析 {platform} 時間 [{raw_time}] 失敗: {e}")
        
    return None


def is_within_time_range(post_time: datetime, start_at: datetime | None, end_at: datetime | None) -> bool:
    """
    判斷發文時間是否在起止邊界內。
    """
    if not post_time:
        return False
    if start_at and post_time < start_at:
        return False
    if end_at and post_time > end_at:
        return False
    return True


def should_keep_post(post_time: datetime | None, raw_time: str, args, platform: str) -> bool:
    """
    綜合判斷此貼文是否符合篩選條件，是否應保留存入資料庫。
    """
    # Google Places 店家資訊無發文時間，預設一律保留
    if platform == "google_places":
        return True
        
    if post_time is None:
        # 若解析不到時間，且使用者設定了過濾機制
        has_filter = (
            getattr(args, "date_range", "all") != "all" or 
            getattr(args, "since_days", None) is not None or 
            getattr(args, "start_date", None) is not None or 
            getattr(args, "end_date", None) is not None
        )
        if not has_filter:
            # 若無設定任何時間過濾條件 (即不限制)，一律保留
            return True
            
        # 若有過濾條件，預設不保留，除非指定了 --keep-unknown-time 旗標
        return getattr(args, "keep_unknown_time", False)
        
    # 有解析到時間，進行範圍比對
    start_at, end_at = parse_date_range(args)
    return is_within_time_range(post_time, start_at, end_at)
