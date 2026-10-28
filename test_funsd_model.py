
from pathlib import Path
import joblib

model_path = Path("models/funsd_text_classifier.pkl")
model = joblib.load(model_path)

samples = [
    "Name of Institution",
    "ABC Engineering College",
    "Registration Number",
    "Date of Approval"
]

predictions = model.predict(samples)

print("FUNSD Model Test Results:")
for text, label in zip(samples, predictions):
    print(f"{text} -> {label}")
