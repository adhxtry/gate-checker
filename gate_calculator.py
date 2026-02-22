from __future__ import annotations

import argparse
import math
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

import httpx
import pdfplumber
from bs4 import BeautifulSoup


@dataclass
class AnswerKeyEntry:
    q_no: int
    q_type: str
    section: str
    key_raw: str


@dataclass
class ResponseQuestion:
    question_id: int
    q_type: str
    status: str
    chosen_labels: List[str]
    given_answer: Optional[float]
    option_map: Dict[str, str]


@dataclass
class EvaluationRow:
    q_no: int
    question_id: int
    q_type: str
    status: str
    student_answer: str
    correct_answer: str
    marks: float
    max_marks: float


def normalize_space(value: str) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


def parse_answer_key(answer_key_pdf: Path) -> List[AnswerKeyEntry]:
    entries: List[AnswerKeyEntry] = []
    with pdfplumber.open(answer_key_pdf) as pdf:
        for page in pdf.pages:
            for table in page.extract_tables() or []:
                if not table or len(table) < 2:
                    continue
                header = [normalize_space(cell or "") for cell in table[0]]
                if len(header) < 4 or "Q. No." not in header[0] or "Q. Type" not in header[1]:
                    continue
                for row in table[1:]:
                    if not row or len(row) < 4:
                        continue
                    q_no_txt = normalize_space(row[0] or "")
                    q_type = normalize_space(row[1] or "")
                    section = normalize_space(row[2] or "")
                    key_raw = normalize_space(row[3] or "")
                    if not q_no_txt.isdigit():
                        continue
                    entries.append(
                        AnswerKeyEntry(
                            q_no=int(q_no_txt),
                            q_type=q_type.upper(),
                            section=section,
                            key_raw=key_raw,
                        )
                    )

    entries.sort(key=lambda e: e.q_no)
    return entries


def _mark_word_to_value(word: str) -> Optional[float]:
    word = word.upper()
    if word == "ONE":
        return 1.0
    if word == "TWO":
        return 2.0
    return None


def parse_mark_scheme(question_paper_pdf: Path, total_questions: int) -> Dict[int, float]:
    marks: Dict[int, float] = {}
    pattern = re.compile(
        r"Q\.\s*(\d+)\s*[–-]\s*Q\.\s*(\d+)\s*Carry\s*(ONE|TWO)\s*mark\s*Each",
        re.IGNORECASE,
    )

    with pdfplumber.open(question_paper_pdf) as pdf:
        for page in pdf.pages:
            text = page.extract_text() or ""
            for start_txt, end_txt, mark_word in pattern.findall(text):
                start_q = int(start_txt)
                end_q = int(end_txt)
                mark_val = _mark_word_to_value(mark_word)
                if mark_val is None:
                    continue
                for q_no in range(start_q, end_q + 1):
                    marks[q_no] = mark_val

    if len(marks) < total_questions:
        for q_no in range(1, total_questions + 1):
            if q_no in marks:
                continue
            marks[q_no] = 1.0 if (q_no <= 5 or 11 <= q_no <= 35) else 2.0

    return marks


def _extract_option_map_from_text(block_text: str) -> Dict[str, str]:
    option_map: Dict[str, str] = {}
    for label in ["A", "B", "C", "D"]:
        pattern = re.compile(
            rf"{label}\s*\.\s*IMG_SRC:([^\s]+)",
            re.IGNORECASE,
        )
        match = pattern.search(block_text)
        if match:
            option_map[label] = match.group(1)

    if len(option_map) == 4:
        return option_map

    fallback_urls = re.findall(r"IMG_SRC:([^\s]+[a-dA-D]\.png)", block_text, flags=re.IGNORECASE)
    unique_urls: List[str] = []
    seen: Set[str] = set()
    for url in fallback_urls:
        if url not in seen:
            seen.add(url)
            unique_urls.append(url)

    if len(unique_urls) >= 4:
        return {
            "A": unique_urls[0],
            "B": unique_urls[1],
            "C": unique_urls[2],
            "D": unique_urls[3],
        }

    return option_map


