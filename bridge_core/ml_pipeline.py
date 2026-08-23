#!/usr/bin/env python3
"""
CHAOS TYPE ZERO ML Pipeline — Training, Evaluation, Deployment
Uses: scikit-learn, numpy, pandas, matplotlib
"""

import os
import json
import pickle
import hashlib
from datetime import datetime
from pathlib import Path

import numpy as np

CTZ_ROOT = Path(__file__).parent.parent
MODELS_DIR = CTZ_ROOT / "data" / "models"


class CTZMLPipeline:
    """CHAOS TYPE ZERO ML Pipeline — train, evaluate, deploy models"""

    def __init__(self):
        MODELS_DIR.mkdir(parents=True, exist_ok=True)
        self.models = {}
        self._load_saved_models()

    def _load_saved_models(self):
        """Load metadata of saved models"""
        meta_file = MODELS_DIR / "models_meta.json"
        if meta_file.exists():
            try:
                self.models = json.loads(meta_file.read_text())
            except Exception:
                self.models = {}

    def _save_meta(self):
        meta_file = MODELS_DIR / "models_meta.json"
        meta_file.write_text(json.dumps(self.models, indent=2))

    # === Train ===

    def train_classifier(self, X, y, model_type: str = "random_forest",
                         test_size: float = 0.2, params: dict = None) -> dict:
        """Train a classification model"""
        try:
            from sklearn.model_selection import train_test_split, cross_val_score
            from sklearn.ensemble import RandomForestClassifier, GradientBoostingClassifier
            from sklearn.svm import SVC
            from sklearn.linear_model import LogisticRegression
            from sklearn.metrics import accuracy_score, classification_report
            from sklearn.preprocessing import StandardScaler
        except ImportError:
            return {"error": "scikit-learn not installed. Run: pip install scikit-learn"}

        X_train, X_test, y_train, y_test = train_test_split(
            X, y, test_size=test_size, random_state=42
        )

        scaler = StandardScaler()
        X_train_s = scaler.fit_transform(X_train)
        X_test_s = scaler.transform(X_test)

        models = {
            "random_forest": RandomForestClassifier,
            "gradient_boosting": GradientBoostingClassifier,
            "svm": SVC,
            "logistic_regression": LogisticRegression,
        }

        if model_type not in models:
            return {"error": f"Unknown model: {model_type}. Use: {list(models.keys())}"}

        clf = models[model_type](**(params or {}))
        clf.fit(X_train_s, y_train)
        y_pred = clf.predict(X_test_s)
        accuracy = accuracy_score(y_test, y_pred)

        # Cross-validation
        cv_scores = cross_val_score(clf, X_train_s, y_train, cv=min(5, len(X_train)))

        # Save model
        model_id = hashlib.md5(json.dumps({
            "type": model_type,
            "accuracy": accuracy,
            "timestamp": datetime.now().isoformat()
        }).encode(), usedforsecurity=False).hexdigest()[:8]

        model_path = MODELS_DIR / f"clf_{model_id}.pkl"
        with open(model_path, "wb") as f:
            pickle.dump({"model": clf, "scaler": scaler, "model_type": model_type}, f)

        self.models[model_id] = {
            "type": "classifier",
            "model_type": model_type,
            "accuracy": round(accuracy, 4),
            "cv_mean": round(float(cv_scores.mean()), 4),
            "cv_std": round(float(cv_scores.std()), 4),
            "n_samples": len(X),
            "n_features": X.shape[1] if hasattr(X, 'shape') else len(X[0]),
            "path": str(model_path),
            "created": datetime.now().isoformat(),
        }
        self._save_meta()

        return {
            "model_id": model_id,
            "accuracy": round(accuracy, 4),
            "cv_scores": [round(s, 4) for s in cv_scores.tolist()],
            "classification_report": classification_report(y_test, y_pred, output_dict=True),
        }

    def train_regressor(self, X, y, model_type: str = "random_forest",
                        test_size: float = 0.2, params: dict = None) -> dict:
        """Train a regression model"""
        try:
            from sklearn.model_selection import train_test_split, cross_val_score
            from sklearn.ensemble import RandomForestRegressor, GradientBoostingRegressor
            from sklearn.linear_model import LinearRegression
            from sklearn.metrics import mean_squared_error, r2_score
            from sklearn.preprocessing import StandardScaler
        except ImportError:
            return {"error": "scikit-learn not installed"}

        X_train, X_test, y_train, y_test = train_test_split(
            X, y, test_size=test_size, random_state=42
        )

        scaler = StandardScaler()
        X_train_s = scaler.fit_transform(X_train)
        X_test_s = scaler.transform(X_test)

        models = {
            "random_forest": RandomForestRegressor,
            "gradient_boosting": GradientBoostingRegressor,
            "linear": LinearRegression,
        }

        if model_type not in models:
            return {"error": f"Unknown model: {model_type}"}

        reg = models[model_type](**(params or {}))
        reg.fit(X_train_s, y_train)
        y_pred = reg.predict(X_test_s)

        mse = mean_squared_error(y_test, y_pred)
        r2 = r2_score(y_test, y_pred)

        model_id = hashlib.md5(json.dumps({
            "type": model_type,
            "r2": r2,
            "timestamp": datetime.now().isoformat()
        }).encode(), usedforsecurity=False).hexdigest()[:8]

        model_path = MODELS_DIR / f"reg_{model_id}.pkl"
        with open(model_path, "wb") as f:
            pickle.dump({"model": reg, "scaler": scaler, "model_type": model_type}, f)

        self.models[model_id] = {
            "type": "regressor",
            "model_type": model_type,
            "r2": round(r2, 4),
            "mse": round(mse, 4),
            "path": str(model_path),
            "created": datetime.now().isoformat(),
        }
        self._save_meta()

        return {"model_id": model_id, "r2": round(r2, 4), "mse": round(mse, 4)}

    # === Predict ===

    def predict(self, model_id: str, X) -> dict:
        """Make predictions using a saved model"""
        if model_id not in self.models:
            return {"error": f"Model {model_id} not found"}

        model_path = self.models[model_id]["path"]
        with open(model_path, "rb") as f:
            data = pickle.load(f)

        model = data["model"]
        scaler = data["scaler"]
        X_scaled = scaler.transform(X)
        predictions = model.predict(X_scaled)

        return {
            "model_id": model_id,
            "predictions": predictions.tolist(),
            "count": len(predictions),
        }

    # === Evaluate ===

    def evaluate(self, model_id: str, X_test, y_test) -> dict:
        """Evaluate model on test data"""
        if model_id not in self.models:
            return {"error": f"Model {model_id} not found"}

        model_path = self.models[model_id]["path"]
        with open(model_path, "rb") as f:
            data = pickle.load(f)

        model = data["model"]
        scaler = data["scaler"]
        X_scaled = scaler.transform(X_test)
        y_pred = model.predict(X_scaled)

        from sklearn.metrics import accuracy_score, mean_squared_error, r2_score

        model_type = self.models[model_id]["type"]
        if model_type == "classifier":
            return {"accuracy": round(accuracy_score(y_test, y_pred), 4)}
        else:
            return {
                "r2": round(r2_score(y_test, y_pred), 4),
                "mse": round(mean_squared_error(y_test, y_pred), 4),
            }

    # === Utilities ===

    def list_models(self) -> list:
        """List all saved models"""
        return [
            {"id": mid, **info}
            for mid, info in self.models.items()
        ]

    def delete_model(self, model_id: str) -> dict:
        """Delete a saved model"""
        if model_id not in self.models:
            return {"error": f"Model {model_id} not found"}
        model_path = Path(self.models[model_id]["path"])
        if model_path.exists():
            model_path.unlink()
        del self.models[model_id]
        self._save_meta()
        return {"status": "deleted", "model_id": model_id}

    def get_status(self) -> dict:
        return {
            "models_dir": str(MODELS_DIR),
            "total_models": len(self.models),
            "models": [
                {"id": mid, "type": info.get("type"), "accuracy": info.get("accuracy")}
                for mid, info in self.models.items()
            ],
        }


# Singleton
_ml = None


def get_ml_pipeline() -> CTZMLPipeline:
    global _ml
    if _ml is None:
        _ml = CTZMLPipeline()
    return _ml


if __name__ == "__main__":
    pipeline = get_ml_pipeline()
    print("=== CHAOS TYPE ZERO ML Pipeline ===")
    print(f"Status: {json.dumps(pipeline.get_status(), indent=2)}")

    # Quick test with synthetic data
    print("\nTraining test classifier...")
    X = np.random.rand(100, 5)
    y = (X[:, 0] + X[:, 1] > 1).astype(int)
    result = pipeline.train_classifier(X, y, model_type="random_forest")
    print(f"Result: {json.dumps(result, indent=2, default=str)}")
