"""Price/area converters ported from scrapper ``src/utils/helpers.py``."""

from __future__ import annotations

from datetime import datetime
from typing import Any


class PriceConverter:
    """만원 단위 정수 변환. ``1.5억`` 같은 소수 억 단위를 정확히 처리한다."""

    @staticmethod
    def to_int(value: Any) -> int:
        if value is None:
            return 0
        raw = str(value).replace(",", "").replace(" ", "").strip()
        if not raw:
            return 0
        total = 0
        if "억" in raw:
            head, _, tail = raw.partition("억")
            head = head.strip()
            if head:
                try:
                    total += int(float(head) * 10000)
                except (TypeError, ValueError):
                    pass
            tail = tail.replace("만", "").strip()
            if tail:
                try:
                    total += int(float(tail))
                except (TypeError, ValueError):
                    pass
            return total
        if "만" in raw:
            try:
                return int(float(raw.replace("만", "").strip()))
            except (TypeError, ValueError):
                return 0
        try:
            return int(float(raw))
        except (TypeError, ValueError):
            return 0

    @staticmethod
    def to_string(value: Any) -> str:
        try:
            amount = int(float(str(value).replace(",", "").strip())) if isinstance(value, str) and ("억" in value or "만" in value) else int(value)
        except (TypeError, ValueError):
            return "0"
        if amount >= 10000:
            eok, man = divmod(amount, 10000)
            return f"{eok}억 {man:,}만" if man else f"{eok}억"
        if amount > 0:
            return f"{amount:,}만"
        return "0"

    @staticmethod
    def to_signed_string(price_int: int, zero_text: str = "") -> str:
        try:
            value = int(price_int)
        except (TypeError, ValueError):
            value = 0
        if value > 0:
            return f"+{PriceConverter.to_string(value)}"
        if value < 0:
            return f"-{PriceConverter.to_string(abs(value))}"
        return zero_text

    @staticmethod
    def representative_price_int(item: Any, trade_type: str | None = None) -> int:
        if not isinstance(item, dict):
            return 0
        trade = str(trade_type or item.get("거래유형", item.get("trade_type", "")) or "").strip()
        if trade == "매매":
            return PriceConverter.to_int(item.get("매매가", item.get("price", "")))
        if trade == "월세":
            rent_value = PriceConverter.to_int(item.get("월세", item.get("monthly", item.get("rent", ""))))
            if rent_value > 0:
                return rent_value
        return PriceConverter.to_int(item.get("보증금", item.get("deposit", "")))


class AreaConverter:
    PYEONG_RATIO = 0.3025

    @classmethod
    def sqm_to_pyeong(cls, sqm: Any) -> float:
        try:
            return round(float(sqm) * cls.PYEONG_RATIO, 1)
        except (TypeError, ValueError):
            return 0.0

    @classmethod
    def pyeong_to_sqm(cls, pyeong: Any) -> float:
        try:
            return round(float(pyeong) / cls.PYEONG_RATIO, 2)
        except (TypeError, ValueError):
            return 0.0


class DateTimeHelper:
    # Upstream uses naive local time in payloads; keep the format stable.
    @staticmethod
    def now_string(fmt: str = "%Y-%m-%d %H:%M:%S") -> str:
        return datetime.now().strftime(fmt)  # noqa: DTZ005

    @staticmethod
    def file_timestamp() -> str:
        return datetime.now().strftime("%Y%m%d_%H%M%S")  # noqa: DTZ005


class PricePerPyeongCalculator:
    @staticmethod
    def calculate(price_int: int, pyeong: float) -> int:
        try:
            price = int(price_int)
            area = float(pyeong)
        except (TypeError, ValueError):
            return 0
        if area <= 0 or price <= 0:
            return 0
        return int(price / area)

    @staticmethod
    def format(price_per_pyeong: int) -> str:
        try:
            value = int(price_per_pyeong)
        except (TypeError, ValueError):
            value = 0
        if value <= 0:
            return "-"
        return PriceConverter.to_string(value) + "/평"


def sale_price_text_to_won(price_text: str) -> int:
    return max(0, int(PriceConverter.to_int(price_text or "") or 0)) * 10_000


def enrich_gap_fields(item: dict[str, Any]) -> dict[str, Any]:
    """매매+기전세금이 있을 때만 갭을 계산하고, 나머지는 0으로 채운다."""
    if not isinstance(item, dict):
        return {}
    trade_type = str(item.get("거래유형", "") or "")
    try:
        prev_jeonse_won = int(item.get("기전세금(원)", 0) or 0)
    except (TypeError, ValueError):
        prev_jeonse_won = 0
    if trade_type != "매매" or prev_jeonse_won <= 0:
        item.setdefault("갭금액(원)", 0)
        item.setdefault("갭비율", 0.0)
        return item
    sale_won = sale_price_text_to_won(str(item.get("매매가", "") or ""))
    if sale_won <= 0:
        item["갭금액(원)"] = 0
        item["갭비율"] = 0.0
        return item
    gap_amount = sale_won - prev_jeonse_won
    item["갭금액(원)"] = int(gap_amount)
    item["갭비율"] = float(gap_amount) / float(sale_won) if sale_won else 0.0
    return item
