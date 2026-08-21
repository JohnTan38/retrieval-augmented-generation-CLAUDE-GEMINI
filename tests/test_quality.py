import math
import json
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import ANY

import httpx
import pytest
from pydantic import ValidationError

from evaluation.quality import (
    LatencyReport,
    QualityReport,
    assert_latency_thresholds,
    assert_quality_thresholds,
)
from evaluation import run_quality as quality_runner
from evaluation.run_quality import (
    EvaluationSample,
    evaluate_with_metrics,
    fetch_query,
    load_golden_queries,
    latency_report,
    run_evaluation,
)


REQUIRED_FLOORS = {
    "faithfulness": 0.85,
    "answer_relevance": 0.80,
    "context_precision": 0.80,
    "citation_validity": 1.00,
    "retrieval_hit_rate": 1.00,
    "successful_completion_rate": 1.00,
}

REQUIRED_LATENCY_CEILINGS = {
    "sources_p95_ms": 1500,
    "first_token_p95_ms": 3000,
    "complete_p95_ms": 15000,
}


def required_report(**updates: float) -> QualityReport:
    return QualityReport(**(REQUIRED_FLOORS | updates))


def test_quality_thresholds_accept_every_required_floor() -> None:
    assert_quality_thresholds(required_report())


def test_latency_thresholds_accept_ceilings_and_reject_each_overage() -> None:
    report = LatencyReport(**REQUIRED_LATENCY_CEILINGS)
    assert_latency_thresholds(report)

    for field, ceiling in REQUIRED_LATENCY_CEILINGS.items():
        with pytest.raises(AssertionError, match=field):
            assert_latency_thresholds(report.model_copy(update={field: ceiling + 1}))


@pytest.mark.parametrize("field", REQUIRED_LATENCY_CEILINGS)
@pytest.mark.parametrize("value", [-1, math.inf, -math.inf, math.nan])
def test_latency_report_rejects_negative_or_nonfinite_values(field: str, value: float) -> None:
    with pytest.raises(ValidationError, match=field):
        LatencyReport(**(REQUIRED_LATENCY_CEILINGS | {field: value}))


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("faithfulness", 0.849),
        ("answer_relevance", 0.799),
        ("context_precision", 0.799),
        ("citation_validity", 0.999),
        ("retrieval_hit_rate", 0.999),
        ("successful_completion_rate", 0.999),
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
        "variant": "research",
        "page": 8,
        "excerpt": "Arnett describes emerging adulthood as a period of exploration.",
        "score": 0.92,
        "download_url": "/documents/swk501-July2025-deep-research-model-answers.pdf",
    }
    events = [
        ("sources", {"request_id": "req-eval-1", "retrieval_mode": "hybrid", "sources": [source], "timings": {"retrieval_ms": 7}}),
        ("token", {"delta": "Arnett emphasizes exploration "}),
        ("token", {"delta": "during emerging adulthood [S1]."}),
        ("complete", {"request_id": "req-eval-1", "timings": {"first_token_ms": 12, "total_ms": 22}, "cited_source_ids": ["S1"], "citation_valid": citation_valid, "generation_complete": True}),
    ]
    return "".join(f"event: {name}\ndata: {json.dumps(data)}\n\n" for name, data in events)


def stream_clock(*, sources_ms: float = 7, first_token_ms: float = 12, complete_ms: float = 22):
    offsets = (0.0, sources_ms / 1000, first_token_ms / 1000, first_token_ms / 1000, complete_ms / 1000)
    calls = 0

    def clock() -> float:
        nonlocal calls
        query, stage = divmod(calls, len(offsets))
        calls += 1
        return query * 60.0 + offsets[stage]

    return clock


def golden_entries() -> list[dict[str, object]]:
    return [
        {
            "id": f"query-{index}",
            "query": f"Study question {index}",
            "expected_documents": ["jan-2026"],
            "expected_topic": "identity",
            "expected_page_range": [12, 15],
        }
        for index in range(10)
    ]


def fetch_body(body: str, *, status: int = 200) -> EvaluationSample:
    transport = httpx.MockTransport(lambda _: httpx.Response(status, text=body))
    with httpx.Client(transport=transport) as client:
        return fetch_query(client, "https://study.invalid/", "query-id", "Question")


