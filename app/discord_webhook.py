import logging

import httpx

from app.models import HouseItem
from app.config import settings

logger = logging.getLogger(__name__)


def _build_house_embed(item: HouseItem) -> dict:
    """建立單一房源的 Discord Embed"""
    price_text = f"${item.price:,} {item.price_unit}" if item.price > 0 else "面議"
    
    fields = [
        {"name": "💰 租金", "value": price_text, "inline": True},
        {"name": "📐 坪數", "value": f"{item.area} 坪" if item.area else "-", "inline": True},
        {"name": "🏠 類型", "value": item.house_type or "-", "inline": True},
        {"name": "🪟 格局", "value": item.layout or "-", "inline": True},
        {"name": "🧱 樓層", "value": item.floor or "-", "inline": True},
        {"name": "📍 地址", "value": item.address or f"{item.region_name}{item.section_name}", "inline": False},
    ]
    
    embed = {
        "title": item.title,
        "url": item.url,
        "color": 2599602,  # #27ACB2
        "fields": fields,
        "footer": {
            "text": f"{item.region_name}{item.section_name}"
        }
    }
    
    # 若有圖片則加入
    if item.image_url:
        embed["thumbnail"] = {"url": item.image_url}
    
    return embed


def push_new_houses(items: list[HouseItem]) -> None:
    """
    將新房源推播至 Discord 頻道。
    每次推播最多 10 個 embeds。
    """
    if not items:
        logger.info("沒有新房源，不推播")
        return
    
    if not settings.DISCORD_WEBHOOK_URL:
        logger.warning("未設定 DISCORD_WEBHOOK_URL，跳過推播")
        return

    # Discord webhook 每次最多 10 個 embeds
    batch_size = 10
    total_batches = (len(items) + batch_size - 1) // batch_size

    with httpx.Client(timeout=15) as client:
        # 先送一則文字摘要
        _send_webhook(
            client,
            content=f"🔔 本次發現 {len(items)} 間新房源，馬上推播給你！",
        )

        for i in range(total_batches):
            batch = items[i * batch_size : (i + 1) * batch_size]
            embeds = [_build_house_embed(item) for item in batch]
            _send_webhook(client, embeds=embeds)
            logger.info(f"已推播第 {i + 1}/{total_batches} 批（{len(batch)} 筆）")


def _send_webhook(
    client: httpx.Client,
    content: str = None,
    embeds: list[dict] = None,
) -> None:
    """發送 Discord webhook 訊息"""
    payload = {}
    if content:
        payload["content"] = content
    if embeds:
        payload["embeds"] = embeds

    resp = client.post(settings.DISCORD_WEBHOOK_URL, json=payload)
    if resp.status_code not in (200, 204):
        logger.error(
            f"Discord webhook 失敗: {resp.status_code} - {resp.text[:200]}"
        )
    else:
        logger.debug("Discord webhook 成功")
