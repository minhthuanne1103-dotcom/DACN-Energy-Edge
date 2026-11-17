"""Quản lý nhu cầu công suất đỉnh (peak demand shaving).

Khi tổng công suất vượt ngưỡng liên tục, cắt lần lượt các tải không trọng yếu theo thứ tự shed_order.
Khi công suất hạ xuống đủ thấp, đóng lại theo thứ tự ngược (hysteresis để tránh đóng/cắt liên tục).
"""


class DemandManager:
    def __init__(self, shed_order, over_n=3, restore_n=15, cooldown=5.0, restore_margin=0.85):
        # shed_order: {tên tải: thứ tự cắt}; chỉ gồm các tải được phép cắt
        self.order = shed_order
        self.over_n, self.restore_n = over_n, restore_n
        self.cooldown, self.restore_margin = cooldown, restore_margin
        self.shed = []          # ngăn xếp tải đang bị cắt
        self.est = {}           # công suất ước tính (kW) của tải trước khi bị cắt
        self._over = self._under = 0
        self._last = float("-inf")

    def release(self, name):
        if name in self.shed:
            self.shed.remove(name)
            self.est.pop(name, None)

    def update(self, now, total_kw, limit_kw, loads):
        """loads: {tên: (đang đóng, công suất kW)}. Trả về danh sách [("shed"|"restore", tên)]."""
        can_restore = bool(self.shed) and (
            total_kw + self.est.get(self.shed[-1], 0.0) <= self.restore_margin * limit_kw)
        self._over = self._over + 1 if total_kw > limit_kw else 0
        self._under = self._under + 1 if can_restore else 0
        if now - self._last < self.cooldown:
            return []
        if self._over >= self.over_n:
            cands = sorted((n for n, (closed, _) in loads.items()
                            if n in self.order and closed and n not in self.shed),
                           key=lambda n: self.order[n])
            if cands:
                n = cands[0]
                self.shed.append(n)
                self.est[n] = loads[n][1]
                self._last, self._over = now, 0
                return [("shed", n)]
        elif self._under >= self.restore_n:
            n = self.shed.pop()
            self.est.pop(n, None)
            self._last, self._under = now, 0
            return [("restore", n)]
        return []