def test_fetch_query_calls_the_real_sse_contract_and_collects_one_safe_sample() -> None:
    def endpoint(request: httpx.Request) -> httpx.Response:
        assert request.method == "POST"
        assert request.url.path == "/api/query"
        assert request.headers["accept"] == "text/event-stream"
        assert json.loads(request.content) == {"query": "How does Arnett apply?"}
        return httpx.Response(200, headers={"content-type": "text/event-stream"}, text=complete_sse())

    with httpx.Client(transport=httpx.MockTransport(endpoint), base_url="https://study.invalid") as client:
        sample = fetch_query(client, "https://study.invalid", "tan-arnett", "How does Arnett apply?", clock=stream_clock())

    assert sample == EvaluationSample(
        query_id="tan-arnett",
        query="How does Arnett apply?",
        answer="Arnett emphasizes exploration during emerging adulthood [S1].",
        retrieved_contexts=["Arnett describes emerging adulthood as a period of exploration."],
        source_ids=["S1"],
        cited_source_ids=["S1"],
        citation_valid=True,
        retrieval_hit=True,
        generation_complete=True,
        sources_ms=7,
        first_token_ms=12,
        complete_ms=22,
    )


def test_fetch_query_uses_client_event_arrival_instead_of_server_reported_timings() -> None:
    transport = httpx.MockTransport(lambda _: httpx.Response(200, text=complete_sse()))
    with httpx.Client(transport=transport) as client:
        sample = fetch_query(
            client,
            "https://study.invalid",
            "latency",
            "Question",
            clock=stream_clock(sources_ms=101, first_token_ms=202, complete_ms=303),
        )
    assert (sample.sources_ms, sample.first_token_ms, sample.complete_ms) == (101, 202, 303)


def test_latency_report_uses_nearest_rank_p95_for_all_live_samples() -> None:
    samples = [
        EvaluationSample("q", "Q", "A [S1]", ["E"], ["S1"], ["S1"], True, sources_ms=i, first_token_ms=i * 2, complete_ms=i * 3)
        for i in range(1, 21)
    ]
    assert latency_report(samples) == LatencyReport(
        sources_p95_ms=19,
        first_token_p95_ms=38,
        complete_p95_ms=57,
    )


def test_latency_report_requires_samples() -> None:
    with pytest.raises(ValueError, match="requires samples"):
        latency_report([])


def test_latency_report_rejects_missing_or_invalid_server_timings() -> None:
    sample = EvaluationSample("q", "Q", "A [S1]", ["E"], ["S1"], ["S1"], True)
    with pytest.raises(ValueError, match="valid server timings"):
        latency_report([sample])




def test_event_parser_accepts_crlf_multiline_data_and_ignores_empty_blocks() -> None:
    blocks = list(quality_runner._event_blocks('\r\n\r\n: keepalive\r\nevent: token\r\ndata: {"delta":\r\ndata: "answer"}\r\n\r\n'))
    assert blocks == [("token", {"delta": "answer"})]


def test_timed_event_parser_flushes_a_final_block_without_a_blank_line() -> None:
    response = httpx.Response(200, text='\n\nevent: token\ndata: {"delta":"answer"}')
    assert list(quality_runner._timed_event_blocks(response, 1.0, lambda: 1.025)) == [
        ("token", {"delta": "answer"}, 25.0),
    ]


@pytest.mark.parametrize(
    "body",
    [
        "event: token\n\n",
        'data: {"delta":"answer"}\n\n',
        "event: token\ndata: not-json\n\n",
        "event: token\ndata: []\n\n",
    ],
)
def test_event_parser_rejects_malformed_blocks(body: str) -> None:
    with pytest.raises(RuntimeError, match="invalid event stream"):
        list(quality_runner._event_blocks(body))


@pytest.mark.parametrize(
    "body",
    [
        'event: token\ndata: {"delta":"out of order"}\n\n',
        'event: sources\ndata: {"sources":[]}\n\n',
        'event: sources\ndata: {"request_id":"r","sources":[]}\n\n',
        'event: error\ndata: {"code":"generation_timeout","message":"Timed out","retryable":true}\n\n',
    ],
)
def test_fetch_query_rejects_incomplete_or_error_streams(body: str) -> None:
    transport = httpx.MockTransport(lambda _: httpx.Response(200, text=body))
    with httpx.Client(transport=transport) as client:
        with pytest.raises(RuntimeError):
            fetch_query(client, "https://study.invalid", "bad", "Question")


