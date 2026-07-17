# Task: PTT Crawler Stability Upgrade

## 1. Task goal

Improve the existing PTT crawler stability while keeping BI-RMP's current database and documentation contract intact.

This task modifies **PTT only**.

Do not modify Google Maps, Threads, runner, or database schema.

---

## 2. Read before editing

Before changing code, read these files and follow them as the source of truth:

```text
README.md
docs/schema_spec.md
docs/dev-spec/database-design.md
database/schema.sql
Backend/core/crawled_post_models.py
Backend/core/supabase.py
Backend/adapters/ptt/crawler.py
Backend/adapters/ptt/config.py
Backend/adapters/ptt/local_buffer.py
Backend/adapters/ptt/snapshot.py
```

Confirm that the official runtime flow is:

```text
clients
-> business
-> service_tasks
-> crawl_jobs
-> crawl_posts
-> crawl_comments
-> post_metric_snapshots / comment_metric_snapshots
-> analysis_results
-> alerts
```

`database/schema.sql` is the authoritative active runtime SQL.

---

## 3. Hard restrictions

Do not do these:

```text
Do not add SerpApi
Do not add Selenium
Do not add LLM calls
Do not change PTT to Playwright
Do not modify Backend/runner.py
Do not modify Backend/adapters/google_maps/*
Do not modify Backend/adapters/threads/*
Do not modify Backend/core/supabase.py
Do not modify Backend/core/task_repositories.py
Do not modify database/schema.sql
Do not add ptt_posts or ptt_comments as official tables
Do not restore old tables: search_results, comments, post_metrics, comment_metrics
Do not treat local buffer as the official data source
```

---

## 4. Allowed files

You may modify or add only these files unless a test requires a very small adjustment elsewhere:

```text
requirements.txt
Backend/adapters/ptt/crawler.py
Backend/adapters/ptt/config.py
Backend/adapters/ptt/parser.py
Backend/adapters/ptt/local_buffer.py
Backend/adapters/ptt/snapshot.py
Backend/tests/test_ptt_parser.py
Backend/tests/test_ptt_local_buffer.py
Backend/tests/test_ptt_snapshot.py
```

---

## 5. Required crawler strategy

PTT must remain HTTP-first:

```text
HTTP request
+ Cookie(over18=1)
+ retry
+ BeautifulSoup / lxml parser
+ fallback boards
+ query variants
+ relevance scoring
+ local JSONL buffer as backup
+ db.save_ptt_posts(posts)
```

Official data must still be written through:

```python
db.save_ptt_posts(posts)
```

This must feed the existing schema flow:

```text
crawl_posts
crawl_comments
post_metric_snapshots
comment_metric_snapshots
```

---

## 6. Step-by-step implementation

### Step 1: Update requirements.txt

Add:

```text
beautifulsoup4>=4.12.0
lxml>=5.0.0
```

Do not add `selectolax` as a required dependency.

---

### Step 2: Add PTT parser module

Create:

```text
Backend/adapters/ptt/parser.py
```

Implement:

```python
from bs4 import BeautifulSoup


def parse_ptt_index_html(html: str) -> list[dict]:
    """
    Parse PTT board index or board search HTML.

    Return:
    [
        {
            "title": str,
            "author_name": str,
            "post_time_raw": str,
            "post_url": str,
        }
    ]
    """
    soup = BeautifulSoup(html, "lxml")
    items = []

    for row in soup.select("div.r-ent"):
        title_node = row.select_one("div.title a")
        author_node = row.select_one("div.author")
        date_node = row.select_one("div.date")

        if not title_node:
            continue

        href = title_node.get("href")
        if not href:
            continue

        post_url = f"https://www.ptt.cc{href}" if href.startswith("/") else href

        items.append({
            "title": title_node.get_text(strip=True),
            "author_name": author_node.get_text(strip=True) if author_node else "",
            "post_time_raw": date_node.get_text(strip=True) if date_node else "",
            "post_url": post_url,
        })

    return items
```

No database writes inside the parser.

---

### Step 3: Replace handwritten index parser usage

In:

```text
Backend/adapters/ptt/crawler.py
```

Update these functions to use `parse_ptt_index_html()`:

```text
_discover_board_search_urls()
_discover_board_index_urls_multi_variants()
```

Keep the following existing behavior:

```text
over18=1 Cookie
retry
fallback boards
query variants
index scan fallback
relevance scoring
cache
quarantine
HTML snapshot on abnormal parse
local buffer
diagnostics
```

You may remove `PTTSearchParser`, or keep it only as deprecated fallback.

---

### Step 4: Preserve over18 Cookie

Every PTT HTTP fetch must keep:

```python
headers={"Cookie": "over18=1"}
```

Applicable to:

```text
board index
board search
article page
```

---

