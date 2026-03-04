from pydantic import BaseModel, field_validator
from typing import Optional
import re

from app.config import settings


class HouseItem(BaseModel):
    post_id: str
    title: str
    price: int                  # 月租金（元）
    price_unit: str = "元/月"
    address: str = ""
    area: Optional[float] = None   # 坪數
    floor: str = ""
    layout: str = ""            # 格局，如 1房1廳
    house_type: str = ""        # 整層住家 / 獨立套房 / 分租套房
    url: str
    image_url: Optional[str] = None
    region_name: str = ""
    section_name: str = ""

    @field_validator("price", mode="before")
    @classmethod
    def parse_price(cls, v) -> int:
        """將各種租金格式轉為整數，例如 '18,000' -> 18000，'面議' -> 0"""
        if isinstance(v, int):
            return v
        if isinstance(v, str):
            cleaned = re.sub(r"[^\d]", "", v)
            return int(cleaned) if cleaned else 0
        return 0

    @field_validator("area", mode="before")
    @classmethod
    def parse_area(cls, v) -> Optional[float]:
        if v is None or v == "":
            return None
        if isinstance(v, (int, float)):
            return float(v)
        try:
            cleaned = re.sub(r"[^\d.]", "", str(v))
            return float(cleaned) if cleaned else None
        except (ValueError, TypeError):
            return None

    @property
    def short_url(self) -> str:
        return f"{settings.BASE_URL}/rent-detail-{self.post_id}.html"
