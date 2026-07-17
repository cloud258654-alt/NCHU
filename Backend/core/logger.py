import logging
import sys
import os
import contextvars
from datetime import datetime, timezone, timedelta

# Context variable to bind the active service task ID to the thread/coroutine context
current_service_task_id = contextvars.ContextVar("current_service_task_id", default=None)

def tw_timezone_converter(timestamp):
    utc_dt = datetime.fromtimestamp(timestamp, tz=timezone.utc)
    taipei_tz = timezone(timedelta(hours=8))
    taipei_dt = utc_dt.astimezone(taipei_tz)
    return taipei_dt.timetuple()

class SupabaseLogHandler(logging.Handler):
    """
    Custom logging handler to write crawler logs directly into Supabase crawl_logs table
    """
    def emit(self, record):
        if "pytest" in sys.modules or os.getenv("PYTEST_CURRENT_TEST"):
            return
        task_id = current_service_task_id.get()
        if not task_id:
            return
        try:
            from core.supabase import get_connection
            log_msg = self.format(record)
            conn = get_connection()
            try:
                with conn:
                    with conn.cursor() as cur:
                        cur.execute(
                            "INSERT INTO crawl_logs (service_task_id, level, message) VALUES (%s, %s, %s)",
                            (int(task_id), record.levelname, log_msg)
                        )
            finally:
                conn.close()
        except Exception:
            # Silently ignore log insertion failures so crawler run is not impacted
            pass

def get_logger(name: str) -> logging.Logger:
    """
    獲取標準格式的 logger 實例，包含 Supabase 寫入與控制台輸出
    """
    logger = logging.getLogger(name)
    if not logger.handlers:
        logger.setLevel(logging.INFO)
        formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")
        formatter.converter = tw_timezone_converter

        # Always add the database logging handler
        db_handler = SupabaseLogHandler()
        db_handler.setFormatter(formatter)
        logger.addHandler(db_handler)
        
        # Conditionally add the console StreamHandler based on environment config
        log_to_console = os.getenv("BI_RMP_LOG_TO_CONSOLE", "true").strip().lower() != "false"
        if log_to_console:
            handler = logging.StreamHandler(sys.stdout)
            handler.setFormatter(formatter)
            logger.addHandler(handler)
        
    return logger
