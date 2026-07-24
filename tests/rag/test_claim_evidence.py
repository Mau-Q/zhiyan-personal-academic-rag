from __future__ import annotations

import unittest

from backend.rag.claim_evidence import (
    ClaimSupportStatus,
    EvidenceSetStatus,
    GeneratedClaim,
    verify_claim_evidence,
    verify_claim_evidence_sets,
)


EVIDENCE = [
    {
        "quote": "The study enrolled 240 participants and used five-fold cross-validation."
    },
    {
        "quote": "The abstract reports a 12-week observation window."
    },
    {
        "quote": "The revised final analysis uses a 16-week observation window."
    },
]

OWNER_ID = "owner_001"
ACTIVE_VERSIONS = {
    "document_alpha": "version_alpha_002",
    "document_beta": "version_beta_001",
}


def internal_evidence(
    *,
    chunk_id: str,
    document_id: str = "document_alpha",
    version_id: str = "version_alpha_002",
    text: str,
    owner_id: str = OWNER_ID,
    is_active: bool = True,
    previous_chunk_id: str | None = None,
    next_chunk_id: str | None = None,
) -> dict[str, object]:
    return {
        "chunk_id": chunk_id,
        "document_id": document_id,
        "version_id": version_id,
        "text": text,
        "owner_id": owner_id,
        "tenant_id": owner_id,
        "is_active": is_active,
        "previous_chunk_id": previous_chunk_id,
        "next_chunk_id": next_chunk_id,
    }


class ClaimEvidenceVerificationTests(unittest.TestCase):
    def test_supported_claim_keeps_bound_numeric_and_lexical_anchors(self):
        report = verify_claim_evidence(
            (
                GeneratedClaim(
                    text="The study enrolled 240 participants.",
                    citation_ids=(1,),
                ),
            ),
            EVIDENCE,
        )

        self.assertEqual(report.records[0].status, ClaimSupportStatus.SUPPORTED)
        self.assertEqual(report.citation_completeness, 1.0)
        self.assertEqual(report.unsupported_claim_rate, 0.0)

    def test_unbound_number_fails_closed(self):
        report = verify_claim_evidence(
            (
                GeneratedClaim(
                    text="The study enrolled 999 participants.",
                    citation_ids=(1,),
                ),
            ),
            EVIDENCE,
        )

        self.assertEqual(report.records[0].status, ClaimSupportStatus.UNSUPPORTED)
        self.assertEqual(
            report.records[0].reason_codes,
            ("NUMERIC_ANCHOR_MISSING_FROM_EVIDENCE",),
        )
        self.assertEqual(report.retained_claims, ())

    def test_generic_academic_words_do_not_establish_core_support(self):
        report = verify_claim_evidence(
            (
                GeneratedClaim(
                    text="The study examines ocean salinity.",
                    citation_ids=(1,),
                ),
            ),
            EVIDENCE,
        )

        self.assertEqual(report.records[0].status, ClaimSupportStatus.UNSUPPORTED)
        self.assertEqual(
            report.records[0].reason_codes,
            ("CORE_LEXICAL_OVERLAP_NOT_ESTABLISHED",),
        )

    def test_numeric_conflict_must_be_disclosed_with_both_values(self):
        disclosed = verify_claim_evidence(
            (
                GeneratedClaim(
                    text=(
                        "The evidence conflicts: the abstract reports 12 weeks, "
                        "whereas the final analysis uses 16 weeks."
                    ),
                    citation_ids=(2, 3),
                ),
            ),
            EVIDENCE,
        )
        omitted = verify_claim_evidence(
            (
                GeneratedClaim(
                    text="The observation window is 12 weeks.",
                    citation_ids=(2, 3),
                ),
            ),
            EVIDENCE,
        )

        self.assertEqual(
            disclosed.records[0].status,
            ClaimSupportStatus.CONFLICTING_EVIDENCE,
        )
        self.assertEqual(omitted.records[0].status, ClaimSupportStatus.UNSUPPORTED)
        self.assertEqual(
            omitted.records[0].reason_codes,
            ("BOUND_NUMERIC_CONFLICT_NOT_DISCLOSED",),
        )

    def test_conflict_disclosure_cannot_carry_an_unbound_extra_clause(self):
        report = verify_claim_evidence(
            (
                GeneratedClaim(
                    text=(
                        "The evidence conflicts between 12 weeks and 16 weeks; "
                        "ocean salinity is high."
                    ),
                    citation_ids=(2, 3),
                ),
            ),
            EVIDENCE,
        )

        self.assertEqual(report.records[0].status, ClaimSupportStatus.UNSUPPORTED)
        self.assertEqual(
            report.records[0].reason_codes,
            ("CORE_LEXICAL_OVERLAP_NOT_ESTABLISHED",),
        )

    def test_safe_limitation_is_retained_without_claiming_support(self):
        report = verify_claim_evidence(
            (
                GeneratedClaim(
                    text="The available evidence does not report the funder.",
                    citation_ids=(1,),
                ),
            ),
            EVIDENCE,
        )

        self.assertEqual(
            report.records[0].status,
            ClaimSupportStatus.INSUFFICIENT_EVIDENCE,
        )
        self.assertEqual(report.retained_claims[0].citation_ids, (1,))

    def test_report_exposes_partial_answer_boundary(self):
        report = verify_claim_evidence(
            (
                GeneratedClaim(
                    text="The study enrolled 240 participants.",
                    citation_ids=(1,),
                ),
                GeneratedClaim(
                    text="The study enrolled 999 participants.",
                    citation_ids=(1,),
                ),
            ),
            EVIDENCE,
        )

        self.assertTrue(report.is_partial_answer)
        self.assertEqual(len(report.retained_claims), 1)
        self.assertEqual(report.unsupported_claim_rate, 0.5)


