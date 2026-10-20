import csv
import json
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "Evaluate a document text classifier and save it only if accuracy and macro-F1 meet their targets."

    def add_arguments(self, parser):
        parser.add_argument("--dataset", required=True, help="CSV with text,label,source_id columns")
        parser.add_argument("--test-dataset", help="Optional independent CSV kept separate from training")
        parser.add_argument("--test-size", type=float, default=0.2)
        parser.add_argument("--seed", type=int, default=42)
        parser.add_argument("--accuracy-target", type=float, default=0.80)
        parser.add_argument("--f1-target", type=float, default=0.80)
        parser.add_argument(
            "--dataset-kind",
            choices=("simulated", "anonymized_osca"),
            default="simulated",
            help="Data provenance label stored with the evaluation manifest",
        )
        parser.add_argument(
            "--artifact",
            default=str(Path(settings.BASE_DIR) / "var" / "document_classifier.joblib"),
            help="Where to save the model if both holdout targets are met",
        )

    def handle(self, *args, **options):
        try:
            from joblib import dump
            from sklearn.calibration import CalibratedClassifierCV
            from sklearn.feature_extraction.text import TfidfVectorizer
            from sklearn.metrics import accuracy_score, classification_report, f1_score
            from sklearn.model_selection import train_test_split
            from sklearn.pipeline import Pipeline
            from sklearn.svm import LinearSVC
        except ImportError as error:
            raise CommandError(
                "ML dependencies are missing. Install them with: python -m pip install -r requirements-ml.txt"
            ) from error

        if not 0 < options["test_size"] < 1:
            raise CommandError("--test-size must be greater than 0 and less than 1.")
        if not 0.80 <= options["accuracy_target"] <= 1 or not 0.80 <= options["f1_target"] <= 1:
            raise CommandError("Production classifier targets cannot be lower than 0.80 for accuracy and macro-F1.")

        dataset_path = Path(options["dataset"])
        if not dataset_path.is_file():
            raise CommandError(f"Dataset file not found: {dataset_path}")

        def read_dataset(path):
            samples = []
            try:
                with path.open("r", encoding="utf-8-sig", newline="") as source:
                    reader = csv.DictReader(source)
                    required_columns = {"text", "label", "source_id"}
                    if not reader.fieldnames or not required_columns.issubset(reader.fieldnames):
                        raise CommandError(f"{path}: CSV must have text,label,source_id columns.")
                    for line_number, row in enumerate(reader, start=2):
                        text = (row.get("text") or "").strip()
                        label = (row.get("label") or "").strip()
                        source_id = (row.get("source_id") or "").strip()
                        if not text or not label or not source_id:
                            raise CommandError(f"{path} line {line_number}: text, label, and source_id are required.")
                        samples.append({"text": text, "label": label, "source_id": source_id})
            except UnicodeDecodeError as error:
                raise CommandError(f"{path}: dataset must be UTF-8 encoded.") from error
            if not samples:
                raise CommandError(f"Dataset is empty: {path}")
            return samples

        rows = read_dataset(dataset_path)
        external_test_path = Path(options["test_dataset"]) if options["test_dataset"] else None
        external_test_rows = read_dataset(external_test_path) if external_test_path else None

        def validate_source_labels(samples, dataset_name):
            source_labels = {}
            label_sources = defaultdict(set)
            for row in samples:
                prior = source_labels.setdefault(row["source_id"], row["label"])
                if prior != row["label"]:
                    raise CommandError(
                        f"{dataset_name}: source_id {row['source_id']!r} has multiple labels."
                    )
                label_sources[row["label"]].add(row["source_id"])
            return source_labels, label_sources

        source_labels, label_sources = validate_source_labels(rows, "Training dataset")
        labels = sorted(label_sources)
        if external_test_rows is not None:
            test_source_labels, test_label_sources = validate_source_labels(external_test_rows, "Test dataset")
            overlap = set(source_labels).intersection(test_source_labels)
            if overlap:
                raise CommandError("Training and test CSVs share source_id values; use distinct original documents.")
            if set(test_label_sources) != set(labels):
                missing = sorted(set(labels) - set(test_label_sources))
                extra = sorted(set(test_label_sources) - set(labels))
                raise CommandError(f"Test dataset labels must match training labels. Missing: {missing}; extra: {extra}.")
            sparse_train = {label: len(sources) for label, sources in label_sources.items() if len(sources) < 5}
            if sparse_train:
                raise CommandError("Need at least 5 distinct training documents per class: " + str(sparse_train))
            sparse_test = {label: len(sources) for label, sources in test_label_sources.items() if len(sources) < 5}
            if sparse_test:
                raise CommandError("Need at least 5 distinct independent test documents per class: " + str(sparse_test))
            train_rows = rows
            test_rows = external_test_rows
            train_groups = set(source_labels)
            test_groups = set(test_source_labels)
            split_description = "Independent test set"
        else:
            sparse_classes = {label: len(groups) for label, groups in label_sources.items() if len(groups) < 5}
            if sparse_classes:
                detail = ", ".join(f"{label}: {count}" for label, count in sorted(sparse_classes.items()))
                raise CommandError(
                    "Need at least 5 distinct source_id values per class for a grouped holdout split. "
                    f"Too few: {detail}."
                )
            unique_groups = list(source_labels)
            group_labels = [source_labels[group] for group in unique_groups]
            try:
                train_groups_list, test_groups_list = train_test_split(
                    unique_groups,
                    test_size=options["test_size"],
                    random_state=options["seed"],
                    stratify=group_labels,
                )
            except ValueError as error:
                raise CommandError(f"Could not create a stratified grouped holdout set: {error}") from error
            train_groups, test_groups = set(train_groups_list), set(test_groups_list)
            train_rows = [row for row in rows if row["source_id"] in train_groups]
            test_rows = [row for row in rows if row["source_id"] in test_groups]
            split_description = "Grouped holdout (development estimate)"

        classifier = Pipeline([
            ("tfidf", TfidfVectorizer(ngram_range=(1, 2), strip_accents="unicode", sublinear_tf=True)),
            ("classifier", CalibratedClassifierCV(
                estimator=LinearSVC(class_weight="balanced", random_state=options["seed"]),
                method="sigmoid",
                cv=3,
            )),
        ])
        try:
            classifier.fit([row["text"] for row in train_rows], [row["label"] for row in train_rows])
        except ValueError as error:
            raise CommandError(f"Could not train classifier: {error}") from error

        actual = [row["label"] for row in test_rows]
        predicted = classifier.predict([row["text"] for row in test_rows])
        accuracy = accuracy_score(actual, predicted)
        macro_f1 = f1_score(actual, predicted, labels=labels, average="macro", zero_division=0)
        self.stdout.write(f"Training rows: {len(train_rows)}")
        self.stdout.write(f"Training source documents: {len(train_groups)}")
        self.stdout.write(f"Test rows: {len(test_rows)}")
        self.stdout.write(f"Test source documents: {len(test_groups)}")
        self.stdout.write(f"Evaluation type: {split_description}")
        self.stdout.write(f"Accuracy: {accuracy:.3f} (target: {options['accuracy_target']:.2f})")
        self.stdout.write(f"Macro F1: {macro_f1:.3f} (target: {options['f1_target']:.2f})")
        self.stdout.write("Per-class report:")
        self.stdout.write(classification_report(actual, predicted, labels=labels, zero_division=0))

        if accuracy < options["accuracy_target"] or macro_f1 < options["f1_target"]:
            raise CommandError("Targets not met. No production classifier artifact was saved.")

        if external_test_rows is None:
            raise CommandError(
                "Development holdout targets met, but this is not an independent test. "
                "No production artifact was saved. Provide --test-dataset to preserve the final test set."
            )
        artifact_path = Path(options["artifact"])
        artifact_path.parent.mkdir(parents=True, exist_ok=True)
        dump(classifier, artifact_path)
        manifest = {
            "evaluation_type": "independent_test",
            "dataset_kind": options["dataset_kind"],
            "passed": True,
            "accuracy": float(accuracy),
            "macro_f1": float(macro_f1),
            "accuracy_target": float(options["accuracy_target"]),
            "f1_target": float(options["f1_target"]),
            "training_documents": len(train_groups),
            "test_documents": len(test_groups),
            "labels": labels,
            "evaluated_at_utc": datetime.now(timezone.utc).isoformat(),
        }
        artifact_path.with_suffix(artifact_path.suffix + ".evaluation.json").write_text(
            json.dumps(manifest, indent=2), encoding="utf-8"
        )
        self.stdout.write(self.style.SUCCESS(f"Independent-test targets met. Classifier saved to {artifact_path}"))
