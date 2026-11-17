"""AI phát hiện bất thường chạy cục bộ tại biên (không cần Internet / đám mây).

Hai mô hình học từ dữ liệu vận hành BÌNH THƯỜNG của từng tải (học không giám sát):
  1. Isolation Forest : phát hiện điểm dữ liệu "dễ bị cô lập" -> bất thường.
  2. Autoencoder nhỏ (MLP 8-6-3-6-8): nén rồi tái tạo; sai số tái tạo lớn -> bất thường.
Đặc trưng: 7 đại lượng đo + độ gợn dòng điện (độ lệch chuẩn tương đối trong cửa sổ W mẫu).
"""
import logging
import os
import random
import warnings

import joblib
import numpy as np
from numpy.lib.stride_tricks import sliding_window_view
from sklearn.ensemble import IsolationForest
from sklearn.exceptions import ConvergenceWarning
from sklearn.neural_network import MLPRegressor
from sklearn.preprocessing import StandardScaler

from .loadmodel import FEATURES, LoadState

log = logging.getLogger("ai")
W = 10                      # kích thước cửa sổ trượt (mẫu)
MODEL_VERSION = 1


def batch_features(x):
    """x: mảng (n, 7) -> (n-W+1, 8). Với đúng W mẫu trả về 1 dòng (dùng khi suy luận thời gian thực)."""
    x = np.asarray(x, dtype=float)
    if len(x) < W:
        return np.empty((0, len(FEATURES) + 1))
    cur = sliding_window_view(x[:, 1], W)
    ripple = cur.std(axis=1) / (cur.mean(axis=1) + 1e-6)
    return np.column_stack([x[W - 1:], ripple])


def generate_normal(load, n=6000, seed=0):
    """Sinh dữ liệu vận hành bình thường (nhiều giờ trong ngày) từ mô hình vật lý của tải."""
    st, rng = LoadState(load, seed), random.Random(seed + 1)
    hour, rows = rng.uniform(0, 24), []
    for k in range(n):
        if k % 300 == 0:
            hour = rng.uniform(0, 24)
        m = st.step(1.0, hour)
        rows.append([m[f] for f in FEATURES])
    return np.array(rows)


class Detector:
    def __init__(self, scaler, iforest, ae, thr):
        self.scaler, self.iforest, self.ae, self.thr = scaler, iforest, ae, thr

    @classmethod
    def train(cls, load, n=6000, seed=0):
        feats = batch_features(generate_normal(load, n, seed))
        scaler = StandardScaler().fit(feats)
        z = scaler.transform(feats)
        iforest = IsolationForest(n_estimators=150, contamination=0.005, random_state=seed).fit(z)
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", ConvergenceWarning)
            ae = MLPRegressor(hidden_layer_sizes=(6, 3, 6), activation="tanh", max_iter=600,
                              random_state=seed).fit(z, z)
        err = ((ae.predict(z) - z) ** 2).mean(axis=1)
        thr = float(np.quantile(err, 0.995)) * 1.5          # ngưỡng sai số tái tạo
        return cls(scaler, iforest, ae, thr)

    def score(self, window):
        """window: W vector đo gần nhất. Trả về (if_score, ae_ratio); bất thường nếu if_score>0 hoặc ae_ratio>1."""
        z = self.scaler.transform(batch_features(window))
        if_score = float(-self.iforest.decision_function(z)[0])
        err = float(((self.ae.predict(z) - z) ** 2).mean())
        return if_score, err / self.thr


def get_detector(load, model_dir):
    """Nạp mô hình đã lưu; nếu chưa có thì huấn luyện (vài giây) rồi lưu lại."""
    path = os.path.join(model_dir, f"{load.name}.v{MODEL_VERSION}.joblib")
    try:
        if os.path.exists(path):
            return joblib.load(path)
    except Exception:
        log.warning("Không đọc được %s, huấn luyện lại", path)
    log.info("Huấn luyện mô hình cho %s ...", load.name)
    det = Detector.train(load)
    try:
        os.makedirs(model_dir, exist_ok=True)
        joblib.dump(det, path)
    except OSError:
        log.warning("Không lưu được mô hình vào %s", model_dir)
    return det


class AiTracker:
    """Đếm số mẫu bất thường liên tiếp để lọc báo động giả."""

    def __init__(self, warn_n=5, trip_n=30):
        self.warn_n, self.trip_n = warn_n, trip_n
        self.consec = 0
        self.flag = False

    def reset(self):
        self.consec, self.flag = 0, False

    def update(self, if_score, ae_ratio):
        self.flag = if_score > 0 or ae_ratio > 1
        self.consec = self.consec + 1 if self.flag else max(0, self.consec - 2)
        return self.consec

    @property
    def warn(self):
        return self.consec >= self.warn_n

    @property
    def trip(self):
        return self.consec >= self.trip_n

    @property
    def state(self):
        return "anomaly" if self.warn else ("suspect" if self.flag else "normal")
