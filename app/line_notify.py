import logging
from typing import Optional

import httpx

from app.models import HouseItem
from app.config import settings

logger = logging.getLogger(__name__)

LINE_API_BASE = "https://api.line.me/v2/bot"
PUSH_API = f"{LINE_API_BASE}/message/push"


def _build_house_bubble(item: HouseItem) -> dict:
    """建立單一房源的 Flex Message Bubble"""
    price_text = f"${item.price:,} {item.price_unit}" if item.price > 0 else "面議"

    body_contents = [
        {
            "type": "text",
            "text": item.title,
            "weight": "bold",
            "size": "md",
            "wrap": True,
            "maxLines": 2,
        },
        {
            "type": "box",
            "layout": "vertical",
            "margin": "md",
            "spacing": "sm",
            "contents": [
                _info_row("💰 租金", price_text),
                _info_row("📍 地址", item.address or f"{item.region_name}{item.section_name}"),
                _info_row("📐 坪數", f"{item.area} 坪" if item.area else "-"),
                _info_row("🏠 類型", item.house_type or "-"),
                _info_row("🪟 格局", item.layout or "-"),
                _info_row("🧱 樓層", item.floor or "-"),
            ],
        },
    ]

    bubble = {
        "type": "bubble",
        "size": "kilo",
        "header": {
            "type": "box",
            "layout": "vertical",
            "contents": [
                {
                    "type": "text",
                    "text": f"{item.region_name}{item.section_name}",
                    "color": "#ffffff",
                    "size": "sm",
                }
            ],
            "backgroundColor": "#27ACB2",
            "paddingBottom": "md",
        },
        "body": {
            "type": "box",
            "layout": "vertical",
            "contents": body_contents,
        },
        "footer": {
            "type": "box",
            "layout": "vertical",
            "contents": [
                {
                    "type": "button",
                    "style": "primary",
                    "color": "#27ACB2",
                    "action": {
                        "type": "uri",
                        "label": "查看詳情",
                        "uri": item.url,
                    },
                }
            ],
        },
    }

    # 若有圖片則加入 hero
    if item.image_url:
        bubble["hero"] = {
            "type": "image",
            "url": item.image_url,
            "size": "full",
            "aspectRatio": "20:13",
            "aspectMode": "cover",
        }

    return bubble


def _info_row(label: str, value: str) -> dict:
    return {
        "type": "box",
        "layout": "baseline",
        "spacing": "sm",
        "contents": [
            {
                "type": "text",
                "text": label,
                "color": "#aaaaaa",
                "size": "sm",
                "flex": 3,
            },
            {
                "type": "text",
                "text": value or "-",
                "wrap": True,
                "color": "#666666",
                "size": "sm",
                "flex": 5,
            },
        ],
    }


def _build_carousel(items: list[HouseItem]) -> dict:
    """將多個 Bubble 組合成 Carousel Flex Message（最多 12 個）"""
    bubbles = [_build_house_bubble(item) for item in items[:12]]
    return {
        "type": "flex",
        "altText": f"🏠 發現 {len(bubbles)} 間新房源！",
        "contents": {
            "type": "carousel",
            "contents": bubbles,
        },
    }


def _build_summary_text(count: int) -> dict:
    return {
        "type": "text",
        "text": f"🔔 發現 {count} 間新房源！以下依序推播。",
    }


def push_new_houses(items: list[HouseItem]) -> None:
    """
    將新房源推播至 LINE 群組。
    每次推播最多 5 則訊息，每則 Carousel 最多 12 個 Bubble。
    """
    if not items:
        logger.info("沒有新房源，不推播")
        return

    headers = {
        "Authorization": f"Bearer {settings.LINE_CHANNEL_ACCESS_TOKEN}",
        "Content-Type": "application/json",
    }

    # 每批最多 12 筆
    batch_size = 12
    total_batches = (len(items) + batch_size - 1) // batch_size

    with httpx.Client(timeout=15) as client:
        # 先送一則文字摘要
        _push_raw(
            client,
            headers,
            messages=[
                {
                    "type": "text",
                    "text": f"🔔 本次發現 {len(items)} 間新房源，馬上推播給你！",
                }
            ],
        )

        for i in range(total_batches):
            batch = items[i * batch_size : (i + 1) * batch_size]
            carousel = _build_carousel(batch)
            _push_raw(client, headers, messages=[carousel])
            logger.info(f"已推播第 {i + 1}/{total_batches} 批（{len(batch)} 筆）")


def _push_raw(
    client: httpx.Client,
    headers: dict,
    messages: list[dict],
    to: Optional[str] = None,
) -> None:
    target = to or settings.LINE_GROUP_ID
    payload = {"to": target, "messages": messages[:5]}

    resp = client.post(PUSH_API, json=payload, headers=headers)
    if resp.status_code != 200:
        logger.error(
            f"LINE push 失敗: {resp.status_code} - {resp.text[:200]}"
        )
    else:
        logger.debug("LINE push 成功")
