"""Live quality runner for the deployed or local SgCare SSE endpoint.

Evaluation-only dependencies are imported lazily so deterministic quality checks do
not require RAGAS, datasets, provider credentials, or a network connection.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import math
import os
import re
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path
from statistics import fmean
from typing import Any, Protocol

import httpx

from evaluation.quality import QualityReport, assert_quality_thresholds


GOLDEN_QUERY_COUNT = 7
EVALUATION_ID = "sgcare-golden-v1"
DEFAULT_JUDGE_MODEL = "gemini-3.5-flash-lite"
GEMINI_OPENAI_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/openai/"
_SOURCE_ID = re.compile(r"S[1-9][0-9]*")
_CITATION = re.compile(r"\[(S[1-9][0-9]*)\]")


@dataclass(frozen=True)
class GoldenQuery:
    query_id: str
    query: str
    expected_documents: tuple[str, ...]
    expected_topic: str
    expected_page_range: tuple[int, int]


@dataclass(frozen=True)
class EvaluationSample:
    query_id: str
    query: str
    answer: str
    retrieved_contexts: list[str]
    source_ids: list[str]
    cited_source_ids: list[str]
    citation_valid: bool


class RagasMetric(Protocol):
    async def ascore(self, **kwargs: object) -> object: ...


ScoreSamples = Callable[[list[EvaluationSample]], QualityReport]


def load_golden_queries(path: Path) -> list[GoldenQuery]:
    """Load and strictly validate the fixed seven-query evaluation set."""

    raw: Any = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, list) or len(raw) != GOLDEN_QUERY_COUNT:
        raise ValueError("quality evaluation requires exactly seven unique golden queries")

    queries: list[GoldenQuery] = []
    identifiers: set[str] = set()
    for item in raw:
        if not isinstance(item, dict):
            raise ValueError("quality evaluation requires exactly seven unique golden queries")
        query_id = item.get("id")
        query = item.get("query")
        documents = item.get("expected_documents")
        topic = item.get("expected_topic")
        page_range = item.get("expected_page_range")
        valid_page_range = (
            isinstance(page_range, list)
            and len(page_range) == 2
            and all(isinstance(page, int) and not isinstance(page, bool) and page > 0 for page in page_range)
            and page_range[0] <= page_range[1]
        )
        if (
            not isinstance(query_id, str)
            or not query_id.strip()
            or query_id in identifiers
            or not isinstance(query, str)
            or not query.strip()
            or not isinstance(documents, list)
            or not documents
            or any(not isinstance(document, str) or not document for document in documents)
            or not isinstance(topic, str)
            or not topic.strip()
            or not valid_page_range
        ):
            raise ValueError("quality evaluation requires exactly seven unique golden queries")
        identifiers.add(query_id)
        queries.append(GoldenQuery(
            query_id=query_id,
            query=query,
            expected_documents=tuple(documents),
            expected_topic=topic,
            expected_page_range=(page_range[0], page_range[1]),
        ))
    return queries


def _event_blocks(body: str) -> Iterable[tuple[str, dict[str, Any]]]:
    for block in re.split(r"\r?\n\r?\n", body):
        if not block.strip():
            continue
        event_name: str | None = None
        data_lines: list[str] = []
        for line in block.splitlines():
            if line.startswith("event:"):
                event_name = line[6:].strip()
            elif line.startswith("data:"):
                data_lines.append(line[5:].lstrip())
        if not event_name or not data_lines:
            raise RuntimeError("The quality endpoint returned an invalid event stream.")
        try:
            data = json.loads("\n".join(data_lines))
        except json.JSONDecodeError as error:
            raise RuntimeError("The quality endpoint returned an invalid event stream.") from error
        if not isinstance(data, dict):
            raise RuntimeError("The quality endpoint returned an invalid event stream.")
        yield event_name, data


def fetch_query(
    client: httpx.Client,
    base_url: str,
    query_id: str,
    query: str,
) -> EvaluationSample:
    """Call the real query route and reduce its source-first SSE response to one sample."""

    response = client.post(
        f"{base_url.rstrip('/')}/api/query",
        json={"query": query},
        headers={"Accept": "text/event-stream"},
        timeout=60.0,
    )
    response.raise_for_status()

    sources_seen = False
    terminal_seen = False
    answer_parts: list[str] = []
    contexts: list[str] = []
    source_ids: list[str] = []
    cited_source_ids: list[str] = []
    server_citation_valid = False

    for event_name, data in _event_blocks(response.text):
        if terminal_seen:
            raise RuntimeError("The quality endpoint returned events after completion.")
        if event_name == "sources":
            raw_sources = data.get("sources")
            if sources_seen or not isinstance(data.get("request_id"), str) or not isinstance(raw_sources, list):
                raise RuntimeError("The quality endpoint returned an invalid sources event.")
            for source in raw_sources:
                if not isinstance(source, dict):
                    raise RuntimeError("The quality endpoint returned invalid source evidence.")
                source_id = source.get("source_id")
                excerpt = source.get("excerpt")
                if not isinstance(source_id, str) or not _SOURCE_ID.fullmatch(source_id) or not isinstance(excerpt, str) or not excerpt.strip():
                    raise RuntimeError("The quality endpoint returned invalid source evidence.")
                source_ids.append(source_id)
                contexts.append(excerpt)
            if len(source_ids) != len(set(source_ids)):
                raise RuntimeError("The quality endpoint returned duplicate source evidence.")
            sources_seen = True
        elif event_name == "token":
            delta = data.get("delta")
            if not sources_seen or not isinstance(delta, str):
                raise RuntimeError("The quality endpoint returned an invalid token event.")
            answer_parts.append(delta)
        elif event_name == "complete":
            raw_cited = data.get("cited_source_ids")
            raw_valid = data.get("citation_valid")
            if not sources_seen or not isinstance(raw_cited, list) or any(not isinstance(item, str) for item in raw_cited) or not isinstance(raw_valid, bool):
                raise RuntimeError("The quality endpoint returned an invalid complete event.")
            cited_source_ids = list(raw_cited)
            server_citation_valid = raw_valid
            terminal_seen = True
        elif event_name == "error":
            message = data.get("message")
            safe_message = message if isinstance(message, str) and message else "The quality endpoint reported an error."
            raise RuntimeError(safe_message)
        else:
            raise RuntimeError("The quality endpoint returned an unknown event.")

    if not sources_seen or not terminal_seen:
        raise RuntimeError("The quality endpoint returned an incomplete event stream.")
    answer = "".join(answer_parts)
    answer_citations = list(dict.fromkeys(_CITATION.findall(answer)))
    citation_valid = (
        server_citation_valid
        and bool(answer.strip())
        and bool(answer_citations)
        and answer_citations == cited_source_ids
        and all(source_id in source_ids for source_id in cited_source_ids)
    )
    return EvaluationSample(
        query_id=query_id,
        query=query,
        answer=answer,
        retrieved_contexts=contexts,
        source_ids=source_ids,
        cited_source_ids=cited_source_ids,
        citation_valid=citation_valid,
    )


def _metric_value(result: object) -> float:
    value = getattr(result, "value", None)
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(float(value)):
        raise ValueError("RAGAS returned an invalid metric score")
    return float(value)


async def evaluate_with_metrics(
    samples: Sequence[EvaluationSample],
    *,
    faithfulness: RagasMetric,
    answer_relevance: RagasMetric,
    context_precision: RagasMetric,
) -> QualityReport:
    """Evaluate samples through the current RAGAS 0.4 collections contracts."""

    if not samples:
        raise ValueError("quality evaluation requires samples")
    faithfulness_scores: list[float] = []
    relevance_scores: list[float] = []
    precision_scores: list[float] = []
    for sample in samples:
        faithfulness_scores.append(_metric_value(await faithfulness.ascore(
            user_input=sample.query,
            response=sample.answer,
            retrieved_contexts=sample.retrieved_contexts,
        )))
        relevance_scores.append(_metric_value(await answer_relevance.ascore(
            user_input=sample.query,
            response=sample.answer,
        )))
        precision_scores.append(_metric_value(await context_precision.ascore(
            user_input=sample.query,
            response=sample.answer,
            retrieved_contexts=sample.retrieved_contexts,
        )))
    return QualityReport(
        faithfulness=fmean(faithfulness_scores),
        answer_relevance=fmean(relevance_scores),
        context_precision=fmean(precision_scores),
        citation_validity=fmean(float(sample.citation_valid) for sample in samples),
    )


def build_ragas_scorer(api_key: str, judge_model: str) -> ScoreSamples:
    """Build an isolated Gemini-backed scorer using RAGAS 0.4 collections APIs."""

    from google import genai
    from openai import AsyncOpenAI
    from ragas.embeddings.base import embedding_factory
    from ragas.llms.base import llm_factory
    from ragas.metrics.collections import (
        AnswerRelevancy,
        ContextPrecisionWithoutReference,
        Faithfulness,
    )

    judge_client = AsyncOpenAI(api_key=api_key, base_url=GEMINI_OPENAI_BASE_URL)
    embedding_client = genai.Client(api_key=api_key)
    llm = llm_factory(judge_model, provider="openai", client=judge_client)
    embeddings = embedding_factory(
        "google",
        model="gemini-embedding-001",
        client=embedding_client,
        interface="modern",
    )
    faithfulness = Faithfulness(llm=llm)
    relevance = AnswerRelevancy(llm=llm, embeddings=embeddings)
    precision = ContextPrecisionWithoutReference(llm=llm)

    def score(samples: list[EvaluationSample]) -> QualityReport:
        async def evaluate_and_close() -> QualityReport:
            try:
                return await evaluate_with_metrics(
                    samples,
                    faithfulness=faithfulness,
                    answer_relevance=relevance,
                    context_precision=precision,
                )
            finally:
                await judge_client.close()

        try:
            return asyncio.run(evaluate_and_close())
        finally:
            embedding_client.close()

    return score


def run_evaluation(
    *,
    base_url: str,
    golden_path: Path,
    output_path: Path,
    judge_model: str,
    scorer: ScoreSamples,
    client: httpx.Client,
) -> int:
    """Collect seven live samples, persist aggregate-only output, and return a gate code."""

    golden_queries = load_golden_queries(golden_path)
    samples = [
        fetch_query(client, base_url, golden.query_id, golden.query)
        for golden in golden_queries
    ]
    report = scorer(samples)
    try:
        assert_quality_thresholds(report)
        passed = True
    except AssertionError:
        passed = False

    payload = {
        "schema_version": 1,
        "evaluation_id": EVALUATION_ID,
        "judge_model": judge_model,
        "golden_query_ids": [golden.query_id for golden in golden_queries],
        "query_count": len(golden_queries),
        "scores": report.model_dump(),
        "passed": passed,
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return 0 if passed else 1


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Evaluate the live SgCare RAG endpoint.")
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--golden", type=Path, default=Path("evaluation/golden-queries.json"))
    parser.add_argument("--judge-model", default=DEFAULT_JUDGE_MODEL)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    api_key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not api_key:
        raise SystemExit("GEMINI_API_KEY is required for live quality evaluation.")
    scorer = build_ragas_scorer(api_key, args.judge_model)
    with httpx.Client() as client:
        return run_evaluation(
            base_url=args.base_url,
            golden_path=args.golden,
            output_path=args.output,
            judge_model=args.judge_model,
            scorer=scorer,
            client=client,
        )


if __name__ == "__main__":
    raise SystemExit(main())
