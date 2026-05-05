#!/usr/bin/env python3
"""
PII Redaction Evaluator
========================

Computes per-category recall, precision, and F1 for PII detection predictions
against ground truth labels.

A predicted span counts as a true positive if its label matches the truth label
and the character-range IoU is at least IOU_THRESHOLD (default 0.5). This
tolerates small boundary drift (off-by-one whitespace/punctuation) while still
flagging predictions that miss most of the entity.

USAGE:
    python evaluate.py <ground_truth.jsonl> <predictions.jsonl>

    e.g., python evaluate.py sample_dataset.jsonl my_predictions.jsonl

INPUT FORMATS:

Ground truth file (one JSON object per line):
    {
      "id": "pub-001",
      "source_text": "...",
      "privacy_mask": [
        {"value": "...", "start": 87, "end": 97, "label": "PERSON_NAME"},
        ...
      ],
      ...
    }

Predictions file (one JSON object per line):
    {
      "id": "pub-001",
      "predicted_spans": [[87, 97, "PERSON_NAME"], ...]
    }

The IDs in the predictions file must match IDs in the ground truth file.
"""

import json
import sys
from collections import defaultdict


def load_jsonl(path):
    rows = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def load_ground_truth(path):
    rows = load_jsonl(path)
    truth = {}
    for row in rows:
        spans = set()
        for span in row.get("privacy_mask", []):
            spans.add((span["start"], span["end"], span["label"]))
        truth[row["id"]] = spans
    return truth, rows


def load_predictions(path):
    rows = load_jsonl(path)
    preds = {}
    for row in rows:
        spans = set()
        for span in row.get("predicted_spans", []):
            if isinstance(span, dict):
                spans.add((span["start"], span["end"], span["label"]))
            else:
                start, end, label = span[0], span[1], span[2]
                spans.add((start, end, label))
        preds[row["id"]] = spans
    return preds


IOU_THRESHOLD = 0.5


def iou(a, b):
    """IoU of two character ranges (start, end)."""
    inter = max(0, min(a[1], b[1]) - max(a[0], b[0]))
    if inter == 0:
        return 0.0
    union = (a[1] - a[0]) + (b[1] - b[0]) - inter
    return inter / union


def match_spans(truth_spans, pred_spans):
    """Greedy one-to-one match by descending IoU, within same label.

    Returns (tp_labels, fp_labels, fn_labels) as lists of label strings.
    """
    by_label_truth = defaultdict(list)
    by_label_pred = defaultdict(list)
    for s in truth_spans:
        by_label_truth[s[2]].append(s)
    for s in pred_spans:
        by_label_pred[s[2]].append(s)

    tp, fp, fn = [], [], []
    for label in set(by_label_truth) | set(by_label_pred):
        ts = by_label_truth.get(label, [])
        ps = by_label_pred.get(label, [])
        candidates = []
        for ti, t in enumerate(ts):
            for pi, p in enumerate(ps):
                v = iou((t[0], t[1]), (p[0], p[1]))
                if v >= IOU_THRESHOLD:
                    candidates.append((v, ti, pi))
        candidates.sort(reverse=True)
        used_t, used_p = set(), set()
        for _, ti, pi in candidates:
            if ti in used_t or pi in used_p:
                continue
            used_t.add(ti)
            used_p.add(pi)
            tp.append(label)
        fn.extend(label for i in range(len(ts)) if i not in used_t)
        fp.extend(label for i in range(len(ps)) if i not in used_p)
    return tp, fp, fn


def compute_metrics(truth_by_id, preds_by_id):
    by_category = defaultdict(lambda: {"tp": 0, "fp": 0, "fn": 0})

    all_ids = set(truth_by_id.keys()) | set(preds_by_id.keys())

    for row_id in all_ids:
        truth_spans = truth_by_id.get(row_id, set())
        pred_spans = preds_by_id.get(row_id, set())

        tp_labels, fp_labels, fn_labels = match_spans(truth_spans, pred_spans)

        for label in tp_labels:
            by_category[label]["tp"] += 1
        for label in fp_labels:
            by_category[label]["fp"] += 1
        for label in fn_labels:
            by_category[label]["fn"] += 1

    per_category = {}
    for label, counts in sorted(by_category.items()):
        tp, fp, fn = counts["tp"], counts["fp"], counts["fn"]
        recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
        precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
        f1 = (2 * recall * precision / (recall + precision)) if (recall + precision) > 0 else 0.0
        per_category[label] = {
            "tp": tp,
            "fp": fp,
            "fn": fn,
            "recall": recall,
            "precision": precision,
            "f1": f1,
        }

    if per_category:
        macro_recall = sum(c["recall"] for c in per_category.values()) / len(per_category)
        macro_precision = sum(c["precision"] for c in per_category.values()) / len(per_category)
        macro_f1 = sum(c["f1"] for c in per_category.values()) / len(per_category)
    else:
        macro_recall = macro_precision = macro_f1 = 0.0

    overall = {
        "recall": macro_recall,
        "precision": macro_precision,
        "f1": macro_f1,
    }

    totals = {
        "tp": sum(c["tp"] for c in per_category.values()),
        "fp": sum(c["fp"] for c in per_category.values()),
        "fn": sum(c["fn"] for c in per_category.values()),
        "ground_truth_spans": sum(len(s) for s in truth_by_id.values()),
        "predicted_spans": sum(len(s) for s in preds_by_id.values()),
    }

    return {
        "per_category": per_category,
        "overall": overall,
        "totals": totals,
    }


