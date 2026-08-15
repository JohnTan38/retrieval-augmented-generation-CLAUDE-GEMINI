import math
import json
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest
from pydantic import ValidationError

from evaluation.quality import QualityReport, assert_quality_thresholds
from evaluation.run_quality import (
    EvaluationSample,
    evaluate_with_metrics,
    fetch_query,
    load_golden_queries,
    run_evaluation,
)


REQUIRED_FLOORS = {
    "faithfulness": 0.85,
    "answer_relevance": 0.80,
    "context_precision": 0.80,
    "citation_validity": 1.00,
}


def required_report(**updates: float) -> QualityReport:
    return QualityReport(**(REQUIRED_FLOORS | updates))


def test_quality_thresholds_accept_every_required_floor() -> None:
    assert_quality_thresholds(required_report())


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("faithfulness", 0.849),
        ("answer_relevance", 0.799),
        ("context_precision", 0.799),
        ("citation_validity", 0.999),
    ],
)
def test_quality_thresholds_reject_each_score_below_its_floor(
    field: str, value: float
) -> None:
    report = required_report(**{field: value})

    with pytest.raises(AssertionError, match=field):
        assert_quality_thresholds(report)


@pytest.mark.parametrize("field", REQUIRED_FLOORS)
@pytest.mark.parametrize("value", [-0.001, 1.001, math.inf, -math.inf, math.nan])
def test_quality_report_rejects_nonfinite_or_out_of_range_scores(
    field: str, value: float
) -> None:
    with pytest.raises(ValidationError, match=field):
        required_report(**{field: value})


@pytest.mark.parametrize("field", REQUIRED_FLOORS)
def test_quality_report_accepts_zero_and_one_for_every_metric(field: str) -> None:
    report = required_report(**{field: 0.0})
    assert getattr(report, field) == 0.0

    report = required_report(**{field: 1.0})
    assert getattr(report, field) == 1.0


def complete_sse(*, citation_valid: bool = True) -> str:
    source = {
        "source_id": "S1",
        "document_id": "jul-2025",
        "filename": "swk501-July2025-deep-research-model-answers.pdf",
        "title": "SWK501 July 2025 Deep-Research Model Answers",
        "semester": "July 2025",
        "page": 8,
        "excerpt": "Arnett describes emerging adulthood as a period of exploration.",
        "score": 0.92,
        "download_url": "/documents/swk501-July2025-deep-research-model-answers.pdf",
    }
    events = [
        ("sources", {"request_id": "req-eval-1", "retrieval_mode": "hybrid", "sources": [source], "timings": {"retrieval_ms": 7}}),
        ("token", {"delta": "Arnett emphasizes exploration "}),
        ("token", {"delta": "during emerging adulthood [S1]."}),
        ("complete", {"request_id": "req-eval-1", "timings": {"total_ms": 22}, "cited_source_ids": ["S1"], "citation_valid": citation_valid}),
    ]
    return "".join(f"event: {name}\ndata: {json.dumps(data)}\n\n" for name, data in events)


def test_fetch_query_calls_the_real_sse_contract_and_collects_one_safe_sample() -> None:
    def endpoint(request: httpx.Request) -> httpx.Response:
        assert request.method == "POST"
        assert request.url.path == "/api/query"
        assert request.headers["accept"] == "text/event-stream"
        assert json.loads(request.content) == {"query": "How does Arnett apply?"}
        return httpx.Response(200, headers={"content-type": "text/event-stream"}, text=complete_sse())

    with httpx.Client(transport=httpx.MockTransport(endpoint), base_url="https://study.invalid") as client:
        sample = fetch_query(client, "https://study.invalid", "tan-arnett", "How does Arnett apply?")

    assert sample == EvaluationSample(
        query_id="tan-arnett",
        query="How does Arnett apply?",
        answer="Arnett emphasizes exploration during emerging adulthood [S1].",
        retrieved_contexts=["Arnett describes emerging adulthood as a period of exploration."],
        source_ids=["S1"],
        cited_source_ids=["S1"],
        citation_valid=True,
    )


@pytest.mark.parametrize(
    "body",
    [
        'event: token\ndata: {"delta":"out of order"}\n\n',
        'event: sources\ndata: {"sources":[]}\n\n',
        'event: error\ndata: {"code":"generation_timeout","message":"Timed out","retryable":true}\n\n',
    ],
)
def test_fetch_query_rejects_incomplete_or_error_streams(body: str) -> None:
    transport = httpx.MockTransport(lambda _: httpx.Response(200, text=body))
    with httpx.Client(transport=transport) as client:
        with pytest.raises(RuntimeError):
            fetch_query(client, "https://study.invalid", "bad", "Question")


