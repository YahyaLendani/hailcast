import numpy as np
import logging
from typing import List, Dict, Any, Tuple
from sklearn.ensemble import IsolationForest

logger = logging.getLogger(__name__)

class AnomalyDetector:
    def __init__(self, contamination: float = 0.05):
        self.contamination = contamination
        self.model = IsolationForest(
            contamination=contamination,
            random_state=42,
            n_estimators=100
        )
        self.is_fitted = False

    def fit_detect(self, demand_records: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Fit Isolation Forest on historical demand aggregates and detect anomalies."""
        if len(demand_records) < 15:
            # Fallback to rolling Z-score if records are few
            return self._zscore_detect(demand_records)

        # Feature matrix: [trip_count, avg_fare, avg_duration, total_revenue]
        features = np.array([
            [
                r.get("trip_count", 0),
                r.get("avg_fare", 0.0),
                r.get("avg_duration_minutes", 0.0),
                r.get("total_revenue", 0.0)
            ]
            for r in demand_records
        ])

        try:
            self.model.fit(features)
            self.is_fitted = True

            # Decision function: negative values indicate outliers
            scores = self.model.decision_function(features)
            # Normalize score to 0..1 (higher = more anomalous)
            norm_scores = 1.0 / (1.0 + np.exp(scores * 5))
            preds = self.model.predict(features)  # -1 for anomaly, 1 for normal

            results = []
            for i, r in enumerate(demand_records):
                is_anom = bool(preds[i] == -1)
                score = round(float(norm_scores[i]), 3)
                
                # Determine severity
                if score > 0.8:
                    severity = "high"
                elif score > 0.6:
                    severity = "medium"
                else:
                    severity = "low"

                rec_copy = dict(r)
                rec_copy["is_anomaly"] = is_anom
                rec_copy["anomaly_score"] = score
                rec_copy["severity"] = severity
                results.append(rec_copy)

            return results
        except Exception as e:
            logger.error("Error running Isolation Forest: %s, falling back to Z-Score", e)
            return self._zscore_detect(demand_records)

    def _zscore_detect(self, demand_records: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Statistical Z-score fallback for demand anomalies."""
        counts = [r.get("trip_count", 0) for r in demand_records]
        if not counts:
            return demand_records

        mean = np.mean(counts)
        std = np.std(counts) or 1.0

        results = []
        for r in demand_records:
            val = r.get("trip_count", 0)
            z = abs((val - mean) / std)
            is_anom = bool(z > 2.5)
            score = round(min(1.0, float(z / 4.0)), 3)
            
            rec_copy = dict(r)
            rec_copy["is_anomaly"] = is_anom
            rec_copy["anomaly_score"] = score
            rec_copy["severity"] = "high" if z > 3.5 else ("medium" if z > 2.5 else "low")
            results.append(rec_copy)

        return results

anomaly_detector = AnomalyDetector()