def _parse_float(value: str) -> Optional[float]:
    try:
        return float(value)
    except ValueError:
        return None


def parse_response_sheet(html_text: str) -> List[ResponseQuestion]:
    soup = BeautifulSoup(html_text, "lxml")
    for img in soup.find_all("img"):
        src = img.get("src", "")
        img.replace_with(f" IMG_SRC:{src} ")

    flat_text = normalize_space(soup.get_text(" "))
    if "Question Type" not in flat_text:
        return []

    start_pattern = re.compile(
        r"Question\s*Type\s*:\s*(MCQ|MSQ|NAT)\s*Question\s*ID\s*:\s*(\d+)\s*Status\s*:\s*"
        r"(Not Attempted and Marked For Review|Marked For Review|Not Answered|Answered)",
        re.IGNORECASE,
    )
    starts = list(start_pattern.finditer(flat_text))
    if not starts:
        return []

    questions: List[ResponseQuestion] = []
    for index, start in enumerate(starts):
        next_start = starts[index + 1].start() if index + 1 < len(starts) else len(flat_text)
        prev_end = starts[index - 1].end() if index > 0 else 0

        metadata_text = flat_text[start.start() : next_start]
        content_text = flat_text[prev_end : start.start()]

        q_type = start.group(1).upper()
        question_id = int(start.group(2))
        status = start.group(3)

        chosen_labels: List[str] = []
        if q_type in {"MCQ", "MSQ"}:
            chosen_match = re.search(r"Chosen\s*Option\s*:\s*([A-D](?:\s*,\s*[A-D])*)", metadata_text, flags=re.IGNORECASE)
            if chosen_match:
                chosen_labels = [part.strip().upper() for part in chosen_match.group(1).split(",") if part.strip()]

        given_answer: Optional[float] = None
        if q_type == "NAT":
            answer_match = re.search(r"Given\s*Answer\s*:\s*([-+]?\d+(?:\.\d+)?)", content_text, flags=re.IGNORECASE)
            if not answer_match:
                answer_match = re.search(r"Given\s*Answer\s*:\s*([-+]?\d+(?:\.\d+)?)", metadata_text, flags=re.IGNORECASE)
            if answer_match:
                given_answer = _parse_float(answer_match.group(1))

        option_map = _extract_option_map_from_text(content_text) if q_type in {"MCQ", "MSQ"} else {}

        questions.append(
            ResponseQuestion(
                question_id=question_id,
                q_type=q_type,
                status=status,
                chosen_labels=chosen_labels,
                given_answer=given_answer,
                option_map=option_map,
            )
        )

    return questions


def _label_to_master_option(option_map: Dict[str, str], label: str) -> Optional[str]:
    if label not in option_map:
        return None
    url = option_map[label]
    match = re.search(r"([a-dA-D])\.png(?:\?|$)", url)
    if not match:
        return None
    return match.group(1).upper()


def parse_nat_range(key_raw: str) -> Tuple[Optional[float], Optional[float]]:
    match = re.search(r"([-+]?\d+(?:\.\d+)?)\s*to\s*([-+]?\d+(?:\.\d+)?)", key_raw, flags=re.IGNORECASE)
    if not match:
        return None, None
    return float(match.group(1)), float(match.group(2))


