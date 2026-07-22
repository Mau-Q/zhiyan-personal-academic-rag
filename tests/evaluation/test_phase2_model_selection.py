from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from backend.rag.generation import GenerationModelIdentity, GenerationResult
from scripts.run_phase2_model_selection import (
    BASE_CASES_SHA256,
    BASELINE_MODEL,
    CANDIDATE_MODEL,
    ModelSelectionGateError,
    SUITE_PATH,
    SUITE_SHA256,
    _canonical_sha256,
    _load_frozen_cases,
    _validate_loopback_url,
    _validate_output_path,
    run_selection,
)


ANSWERS = {
    "该研究纳入了多少样本，并采用什么验证方法评估模型？": (
        "研究纳入240名受试者，开发阶段采用五折交叉验证，并在独立外部测试集上评估。 [1][2]"
    ),
    "在同一测试集上，模型A与模型B的AUROC和灵敏度分别是多少，哪个模型更高？": (
        "模型A的AUROC为0.84、灵敏度为0.78；模型B分别为0.89和0.80，因此模型B更高。 [1][2]"
    ),
    "主要终点的观察窗口是多少周？如果证据存在差异，请明确说明。": (
        "两处证据存在差异：摘要写12 周，修订方案写16 周且最终分析采用16 周。 [1][2]"
    ),
    "这项研究由哪个机构资助？": "现有证据未提供资助机构，无法确定。 [1]",
}


class FakeProvider:
    def __init__(
        self,
        *,
        model: str,
        expected_digest: str,
        base_url: str,
        candidate_regression: bool = False,
        incomplete_candidate: bool = False,
        varying_candidate_wording: bool = False,
    ) -> None:
        del base_url
        self.model = model
        self.candidate_regression = candidate_regression
        self.incomplete_candidate = incomplete_candidate
        self.varying_candidate_wording = varying_candidate_wording
        self.question_calls = {}
        self.identity = GenerationModelIdentity(
            provider="ollama",
            model=model,
            digest=expected_digest,
        )

    def configured_identity(self):
        return self.identity

    def generate(self, question, evidence):
        del evidence
        self.question_calls[question] = self.question_calls.get(question, 0) + 1
        if self.incomplete_candidate and self.model == CANDIDATE_MODEL.model:
            raise RuntimeError("private provider detail")
        answer = ANSWERS[question]
        if (
            self.varying_candidate_wording
            and self.model == CANDIDATE_MODEL.model
            and question == "这项研究由哪个机构资助？"
            and self.question_calls[question] == 2
        ):
            answer = "提供的证据中没有提及本研究的资助机构。 [1]"
        if (
            self.candidate_regression
            and self.model == CANDIDATE_MODEL.model
            and question == "这项研究由哪个机构资助？"
        ):
            answer = "该研究由国家自然科学基金资助。 [1]"
        return GenerationResult(
            answer=answer,
            identity=self.identity,
            prompt_eval_count=120,
            eval_count=24,
        )


class FakeProviderFactory:
    def __init__(
        self,
        *,
        candidate_regression: bool = False,
        incomplete_candidate: bool = False,
        varying_candidate_wording: bool = False,
    ) -> None:
        self.candidate_regression = candidate_regression
        self.incomplete_candidate = incomplete_candidate
        self.varying_candidate_wording = varying_candidate_wording

    def __call__(self, **kwargs):
        return FakeProvider(
            **kwargs,
            candidate_regression=self.candidate_regression,
            incomplete_candidate=self.incomplete_candidate,
            varying_candidate_wording=self.varying_candidate_wording,
        )


