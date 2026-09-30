#!/usr/bin/env python3
"""Build full word/phrase statistics from MyStem output.

Optional --keywords-file accepts a plain-text list of key words/phrases.
It is lemmatized with MyStem once before matching against the text lemmas.
"""
import argparse
import math
import re
import subprocess
import tempfile
from collections import Counter
from pathlib import Path

WORD_RE = re.compile(r"[а-яёa-z-]+", re.I)


def parse_mystem_output(text: str) -> list[str]:
    tokens = []
    for lemma in re.findall(r"\{([^}]+)\}", text):
        value = lemma.split("|")[0].strip().lower()
        if re.fullmatch(r"[а-яёa-z-]+", value):
            tokens.append(value)
    return tokens


def load_stop_words(path: Path) -> tuple[set[str], list[tuple[str, ...]]]:
    single, phrases = set(), []
    for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        parts = [x.lower() for x in WORD_RE.findall(line)]
        if not parts or parts == ["стоп", "слова"]:
            continue
        if len(parts) == 1:
            single.add(parts[0])
        else:
            phrases.append(tuple(parts))
    return single, sorted(set(phrases), key=len, reverse=True)


def remove_stop_words(tokens: list[str], single: set[str], phrases: list[tuple[str, ...]]) -> tuple[list[str], int]:
    result, removed, i = [], 0, 0
    while i < len(tokens):
        phrase = next((p for p in phrases if tuple(tokens[i:i + len(p)]) == p), None)
        if phrase:
            i += len(phrase)
            removed += len(phrase)
        elif tokens[i] in single:
            i += 1
            removed += 1
        else:
            result.append(tokens[i])
            i += 1
    return result, removed


def ngrams(tokens: list[str], n: int) -> Counter:
    return Counter(" ".join(tokens[i:i + n]) for i in range(len(tokens) - n + 1))


def lemma_keywords(path: Path, mystem: Path) -> list[tuple[str, ...]]:
    with tempfile.TemporaryDirectory() as temp:
        source = Path(temp) / "keywords.txt"
        output = Path(temp) / "keywords.mystem.txt"
        source.write_text(path.read_text(encoding="utf-8", errors="ignore"), encoding="utf-8")
        subprocess.run([str(mystem), str(source), str(output), "-d", "-l"], check=True)
        # Each nonempty source line is a key; retain its corresponding normalized form.
        # For a word-list this safely yields one lemma phrase per input line.
        return [tuple(parse_mystem_output(line)) for line in output.read_text(encoding="utf-8", errors="ignore").splitlines() if parse_mystem_output(line)]


def format_counter(title: str, counts: Counter, top: int) -> list[str]:
    total = sum(counts.values())
    lines = ["", f"{title} (топ-{top}):"]
    lines += [
        f"{item} — {count} ({count * 100 / total:.2f}%)"
        for item, count in counts.most_common(top)
    ] if total else ["Нет данных."]
    return lines


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("mystem_output", type=Path)
    ap.add_argument("source_text", type=Path)
    ap.add_argument("stop_words", type=Path)
    ap.add_argument("report", type=Path)
    ap.add_argument("--cleaned-output", type=Path)
    ap.add_argument("--keywords-file", type=Path)
    ap.add_argument("--mystem", type=Path, default=Path("./mystem"))
    ap.add_argument("--top", type=int, default=30)
    args = ap.parse_args()

    source = args.source_text.read_text(encoding="utf-8", errors="ignore")
    chars_without_spaces = len(re.sub(r"\s+", "", source))
    tokens = parse_mystem_output(args.mystem_output.read_text(encoding="utf-8", errors="ignore"))
    single, phrase_stops = load_stop_words(args.stop_words)
    clean, removed = remove_stop_words(tokens, single, phrase_stops)
    words, bigrams, trigrams = Counter(clean), ngrams(clean, 2), ngrams(clean, 3)
    nausea = (math.sqrt(sum(n * n for n in words.values())) * 100 / sum(words.values())) if words else 0.0

    lines = [
        "Полный отчёт MyStem",
        "",
        "Общая статистика:",
        f"Символов с пробелами: {len(source)}",
        f"Символов без пробелов: {chars_without_spaces}",
        f"Слов в лемматизированном тексте: {len(tokens)}",
        f"Стоп-слов удалено: {removed}",
        f"Слов после удаления стоп-слов: {len(clean)}",
        f"Уникальных слов после очистки: {len(words)}",
        f"Уникальных биграмм после очистки: {len(bigrams)}",
        f"Уникальных триграмм после очистки: {len(trigrams)}",
        f"Академическая тошнота: {nausea:.2f}%",
        "Формула: sqrt(Σ(частота слова²)) × 100 / Σ(частот всех слов); расчёт по словам после удаления стоп-слов.",
    ]
    lines += format_counter("Ключевые слова текста", words, args.top)
    lines += format_counter("Фразы из двух слов", bigrams, args.top)
    lines += format_counter("Фразы из трёх слов", trigrams, args.top)

    if args.keywords_file:
        if not args.keywords_file.exists():
            raise SystemExit(f"Не найден файл ключевых слов: {args.keywords_file}")
        keys = lemma_keywords(args.keywords_file, args.mystem)
        key_counts = Counter()
        for key in keys:
            phrase = " ".join(key)
            if len(key) == 1:
                key_counts[phrase] = words[phrase]
            else:
                key_counts[phrase] = ngrams(clean, len(key))[phrase]
        lines += ["", "Заданные ключевые слова (ключи предварительно лемматизированы MyStem):"]
        lines += [f"{count}\t{key}" for key, count in key_counts.items()]
    else:
        lines += ["", "Заданные ключевые слова: файл не предоставлен."]

    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text("\n".join(lines) + "\n", encoding="utf-8")
    if args.cleaned_output:
        args.cleaned_output.write_text(" ".join(clean) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