class MultiEvidenceSetVerificationTests(unittest.TestCase):
    def verify(
        self,
        claim: GeneratedClaim,
        evidence: list[dict[str, object]],
        *,
        active_chunk_identities: dict[str, tuple[str, str]] | None = None,
    ):
        chunk_identities = active_chunk_identities or {
            str(item["chunk_id"]): (
                str(item["document_id"]),
                str(item["version_id"]),
            )
            for item in evidence
        }
        return verify_claim_evidence_sets(
            (claim,),
            evidence,
            expected_owner_id=OWNER_ID,
            active_document_versions=ACTIVE_VERSIONS,
            active_chunk_identities=chunk_identities,
        ).records[0]

    def test_single_evidence_forms_supported_deterministic_set(self):
        record = self.verify(
            GeneratedClaim(
                text="The study enrolled 240 participants.",
                citation_ids=(1,),
            ),
            [
                internal_evidence(
                    chunk_id="chunk_alpha_001",
                    text="The study enrolled 240 participants.",
                )
            ],
        )

        self.assertEqual(
            record.status,
            EvidenceSetStatus.SUPPORTED_BY_EVIDENCE_SET,
        )
        self.assertEqual(record.evidence_set.citation_ids, (1,))
        self.assertEqual(record.evidence_set.chunk_ids, ("chunk_alpha_001",))
        self.assertFalse(record.evidence_set.adjacent_chunk_added)

    def test_multiple_evidence_collectively_supports_claim(self):
        record = self.verify(
            GeneratedClaim(
                text="The study enrolled 240 participants; "
                "the observation window was 12 weeks.",
                citation_ids=(1, 2),
            ),
            [
                internal_evidence(
                    chunk_id="chunk_alpha_001",
                    text="The study enrolled 240 participants.",
                    next_chunk_id="chunk_alpha_002",
                ),
                internal_evidence(
                    chunk_id="chunk_alpha_002",
                    text="The observation window was 12 weeks.",
                    previous_chunk_id="chunk_alpha_001",
                ),
            ],
        )

        self.assertEqual(
            record.status,
            EvidenceSetStatus.SUPPORTED_BY_EVIDENCE_SET,
        )
        self.assertEqual(record.evidence_set.citation_ids, (1, 2))

    def test_cross_version_evidence_fails_closed(self):
        record = self.verify(
            GeneratedClaim(
                text="The study enrolled 240 participants.",
                citation_ids=(1, 2),
            ),
            [
                internal_evidence(
                    chunk_id="chunk_alpha_old",
                    version_id="version_alpha_001",
                    text="The study enrolled 200 participants.",
                ),
                internal_evidence(
                    chunk_id="chunk_alpha_current",
                    text="The study enrolled 240 participants.",
                ),
            ],
        )

        self.assertEqual(
            record.status,
            EvidenceSetStatus.INSUFFICIENT_EVIDENCE,
        )
        self.assertIn(
            record.reason_codes[0],
            {"EVIDENCE_SET_CROSS_VERSION", "EVIDENCE_VERSION_NOT_CURRENT"},
        )

    def test_owner_mismatch_fails_closed(self):
        record = self.verify(
            GeneratedClaim(text="The study enrolled 240 participants.", citation_ids=(1,)),
            [
                internal_evidence(
                    chunk_id="chunk_alpha_001",
                    text="The study enrolled 240 participants.",
                    owner_id="owner_other",
                )
            ],
        )

        self.assertEqual(
            record.status,
            EvidenceSetStatus.INSUFFICIENT_EVIDENCE,
        )
        self.assertEqual(record.reason_codes, ("EVIDENCE_OWNER_MISMATCH",))

    def test_inactive_evidence_fails_closed(self):
        record = self.verify(
            GeneratedClaim(text="The study enrolled 240 participants.", citation_ids=(1,)),
            [
                internal_evidence(
                    chunk_id="chunk_alpha_001",
                    text="The study enrolled 240 participants.",
                    is_active=False,
                )
            ],
        )

        self.assertEqual(
            record.status,
            EvidenceSetStatus.INSUFFICIENT_EVIDENCE,
        )
        self.assertEqual(record.reason_codes, ("EVIDENCE_VERSION_NOT_ACTIVE",))

    def test_chunk_document_version_identity_mismatch_fails_closed(self):
        record = self.verify(
            GeneratedClaim(text="The study enrolled 240 participants.", citation_ids=(1,)),
            [
                internal_evidence(
                    chunk_id="chunk_alpha_001",
                    text="The study enrolled 240 participants.",
                )
            ],
            active_chunk_identities={
                "chunk_alpha_001": ("document_beta", "version_beta_001")
            },
        )

        self.assertEqual(
            record.status,
            EvidenceSetStatus.INSUFFICIENT_EVIDENCE,
        )
        self.assertEqual(
            record.reason_codes,
            ("EVIDENCE_CHUNK_IDENTITY_NOT_CURRENT",),
        )

    def test_numeric_unit_conflict_is_exposed(self):
        record = self.verify(
            GeneratedClaim(
                text="The observation window is 12 weeks.",
                citation_ids=(1, 2),
            ),
            [
                internal_evidence(
                    chunk_id="chunk_alpha_001",
                    text="The abstract reports a 12-week observation window.",
                ),
                internal_evidence(
                    chunk_id="chunk_alpha_002",
                    text="The final analysis reports a 16-week observation window.",
                ),
            ],
        )

        self.assertEqual(
            record.status,
            EvidenceSetStatus.CONFLICTING_EVIDENCE,
        )
        self.assertEqual(
            record.reason_codes,
            ("BOUND_NUMERIC_CONFLICT_NOT_DISCLOSED",),
        )

    def test_number_with_wrong_unit_is_not_supported(self):
        record = self.verify(
            GeneratedClaim(
                text="The observation window was 12 weeks.",
                citation_ids=(1,),
            ),
            [
                internal_evidence(
                    chunk_id="chunk_alpha_001",
                    text="The observation window was 12 days.",
                )
            ],
        )

        self.assertEqual(
            record.status,
            EvidenceSetStatus.INSUFFICIENT_EVIDENCE,
        )
        self.assertEqual(record.reason_codes, ("NUMERIC_UNIT_NOT_ESTABLISHED",))

    def test_partially_supported_when_only_one_clause_is_established(self):
        record = self.verify(
            GeneratedClaim(
                text="The study enrolled 240 participants; "
                "the study measured ocean salinity.",
                citation_ids=(1,),
            ),
            [
                internal_evidence(
                    chunk_id="chunk_alpha_001",
                    text="The study enrolled 240 participants.",
                )
            ],
        )

        self.assertEqual(
            record.status,
            EvidenceSetStatus.PARTIALLY_SUPPORTED,
        )

    def test_one_reciprocal_neighbor_can_be_added_without_score_change(self):
        record = self.verify(
            GeneratedClaim(
                text="The observation window was 12 weeks.",
                citation_ids=(1,),
            ),
            [
                internal_evidence(
                    chunk_id="chunk_alpha_001",
                    text="The study describes its observation protocol.",
                    next_chunk_id="chunk_alpha_002",
                ),
                internal_evidence(
                    chunk_id="chunk_alpha_002",
                    text="The observation window was 12 weeks.",
                    previous_chunk_id="chunk_alpha_001",
                ),
                internal_evidence(
                    chunk_id="chunk_beta_001",
                    document_id="document_beta",
                    version_id="version_beta_001",
                    text="The observation window was 12 weeks.",
                ),
            ],
        )

        self.assertEqual(
            record.status,
            EvidenceSetStatus.SUPPORTED_BY_EVIDENCE_SET,
        )
        self.assertEqual(record.evidence_set.citation_ids, (1, 2))
        self.assertTrue(record.evidence_set.adjacent_chunk_added)
        self.assertIn("RETRIEVAL_SCORE_UNCHANGED", record.reason_codes)

    def test_non_reciprocal_or_cross_document_candidate_is_not_added(self):
        record = self.verify(
            GeneratedClaim(
                text="The observation window was 12 weeks.",
                citation_ids=(1,),
            ),
            [
                internal_evidence(
                    chunk_id="chunk_alpha_001",
                    text="The study describes its observation protocol.",
                    next_chunk_id="chunk_alpha_002",
                ),
                internal_evidence(
                    chunk_id="chunk_beta_001",
                    document_id="document_beta",
                    version_id="version_beta_001",
                    text="The observation window was 12 weeks.",
                    previous_chunk_id="chunk_alpha_001",
                ),
            ],
        )

        self.assertEqual(
            record.status,
            EvidenceSetStatus.INSUFFICIENT_EVIDENCE,
        )
        self.assertEqual(record.evidence_set.citation_ids, (1,))

    def test_comparison_objects_and_qualifier_must_be_present(self):
        supported = self.verify(
            GeneratedClaim(
                text="Under the noisy condition, Model A is better than Model B.",
                citation_ids=(1,),
            ),
            [
                internal_evidence(
                    chunk_id="chunk_alpha_001",
                    text=(
                        "Under the noisy condition, Model A performs better than "
                        "Model B."
                    ),
                )
            ],
        )
        missing_qualifier = self.verify(
            GeneratedClaim(
                text="Under the noisy condition, Model A is better than Model B.",
                citation_ids=(1,),
            ),
            [
                internal_evidence(
                    chunk_id="chunk_alpha_001",
                    text="Model A performs better than Model B.",
                )
            ],
        )

        self.assertEqual(
            supported.status,
            EvidenceSetStatus.SUPPORTED_BY_EVIDENCE_SET,
        )
        self.assertEqual(
            missing_qualifier.status,
            EvidenceSetStatus.PARTIALLY_SUPPORTED,
        )
        self.assertEqual(
            missing_qualifier.reason_codes,
            ("QUALIFYING_CONDITION_NOT_ESTABLISHED",),
        )


if __name__ == "__main__":
    unittest.main()
