import os, time, joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import classification_report, confusion_matrix

os.makedirs("./ai-service/models", exist_ok=True)
os.makedirs("./dataset", exist_ok=True)
CSV_PATH = "./dataset/energy_training_data.csv"

def generate_dataset(n_samples=2500):
    np.random.seed(42)
    rows, prev_i = [], 12.0
    for _ in range(n_samples):
        anom = 1 if np.random.rand() < 0.15 else 0
        if anom == 0:
            v, i, pf = np.random.uniform(218.0, 224.0), np.random.uniform(10.0, 15.0), np.random.uniform(0.88, 0.96)
        else:
            mode = np.random.choice(["OVERLOAD", "SAG", "LEAK"])
            if mode == "OVERLOAD": v, i, pf = np.random.uniform(210.0, 216.0), np.random.uniform(28.0, 42.0), np.random.uniform(0.75, 0.85)
            elif mode == "SAG": v, i, pf = np.random.uniform(165.0, 185.0), np.random.uniform(18.0, 25.0), np.random.uniform(0.70, 0.82)
            else: v, i, pf = np.random.uniform(218.0, 225.0), np.random.uniform(16.0, 22.0), np.random.uniform(0.45, 0.62)
        p_w, s_va, c_diff = round(v * i * pf, 1), round(v * i, 2), round(abs(i - prev_i), 2)
        prev_i = i
        rows.append([round(v, 1), round(i, 2), p_w, round(pf, 2), s_va, c_diff, anom])
    cols = ["voltage", "current", "power_w", "power_factor", "apparent_power_va", "current_diff", "simulated_anomaly"]
    df = pd.DataFrame(rows, columns=cols)
    df.to_csv(CSV_PATH, index=False)
    return df

def main():
    df = pd.read_csv(CSV_PATH) if os.path.exists(CSV_PATH) else generate_dataset()
    features = ["voltage", "current", "power_w", "power_factor", "apparent_power_va", "current_diff"]
    X, y_true = df[features].values, df["simulated_anomaly"].values
    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X)

    model = IsolationForest(n_estimators=150, contamination=0.15, random_state=42, n_jobs=-1)
    model.fit(X_scaled)

    t0 = time.perf_counter()
    preds = model.predict(X_scaled)
    latency_ms = ((time.perf_counter() - t0) / len(X_scaled)) * 1000
    y_pred = np.where(preds == -1, 1, 0)

    print(f"\n[OK] Thoi gian suy luan trung binh: {latency_ms:.4f} ms/mau")
    print("Confusion Matrix:\n", confusion_matrix(y_true, y_pred))
    print("\nClassification Report:\n", classification_report(y_true, y_pred, target_names=["Normal (0)", "Anomaly (1)"]))

    joblib.dump(model, "./ai-service/models/iso_forest.joblib")
    joblib.dump(scaler, "./ai-service/models/scaler.joblib")
    print("[OK] Da luu model va scaler vao ./ai-service/models/")

if __name__ == "__main__":
    main()
