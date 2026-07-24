from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from backend.evaluation.claim_evidence_nli import (
    NliCandidateError,
    NliPair,
    PositiveClaimGroup,
    evaluate_nli_candidate,
    load_nli_candidate_config,
)
from scripts.run_phase4_multilingual_nli_gate import build_workload


CONFIG = (
    Path(__file__).resolve().parents[2]
    / "evaluation"
    / "claim_evidence"
    / "phase4-multilingual-nli-rtx4090-v1.json"
)


class FakeScorer:
    def __init__(
        self,
        logits: list[list[float]],
        *,
        token_lengths: list[int] | None = None,
    ):
        self.logits = logits
        self.lengths = token_lengths or [20] * len(logits)

    def score(self, pairs: list[tuple[str, str]]) -> list[list[float]]:
        return self.logits

    def token_lengths(self, pairs: list[tuple[str, str]]) -> list[int]:
        return self.lengths


class Phase4MultilingualNliCandidateTests(unittest.TestCase):
    def setUp(self) -> None:
        self.config = load_nli_candidate_config(CONFIG)
        self.pairs = [
            NliPair("a", "Evidence A", "Claim A"),
            NliPair("b", "Evidence B", "Claim B"),
            NliPair("c", "Evidence C", "Claim C"),
        ]

    def test_frozen_config_keeps_mac_fake_and_remote_cuda_boundary(self) -> None:
        self.assertEqual(self.config.model["mac_execution"], "FAKE_SCORER_ONLY")
        self.assertEqual(self.config.model["remote_device"], "cuda")
        self.assertEqual(self.config.model["remote_dtype"], "float16")
        self.assertFalse(self.config.model["trust_remote_code"])
        self.assertEqual(
            self.config.model["label_mapping"],
            ["entailment", "neutral", "contradiction"],
        )
        self.assertEqual(self.config.scope["test"], "NOT_READ_NOT_RUN")
        self.assertEqual(self.config.scope["acceptance"], "NOT_READ_NOT_RUN")

    def test_positive_only_diagnostic_can_qualify_for_remote_adjudication(self) -> None:
        report = evaluate_nli_candidate(
            config=self.config,
            pairs=self.pairs,
            candidate_supported_pair_keys=["a"],
            candidate_partial_pair_keys=["c"],
            human_positive_claims=[
                PositiveClaimGroup(("a",)),
                PositiveClaimGroup(("b",)),
            ],
            scorer=FakeScorer(
                [
                    [5.0, 0.0, -1.0],
                    [4.0, 0.0, -1.0],
                    [0.0, 4.0, -1.0],
                ]
            ),
        )

        self.assertEqual(report["decision"]["positive_retention_gate"], "PASS")
        self.assertEqual(
            report["decision"]["decision"],
            "ELIGIBLE_FOR_REMOTE_ADJUDICATED_NLI_GATE",
        )
        self.assertFalse(report["decision"]["online_enforcement_enabled"])
        self.assertEqual(
            report["unavailable_metrics"]["precision"],
            "NOT_MEASURABLE_NO_HUMAN_ADJUDICATED_NEGATIVES",
        )
        self.assertNotIn("Evidence A", str(report))

    def test_low_positive_retention_rejects_candidate_without_online_change(self) -> None:
        report = evaluate_nli_candidate(
            config=self.config,
            pairs=self.pairs,
            candidate_supported_pair_keys=["a"],
            candidate_partial_pair_keys=[],
            human_positive_claims=[
                PositiveClaimGroup(("a",)),
                PositiveClaimGroup(("b",)),
            ],
            scorer=FakeScorer(
                [
                    [0.0, 5.0, -1.0],
                    [0.0, 4.0, -1.0],
                    [3.0, 0.0, -1.0],
                ]
            ),
        )

        self.assertEqual(report["decision"]["positive_retention_gate"], "FAIL")
        self.assertEqual(
            report["decision"]["decision"],
            "KEEP_DETERMINISTIC_AUDIT_ONLY_REJECT_NLI_CANDIDATE",
        )
        self.assertFalse(report["decision"]["online_enforcement_enabled"])

    def test_multi_chunk_positive_is_retained_when_any_bound_chunk_entails(self) -> None:
        report = evaluate_nli_candidate(
            config=self.config,
            pairs=self.pairs,
            candidate_supported_pair_keys=["a"],
            candidate_partial_pair_keys=[],
            human_positive_claims=[PositiveClaimGroup(("b", "c"))],
            scorer=FakeScorer(
                [
                    [5.0, 0.0, -1.0],
                    [0.0, 4.0, -1.0],
                    [4.0, 0.0, -1.0],
                ]
            ),
        )

        self.assertEqual(
            report["positive_diagnostics"]["human_finalized_positive_retained"],
            1,
        )

    def test_invalid_or_misaligned_scorer_output_fails_closed(self) -> None:
        with self.assertRaisesRegex(
            NliCandidateError, "NLI_SCORER_OUTPUT_COUNT_INVALID"
        ):
            evaluate_nli_candidate(
                config=self.config,
                pairs=self.pairs,
                candidate_supported_pair_keys=["a"],
                candidate_partial_pair_keys=[],
                human_positive_claims=[PositiveClaimGroup(("a",))],
                scorer=FakeScorer([[1.0, 0.0, -1.0]]),
            )

    def test_config_rejects_online_enforcement_or_holdout_scope(self) -> None:
        text = CONFIG.read_text(encoding="utf-8")
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "config.json"
            path.write_text(
                text.replace(
                    '"candidate_pass_enables_online_enforcement": false',
                    '"candidate_pass_enables_online_enforcement": true',
                ),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(
                NliCandidateError, "NLI_ONLINE_ENFORCEMENT_MUST_REMAIN_DISABLED"
            ):
                load_nli_candidate_config(path)

            path.write_text(
                text.replace('"test": "NOT_READ_NOT_RUN"', '"test": "READ"'),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(NliCandidateError, "NLI_SCOPE_INVALID"):
                load_nli_candidate_config(path)

    def test_workload_uses_evidence_as_premise_and_claim_as_hypothesis(self) -> None:
        private_rows = {
            "q1": {
                "final_labels": {
                    "answerability": "ANSWERABLE",
                    "reference_claims": [{"claim_id": "c1", "text": "声明"}],
                    "chunk_judgments": [
                        {"chunk_id": "e1", "supports_claims": ["c1"]}
                    ],
                },
                "frozen_evidence_chunks": [
                    {"chunk_id": "e1", "text": "Evidence text"}
                ],
            }
        }
        reviews = [
            {
                "question_id": "q1",
                "claim_id": "c1",
                "chunk_id": "e1",
                "relation": "SUPPORTED",
                "citation_complete": "true",
            }
        ]
        pairs, supported, partial, groups = build_workload(
            private_rows=private_rows,
            reviews=reviews,
            expected_candidate_supported=1,
            expected_candidate_partial=0,
            expected_human_positives=1,
        )
        self.assertEqual(
            [(pair.premise, pair.hypothesis) for pair in pairs],
            [("Evidence text", "声明")],
        )
        self.assertEqual(supported, [pairs[0].key])
        self.assertEqual(partial, [])
        self.assertEqual(groups[0].pair_keys, (pairs[0].key,))


if __name__ == "__main__":
    unittest.main()