def test_fetch_query_propagates_http_failures() -> None:
    with pytest.raises(httpx.HTTPStatusError):
        fetch_body("unavailable", status=503)


@pytest.mark.parametrize(
    ("body", "message"),
    [
        ('event: sources\ndata: {"request_id":7,"sources":[]}\n\n', "invalid sources"),
        ('event: sources\ndata: {"request_id":"r","sources":{}}\n\n', "invalid sources"),
        (
            'event: sources\ndata: {"request_id":"r","sources":[]}\n\n'
            'event: sources\ndata: {"request_id":"r","sources":[]}\n\n',
            "invalid sources",
        ),
        ('event: sources\ndata: {"request_id":"r","sources":[7]}\n\n', "invalid source evidence"),
        ('event: sources\ndata: {"request_id":"r","sources":[{"source_id":"bad","excerpt":"ok"}]}\n\n', "invalid source evidence"),
        ('event: sources\ndata: {"request_id":"r","sources":[{"source_id":"S1","excerpt":""}]}\n\n', "invalid source evidence"),
        (
            'event: sources\ndata: {"request_id":"r","sources":[{"source_id":"S1","document_id":"doc","page":1,"variant":"research","excerpt":"one"},{"source_id":"S1","document_id":"doc","page":2,"variant":"research","excerpt":"two"}]}\n\n',
            "duplicate source evidence",
        ),
        ('event: token\ndata: {"delta":"early"}\n\n', "invalid token"),
        ('event: sources\ndata: {"request_id":"r","sources":[]}\n\nevent: token\ndata: {"delta":7}\n\n', "invalid token"),
        ('event: complete\ndata: {"cited_source_ids":[],"citation_valid":true}\n\n', "invalid complete"),
        ('event: sources\ndata: {"request_id":"r","sources":[]}\n\nevent: complete\ndata: {"cited_source_ids":{},"citation_valid":true}\n\n', "invalid complete"),
        ('event: sources\ndata: {"request_id":"r","sources":[]}\n\nevent: complete\ndata: {"cited_source_ids":[7],"citation_valid":true}\n\n', "invalid complete"),
        ('event: sources\ndata: {"request_id":"r","sources":[]}\n\nevent: complete\ndata: {"cited_source_ids":[],"citation_valid":"yes"}\n\n', "invalid complete"),
        ('event: mystery\ndata: {}\n\n', "unknown event"),
        ('event: error\ndata: {"message":7}\n\n', "reported an error"),
        ('event: error\ndata: {"message":""}\n\n', "reported an error"),
        (
            'event: sources\ndata: {"request_id":"r","sources":[]}\n\nevent: complete\ndata: {"cited_source_ids":[],"citation_valid":true,"generation_complete":true}\n\nevent: token\ndata: {"delta":"late"}\n\n',
            "events after completion",
        ),
    ],
)
def test_fetch_query_rejects_each_invalid_contract_shape(body: str, message: str) -> None:
    with pytest.raises(RuntimeError, match=message):
        fetch_body(body)


@pytest.mark.parametrize(
    ("answer", "cited", "server_valid"),
    [
        ("", [], True),
        ("uncited answer", [], True),
        ("answer [S1]", ["S2"], True),
        ("answer [S2]", ["S2"], True),
        ("answer [S1]", ["S1"], False),
    ],
)
def test_fetch_query_marks_every_invalid_citation_relationship(
    answer: str, cited: list[str], server_valid: bool
) -> None:
    source = {"source_id": "S1", "document_id": "doc", "page": 1, "variant": "research", "excerpt": "Evidence"}
    body = (
        f'event: sources\ndata: {json.dumps({"request_id": "r", "sources": [source]})}\n\n'
        f'event: token\ndata: {json.dumps({"delta": answer})}\n\n'
        f'event: complete\ndata: {json.dumps({"cited_source_ids": cited, "citation_valid": server_valid, "generation_complete": True})}\n\n'
    )
    assert fetch_body(body).citation_valid is False


