import json
import logging
import random
import subprocess
import tempfile
import os
import time
from typing import Optional

import httpx

from app.models import HouseItem
from app.config import settings

logger = logging.getLogger(__name__)

# 多組 User-Agent，每次隨機擇一
UA_POOL = [
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 13_4) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.4 Safari/605.1.15",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:124.0) Gecko/20100101 Firefox/124.0",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
]

_ACCEPT_LANGUAGES = [
    "zh-TW,zh;q=0.9,en-US;q=0.8,en;q=0.7",
    "zh-TW,zh;q=0.8,en;q=0.6",
    "en-US,en;q=0.9,zh-TW;q=0.8,zh;q=0.7",
    "zh-TW,zh;q=0.9",
]


def _build_url_from_query(raw_query: str) -> str:
    """將 .env 中預組好的 query string 加上 cache-bust 參數後組成完整 URL"""
    ts = int(time.time())
    noise = random.randint(100000, 999999)
    return f"{settings.BASE_URL}/list?{raw_query}&t={ts}&_={noise}"


def _extract_nuxt_expr(html: str) -> str:
    marker = "<script>window.__NUXT__="
    idx = html.find(marker)
    if idx == -1:
        raise ValueError("window.__NUXT__ not found in page HTML")
    idx_expr = idx + len(marker)
    idx_end = html.find("</script>", idx_expr)
    if idx_end == -1:
        raise ValueError("Could not find </script> after __NUXT__")
    return html[idx_expr:idx_end]


def _eval_nuxt_to_json(nuxt_expr: str) -> dict:

    js_code = f"""
const d = {nuxt_expr};
const rl = d.pinia && d.pinia["rent-list"];
if (!rl) {{ console.log(JSON.stringify({{error: "rent-list store not found"}})); process.exit(0); }}
const out = {{
  total: rl.total,
  dataList: rl.dataList || [],
  topDataList: rl.topDataList || [],
}};
console.log(JSON.stringify(out));
"""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".js", delete=False, encoding="utf-8") as f:
        f.write(js_code)
        tmp_path = f.name
    try:
        result = subprocess.run(
            ["node", tmp_path],
            capture_output=True,
            text=True,
            timeout=20,
        )
        if result.returncode != 0:
            raise RuntimeError(f"Node.js error: {result.stderr[:200]}")
        return json.loads(result.stdout.strip())
    finally:
        os.unlink(tmp_path)


def _parse_item(row: dict) -> Optional[HouseItem]:
    """將 pinia dataList 的單筆資料轉為 HouseItem"""
    try:
        post_id = str(row.get("id", ""))
        if not post_id:
            return None

        price_val = row.get("price", 0)
        url = row.get("url") or f"{settings.BASE_URL}/{post_id}"

        # 確保是完整 URL
        if url.startswith("/"):
            url = settings.BASE_URL + url

        photo_list = row.get("photoList", [])
        image_url = photo_list[0] if photo_list else None

        return HouseItem(
            post_id=post_id,
            title=row.get("title", "").strip(),
            price=price_val,
            price_unit=row.get("price_unit", "元/月"),
            address=row.get("address", "").strip(),
            area=row.get("area"),
            floor=row.get("floor_name", ""),
            layout=row.get("layoutStr", row.get("room", "")),
            house_type=row.get("kind_name", ""),
            url=url,
            image_url=image_url,
            region_name=str(row.get("regionid", "")),
            section_name=str(row.get("sectionid", "")),
        )
    except Exception as e:
        logger.warning(f"解析房源失敗 (id={row.get('id', '?')}): {e}")
        return None


def _fetch_single_query(raw_query: str) -> list[HouseItem]:
    """針對單一 query string 抓取並解析房源清單"""
    list_url = _build_url_from_query(raw_query)
    ua = random.choice(UA_POOL)
    accept_lang = random.choice(_ACCEPT_LANGUAGES)
    headers = {
        "User-Agent": ua,
        "Accept-Language": accept_lang,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
        "Cache-Control": "no-cache",
        "Pragma": "no-cache",
    }
    logger.info(f"抓取列表頁 (UA: {ua[:40]}...): {list_url}")

    try:
        with httpx.Client(timeout=20, follow_redirects=True) as client:
            resp = client.get(list_url, headers=headers)
            resp.raise_for_status()
            html = resp.text
    except Exception as e:
        logger.error(f"無法取得列表頁: {e}")
        return []

    logger.info(f"頁面大小: {len(html):,} 字元")

    try:
        nuxt_expr = _extract_nuxt_expr(html)
    except ValueError as e:
        logger.error(f"無法提取 __NUXT__ 資料: {e}")
        return []

    try:
        data = _eval_nuxt_to_json(nuxt_expr)
    except Exception as e:
        logger.error(f"Node.js 解析失敗: {e}")
        return []

    if "error" in data:
        logger.error(f"__NUXT__ 結構錯誤: {data['error']}")
        return []

    total = data.get("total", 0)
    data_list = data.get("dataList", [])
    logger.info(f"總房源數: {total}，本頁取得: {len(data_list)} 筆")

    houses = []
    for row in data_list:
        item = _parse_item(row)
        if item:
            houses.append(item)
    return houses


def fetch_houses() -> list[HouseItem]:
    """依序執行所有非空的 QUERY_N，合併結果並以 post_id 去重"""
    queries = [q.strip() for q in [settings.QUERY_1, settings.QUERY_2] if q.strip()]
    if not queries:
        logger.warning("未設定任何搜尋條件 (QUERY_1, QUERY_2 皆為空)，略過爬蟲")
        return []

    seen: dict[str, HouseItem] = {}
    for idx, raw_query in enumerate(queries, start=1):
        logger.info(f"▶ 執行第 {idx} 組查詢: {raw_query}")
        for item in _fetch_single_query(raw_query):
            if item.post_id not in seen:
                seen[item.post_id] = item

    logger.info(f"爬蟲完成，共 {len(queries)} 組查詢，合計 {len(seen)} 筆不重複房源")
    return list(seen.values())
