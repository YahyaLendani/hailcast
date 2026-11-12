import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List
from app.core.config import settings

logger = logging.getLogger(__name__)

class ExperimentTracker:
    def __init__(self):
        self.experiments_file = settings.MODEL_DIR / "experiments_registry.json"

    def log_experiment(
        self,
        model_name: str,
        params: Dict[str, Any],
        metrics: Dict[str, float],
        artifacts: Dict[str, str],
        dataset_info: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Log experiment run metrics and metadata."""
        run_record = {
            "run_id": f"exp-{datetime.utcnow().strftime('%Y%m%d-%H%M%S')}-{model_name[:8]}",
            "timestamp": datetime.utcnow().isoformat(),
            "model_name": model_name,
            "parameters": params,
            "metrics": metrics,
            "artifacts": artifacts,
            "dataset_info": dataset_info
        }

        # Try MLflow if available
        try:
            import mlflow
            with mlflow.start_run(run_name=model_name):
                mlflow.log_params(params)
                mlflow.log_metrics(metrics)
        except Exception:
            pass

        # Local JSON Experiment Store
        history = self.get_experiments()
        history.append(run_record)
        try:
            with open(self.experiments_file, "w", encoding="utf-8") as f:
                json.dump(history, f, indent=2)
            logger.info("Logged experiment %s to registry.", run_record["run_id"])
        except Exception as e:
            logger.error("Failed to write experiment registry: %s", e)

        return run_record

    def get_experiments(self) -> List[Dict[str, Any]]:
        if not self.experiments_file.exists():
            return []
        try:
            with open(self.experiments_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return []

experiment_tracker = ExperimentTracker()