def test_fetch_query_accepts_grouped_citations_using_the_runtime_parser() -> None:
    sources = [
        {"source_id": source_id, "document_id": "doc", "page": page, "variant": "research", "excerpt": "Evidence"}
        for source_id, page in (("S1", 1), ("S2", 2))
    ]
    body = (
        f'event: sources\ndata: {json.dumps({"request_id": "r", "sources": sources})}\n\n'
        'event: token\ndata: {"delta":"Supported comparison [S1, S2]."}\n\n'
        'event: complete\ndata: {"cited_source_ids":["S1","S2"],"citation_valid":true,"generation_complete":true}\n\n'
    )

    sample = fetch_body(body)

    assert sample.citation_valid is True
    assert sample.cited_source_ids == ["S1", "S2"]


def test_load_golden_queries_requires_exactly_ten_unique_safe_entries(tmp_path: Path) -> None:
    golden_path = tmp_path / "golden.json"
    entries = golden_entries()
    golden_path.write_text(json.dumps(entries), encoding="utf-8")

    loaded = load_golden_queries(golden_path)
    assert [item.query_id for item in loaded] == [f"query-{index}" for index in range(10)]

    entries[-1]["id"] = "query-0"
    golden_path.write_text(json.dumps(entries), encoding="utf-8")
    with pytest.raises(ValueError, match="ten unique"):
        load_golden_queries(golden_path)


@pytest.mark.parametrize(
    "replacement",
    [
        None,
        {"id": 7, "query": "q", "expected_documents": ["doc"], "expected_topic": "t", "expected_page_range": [1, 2]},
        {"id": "", "query": "q", "expected_documents": ["doc"], "expected_topic": "t", "expected_page_range": [1, 2]},
        {"id": "new", "query": 7, "expected_documents": ["doc"], "expected_topic": "t", "expected_page_range": [1, 2]},
        {"id": "new", "query": "", "expected_documents": ["doc"], "expected_topic": "t", "expected_page_range": [1, 2]},
        {"id": "new", "query": "q", "expected_documents": "doc", "expected_topic": "t", "expected_page_range": [1, 2]},
        {"id": "new", "query": "q", "expected_documents": [], "expected_topic": "t", "expected_page_range": [1, 2]},
        {"id": "new", "query": "q", "expected_documents": [7], "expected_topic": "t", "expected_page_range": [1, 2]},
        {"id": "new", "query": "q", "expected_documents": [""], "expected_topic": "t", "expected_page_range": [1, 2]},
        {"id": "new", "query": "q", "expected_documents": ["doc"], "expected_topic": 7, "expected_page_range": [1, 2]},
        {"id": "new", "query": "q", "expected_documents": ["doc"], "expected_topic": "", "expected_page_range": [1, 2]},
        {"id": "new", "query": "q", "expected_documents": ["doc"], "expected_topic": "t", "expected_page_range": "1-2"},
        {"id": "new", "query": "q", "expected_documents": ["doc"], "expected_topic": "t", "expected_page_range": [1]},
        {"id": "new", "query": "q", "expected_documents": ["doc"], "expected_topic": "t", "expected_page_range": [True, 2]},
        {"id": "new", "query": "q", "expected_documents": ["doc"], "expected_topic": "t", "expected_page_range": [0, 2]},
        {"id": "new", "query": "q", "expected_documents": ["doc"], "expected_topic": "t", "expected_page_range": [3, 2]},
    ],
)
def test_load_golden_queries_rejects_each_unsafe_entry_shape(tmp_path: Path, replacement: object) -> None:
    entries = golden_entries()
    entries[0] = replacement  # type: ignore[assignment]
    golden_path = tmp_path / "golden.json"
    golden_path.write_text(json.dumps(entries), encoding="utf-8")

    with pytest.raises(ValueError, match="ten unique"):
        load_golden_queries(golden_path)


@pytest.mark.parametrize("payload", [{}, [], golden_entries()[:6]])
def test_load_golden_queries_rejects_non_list_or_wrong_count(tmp_path: Path, payload: object) -> None:
    golden_path = tmp_path / "golden.json"
    golden_path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError, match="exactly ten"):
        load_golden_queries(golden_path)


class ContractMetric:
    def __init__(self, required_keys: set[str], values: list[float]) -> None:
        self.required_keys = required_keys
        self.values = iter(values)

    async def ascore(self, **kwargs: object) -> SimpleNamespace:
        if set(kwargs) != self.required_keys or any(not value for value in kwargs.values()):
            raise AssertionError(f"unexpected RAGAS call: {kwargs}")
        return SimpleNamespace(value=next(self.values))


