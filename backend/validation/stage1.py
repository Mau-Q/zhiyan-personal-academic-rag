"""Fail-closed Stage 1 reconciliation across PostgreSQL, ES, and Milvus."""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import asdict, dataclass

from backend.retrieval.online import ReadyVersionRepository, VersionRouteInspector
from backend.storage.models import IndexState, LifecycleStatus


_CONTRACT_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")


class Stage1ReconciliationError(RuntimeError):
    """Raised when the three stores cannot prove one identical online scope."""


@dataclass(frozen=True)
class ReconciledVersion:
    document_id: str
    document_version_id: str
    content_sha256: str
    source_snapshot_sha256: str
    parse_version: str
    elasticsearch_index: str
    milvus_collection: str


@dataclass(frozen=True)
class Stage1ReconciliationReport:
    schema_version: str
    status: str
    owner_id: str
    requested_document_ids: tuple[str, ...]
    versions: tuple[ReconciledVersion, ...]

    def model_dump(self) -> dict[str, object]:
        """Return a JSON-ready report without content, credentials, or endpoints."""

        return asdict(self)


def reconcile_ready_scope(
    *,
    repository: ReadyVersionRepository,
    elasticsearch: VersionRouteInspector,
    milvus: VersionRouteInspector,
    owner_id: str,
    document_ids: Sequence[str],
) -> Stage1ReconciliationReport:
    """Prove exact READY truth and both physical routes for an owner scope."""

    requested = tuple(document_ids)
    if (
        not _CONTRACT_ID_PATTERN.fullmatch(owner_id)
        or not requested
        or len(requested) != len(set(requested))
        or any(not _CONTRACT_ID_PATTERN.fullmatch(value) for value in requested)
    ):
        raise Stage1ReconciliationError("reconciliation scope identity is invalid")

    try:
        versions = repository.resolve_online_versions(
            owner_id=owner_id,
            document_ids=requested,
        )
    except Exception as exc:
        raise Stage1ReconciliationError(
            "PostgreSQL READY truth could not be resolved"
        ) from exc

    by_document = {version.document_id: version for version in versions}
    if len(by_document) != len(versions) or set(by_document) != set(requested):
        raise Stage1ReconciliationError(
            "PostgreSQL READY truth does not match the requested document scope"
        )

    reconciled: list[ReconciledVersion] = []
    for document_id in sorted(requested):
        version = by_document[document_id]
        if (
            version.owner_id != owner_id
            or version.lifecycle_status is not LifecycleStatus.READY
            or not version.is_active
            or version.index_states.elasticsearch_chunks is not IndexState.READY
            or version.index_states.milvus_vectors is not IndexState.READY
        ):
            raise Stage1ReconciliationError(
                "PostgreSQL returned a version outside the READY contract"
            )
        try:
            elasticsearch_index = elasticsearch.verify_online_version(
                owner_id=owner_id,
                document_id=document_id,
                document_version_id=version.document_version_id,
            )
            milvus_collection = milvus.verify_online_version(
                owner_id=owner_id,
                document_id=document_id,
                document_version_id=version.document_version_id,
            )
        except Exception as exc:
            raise Stage1ReconciliationError(
                "a READY physical route could not prove matching active data"
            ) from exc
        reconciled.append(
            ReconciledVersion(
                document_id=document_id,
                document_version_id=version.document_version_id,
                content_sha256=version.content_sha256,
                source_snapshot_sha256=version.source_snapshot_sha256,
                parse_version=version.parse_version,
                elasticsearch_index=elasticsearch_index,
                milvus_collection=milvus_collection,
            )
        )

    return Stage1ReconciliationReport(
        schema_version="stage1_reconciliation_report_v1",
        status="PASS",
        owner_id=owner_id,
        requested_document_ids=requested,
        versions=tuple(reconciled),
    )
