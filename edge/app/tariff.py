"""Biểu giá điện theo thời gian sử dụng (TOU), mô phỏng theo khung giờ của EVN cho khách hàng sản xuất."""
from datetime import datetime, timedelta, timezone

from . import config as C


def local_now():
    return datetime.now(timezone(timedelta(hours=C.UTC_OFFSET_H)))


def tariff(now):
    """Trả về (tên khung giờ, đơn giá VND/kWh).

    Thấp điểm 22:00-04:00; cao điểm 09:30-11:30 và 17:00-20:00 (Thứ 2 - Thứ 7); còn lại bình thường.
    """
    m = now.hour * 60 + now.minute
    if m >= 22 * 60 or m < 4 * 60:
        return "offpeak", C.PRICE_OFFPEAK
    if now.weekday() != 6 and (570 <= m < 690 or 1020 <= m < 1200):
        return "peak", C.PRICE_PEAK
    return "normal", C.PRICE_NORMAL