@pytest.mark.parametrize("value", [True, "0.9", None, math.nan, math.inf, -math.inf])
def test_metric_value_rejects_non_numeric_or_nonfinite_results(value: object) -> None:
    with pytest.raises(ValueError, match="invalid metric score"):
        quality_runner._metric_value(SimpleNamespace(value=value))


@pytest.mark.parametrize(("value", "expected"), [(1, 1.0), (0.75, 0.75)])
def test_metric_value_accepts_finite_numeric_results(value: object, expected: float) -> None:
    assert quality_runner._metric_value(SimpleNamespace(value=value)) == expected


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
        retrieval_hit_rate=1.0,
        successful_completion_rate=1.0,
    )


@pytest.mark.asyncio
async def test_evaluate_with_metrics_rejects_an_empty_sample_set() -> None:
    metric = ContractMetric(set(), [])
    with pytest.raises(ValueError, match="requires samples"):
        await evaluate_with_metrics(
            [],
            faithfulness=metric,
            answer_relevance=metric,
            context_precision=metric,
        )


def install_fake_ragas_modules(monkeypatch: pytest.MonkeyPatch) -> dict[str, object]:
    symbols: dict[str, object] = {}

    class AsyncOpenAI:
        pass

    class GenaiClient:
        pass

    def llm_factory(*args: object, **kwargs: object) -> object:
        return (args, kwargs)

    def embedding_factory(*args: object, **kwargs: object) -> object:
        return (args, kwargs)

    class Faithfulness:
        pass

    class AnswerRelevancy:
        pass

    class ContextPrecisionWithoutReference:
        pass

    symbols.update(locals())
    google = ModuleType("google")
    genai = ModuleType("google.genai")
    genai.Client = GenaiClient  # type: ignore[attr-defined]
    google.genai = genai  # type: ignore[attr-defined]
    openai = ModuleType("openai")
    openai.AsyncOpenAI = AsyncOpenAI  # type: ignore[attr-defined]
    ragas = ModuleType("ragas")
    ragas_embeddings = ModuleType("ragas.embeddings")
    ragas_embeddings_base = ModuleType("ragas.embeddings.base")
    ragas_embeddings_base.embedding_factory = embedding_factory  # type: ignore[attr-defined]
    ragas_llms = ModuleType("ragas.llms")
    ragas_llms_base = ModuleType("ragas.llms.base")
    ragas_llms_base.llm_factory = llm_factory  # type: ignore[attr-defined]
    ragas_metrics = ModuleType("ragas.metrics")
    ragas_collections = ModuleType("ragas.metrics.collections")
    ragas_collections.Faithfulness = Faithfulness  # type: ignore[attr-defined]
    ragas_collections.AnswerRelevancy = AnswerRelevancy  # type: ignore[attr-defined]
    ragas_collections.ContextPrecisionWithoutReference = ContextPrecisionWithoutReference  # type: ignore[attr-defined]
    modules = {
        "google": google,
        "google.genai": genai,
        "openai": openai,
        "ragas": ragas,
        "ragas.embeddings": ragas_embeddings,
        "ragas.embeddings.base": ragas_embeddings_base,
        "ragas.llms": ragas_llms,
        "ragas.llms.base": ragas_llms_base,
        "ragas.metrics": ragas_metrics,
        "ragas.metrics.collections": ragas_collections,
    }
    for name, module in modules.items():
        monkeypatch.setitem(sys.modules, name, module)
    return symbols


def test_load_ragas_runtime_resolves_the_current_0_4_3_api_symbols(monkeypatch: pytest.MonkeyPatch) -> None:
    symbols = install_fake_ragas_modules(monkeypatch)

    runtime = quality_runner._load_ragas_runtime()

    assert runtime.async_openai is symbols["AsyncOpenAI"]
    assert runtime.genai_client is symbols["GenaiClient"]
    assert runtime.llm_factory is symbols["llm_factory"]
    assert runtime.embedding_factory is symbols["embedding_factory"]
    assert runtime.faithfulness is symbols["Faithfulness"]
    assert runtime.answer_relevancy is symbols["AnswerRelevancy"]
    assert runtime.context_precision is symbols["ContextPrecisionWithoutReference"]


