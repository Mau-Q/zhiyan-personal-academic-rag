"""Optional fixed Cross-Encoder post-processing for authorized online RRF candidates."""

from __future__ import annotations

import json
import math
import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal, Protocol

from backend.evaluation.reranker import directory_sha256
from backend.retrieval.online import OnlineVisibilityUnavailableError


JsonObject = dict[str, Any]
ONLINE_RERANKER_BACKEND = "online_fixed_cross_encoder_bge_v2_m3_v1"
ONLINE_RERANKER_APPLIED_WARNING = (
    "ONLINE_POSTGRES_READY_ES_MILVUS_RRF_BGE_RERANKER_V2_M3_FAKE_LLM"
)
ONLINE_RERANKER_FALLBACK_WARNING = (
    "ONLINE_POSTGRES_READY_ES_MILVUS_RRF_RERANKER_FALLBACK_FAKE_LLM"
)
ONLINE_RERANKER_EXECUTION_BOUNDARY = (
    "ONLINE_POSTGRES_READY_ES_MILVUS_RRF_BGE_RERANKER_V2_M3_FAKE_LLM"
)
_CONFIG_KEYS = {
    "schema_version",
    "candidate_top_k",
    "failure_policy",
    "model",
}
_MODEL_KEYS = {
    "provider",
    "model_id",
    "revision",
    "snapshot_sha256",
    "max_length",
    "batch_size",
    "device",
    "trust_remote_code",
    "input_template",
}


class OnlineCrossEncoderScorer(Protocol):
    def score(self, pairs: Sequence[tuple[str, str]]) -> list[float]: ...


class OnlineDocumentTitleProvider(Protocol):
    def resolve_titles(
        self,
        *,
        owner_id: str,
        document_ids: Sequence[str],
    ) -> Mapping[str, str]: ...


@dataclass(frozen=True)
class OnlineRerankerConfig:
    candidate_top_k: int
    failure_policy: Literal["FALLBACK_TO_AUTHORIZED_RRF"]
    model: Mapping[str, Any]


@dataclass(frozen=True)
class OnlineRerankOutcome:
    chunks: tuple[JsonObject, ...]
    status: Literal["APPLIED", "FALLBACK", "NO_EVIDENCE"]
    failure_code: str | None
    candidate_count: int
    output_count: int
    reranker_latency_ms: float


class StaticDocumentTitleProvider:
    """Server-owned title mapping for one already-authorized runtime scope."""

    def __init__(self, titles: Mapping[str, str]) -> None:
        if not titles or any(
            not isinstance(document_id, str)
            or not document_id
            or not isinstance(title, str)
            or not title.strip()
            for document_id, title in titles.items()
        ):
            raise ValueError("online Reranker title mapping is invalid")
        self._titles = {document_id: title.strip() for document_id, title in titles.items()}

    def resolve_titles(
        self,
        *,
        owner_id: str,
        document_ids: Sequence[str],
    ) -> Mapping[str, str]:
        if not owner_id:
            raise ValueError("online Reranker owner identity is missing")
        requested = tuple(document_ids)
        if len(requested) != len(set(requested)):
            raise ValueError("online Reranker document identities are duplicated")
        return {
            document_id: self._titles[document_id]
            for document_id in requested
            if document_id in self._titles
        }


