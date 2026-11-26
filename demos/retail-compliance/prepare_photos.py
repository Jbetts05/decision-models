"""Derive each visit's photos (crops, blur) from the generated images listed in every scenario's visits.json."""

import json
from pathlib import Path

from PIL import Image, ImageFilter

SCENARIOS = Path(__file__).resolve().parent / "scenarios"


def prepare(scenario):
    manifest = json.loads((scenario / "visits.json").read_text(encoding="utf-8"))
    for visit in manifest["visits"]:
        folder = scenario / "images" / "visits" / visit["id"]
        folder.mkdir(parents=True, exist_ok=True)
        with Image.open(scenario / visit["source"]) as source:
            for photo in visit["photos"]:
                image = source.convert("RGB")
                crop = photo.get("crop")
                if crop:
                    image = image.crop(tuple(manifest["crops"][crop] if isinstance(crop, str) else crop))
                if photo.get("blur"):
                    image = image.filter(ImageFilter.GaussianBlur(photo["blur"]))
                if max(image.size) > 1568 or min(image.size) < 280:
                    raise ValueError(f"{scenario.name} visit {visit['id']} {photo['type']} is {image.size}; "
                                     "Decision-1.1 needs 280 to 1568 px per side.")
                image.save(folder / f"{photo['type']}.jpg", "JPEG", quality=90)
        print(f"{scenario.name} {visit['id']}: {', '.join(p['type'] for p in visit['photos'])}")


def main():
    for scenario in sorted(path for path in SCENARIOS.iterdir() if (path / "visits.json").exists()):
        prepare(scenario)


if __name__ == "__main__":
    main()