def scorer_runtime(events: list[object], *, metric_error: Exception | None = None) -> object:
    class JudgeClient:
        def __init__(self, **kwargs: object) -> None:
            events.append(("judge-client", kwargs))

        async def close(self) -> None:
            events.append("judge-close")

    class EmbeddingClient:
        def __init__(self, **kwargs: object) -> None:
            events.append(("embedding-client", kwargs))

        def close(self) -> None:
            events.append("embedding-close")

    class Metric:
        def __init__(self, name: str, **kwargs: object) -> None:
            self.name = name
            events.append((name, kwargs))

        async def ascore(self, **kwargs: object) -> SimpleNamespace:
            events.append((f"{self.name}-score", kwargs))
            if metric_error is not None:
                raise metric_error
            values = {"faithfulness": 0.85, "relevance": 0.8, "precision": 0.8}
            return SimpleNamespace(value=values[self.name])

    def llm_factory(*args: object, **kwargs: object) -> str:
        events.append(("llm-factory", args, kwargs))
        return "llm"

    def embedding_factory(*args: object, **kwargs: object) -> str:
        events.append(("embedding-factory", args, kwargs))
        return "embeddings"

    return quality_runner.RagasRuntime(
        async_openai=JudgeClient,
        genai_client=EmbeddingClient,
        llm_factory=llm_factory,
        embedding_factory=embedding_factory,
        faithfulness=lambda **kwargs: Metric("faithfulness", **kwargs),
        answer_relevancy=lambda **kwargs: Metric("relevance", **kwargs),
        context_precision=lambda **kwargs: Metric("precision", **kwargs),
    )


def one_evaluation_sample() -> EvaluationSample:
    return EvaluationSample("q1", "Question", "Answer [S1]", ["Evidence"], ["S1"], ["S1"], True)


def test_build_ragas_scorer_constructs_current_clients_metrics_and_closes_them() -> None:
    events: list[object] = []
    scorer = quality_runner.build_ragas_scorer("secret-key", "gemini-judge", runtime=scorer_runtime(events))

    assert scorer([one_evaluation_sample()]) == required_report()
    assert events == [
        ("judge-client", {"api_key": "secret-key", "base_url": quality_runner.GEMINI_OPENAI_BASE_URL}),
        ("embedding-client", {"api_key": "secret-key"}),
        (
            "llm-factory",
            ("gemini-judge",),
            {"provider": "openai", "client": ANY, "max_tokens": quality_runner.JUDGE_MAX_TOKENS},
        ),
        ("embedding-factory", ("google",), {"model": "gemini-embedding-001", "client": ANY, "interface": "modern"}),
        ("faithfulness", {"llm": "llm"}),
        ("relevance", {"llm": "llm", "embeddings": "embeddings"}),
        ("precision", {"llm": "llm"}),
        ("faithfulness-score", {"user_input": "Question", "response": "Answer [S1]", "retrieved_contexts": ["Evidence"]}),
        ("relevance-score", {"user_input": "Question", "response": "Answer [S1]"}),
        ("precision-score", {"user_input": "Question", "response": "Answer [S1]", "retrieved_contexts": ["Evidence"]}),
        "judge-close",
        "embedding-close",
    ]


def test_build_ragas_scorer_closes_both_clients_when_scoring_fails() -> None:
    events: list[object] = []
    scorer = quality_runner.build_ragas_scorer(
        "secret-key", "gemini-judge", runtime=scorer_runtime(events, metric_error=RuntimeError("judge failed"))
    )

    with pytest.raises(RuntimeError, match="judge failed"):
        scorer([one_evaluation_sample()])
    assert events[-2:] == ["judge-close", "embedding-close"]


