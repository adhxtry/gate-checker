# GATE Marks Calculator

A Python CLI tool to calculate GATE marks from:
- master question paper PDF
- master answer key PDF
- candidate response sheet URL

It handles the response-sheet option permutation problem automatically by mapping option image filenames (`...a.png`, `...b.png`, etc.) back to canonical master options.

## Requirements

- Python 3.9+
- [`uv`](https://github.com/astral-sh/uv)

## Install

```bash
uv sync
```

## Usage

```bash
uv run python main.py \
  --answer-key G26XXXX-CS26SXXXXXXXX-answerKey.pdf \
  --question-paper G26XXXX-CS26SXXXXXXXX-questionPaper.pdf \
  --response-sheet "https://...candidate_response_sheet.html"
```

### Detailed per-question output

```bash
uv run python main.py \
  --answer-key G26XXXX-CS26SXXXXXXXX-answerKey.pdf \
  --question-paper G26XXXX-CS26SXXXXXXXX-questionPaper.pdf \
  --response-sheet "https://...candidate_response_sheet.html" \
  --detailed
```

## CLI Arguments

- `--answer-key` (required): path to master answer key PDF
- `--question-paper` (required): path to master question paper PDF
- `--response-sheet` (required): candidate response sheet URL
- `--detailed` (optional): print per-question breakdown (CSV-like rows)

## What the script does

1. Parses answer key table (`Q. No.`, `Q. Type`, `Key/Range`) from PDF.
2. Parses mark bands from question paper (`Carry ONE/TWO mark Each`).
3. Downloads and parses response sheet HTML.
4. Sorts response questions by `Question ID` and aligns with answer-key order.
5. Resolves option permutation for MCQ/MSQ using option image suffix letters.
6. Scores all questions and prints totals.

## Scoring Rules

- **MCQ**: correct `+marks`, wrong `-marks/3`, unattempted `0`
- **MSQ**: exact set match required for full marks; else `0` (no negative)
- **NAT**: answer within official range gets full marks; else `0` (no negative)

## Notes

- If the response sheet URL is private/expired, fetching may fail.