class Phase2ModelSelectionTests(unittest.TestCase):
    def test_frozen_suite_and_model_identities_are_exact(self):
        payload = json.loads(SUITE_PATH.read_text(encoding="utf-8"))

        self.assertEqual(_canonical_sha256(payload), SUITE_SHA256)
        cases = _load_frozen_cases()
        self.assertEqual(len(cases), 4)
        self.assertEqual(
            payload["base_cases"]["sha256"],
            BASE_CASES_SHA256,
        )
        insufficient = next(
            case for case in cases if case["case_id"] == "zh.evidence.insufficient"
        )
        self.assertIn(
            "没有提及", insufficient["required_any_term_groups"][0]
        )
        self.assertEqual(BASELINE_MODEL.model, "llama3.2:latest")
        self.assertEqual(
            CANDIDATE_MODEL.digest,
            "bdbd181c33f2ed1b31c972991882db3cf4d192569092138a7d29e973cd9debe8",
        )

    def test_candidate_promotes_only_after_all_fixed_hard_gates_pass(self):
        report = run_selection(
            base_url="http://127.0.0.1:11434",
            provider_factory=FakeProviderFactory(),
        )

        self.assertEqual(report["status"], "PASS")
        self.assertEqual(report["decision"], "PROMOTE_QWEN3_14B")
        self.assertTrue(report["candidate_eligible"])
        self.assertTrue(report["results"][1]["hard_gate_pass"])
        self.assertNotIn("240名受试者", json.dumps(report, ensure_ascii=False))

    def test_semantic_replay_can_pass_without_byte_identity(self):
        report = run_selection(
            base_url="http://127.0.0.1:11434",
            provider_factory=FakeProviderFactory(varying_candidate_wording=True),
        )

        candidate = report["results"][1]
        insufficient = next(
            case
            for case in candidate["cases"]
            if case["case_id"] == "zh.evidence.insufficient"
        )
        self.assertEqual(report["decision"], "PROMOTE_QWEN3_14B")
        self.assertTrue(insufficient["stable_replay"])
        self.assertFalse(insufficient["byte_stable_replay"])
        self.assertEqual(insufficient["semantic_checks_by_attempt"], [True, True])

    def test_unsupported_candidate_claim_keeps_fallback(self):
        report = run_selection(
            base_url="http://127.0.0.1:11434",
            provider_factory=FakeProviderFactory(candidate_regression=True),
        )

        self.assertEqual(report["status"], "PASS")
        self.assertEqual(report["decision"], "KEEP_LLAMA3_2")
        self.assertFalse(report["candidate_eligible"])
        self.assertEqual(report["results"][1]["hard_gate_cases_passed"], 3)

    def test_provider_failure_is_sanitized_and_does_not_decide_selection(self):
        report = run_selection(
            base_url="http://127.0.0.1:11434",
            provider_factory=FakeProviderFactory(incomplete_candidate=True),
        )

        self.assertEqual(report["status"], "FAIL")
        self.assertEqual(report["error_code"], "MODEL_SELECTION_EXECUTION_INCOMPLETE")
        self.assertNotIn("private provider detail", json.dumps(report))

    def test_case_drift_and_unsafe_endpoints_fail_closed(self):
        payload = json.loads(SUITE_PATH.read_text(encoding="utf-8"))
        payload["semantic_overrides"][0]["required_any_term_groups"][0].append(
            "drift"
        )
        with tempfile.TemporaryDirectory() as directory:
            changed = Path(directory) / "cases.json"
            changed.write_text(json.dumps(payload), encoding="utf-8")
            with self.assertRaisesRegex(
                ModelSelectionGateError, "FROZEN_SUITE_DIGEST_MISMATCH"
            ):
                _load_frozen_cases(changed)

        with self.assertRaisesRegex(
            ModelSelectionGateError, "OLLAMA_URL_MUST_USE_LOOPBACK"
        ):
            _validate_loopback_url("https://models.example.com")
        with self.assertRaisesRegex(
            ModelSelectionGateError, "OUTPUT_MUST_BE_RUNTIME_JSON"
        ):
            _validate_output_path(Path("report.json"))


if __name__ == "__main__":
    unittest.main()