def test_run_evaluation_writes_only_aggregate_scores_and_safe_identifiers(tmp_path: Path) -> None:
    golden_path = tmp_path / "golden.json"
    output_path = tmp_path / "quality.json"
    entries = [
        {"id": f"safe-{index}", "query": f"private prompt {index}", "expected_documents": ["jan-2026"], "expected_topic": "topic", "expected_page_range": [1, 2]}
        for index in range(10)
    ]
    golden_path.write_text(json.dumps(entries), encoding="utf-8")

    def endpoint(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text=complete_sse())

    def scorer(samples: list[EvaluationSample]) -> QualityReport:
        assert len(samples) == 10
        return required_report()

    with httpx.Client(transport=httpx.MockTransport(endpoint)) as client:
        exit_code = run_evaluation(
            base_url="https://secret-host.invalid",
            golden_path=golden_path,
            output_path=output_path,
            judge_model="gemini-evaluator",
            scorer=scorer,
            client=client,
            clock=stream_clock(),
        )

    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert exit_code == 0
    assert payload == {
        "schema_version": 1,
        "evaluation_id": "sgcare-golden-v2",
        "judge_model": "gemini-evaluator",
        "golden_query_ids": [f"safe-{index}" for index in range(10)],
        "query_count": 10,
        "scores": REQUIRED_FLOORS,
        "latency_p95_ms": {"complete_p95_ms": 22, "first_token_p95_ms": 12, "sources_p95_ms": 7},
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
        for index in range(10)
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


def test_run_evaluation_fails_when_live_latency_exceeds_a_ceiling(tmp_path: Path) -> None:
    golden_path = tmp_path / "golden.json"
    output_path = tmp_path / "quality.json"
    golden_path.write_text(json.dumps(golden_entries()), encoding="utf-8")
    with httpx.Client(transport=httpx.MockTransport(lambda _: httpx.Response(200, text=complete_sse()))) as client:
        exit_code = run_evaluation(
            base_url="https://study.invalid",
            golden_path=golden_path,
            output_path=output_path,
            judge_model="gemini-evaluator",
            scorer=lambda _: required_report(),
            client=client,
            clock=stream_clock(complete_ms=15001),
        )
    assert exit_code == 1
    assert json.loads(output_path.read_text(encoding="utf-8"))["passed"] is False


def test_parse_args_applies_defaults_and_accepts_explicit_overrides() -> None:
    defaults = quality_runner.parse_args(["--base-url", "https://study.invalid", "--output", "result.json"])
    assert defaults.base_url == "https://study.invalid"
    assert defaults.output == Path("result.json")
    assert defaults.golden == Path("evaluation/golden-queries.json")
    assert defaults.judge_model == quality_runner.DEFAULT_JUDGE_MODEL

    custom = quality_runner.parse_args([
        "--base-url", "http://127.0.0.1:3000/", "--output", "custom.json",
        "--golden", "custom-golden.json", "--judge-model", "custom-judge",
    ])
    assert custom.golden == Path("custom-golden.json")
    assert custom.judge_model == "custom-judge"


def test_main_rejects_a_missing_or_blank_live_key(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("GEMINI_API_KEY", "   ")
    with pytest.raises(SystemExit, match="GEMINI_API_KEY is required"):
        quality_runner.main(["--base-url", "https://study.invalid", "--output", str(tmp_path / "result.json")])


def test_main_builds_the_scorer_and_runs_with_a_managed_http_client(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    calls: list[object] = []
    scorer = lambda _: required_report()  # noqa: E731

    class ClientContext:
        def __enter__(self) -> str:
            calls.append("client-enter")
            return "managed-client"

        def __exit__(self, *args: object) -> None:
            calls.append(("client-exit", args))

    def build(api_key: str, judge_model: str) -> object:
        calls.append(("build", api_key, judge_model))
        return scorer

    def run(**kwargs: object) -> int:
        calls.append(("run", kwargs))
        return 17

    monkeypatch.setenv("GEMINI_API_KEY", " authorized-key ")
    monkeypatch.setattr(quality_runner, "build_ragas_scorer", build)
    monkeypatch.setattr(quality_runner.httpx, "Client", ClientContext)
    monkeypatch.setattr(quality_runner, "run_evaluation", run)
    output = tmp_path / "result.json"
    golden = tmp_path / "golden.json"

    result = quality_runner.main([
        "--base-url", "https://study.invalid", "--output", str(output),
        "--golden", str(golden), "--judge-model", "custom-judge",
    ])

    assert result == 17
    assert calls[0] == ("build", "authorized-key", "custom-judge")
    assert calls[1] == "client-enter"
    assert calls[2] == ("run", {
        "base_url": "https://study.invalid",
        "golden_path": golden,
        "output_path": output,
        "judge_model": "custom-judge",
        "scorer": scorer,
        "client": "managed-client",
    })
    assert calls[3][0] == "client-exit"  # type: ignore[index]
