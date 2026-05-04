import asyncio
import logging
import random
import sys
from contextlib import asynccontextmanager
from datetime import datetime, timezone, timedelta

from fastapi import FastAPI, HTTPException, BackgroundTasks
from pydantic import BaseModel

from app.config import settings
from app.crawler import fetch_houses
from app.gsheet import get_existing_ids, append_houses, get_blacklist_titles, get_blacklist_addrs
from app.discord_webhook import push_new_houses

# ── 日誌設定 ───────────────────────────────────────────────────────────
logging.basicConfig(
    stream=sys.stdout,
    level=getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO),
    format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
)
logger = logging.getLogger(__name__)


# ── FastAPI App ────────────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("🏠 監控系統啟動")
    yield
    logger.info("🏠 監控系統關閉")


app = FastAPI(
    title="租屋監控系統",
    description="自動爬取新房源並推播至 Discord 頻道",
    version="1.0.0",
    lifespan=lifespan,
)


# ── 資料模型 ───────────────────────────────────────────────────────────
class TriggerRequest(BaseModel):
    pass  # 搜尋條件由 .env QUERY_1 / QUERY_2 控制


class TriggerResponse(BaseModel):
    status: str
    fetched: int
    new: int
    blacklisted: int
    pushed: int
    message: str


# ── 核心流程 ───────────────────────────────────────────────────────────
def run_crawl_pipeline() -> dict:
    """
    完整去重與推播流程：
    1. 從 Google Sheet 讀取已存在的 post_id set
    2. 讀取黑名單標題清單
    3. 執行爬蟲取得房源清單（依 QUERY_1, QUERY_2）
    4. 比對 set，篩選出新房源
    5. 過濾黑名單標題
    6. 推播至 Discord 並寫入 Google Sheet
    """
    logger.info("▶ 開始執行爬蟲流程")

    existing_ids = get_existing_ids()
    blacklist_titles = get_blacklist_titles()
    blacklist_addrs = get_blacklist_addrs()
    houses = fetch_houses()

    # Post ID 去重
    new_houses = [h for h in houses if h.post_id not in existing_ids]
    
    # 黑名單過濾（標題 + 地址）
    filtered_houses = [
        h for h in new_houses
        if not any(keyword in h.title for keyword in blacklist_titles)
        and not any(keyword in h.address for keyword in blacklist_addrs)
    ]
    
    blacklisted_count = len(new_houses) - len(filtered_houses)
    
    logger.info(
        f"爬取 {len(houses)} 筆，"
        f"去重後 {len(new_houses)} 筆，"
        f"黑名單過濾 {blacklisted_count} 筆，"
        f"最終推播 {len(filtered_houses)} 筆新房源"
    )

    if filtered_houses:
        push_new_houses(filtered_houses)
        append_houses(filtered_houses)
        logger.info(f"✅ 已推播並寫入 {len(filtered_houses)} 筆新房源")
    else:
        logger.info("ℹ️ 無新房源，本次略過推播")

    return {
        "fetched": len(houses),
        "new": len(new_houses),
        "blacklisted": blacklisted_count,
        "pushed": len(filtered_houses),
    }


# ── 端點 ───────────────────────────────────────────────────────────────
@app.get("/", tags=["Health"])
def health_check():
    """Render 存活偵測端點"""
    return {"status": "ok", "service": "租屋監控系統"}


@app.post("/trigger", response_model=TriggerResponse, tags=["Crawler"])
async def trigger_crawl(
    body: TriggerRequest = TriggerRequest(),
    background_tasks: BackgroundTasks = BackgroundTasks(),
):
    """
    觸發爬蟲並執行推播流程。
    接收請求後隨機延遲 0~120 秒，避免被識別為機器人。
    晚上 21:00 ~ 隔天 10:00（台灣時間）期間不執行。
    """
    logger.info(f"收到 /trigger 請求: {body.model_dump()}")

    # ── 靜音時段檢查（台灣時間 21:00 ~ 10:00）────────────────────────
    tw_now = datetime.now(timezone(timedelta(hours=8)))
    hour = tw_now.hour
    if hour >= 21 or hour < 10:
        msg = f"Quiet hours ({tw_now.strftime('%H:%M')} CST) — skipping crawl. No point calling landlords now."
        logger.info(msg)
        return TriggerResponse(
            status="skipped",
            fetched=0,
            new=0,
            blacklisted=0,
            pushed=0,
            message=msg
        )

    delay = random.uniform(0, 120)
    logger.info(f"隨機延遲 {delay:.1f} 秒後開始執行...")
    await asyncio.sleep(delay)

    try:
        result = run_crawl_pipeline()
    except Exception as e:
        logger.exception("爬蟲流程發生錯誤")
        raise HTTPException(status_code=500, detail=str(e))

    return TriggerResponse(
        status="ok",
        fetched=result["fetched"],
        new=result["new"],
        blacklisted=result["blacklisted"],
        pushed=result["pushed"],
        message=(
            f"共抓取 {result['fetched']} 筆，"
            f"去重後 {result['new']} 筆，"
            f"黑名單過濾 {result['blacklisted']} 筆，"
            f"推播 {result['pushed']} 筆新房源"
        ),
    )