def load_online_reranker_config(path: Path) -> OnlineRerankerConfig:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict) or set(value) != _CONFIG_KEYS:
        raise ValueError("online Reranker config fields are invalid")
    if value["schema_version"] != "online_fixed_cross_encoder_config_v1":
        raise ValueError("unsupported online Reranker config")
    if value["failure_policy"] != "FALLBACK_TO_AUTHORIZED_RRF":
        raise ValueError("online Reranker failure policy is invalid")
    if (
        not isinstance(value["candidate_top_k"], int)
        or not 3 <= value["candidate_top_k"] <= 50
    ):
        raise ValueError("online Reranker candidate_top_k is invalid")
    model = value["model"]
    if not isinstance(model, dict) or set(model) != _MODEL_KEYS:
        raise ValueError("online Reranker model fields are invalid")
    if model["provider"] != "sentence_transformers_cross_encoder":
        raise ValueError("online Reranker provider is invalid")
    if model["input_template"] != "question_title_section_text_v1":
        raise ValueError("online Reranker input template is invalid")
    if model["trust_remote_code"] is not False:
        raise ValueError("online Reranker must not trust remote code")
    for field in ("model_id", "revision", "snapshot_sha256", "device"):
        if not isinstance(model[field], str) or not model[field]:
            raise ValueError(f"online Reranker model {field} is invalid")
    if len(model["revision"]) != 40 or any(
        character not in "0123456789abcdef" for character in model["revision"]
    ):
        raise ValueError("online Reranker revision is invalid")
    if len(model["snapshot_sha256"]) != 64 or any(
        character not in "0123456789abcdef"
        for character in model["snapshot_sha256"]
    ):
        raise ValueError("online Reranker snapshot_sha256 is invalid")
    if not isinstance(model["max_length"], int) or model["max_length"] != 512:
        raise ValueError("online Reranker max_length is invalid")
    if not isinstance(model["batch_size"], int) or model["batch_size"] != 16:
        raise ValueError("online Reranker batch_size is invalid")
    return OnlineRerankerConfig(
        candidate_top_k=value["candidate_top_k"],
        failure_policy=value["failure_policy"],
        model=dict(model),
    )


def _passage(chunk: Mapping[str, Any], titles: Mapping[str, str]) -> str:
    document_id = chunk.get("document_id")
    section_path = chunk.get("section_path")
    text = chunk.get("text")
    if not isinstance(document_id, str) or document_id not in titles:
        raise LookupError("online Reranker document title is unavailable")
    if not isinstance(section_path, str) or not section_path:
        raise ValueError("online Reranker candidate section is invalid")
    if not isinstance(text, str) or not text:
        raise ValueError("online Reranker candidate text is invalid")
    return f"Title: {titles[document_id]}\nSection: {section_path}\n{text}"


class SentenceTransformersOnlineCrossEncoder:
    """Pinned optional runtime loader; importing the base package stays lightweight."""

    def __init__(
        self,
        *,
        config: OnlineRerankerConfig,
        cache_dir: Path,
    ) -> None:
        try:
            from huggingface_hub import snapshot_download
            from sentence_transformers import CrossEncoder
        except ImportError as exc:
            raise RuntimeError("online Reranker dependencies are unavailable") from exc
        model = config.model
        snapshot = Path(
            snapshot_download(
                repo_id=str(model["model_id"]),
                revision=str(model["revision"]),
                cache_dir=cache_dir,
            )
        )
        if directory_sha256(snapshot) != model["snapshot_sha256"]:
            raise RuntimeError("online Reranker model snapshot identity drifted")
        self.encoder = CrossEncoder(
            str(snapshot),
            device=str(model["device"]),
            max_length=int(model["max_length"]),
            trust_remote_code=False,
        )
        self.batch_size = int(model["batch_size"])

    def score(self, pairs: Sequence[tuple[str, str]]) -> list[float]:
        values = self.encoder.predict(
            list(pairs),
            batch_size=self.batch_size,
            show_progress_bar=False,
            convert_to_numpy=True,
        )
        return [float(value) for value in values.reshape(-1).tolist()]


