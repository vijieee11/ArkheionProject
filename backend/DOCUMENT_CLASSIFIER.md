# Document classifier workflow

The upload page can display a **suggested document type** from a locally trained text classifier. A staff member must still verify the suggestion. OCR may produce a few explicitly labelled identity fields as **unverified drafts** for the uploader to inspect. Those fields and OCR text are returned only in the upload response and are not saved to the senior profile or document record.

## Simulated development data

`data/document_classifier_simulated.csv` contains 60 entirely simulated text samples (12 each for five text-document classes): `OSCA Form No. 1`, `Birth certificate`, `Government ID`, `LCE endorsement letter`, and `Other`. It contains no real senior records. Its score is **not evidence** that the model meets the 80% target on real OSCA documents. The language is synthetic and much simpler than real uploads. The demo artifact is not loaded by default. To explicitly enable it for a demonstration, set `$env:ARKHEION_USE_DEMO_CLASSIFIER = "1"` before starting Django. Never use this mode for real OSCA decisions.

The text classifier cannot classify photo-only classes such as `2x2 ID photo` or `Full body photo` from text. Those need a separate image classifier or OCR/vision workflow and labeled image data.

## Dataset format

Create a UTF-8 CSV with these columns:

| Column | Meaning |
| --- | --- |
| `text` | Text copied from an anonymized or simulated document. |
| `label` | Correct document class, written consistently. |
| `source_id` | Unique identifier for the original document, reused if that document has multiple text rows. |

Do not include names, OSCA IDs, addresses, or other identifying information. Do not label one source document with multiple classes. The evaluator requires at least five distinct source documents per class; more balanced and varied examples are needed for dependable metrics.

An empty CSV template is at `data/document_classifier_template.csv`. Build a separate dataset from anonymized or simulated examples. For a meaningful 80% target claim, evaluate with a separate, representative labeled set that was not used to develop or tune the model.

## Install optional packages

From `D:\ArkheionProject\backend`, with the project virtual environment active:

```powershell
python -m pip install -r requirements-ml.txt
```

RapidOCR is installed as a Python package and does not require the separate Tesseract Windows installer. Start Django after installing the optional packages:

```powershell
python manage.py runserver
``` 

OCR is run during upload for JPG/PNG and scanned PDFs (up to 10 PDF pages). The extracted text is shown to the authenticated uploader for that upload response only; it is not stored in the database. OCR output can be inaccurate, especially for handwriting, low-quality photos, or mixed languages, and needs human review.

## Evaluate a labeled dataset

```powershell
python manage.py evaluate_document_classifier --dataset .\data\your_labeled_dataset.csv
```

The command can make a stratified 80/20 holdout split by `source_id`, so text rows from the same document cannot leak across training and evaluation. This is a development estimate, not a final independent test. It reports accuracy, macro-F1, and per-class precision/recall/F1. Passing this split alone does not save a production model.

For a final evaluation against a labeled test set that was not used in training or tuning, provide separate CSVs:

```powershell
python manage.py evaluate_document_classifier --dataset .\data\osca_train.csv --test-dataset .\data\osca_test.csv --dataset-kind anonymized_osca --artifact .\var\document_classifier.joblib
```

The command rejects overlapping `source_id` values and requires the same labels in both files. Both files need at least five distinct source documents per class. The model targets cannot be set below 0.80 accuracy and macro-F1. With `--test-dataset`, the saved model remains trained on the training CSV only; the test data is not folded into the artifact. An evaluation manifest is saved beside the model. The `--dataset-kind` value appears in the upload UI; simulated-test performance must not be reported as real OSCA-document performance. Preserve the independent test set and do not tune against it.

For the real OSCA model, use only an OSCA-approved anonymized labeled dataset, then run:

```powershell
Remove-Item Env:ARKHEION_USE_DEMO_CLASSIFIER -ErrorAction SilentlyContinue
Remove-Item Env:ARKHEION_DOCUMENT_CLASSIFIER_PATH -ErrorAction SilentlyContinue
python manage.py evaluate_document_classifier --dataset .\data\osca_anonymized_labeled.csv --artifact .\var\document_classifier.joblib
```

After the command reports both metrics at or above 0.80, restart Django. The production artifact is then selected by default. A simulated-data score must not be reported as real-document performance. Confidence percentages are for staff guidance and are not document verification.

## Limitations

- `pypdf` and `python-docx` extract text from text-based PDFs and DOCX files. RapidOCR processes JPG/PNG files and scanned PDFs (up to 10 pages).
- The model predicts only the document class and does not verify document authenticity. Confidence percentages are calibrated model scores, not proof that a document is genuine or that a prediction is correct. OCR field suggestions are conservative and unverified; a staff member must compare every value with the source document.
- The saved model is a local generated artifact and is intentionally excluded from Git. Install dependencies and evaluate the dataset on each development environment that needs predictions.


