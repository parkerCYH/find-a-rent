import asyncio
import logging
import random
import sys
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, BackgroundTasks
from pydantic import BaseModel

from app.config import settings
from app.crawler import fetch_houses
from app.gsheet import get_existing_ids, append_houses
from app.line_notify import push_new_houses

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
    logger.info("🏠 591 監控系統啟動")
    yield
    logger.info("🏠 591 監控系統關閉")


app = FastAPI(
    title="591 租屋監控系統",
    description="自動爬取 591 新房源並推播至 LINE 群組",
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
    message: str


# ── 核心流程 ───────────────────────────────────────────────────────────
def run_crawl_pipeline() -> dict:
    """
    完整去重與推播流程：
    1. 從 Google Sheet 讀取已存在的 post_id set
    2. 執行爬蟲取得房源清單（依 QUERY_1, QUERY_2）
    3. 比對 set，篩選出新房源
    4. 推播至 LINE 並寫入 Google Sheet
    """
    logger.info("▶ 開始執行爬蟲流程")

    existing_ids = get_existing_ids()
    houses = fetch_houses()

    new_houses = [h for h in houses if h.post_id not in existing_ids]
    logger.info(f"爬取 {len(houses)} 筆，其中 {len(new_houses)} 筆為新房源")

    if new_houses:
        push_new_houses(new_houses)
        append_houses(new_houses)
        logger.info(f"✅ 已推播並寫入 {len(new_houses)} 筆新房源")
    else:
        logger.info("ℹ️ 無新房源，本次略過推播")

    return {
        "fetched": len(houses),
        "new": len(new_houses),
    }


# ── 端點 ───────────────────────────────────────────────────────────────
@app.get("/", tags=["Health"])
def health_check():
    """Render 存活偵測端點"""
    return {"status": "ok", "service": "591 租屋監控系統"}


@app.post("/trigger", response_model=TriggerResponse, tags=["Crawler"])
async def trigger_crawl(
    body: TriggerRequest = TriggerRequest(),
    background_tasks: BackgroundTasks = BackgroundTasks(),
):
    """
    觸發爬蟲並執行推播流程。
    接收請求後隨機延遲 0~120 秒，避免被識別為機器人。
    """
    logger.info(f"收到 /trigger 請求: {body.model_dump()}")

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
        message=f"共抓取 {result['fetched']} 筆，推播 {result['new']} 筆新房源",
    )