class OnlineFixedCrossEncoderReranker:
    """Rerank only an already-authorized candidate set, with bounded safe fallback."""

    def __init__(
        self,
        *,
        config: OnlineRerankerConfig,
        scorer: OnlineCrossEncoderScorer,
        title_provider: OnlineDocumentTitleProvider,
    ) -> None:
        self.config = config
        self.scorer = scorer
        self.title_provider = title_provider

    def rerank(
        self,
        question: str,
        candidates: Sequence[Mapping[str, Any]],
        *,
        owner_id: str,
        document_ids: Sequence[str],
        top_k: int,
    ) -> OnlineRerankOutcome:
        started = time.perf_counter()
        if not isinstance(question, str) or not question.strip():
            raise ValueError("online Reranker question is invalid")
        normalized = [dict(candidate) for candidate in candidates]
        self._validate_authorized_candidates(
            normalized,
            owner_id=owner_id,
            document_ids=document_ids,
            top_k=top_k,
        )
        if not normalized:
            return OnlineRerankOutcome(
                chunks=(),
                status="NO_EVIDENCE",
                failure_code=None,
                candidate_count=0,
                output_count=0,
                reranker_latency_ms=(time.perf_counter() - started) * 1000,
            )
        try:
            candidate_document_ids = tuple(
                dict.fromkeys(str(candidate["document_id"]) for candidate in normalized)
            )
            titles = self.title_provider.resolve_titles(
                owner_id=owner_id,
                document_ids=candidate_document_ids,
            )
            pairs = [(question, _passage(candidate, titles)) for candidate in normalized]
        except Exception:
            return self._fallback(
                normalized,
                top_k=top_k,
                started=started,
                failure_code="TITLE_OR_TEMPLATE_UNAVAILABLE",
            )
        try:
            scores = self.scorer.score(pairs)
        except Exception:
            return self._fallback(
                normalized,
                top_k=top_k,
                started=started,
                failure_code="MODEL_SCORING_UNAVAILABLE",
            )
        if len(scores) != len(normalized) or any(
            not isinstance(score, (int, float))
            or isinstance(score, bool)
            or not math.isfinite(float(score))
            for score in scores
        ):
            return self._fallback(
                normalized,
                top_k=top_k,
                started=started,
                failure_code="MODEL_SCORE_INVALID",
            )
        ordered = sorted(
            range(len(normalized)),
            key=lambda index: (
                -float(scores[index]),
                index,
                str(normalized[index]["chunk_id"]),
            ),
        )
        selected = tuple(normalized[index] for index in ordered[:top_k])
        if not {str(chunk["chunk_id"]) for chunk in selected}.issubset(
            {str(chunk["chunk_id"]) for chunk in normalized}
        ):
            raise OnlineVisibilityUnavailableError(
                "online Reranker expanded the authorized candidate set"
            )
        return OnlineRerankOutcome(
            chunks=selected,
            status="APPLIED",
            failure_code=None,
            candidate_count=len(normalized),
            output_count=len(selected),
            reranker_latency_ms=(time.perf_counter() - started) * 1000,
        )

    def _validate_authorized_candidates(
        self,
        candidates: Sequence[Mapping[str, Any]],
        *,
        owner_id: str,
        document_ids: Sequence[str],
        top_k: int,
    ) -> None:
        if not isinstance(top_k, int) or isinstance(top_k, bool):
            raise ValueError("online Reranker top_k is invalid")
        if (
            top_k < 1
            or top_k > self.config.candidate_top_k
            or len(candidates) > self.config.candidate_top_k
        ):
            raise ValueError("online Reranker candidate or output bound is invalid")
        requested = set(document_ids)
        chunk_ids: set[str] = set()
        for candidate in candidates:
            chunk_id = candidate.get("chunk_id")
            document_id = candidate.get("document_id")
            version_id = candidate.get("version_id")
            if (
                not isinstance(chunk_id, str)
                or not chunk_id
                or chunk_id in chunk_ids
                or candidate.get("tenant_id") != owner_id
                or not isinstance(document_id, str)
                or not isinstance(version_id, str)
                or not version_id
                or (requested and document_id not in requested)
                or candidate.get("is_active") is not True
            ):
                raise OnlineVisibilityUnavailableError(
                    "online Reranker candidate violates authorized READY identity"
                )
            chunk_ids.add(chunk_id)

    @staticmethod
    def _fallback(
        candidates: Sequence[JsonObject],
        *,
        top_k: int,
        started: float,
        failure_code: str,
    ) -> OnlineRerankOutcome:
        selected = tuple(dict(candidate) for candidate in candidates[:top_k])
        return OnlineRerankOutcome(
            chunks=selected,
            status="FALLBACK",
            failure_code=failure_code,
            candidate_count=len(candidates),
            output_count=len(selected),
            reranker_latency_ms=(time.perf_counter() - started) * 1000,
        )
