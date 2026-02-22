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

### Mode 1: Direct file paths

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

### Mode 2: Subject code auto-discovery from `sample/`

Drop two files in `sample/` for the subject (one answer key + one question paper), then run:

```bash
# For Computer Science Set 2
uv run python main.py \
  --subject-code CS26S2 \
  --response-sheet "https://...candidate_response_sheet.html"
```

For Data Science, for example:

```bash
uv run python main.py \
  --subject-code DA26 \
  --response-sheet "https://...candidate_response_sheet.html"
```

By default, the script scans `sample/`. You can override with `--sample-dir`.
Please contribute more sample PDFs for different subjects and sets!

## CLI Arguments

- `--answer-key`: path to master answer key PDF
- `--question-paper`: path to master question paper PDF
- `--subject-code`: subject code like `CS26` / `DA26`; auto-picks matching PDFs from `sample/`
- `--sample-dir`: directory used with `--subject-code` (default: `sample`)
- `--response-sheet` (required): candidate response sheet URL
- `--detailed` (optional): print per-question breakdown (CSV-like rows)

You must provide either:
- `--subject-code`, or
- both `--answer-key` and `--question-paper`

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
- In `--subject-code` mode, filenames are matched case-insensitively by subject code + `answerKey` / `questionPaper`.
- If multiple PDFs match the same subject and type, the script throws an error and asks for explicit files.
