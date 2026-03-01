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

BASE_URL = "https://rent.591.com.tw"

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


def _build_list_url(
    region: int,
    section: Optional[str] = None,
    price_min: Optional[int] = None,
    price_max: Optional[int] = None,
    layout: Optional[str] = None,
    other: Optional[str] = None,
    shape: Optional[str] = None,
    bathroom: Optional[str] = None,
    notice: Optional[str] = None,
) -> str:
    # 加入時間戳與隨機數作為對筒 cache-bust參數
    ts = int(time.time())
    noise = random.randint(100000, 999999)
    params = [
        f"region={region}",
        "order=posttime",
        "orderType=desc",
        f"t={ts}",
        f"_={noise}",
    ]
    if section:
        params.append(f"section={section}")
    # 租金：591 格式為 price=min_max
    if price_min and price_min > 0 and price_max and price_max > 0:
        params.append(f"price={price_min}_{price_max}")
    elif price_min and price_min > 0:
        params.append(f"price={price_min}_")
    elif price_max and price_max > 0:
        params.append(f"price=0_{price_max}")
    if layout:
        params.append(f"layout={layout}")
    if other:
        params.append(f"other={other}")
    if shape:
        params.append(f"shape={shape}")
    if bathroom:
        params.append(f"bathroom={bathroom}")
    if notice:
        params.append(f"notice={notice}")
    return f"{BASE_URL}/list?" + "&".join(params)


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
        url = row.get("url") or f"{BASE_URL}/{post_id}"

        # 確保是完整 URL
        if url.startswith("/"):
            url = BASE_URL + url

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


def fetch_houses(
    region: Optional[int] = None,
    section: Optional[str] = None,
    price_min: Optional[int] = None,
    price_max: Optional[int] = None,
    max_pages: int = 5,  # 保留參數相容性，目前 SSR 方案固定 1 頁
) -> list[HouseItem]:
 
    region = region or settings.REGION
    list_url = _build_list_url(
        region=region,
        section=section or (settings.SECTION if settings.SECTION else None),
        price_min=price_min if price_min is not None else (settings.PRICE_MIN or None),
        price_max=price_max if price_max is not None else (settings.PRICE_MAX or None),
        layout=settings.LAYOUT or None,
        other=settings.OTHER or None,
        shape=settings.SHAPE or None,
        bathroom=settings.BATHROOM or None,
        notice=settings.NOTICE or None,
    )
    ua = random.choice(UA_POOL)
    accept_lang = random.choice(_ACCEPT_LANGUAGES)
    headers = {
        "User-Agent": ua,
        "Accept-Language": accept_lang,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
        "Cache-Control": "no-cache",
        "Pragma": "no-cache",
    }
    logger.info(f"抓取 591 列表頁 (UA: {ua[:40]}...): {list_url}")

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

    logger.info(f"爬蟲完成，成功解析 {len(houses)} 筆房源")
    return houses
