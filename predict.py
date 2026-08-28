#!/usr/bin/env python3
"""Run the PII detector over a dataset and write a predictions file.

USAGE:
    python predict.py [input.jsonl] [output.jsonl]

    e.g., python predict.py sample_dataset.jsonl predictions.jsonl

Reads each row's "source_text", runs it through redactor.detect(), and
writes one JSON object per line in the format evaluate.py expects:
    {"id": "pub-001", "predicted_spans": [[87, 97, "PERSON_NAME"], ...]}
"""

import json
import sys

from redactor import detect


def predict_file(input_path: str, output_path: str) -> None:
    with open(input_path) as infile, open(output_path, "w") as outfile:
        for line in infile:
            line = line.strip()
            if not line:
                continue
            row = json.loads(line)
            spans = sorted(detect(row["source_text"]), key=lambda s: (s.start, s.end))
            outfile.write(json.dumps({
                "id": row["id"],
                "predicted_spans": [list(span.as_triple()) for span in spans],
            }) + "\n")


def main() -> None:
    input_path = sys.argv[1] if len(sys.argv) > 1 else "sample_dataset.jsonl"
    output_path = sys.argv[2] if len(sys.argv) > 2 else "predictions.jsonl"
    predict_file(input_path, output_path)
    print(f"Wrote predictions for {input_path} to {output_path}")


if __name__ == "__main__":
    main()
