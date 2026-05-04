import logging
import urllib.parse
from typing import Optional

import gspread
from google.oauth2.service_account import Credentials

from app.models import HouseItem
from app.config import settings

logger = logging.getLogger(__name__)

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

# POST ID 位於第 13 欄（M 欄）
POST_ID_COL = 13

HEADERS = [
    "Type",       # A - 手動填寫
    "LINK",       # B - 超連結（title + url）
    "租金",        # C
    "管理費",      # D - 手動填寫
    "月租金",      # E - 手動填寫（租金 + 管理費）
    "仲介費",      # F - 手動填寫
    "地區",        # G
    "Google Map",  # H
    "坪數",        # I
    "樓層",        # J
    "優點",        # K - 手動填寫
    "缺點",        # L - 手動填寫
    "POST ID",     # M - 唯一值
]

BLACKLIST_HEADERS = [
    "黑名單標題",   # A - 要過濾的關鍵字
]

BLACKLIST_ADDR_HEADERS = [
    "黑名單地址",   # A - 要過濾的地址關鍵字
]


def _hyperlink(url: str, label: str) -> str:
    """產生 Google Sheets HYPERLINK 公式"""
    # 逸出雙引號
    url = url.replace('"', '%22')
    label = label.replace('"', "'")
    return f'=HYPERLINK("{url}","{label}")'


def _maps_link(address: str) -> str:
    if not address:
        return ""
    query = urllib.parse.quote(address)
    url = f"https://www.google.com/maps/search/?api=1&query={query}"
    return _hyperlink(url, "查看地圖")


def _get_worksheet() -> gspread.Worksheet:
    """建立授權並取得目標 Worksheet"""
    creds = Credentials.from_service_account_file(
        settings.GCP_SERVICE_ACCOUNT_FILE,
        scopes=SCOPES,
    )
    gc = gspread.authorize(creds)
    spreadsheet = gc.open_by_key(settings.GOOGLE_SHEET_ID)

    try:
        worksheet = spreadsheet.worksheet(settings.SHEET_NAME)
    except gspread.WorksheetNotFound:
        worksheet = spreadsheet.add_worksheet(
            title=settings.SHEET_NAME, rows="1000", cols="20"
        )
        worksheet.append_row(HEADERS)
        logger.info(f"已建立新工作表: {settings.SHEET_NAME}")

    return worksheet


def get_existing_ids() -> set[str]:
    """
    讀取試算表中所有已記錄的 post_id（M 欄），回傳 set（O(1) 查找）
    """
    ws = _get_worksheet()
    all_values = ws.col_values(POST_ID_COL)  # M 欄 = POST ID

    # 跳過標題列
    ids = {v.strip() for v in all_values[1:] if v.strip()}
    logger.info(f"Google Sheet 現有 {len(ids)} 筆記錄")
    return ids


def _build_row(item: HouseItem) -> list:
    return [
        "",                                                      # A: Type（手動）
        _hyperlink(item.url, item.title),                        # B: LINK
        item.price,                                              # C: 租金
        "",                                                      # D: 管理費（手動）
        "",                                                      # E: 月租金（手動）
        "",                                                      # F: 仲介費（手動）
        item.address or "",                                      # G: 地區
        _maps_link(item.address) if item.address else "",        # H: Google Map
        item.area if item.area is not None else "",              # I: 坪數
        item.floor,                                              # J: 樓層
        "",                                                      # K: 優點（手動）
        "",                                                      # L: 缺點（手動）
        item.post_id,                                            # M: POST ID
    ]


def append_house(item: HouseItem) -> None:
    """將單筆新房源寫入試算表末端"""
    ws = _get_worksheet()
    ws.append_row(_build_row(item), value_input_option="USER_ENTERED")
    logger.debug(f"已寫入: {item.post_id} - {item.title}")


def append_houses(items: list[HouseItem]) -> int:
    """
    批次寫入多筆房源（一次 API 呼叫，效率更高）

    Returns:
        寫入筆數
    """
    if not items:
        return 0

    ws = _get_worksheet()
    rows = [_build_row(item) for item in items]
    ws.append_rows(rows, value_input_option="USER_ENTERED")
    logger.info(f"批次寫入 {len(rows)} 筆房源至 Google Sheet")
    return len(rows)


def get_blacklist_titles() -> set[str]:
    """
    讀取黑名單工作表中的所有標題關鍵字，回傳 set（O(1) 查找）
    如果工作表不存在，會自動創建
    """
    creds = Credentials.from_service_account_file(
        settings.GCP_SERVICE_ACCOUNT_FILE,
        scopes=SCOPES,
    )
    gc = gspread.authorize(creds)
    spreadsheet = gc.open_by_key(settings.GOOGLE_SHEET_ID)

    try:
        worksheet = spreadsheet.worksheet(settings.BLACKLIST_SHEET_NAME)
    except gspread.WorksheetNotFound:
        worksheet = spreadsheet.add_worksheet(
            title=settings.BLACKLIST_SHEET_NAME, rows="100", cols="5"
        )
        worksheet.append_row(BLACKLIST_HEADERS)
        logger.info(f"已建立新黑名單工作表: {settings.BLACKLIST_SHEET_NAME}")

    # 讀取 A 欄所有值
    all_values = worksheet.col_values(1)  # A 欄 = 黑名單標題

    # 跳過標題列，去除前後空白
    keywords = {v.strip() for v in all_values[1:] if v.strip()}
    logger.info(f"黑名單工作表載入 {len(keywords)} 個關鍵字")
    return keywords


def get_blacklist_addrs() -> set[str]:
    """
    讀取黑名單地址工作表中的所有地址關鍵字，回傳 set（O(1) 查找）
    如果工作表不存在，會自動創建
    """
    creds = Credentials.from_service_account_file(
        settings.GCP_SERVICE_ACCOUNT_FILE,
        scopes=SCOPES,
    )
    gc = gspread.authorize(creds)
    spreadsheet = gc.open_by_key(settings.GOOGLE_SHEET_ID)

    try:
        worksheet = spreadsheet.worksheet(settings.BLACKLIST_ADDR_SHEET_NAME)
    except gspread.WorksheetNotFound:
        worksheet = spreadsheet.add_worksheet(
            title=settings.BLACKLIST_ADDR_SHEET_NAME, rows="100", cols="5"
        )
        worksheet.append_row(BLACKLIST_ADDR_HEADERS)
        logger.info(f"已建立新黑名單地址工作表: {settings.BLACKLIST_ADDR_SHEET_NAME}")

    # 讀取 A 欄所有值
    all_values = worksheet.col_values(1)  # A 欄 = 黑名單地址

    # 跳過標題列，去除前後空白
    addrs = {v.strip() for v in all_values[1:] if v.strip()}
    logger.info(f"黑名單地址工作表載入 {len(addrs)} 個關鍵字")
    return addrs
