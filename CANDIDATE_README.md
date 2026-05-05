# CANDIDATE_README

Technical scaffolding for the PII redaction take-home. See `README.md` for the
assignment itself.

## Files

- `sample_dataset.jsonl` — 10 rows of labeled data for development and testing
- `evaluate.py` — script for computing recall, precision, and F1 on your predictions
- `example_predictions.jsonl` — small example showing the prediction file format

## Dataset Format

Each line in `sample_dataset.jsonl` is a JSON object with these fields:

| Field | Type | Description |
|---|---|---|
| `id` | string | Unique row identifier (e.g., `"pub-001"`) |
| `source_text` | string | The text containing PII |
| `target_text` | string | The text with PII replaced by category placeholders |
| `privacy_mask` | list of objects | Span annotations: `{"value": "...", "start": N, "end": N, "label": "..."}` |
| `span_labels` | list of triples | Same info as `[start, end, label]` triples |

Span offsets are character-based, zero-indexed, with end exclusive (i.e.,
`source_text[start:end]` slices to the PII value).

## Prediction Format

Your code should produce a JSONL file where each line is:

```json
{"id": "pub-001", "predicted_spans": [[87, 97, "PERSON_NAME"], [146, 169, "EMAIL"]]}
```

- `id` must match an `id` from the dataset.
- `predicted_spans` is a list of `[start, end, label]` triples.
- `start` and `end` use the same convention as the dataset (character-indexed,
  end exclusive).
- `label` must be one of the six categories: `EMAIL`, `PHONE_NUMBER`,
  `PERSON_NAME`, `STREET_ADDRESS`, `SSN`, `DATE_OF_BIRTH`.

You may include a row with no predictions: `{"id": "pub-001", "predicted_spans": []}`.

See `example_predictions.jsonl` for a concrete example.

## Running the Evaluator

```bash
python evaluate.py sample_dataset.jsonl your_predictions.jsonl
```

The evaluator reports per-category and overall metrics. Read the script for
details on what it computes and how it computes it.

## Questions

If anything is unclear, please reach out before you start coding. We would
rather answer a clarifying question than have you guess.
