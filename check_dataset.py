
from pathlib import Path
import json

# Update this path if your dataset is stored elsewhere
BASE_DIR = Path(__file__).resolve().parent
DATASET_DIR = BASE_DIR / "dataset" / "training_data"

IMAGES_DIR = DATASET_DIR / "images"
ANNOTATIONS_DIR = DATASET_DIR / "annotations"

print("Checking FUNSD dataset...\n")
print("Dataset path:", DATASET_DIR)
print("Images folder exists:", IMAGES_DIR.exists())
print("Annotations folder exists:", ANNOTATIONS_DIR.exists())

if not IMAGES_DIR.exists() or not ANNOTATIONS_DIR.exists():
    print("\nERROR: Dataset folders not found.")
    print("Check the folder path and the dataset's actual structure.")
else:
    images = list(IMAGES_DIR.glob("*.png"))
    annotations = list(ANNOTATIONS_DIR.glob("*.json"))

    print("Number of PNG images:", len(images))
    print("Number of JSON annotations:", len(annotations))

    if annotations:
        with open(annotations[0], "r", encoding="utf-8") as file:
            data = json.load(file)

        print("\nExample annotation filename:", annotations[0].name)
        print("Top-level keys:", list(data.keys()))

        if "form" in data:
            print("Number of annotated form items:", len(data["form"]))
            if data["form"]:
                print("Example item keys:", list(data["form"][0].keys()))

        print("\nDataset check completed.")
