#!/usr/bin/env python3
"""Deterministic tests for blind-listening evidence and analysis."""

import copy
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import jsonschema

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import listening


ROOT = Path(__file__).resolve().parents[2]
PILOT = ROOT / "evals" / "listening" / "pilot"
EXPERIMENT_PATH = PILOT / "experiment.json"
RESULTS_PATH = PILOT / "synthetic-results.json"


class ManifestTests(unittest.TestCase):
    def test_pilot_and_every_raw_session_validate(self):
        experiment = listening.validate_experiment(EXPERIMENT_PATH)
        digest = listening.manifest_digest(experiment)
        schema = listening.load_json(ROOT / "evals" / "listening" / "session-schema-v1.json")
        for session in listening.load_json(RESULTS_PATH):
            jsonschema.validate(session, schema)
            listening.validate_session(session, experiment, digest)

    def test_hidden_reference_must_match_explicit_reference(self):
        value = listening.load_json(EXPERIMENT_PATH)
        value["trials"][0]["stimuli"][0]["sha256"] = "0" * 64
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "experiment.json"
            path.write_text(json.dumps(value))
            with self.assertRaisesRegex(ValueError, "hidden reference"):
                listening.validate_experiment(path, verify_files=False)

    def test_path_escape_and_digest_tamper_fail_closed(self):
        value = listening.load_json(EXPERIMENT_PATH)
        value["trials"][0]["stimuli"][1]["path"] = "../secret.wav"
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "experiment.json"
            path.write_text(json.dumps(value))
            with self.assertRaises((ValueError, jsonschema.ValidationError)):
                listening.validate_experiment(path, verify_files=False)
        value = listening.load_json(EXPERIMENT_PATH)
        value["trials"][0]["stimuli"][1]["sha256"] = "f" * 64
        with tempfile.TemporaryDirectory(dir=PILOT.parent) as directory:
            path = Path(directory) / "experiment.json"
            path.write_text(json.dumps(value))
            with self.assertRaisesRegex(ValueError, "digest mismatch|missing stimulus"):
                listening.validate_experiment(path)


class RandomizationTests(unittest.TestCase):
    def test_python_and_browser_javascript_vectors_match(self):
        experiment = listening.load_json(EXPERIMENT_PATH)
        seeds = [0, 1, 0x10010001, 0xFFFFFFFF]
        expected = {str(seed): listening.expected_presentations(experiment, seed) for seed in seeds}
        script = f"""
          import {{ presentations }} from './evals/listening/randomization.js';
          const experiment = {json.dumps(experiment)};
          const seeds = {json.dumps(seeds)};
          console.log(JSON.stringify(Object.fromEntries(seeds.map((seed) => [String(seed), presentations(experiment, seed)]))));
        """
        actual = json.loads(subprocess.check_output(["node", "--input-type=module", "-e", script], cwd=ROOT, text=True))
        self.assertEqual(actual, expected)

    def test_randomization_is_deterministic_and_position_balanced(self):
        ids = ["a", "b", "c"]
        self.assertEqual(listening.shuffled_ids(ids, 12345), listening.shuffled_ids(ids, 12345))
        counts = {item: [0, 0, 0] for item in ids}
        orders = set()
        seed = 0x12345678
        for _ in range(600):
            seed = listening.xorshift32(seed ^ 0x9E3779B9)
            order = listening.shuffled_ids(ids, seed)
            orders.add(tuple(order))
            for position, item in enumerate(order):
                counts[item][position] += 1
        self.assertEqual(len(orders), 6)
        for positions in counts.values():
            self.assertLess(max(positions) - min(positions), 55)

    def test_presentation_tamper_is_rejected(self):
        experiment = listening.load_json(EXPERIMENT_PATH)
        digest = listening.manifest_digest(experiment)
        session = copy.deepcopy(listening.load_json(RESULTS_PATH)[0])
        session["trials"][0]["presentation"].reverse()
        with self.assertRaisesRegex(ValueError, "randomization mismatch"):
            listening.validate_session(session, experiment, digest)


