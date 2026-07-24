from __future__ import annotations

import unittest

from backend.rag.claim_evidence import (
    ClaimSupportStatus,
    GeneratedClaim,
    verify_claim_evidence,
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


if __name__ == "__main__":
    unittest.main()