def test_load_golden_queries_requires_exactly_seven_unique_safe_entries(tmp_path: Path) -> None:
    golden_path = tmp_path / "golden.json"
    entries = [
        {
            "id": f"query-{index}",
            "query": f"Study question {index}",
            "expected_documents": ["jan-2026"],
            "expected_topic": "identity",
            "expected_page_range": [12, 15],
        }
        for index in range(7)
    ]
    golden_path.write_text(json.dumps(entries), encoding="utf-8")

    loaded = load_golden_queries(golden_path)
    assert [item.query_id for item in loaded] == [f"query-{index}" for index in range(7)]

    entries[-1]["id"] = "query-0"
    golden_path.write_text(json.dumps(entries), encoding="utf-8")
    with pytest.raises(ValueError, match="seven unique"):
        load_golden_queries(golden_path)


class ContractMetric:
    def __init__(self, required_keys: set[str], values: list[float]) -> None:
        self.required_keys = required_keys
        self.values = iter(values)

    async def ascore(self, **kwargs: object) -> SimpleNamespace:
        if set(kwargs) != self.required_keys or any(not value for value in kwargs.values()):
            raise AssertionError(f"unexpected RAGAS call: {kwargs}")
        return SimpleNamespace(value=next(self.values))


@pytest.mark.asyncio
async def test_evaluate_with_metrics_uses_current_ragas_contracts_and_aggregates() -> None:
    samples = [
        EvaluationSample("q1", "Question one", "Answer one [S1].", ["Context one"], ["S1"], ["S1"], True),
        EvaluationSample("q2", "Question two", "Answer two [S1].", ["Context two"], ["S1"], ["S1"], False),
    ]

    report = await evaluate_with_metrics(
        samples,
        faithfulness=ContractMetric({"user_input", "response", "retrieved_contexts"}, [0.8, 1.0]),
        answer_relevance=ContractMetric({"user_input", "response"}, [0.7, 0.9]),
        context_precision=ContractMetric({"user_input", "response", "retrieved_contexts"}, [0.6, 1.0]),
    )

    assert report == QualityReport(
        faithfulness=0.9,
        answer_relevance=0.8,
        context_precision=0.8,
        citation_validity=0.5,
    )


def test_run_evaluation_writes_only_aggregate_scores_and_safe_identifiers(tmp_path: Path) -> None:
    golden_path = tmp_path / "golden.json"
    output_path = tmp_path / "quality.json"
    entries = [
        {"id": f"safe-{index}", "query": f"private prompt {index}", "expected_documents": ["jan-2026"], "expected_topic": "topic", "expected_page_range": [1, 2]}
        for index in range(7)
    ]
    golden_path.write_text(json.dumps(entries), encoding="utf-8")

    def endpoint(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text=complete_sse())

    def scorer(samples: list[EvaluationSample]) -> QualityReport:
        assert len(samples) == 7
        return required_report()

    with httpx.Client(transport=httpx.MockTransport(endpoint)) as client:
        exit_code = run_evaluation(
            base_url="https://secret-host.invalid",
            golden_path=golden_path,
            output_path=output_path,
            judge_model="gemini-evaluator",
            scorer=scorer,
            client=client,
        )

    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert exit_code == 0
    assert payload == {
        "schema_version": 1,
        "evaluation_id": "sgcare-golden-v1",
        "judge_model": "gemini-evaluator",
        "golden_query_ids": [f"safe-{index}" for index in range(7)],
        "query_count": 7,
        "scores": REQUIRED_FLOORS,
        "passed": True,
    }
    serialized = output_path.read_text(encoding="utf-8")
    assert "private prompt" not in serialized
    assert "secret-host" not in serialized
    assert "Arnett emphasizes" not in serialized


def test_run_evaluation_writes_failed_aggregates_and_exits_nonzero(tmp_path: Path) -> None:
    golden_path = tmp_path / "golden.json"
    output_path = tmp_path / "quality.json"
    entries = [
        {"id": f"safe-{index}", "query": f"Question {index}", "expected_documents": ["jan-2026"], "expected_topic": "topic", "expected_page_range": [1, 2]}
        for index in range(7)
    ]
    golden_path.write_text(json.dumps(entries), encoding="utf-8")
    transport = httpx.MockTransport(lambda _: httpx.Response(200, text=complete_sse()))

    with httpx.Client(transport=transport) as client:
        exit_code = run_evaluation(
            base_url="https://study.invalid",
            golden_path=golden_path,
            output_path=output_path,
            judge_model="gemini-evaluator",
            scorer=lambda _: required_report(faithfulness=0.84),
            client=client,
        )

    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert exit_code == 1
    assert payload["passed"] is False
    assert payload["scores"]["faithfulness"] == 0.84
