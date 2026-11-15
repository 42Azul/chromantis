"""Read one image from stdin and emit OCR compatible with enrich_images.py."""

import argparse
import json
import subprocess
import sys


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--language", default="eng")
    args = parser.parse_args()
    result = subprocess.run(
        ["tesseract", "stdin", "stdout", "-l", args.language],
        stdin=sys.stdin.buffer,
        stdout=subprocess.PIPE,
        check=True,
    )
    json.dump(
        {"caption": "", "ocr_text": result.stdout.decode("utf-8").strip(), "object_tags": []},
        sys.stdout,
    )


if __name__ == "__main__":
    main()