def evaluate(
    answer_key: List[AnswerKeyEntry],
    mark_scheme: Dict[int, float],
    response_questions: List[ResponseQuestion],
) -> List[EvaluationRow]:
    sorted_responses = sorted(response_questions, key=lambda q: q.question_id)
    if len(sorted_responses) < len(answer_key):
        raise ValueError(
            f"Response sheet has only {len(sorted_responses)} questions, but answer key has {len(answer_key)}."
        )

    rows: List[EvaluationRow] = []
    for index, key_entry in enumerate(answer_key):
        response = sorted_responses[index]
        max_marks = mark_scheme.get(key_entry.q_no, 1.0)
        earned = 0.0

        student_answer = "--"
        correct_answer = key_entry.key_raw

        if key_entry.q_type == "MCQ":
            if response.chosen_labels:
                mapped = _label_to_master_option(response.option_map, response.chosen_labels[0])
                if mapped:
                    student_answer = mapped
                    if mapped == key_entry.key_raw:
                        earned = max_marks
                    else:
                        earned = -(max_marks / 3.0)
        elif key_entry.q_type == "MSQ":
            mapped_answers = {
                mapped
                for label in response.chosen_labels
                for mapped in [_label_to_master_option(response.option_map, label)]
                if mapped
            }
            if mapped_answers:
                student_answer = ";".join(sorted(mapped_answers))
            correct_set = {item.strip().upper() for item in key_entry.key_raw.split(";") if item.strip()}
            if mapped_answers == correct_set:
                earned = max_marks
        elif key_entry.q_type == "NAT":
            lo, hi = parse_nat_range(key_entry.key_raw)
            if response.given_answer is not None:
                student_answer = str(response.given_answer)
                if lo is not None and hi is not None and (lo - 1e-9) <= response.given_answer <= (hi + 1e-9):
                    earned = max_marks

        rows.append(
            EvaluationRow(
                q_no=key_entry.q_no,
                question_id=response.question_id,
                q_type=key_entry.q_type,
                status=response.status,
                student_answer=student_answer,
                correct_answer=correct_answer,
                marks=earned,
                max_marks=max_marks,
            )
        )

    return rows


def print_summary(rows: List[EvaluationRow]) -> None:
    total = sum(row.marks for row in rows)
    max_total = sum(row.max_marks for row in rows)
    print(f"Total Marks: {total:.2f} / {max_total:.2f}")

    one_mark_total = sum(row.marks for row in rows if math.isclose(row.max_marks, 1.0))
    two_mark_total = sum(row.marks for row in rows if math.isclose(row.max_marks, 2.0))
    print(f"1-mark questions subtotal: {one_mark_total:.2f}")
    print(f"2-mark questions subtotal: {two_mark_total:.2f}")


def print_detailed(rows: List[EvaluationRow]) -> None:
    print("q_no,qid,type,status,student,correct,marks")
    for row in rows:
        print(
            f"{row.q_no},{row.question_id},{row.q_type},"
            f"{row.status},{row.student_answer},{row.correct_answer},{row.marks:.2f}"
        )


def fetch_response_html(url: str) -> str:
    headers = {"User-Agent": "Mozilla/5.0"}
    response = httpx.get(url, headers=headers, follow_redirects=True, timeout=30)
    response.raise_for_status()
    return response.text


def run(
    answer_key_pdf: Path,
    question_paper_pdf: Path,
    response_sheet_url: str,
    detailed: bool,
) -> None:
    answer_key = parse_answer_key(answer_key_pdf)
    if not answer_key:
        raise ValueError("Could not parse answer key table.")

    mark_scheme = parse_mark_scheme(question_paper_pdf, total_questions=len(answer_key))
    html = fetch_response_html(response_sheet_url)
    responses = parse_response_sheet(html)
    if not responses:
        raise ValueError("Could not parse response sheet questions from HTML.")

    rows = evaluate(answer_key, mark_scheme, responses)

    if detailed:
        print_detailed(rows)
    print_summary(rows)


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="GATE Marks Calculator")
    parser.add_argument("--answer-key", required=True, type=Path, help="Path to master answer key PDF")
    parser.add_argument("--question-paper", required=True, type=Path, help="Path to master question paper PDF")
    parser.add_argument("--response-sheet", required=True, help="URL of candidate response sheet")
    parser.add_argument("--detailed", action="store_true", help="Print per-question breakdown")
    return parser


def main() -> None:
    parser = build_arg_parser()
    args = parser.parse_args()
    run(
        answer_key_pdf=args.answer_key,
        question_paper_pdf=args.question_paper,
        response_sheet_url=args.response_sheet,
        detailed=args.detailed,
    )


if __name__ == "__main__":
    main()