### Step 5: Local buffer behavior

Local buffer is backup only, not official data.

Ensure:

```text
If posts exist, write local buffer before DB write.
Buffer content must preserve the current PTT post payload.
If buffer write fails, record diagnostics error.
If DB write fails, do not lose already crawled posts.
Return buffer_path in the adapter result.
```

JSONL line format:

```json
{
  "platform": "ptt",
  "query": "...",
  "crawl_job_id": "...",
  "service_task_id": "...",
  "buffered_at": "...",
  "payload": {}
}
```

Keep buffer logic centralized in:

```text
Backend/adapters/ptt/local_buffer.py
```

---

### Step 6: Snapshot behavior

HTML snapshot is debug only, not official data.

Ensure:

```text
Abnormal parse can save HTML.
Service mode can also save snapshot.
Filename must be sanitized.
Snapshot must not replace DB writes.
```

Keep snapshot logic centralized in:

```text
Backend/adapters/ptt/snapshot.py
```

---

### Step 7: Diagnostics

Extend PTT diagnostics with:

```python
"error": {
    "type": None,
    "message": None,
    "recoverable": None,
}
```

Supported error types:

```text
timeout
connection_reset
http_403
http_404
http_429
fetch_failed
parse_failed
empty_result
buffer_write_failed
db_write_failed
unknown
```

---

### Step 8: Adapter return shape

Make PTT `main()` return:

```python
{
    "platform": "ptt",
    "status": "success" | "failed" | "partial_success",
    "inserted": saved_count,
    "cards_found": len(posts),
    "elapsed": elapsed_time,
    "error_type": None | "...",
    "error_message": None | "...",
    "buffer_path": str(buffer_path) if buffer_path else None,
    "diagnostics": diagnostics,
}
```

Status rules:

```text
posts exist + buffer success + DB success:
  status = success

posts exist + buffer success + DB failure:
  status = partial_success
  error_type = db_write_failed

posts exist + buffer failure:
  status = failed
  error_type = buffer_write_failed

posts empty:
  classify as empty_result / fetch_failed / parse_failed using diagnostics
```

---

## 7. Tests to add

Add or update:

```text
Backend/tests/test_ptt_parser.py
Backend/tests/test_ptt_local_buffer.py
Backend/tests/test_ptt_snapshot.py
```

Minimum tests:

```text
1. parse_ptt_index_html parses a normal PTT index row.
2. parse_ptt_index_html skips deleted rows with no title link.
3. local buffer writes valid JSONL.
4. local buffer preserves Traditional Chinese payload content.
5. snapshot saves HTML.
6. snapshot sanitizes unsafe filename characters.
7. crawler.py compiles.
```

Parser test sample:

```html
<div class="r-ent">
  <div class="title">
    <a href="/bbs/Food/M.1234567890.A.html">[食記] 台南 牛肉湯</a>
  </div>
  <div class="meta">
    <div class="author">cloud</div>
    <div class="date">7/08</div>
  </div>
</div>
```

Expected:

```python
[
    {
        "title": "[食記] 台南 牛肉湯",
        "author_name": "cloud",
        "post_time_raw": "7/08",
        "post_url": "https://www.ptt.cc/bbs/Food/M.1234567890.A.html",
    }
]
```

Deleted row sample:

```html
<div class="r-ent">
  <div class="title">
    (本文已被刪除) [cloud]
  </div>
  <div class="meta">
    <div class="author">-</div>
    <div class="date">7/08</div>
  </div>
</div>
```

Expected:

```python
[]
```

---

## 8. Verification commands

Run these after modification:

```powershell
python -m compileall -q Backend
python -m pytest -q
python Backend/runner.py --business-name "文章牛肉湯" --keyword "服務態度" --max-results 3 --dry-run
```

If the final dry-run fails because the local environment lacks required env vars or external network, report that clearly. Do not fake success.

---

## 9. Final self-report format

After finishing, report exactly this checklist:

```text
1. README.md read:
2. docs/schema_spec.md read:
3. docs/dev-spec/database-design.md read:
4. database/schema.sql confirmed authoritative:
5. Added beautifulsoup4 / lxml:
6. Added Backend/adapters/ptt/parser.py:
7. PTT index/search discovery uses parse_ptt_index_html:
8. Official DB write still uses db.save_ptt_posts(posts):
9. No platform-specific official tables added:
10. local buffer remains backup only:
11. snapshot remains debug only:
12. diagnostics includes error.type / message / recoverable:
13. PTT over18 Cookie preserved:
14. fallback boards / query variants / retry preserved:
15. compileall result:
16. pytest result:
17. dry-run result:
18. modified files:
19. risks and follow-up suggestions:
```

---

## 10. Suggested commit message

```text
feat(ptt): improve HTTP-first crawler stability
```
