
from pathlib import Path
import json
from collections import Counter

BASE_DIR = Path(__file__).resolve().parent

# Your current dataset location
DATASET_DIR = BASE_DIR / "dataset" / "training_data"
ANNOTATIONS_DIR = DATASET_DIR / "annotations"

label_counts = Counter()
total_forms = 0
total_items = 0

for file_path in ANNOTATIONS_DIR.glob("*.json"):
    with open(file_path, "r", encoding="utf-8") as file:
        data = json.load(file)

    total_forms += 1

    for item in data.get("form", []):
        label = item.get("label", "unknown")
        label_counts[label] += 1
        total_items += 1

print("FUNSD DATASET SUMMARY")
print("---------------------")
print("Forms:", total_forms)
print("Annotated text items:", total_items)
print("\nLabel counts:")

for label, count in label_counts.most_common():
    print(f"{label}: {count}")

print("\nInspection completed.")