def compute_hallucination_rate(truth_rows, preds_by_id):
    zero_label_row_ids = [r["id"] for r in truth_rows if not r.get("privacy_mask")]
    total_hallucinations = 0
    rows_with_hallucinations = 0

    per_row = []
    for row_id in zero_label_row_ids:
        n_preds = len(preds_by_id.get(row_id, set()))
        if n_preds > 0:
            rows_with_hallucinations += 1
            total_hallucinations += n_preds
        per_row.append((row_id, n_preds))

    return {
        "n_zero_label_rows": len(zero_label_row_ids),
        "rows_with_hallucinations": rows_with_hallucinations,
        "total_hallucinations": total_hallucinations,
        "per_row": per_row,
    }


def print_report(metrics, hallucination_stats):
    print("=" * 70)
    print("PII REDACTION EVALUATION REPORT")
    print("=" * 70)
    print(f"Mode: IoU >= {IOU_THRESHOLD} (label must match)")

    print("\nPer-category metrics:")
    print(f"{'Category':<20} {'TP':>5} {'FP':>5} {'FN':>5} {'Recall':>8} {'Prec':>8} {'F1':>8}")
    print("-" * 70)
    for label, m in metrics["per_category"].items():
        print(f"{label:<20} {m['tp']:>5} {m['fp']:>5} {m['fn']:>5} "
              f"{m['recall']:>8.3f} {m['precision']:>8.3f} {m['f1']:>8.3f}")

    print("\nOverall (macro-averaged across categories):")
    o = metrics["overall"]
    print(f"  Recall:    {o['recall']:.3f}")
    print(f"  Precision: {o['precision']:.3f}")
    print(f"  F1:        {o['f1']:.3f}")

    t = metrics["totals"]
    print(f"\nTotals: {t['tp']} TP, {t['fp']} FP, {t['fn']} FN")
    print(f"  Ground truth spans: {t['ground_truth_spans']}")
    print(f"  Predicted spans:    {t['predicted_spans']}")

    h = hallucination_stats
    if h["n_zero_label_rows"] > 0 and h["rows_with_hallucinations"] > 0:
        print(f"\nRows with no ground truth PII: {h['n_zero_label_rows']}")
        print(f"  Rows where predictions were made: {h['rows_with_hallucinations']}")
        print(f"  Total predictions on these rows: {h['total_hallucinations']}")

    print()


def main():
    if len(sys.argv) != 3:
        print("Usage: python evaluate.py <ground_truth.jsonl> <predictions.jsonl>")
        sys.exit(1)

    ground_truth_path = sys.argv[1]
    predictions_path = sys.argv[2]

    truth_by_id, truth_rows = load_ground_truth(ground_truth_path)
    preds_by_id = load_predictions(predictions_path)

    unknown_ids = set(preds_by_id.keys()) - set(truth_by_id.keys())
    if unknown_ids:
        print(f"WARNING: predictions file contains {len(unknown_ids)} IDs not "
              f"found in ground truth: {sorted(unknown_ids)[:5]}...", file=sys.stderr)

    missing_ids = set(truth_by_id.keys()) - set(preds_by_id.keys())
    if missing_ids:
        print(f"INFO: predictions file is missing {len(missing_ids)} of "
              f"{len(truth_by_id)} ground truth rows.", file=sys.stderr)

    metrics = compute_metrics(truth_by_id, preds_by_id)
    hallucination_stats = compute_hallucination_rate(truth_rows, preds_by_id)
    print_report(metrics, hallucination_stats)


if __name__ == "__main__":
    main()
