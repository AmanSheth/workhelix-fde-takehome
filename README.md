# PII Redaction Prototype

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Run

Detect and redact PII in a string, from the command line:

```bash
python redactor.py "Contact Sarah Chen at sarah.chen@acmecorp.com"
echo "Contact Sarah Chen at sarah.chen@acmecorp.com" | python redactor.py
```

Or as a Python function:

```python
from redactor import redact

redacted_text, spans = redact("Contact Sarah Chen at sarah.chen@acmecorp.com")
```

Generate predictions for a dataset:

```bash
python predict.py sample_dataset.jsonl predictions.jsonl
```

Score predictions:

```bash
python evaluate.py sample_dataset.jsonl predictions.jsonl
```

## Files

- `redactor.py` — detection and redaction logic
- `predict.py` — batch driver, dataset in -> predictions.jsonl out
- `evaluate.py` — scorer (provided)