class AnalysisTests(unittest.TestCase):
    def test_synthetic_pilot_proves_exclusion_uncertainty_and_raw_retention(self):
        experiment = listening.load_json(EXPERIMENT_PATH)
        sessions = listening.load_json(RESULTS_PATH)
        report = listening.analyze(experiment, sessions)
        self.assertEqual(report["n_submitted"], 6)
        self.assertEqual(report["n_included"], 5)
        self.assertEqual(report["exclusions"], [{"session_id": "synthetic-pilot-6", "reason": "hidden_reference_below_threshold:synthetic-tone-mushra"}])
        self.assertEqual(report["stimuli"]["condition-h"]["role"], "hidden_reference")
        self.assertEqual(report["stimuli"]["condition-a"]["role"], "anchor")
        self.assertEqual(report["stimuli"]["condition-c"]["mean"], 80.6)
        self.assertEqual(len(report["stimuli"]["condition-c"]["mean_ci95_bootstrap"]), 2)
        self.assertEqual(report["raw_sessions"], sessions)
        self.assertIsNone(report["quality_verdict"])
        self.assertEqual(report["evidence_kind_counts"]["human"], 0)
        self.assertIn("validate only the harness", report["interpretation"])

    def test_analysis_is_byte_deterministic(self):
        experiment = listening.load_json(EXPERIMENT_PATH)
        sessions = listening.load_json(RESULTS_PATH)
        first = listening.canonical_json(listening.analyze(experiment, sessions))
        second = listening.canonical_json(listening.analyze(experiment, sessions))
        self.assertEqual(first, second)

    def test_abx_uncertainty_and_ab_preference_are_listener_level(self):
        experiment = {
            "id": "protocol-fixture",
            "trials": [
                {"id": "ab", "protocol": "ab", "stimuli": [{"id": "a", "role": "candidate"}, {"id": "b", "role": "incumbent"}]},
                {"id": "abx", "protocol": "abx", "x_source": "a", "stimuli": [{"id": "a", "role": "candidate"}, {"id": "b", "role": "incumbent"}]},
            ],
            "exclusion_policy": {"min_completed_trials": 2, "hidden_reference_min_score": 90},
        }
        digest = listening.manifest_digest(experiment)
        sessions = []
        for index, seed in enumerate([11, 22, 33, 44]):
            order = listening.expected_presentations(experiment, seed)
            sessions.append({
                "schema_version": "1.0.0", "experiment_id": experiment["id"], "experiment_digest": digest,
                "session_id": f"p-{index}", "evidence_kind": "human",
                "listener": {"id": f"p-{index}", "experience": "test", "hearing_notes": "none"},
                "setup": {"transducer": "headphones", "environment": "test", "device": "test", "volume_check": True},
                "randomization": {"algorithm": listening.RANDOMIZATION_ALGORITHM, "seed": seed},
                "started_at": "x", "submitted_at": "y",
                "trials": [
                    {"trial_id": "ab", "protocol": "ab", "presentation": order["ab"], "response": {"choice": "a" if index < 3 else "b"}, "play_counts": {"a": 1, "b": 1}},
                    {"trial_id": "abx", "protocol": "abx", "presentation": order["abx"], "response": {"choice": "a" if index != 3 else "b"}, "play_counts": {"a": 1, "b": 1, "x": 1}},
                ],
            })
        report = listening.analyze(experiment, sessions)
        self.assertEqual(report["stimuli"]["a"]["preference_count"], 3)
        self.assertEqual(report["stimuli"]["a"]["preference_total"], 4)
        self.assertEqual(report["abx"]["correct"], 3)
        self.assertEqual(report["abx"]["total"], 4)
        self.assertEqual(len(report["abx"]["accuracy_ci95_wilson"]), 2)


if __name__ == "__main__":
    unittest.main()
