"""Optional learned reranker for generic targets.

The model is advisory evidence. Heuristic geometry and human review remain
authoritative until a real field-level gold set supports promotion.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .models import FieldSpec
from .training_data import field_features


def train_target_model(records: list[dict[str, Any]]) -> tuple[Any, dict[str, Any]]:
    from sklearn.feature_extraction import DictVectorizer
    from sklearn.linear_model import LogisticRegression
    from sklearn.metrics import accuracy_score, f1_score
    from sklearn.model_selection import GroupShuffleSplit
    from sklearn.pipeline import Pipeline

    usable = [record for record in records if record["kind"] in {
        "text", "textarea", "date", "number", "identifier", "choice",
        "image", "signature", "composite", "negative",
    }]
    features = [field_features(record) for record in usable]
    labels = [record["kind"] for record in usable]
    groups = [record["group"] for record in usable]
    if len(set(labels)) < 3:
        raise RuntimeError("training corpus needs at least three target classes")
    counts = {label: labels.count(label) for label in set(labels)}
    holdout_fraction = max(0.25, len(counts) / len(usable))
    splitter = GroupShuffleSplit(n_splits=1, test_size=holdout_fraction, random_state=42)
    train_indices, test_indices = next(splitter.split(features, labels, groups=groups))
    model = Pipeline([
        ("vectorizer", DictVectorizer(sparse=True)),
        ("classifier", LogisticRegression(max_iter=1500, class_weight="balanced")),
    ])
    model.fit([features[index] for index in train_indices], [labels[index] for index in train_indices])
    predictions = model.predict([features[index] for index in test_indices])
    truth = [labels[index] for index in test_indices]
    receipt = {
        "schema": "pdf-form-field-lab.target-model.v1",
        "model_type": "DictVectorizer + balanced LogisticRegression",
        "label_intent_layer": "deterministic label_ner.py features used as advisory inputs",
        "feature_contract": "normalized geometry + lexical cues + label-intent entities",
        "record_count": len(usable),
        "class_counts": {label: labels.count(label) for label in sorted(set(labels))},
        "source_groups": sorted(set(groups)),
        "holdout_count": len(test_indices),
        "holdout_accuracy": round(float(accuracy_score(truth, predictions)), 4),
        "holdout_macro_f1": round(float(f1_score(truth, predictions, average="macro", zero_division=0)), 4),
        "supervision": "weak-and-reviewed-mixed; not a field-level gold benchmark",
        "split_strategy": "group-disjoint GroupShuffleSplit",
        "train_groups": sorted({groups[index] for index in train_indices}),
        "holdout_groups": sorted({groups[index] for index in test_indices}),
    }
    return model, receipt


def save_target_model(model: Any, path: Path) -> None:
    from joblib import dump
    path.parent.mkdir(parents=True, exist_ok=True)
    dump(model, path)


def load_target_model(path: Path) -> Any | None:
    if not path.is_file():
        return None
    from joblib import load
    return load(path)


def model_evidence(model: Any, field: FieldSpec) -> tuple[str, float]:
    features = field_features(field)
    predicted = str(model.predict([features])[0])
    probabilities = model.predict_proba([features])[0]
    confidence = float(max(probabilities))
    return predicted, confidence
