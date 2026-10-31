"""Operator-only pre-generation. No image calls happen while an app reads the catalog."""
import argparse
import asyncio
import json
import sys
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
load_dotenv(ROOT / ".env")

from malo_ai import images
from malo_ai.schemas import PersonaImageRequest

parser = argparse.ArgumentParser(description="Prepare and cache Malo character expressions with OpenAI.")
parser.add_argument("--character", choices=["all", *images.CHARACTERS], default="all")
parser.add_argument("--emotion", choices=["all", *images.EXPRESSIONS], default="all")
parser.add_argument("--output-report", type=Path)
args = parser.parse_args()


async def main():
    characters = list(images.CHARACTERS) if args.character == "all" else [args.character]
    emotions = list(images.EXPRESSIONS) if args.emotion == "all" else [args.emotion]
    report = {"model": images.MODEL, "quality": images.QUALITY, "size": images.SIZE, "items": []}
    try:
        for character in characters:
            for emotion in emotions:
                result = await images.generate(PersonaImageRequest(characterId=character, emotion=emotion))
                report["items"].append(result)
                print(json.dumps({"assetKey": result["assetKey"], "cached": result["cached"],
                    "estimatedCostUsd": result["estimatedCostUsd"], "localPath": str(images.image_path(result["assetId"]))}), flush=True)
    finally:
        if args.output_report:
            args.output_report.parent.mkdir(parents=True, exist_ok=True)
            args.output_report.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")


asyncio.run(main())
