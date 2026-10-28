
from pathlib import Path
import json
import random
import joblib

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline
from sklearn.metrics import classification_report

BASE_DIR = Path(__file__).resolve().parent
ANNOTATIONS_DIR = BASE_DIR / "dataset" / "training_data" / "annotations"
MODEL_DIR = BASE_DIR / "models"
MODEL_PATH = MODEL_DIR / "funsd_text_classifier.pkl"

# Load annotations grouped by form
forms = []

for path in ANNOTATIONS_DIR.glob("*.json"):
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    examples = []
    for item in data.get("form", []):
        text = item.get("text", "").strip()
        label = item.get("label", "").strip()

        if text and label in {"question", "answer", "header", "other"}:
            examples.append((text, label))

    if examples:
        forms.append(examples)

# Split by form, not by individual text item
random.Random(42).shuffle(forms)
split_index = int(len(forms) * 0.8)

train_forms = forms[:split_index]
test_forms = forms[split_index:]

train_examples = [item for form in train_forms for item in form]
test_examples = [item for form in test_forms for item in form]

X_train = [text for text, label in train_examples]
y_train = [label for text, label in train_examples]
X_test = [text for text, label in test_examples]
y_test = [label for text, label in test_examples]

print("Training forms:", len(train_forms))
print("Testing forms:", len(test_forms))
print("Training text items:", len(X_train))
print("Testing text items:", len(X_test))

# Train the text classifier
model = Pipeline([
    ("tfidf", TfidfVectorizer(ngram_range=(1, 2), lowercase=True)),
    ("classifier", LogisticRegression(max_iter=1000, class_weight="balanced"))
])

model.fit(X_train, y_train)

# Evaluate on unseen forms
predictions = model.predict(X_test)
print("\nEvaluation on held-out forms:")
print(classification_report(y_test, predictions, zero_division=0))

# Save the model
MODEL_DIR.mkdir(parents=True, exist_ok=True)
joblib.dump(model, MODEL_PATH)

print("\nModel saved to:", MODEL_PATH)
