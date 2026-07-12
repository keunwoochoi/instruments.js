#!/usr/bin/env python3
"""Deterministic tests for blind-listening evidence and analysis."""

import copy
import json
import os
import shutil
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

    def test_stimulus_ids_must_be_unique_across_trials(self):
        value = listening.load_json(EXPERIMENT_PATH)
        duplicate = copy.deepcopy(value["trials"][0])
        duplicate["id"] = "duplicate-trial"
        value["trials"].append(duplicate)
        value["exclusion_policy"]["min_completed_trials"] = 2
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "experiment.json"
            path.write_text(json.dumps(value))
            with self.assertRaisesRegex(ValueError, "globally unique"):
                listening.validate_experiment(path, verify_files=False)


class RandomizationTests(unittest.TestCase):
    def test_python_and_browser_javascript_vectors_match(self):
        experiment = listening.load_json(EXPERIMENT_PATH)
        seeds = [0, 1, 0x10010001, 0xFFFFFFFF]
        expected = {
            str(seed): {
                "presentations": listening.expected_presentations(experiment, seed),
                "trial_order": listening.expected_trial_order(experiment, seed),
            }
            for seed in seeds
        }
        script = f"""
          import {{ presentations, trialOrder }} from './evals/listening/randomization.js';
          const experiment = {json.dumps(experiment)};
          const seeds = {json.dumps(seeds)};
          console.log(JSON.stringify(Object.fromEntries(seeds.map((seed) => [String(seed), {{ presentations: presentations(experiment, seed), trial_order: trialOrder(experiment, seed) }}]))));
        """
        actual = json.loads(subprocess.check_output(["node", "--input-type=module", "-e", script], cwd=ROOT, text=True))
        self.assertEqual(actual, expected)

    def test_python_and_browser_manifest_digests_match_integer_valued_floats(self):
        experiment = listening.load_json(EXPERIMENT_PATH)
        self.assertEqual(experiment["level_matching"]["target_lufs"], -23.0)
        script = f"""
          import {{ manifestDigest }} from './evals/listening/randomization.js';
          const experiment = {json.dumps(experiment)};
          console.log(await manifestDigest(experiment));
        """
        browser_digest = subprocess.check_output(["node", "--input-type=module", "-e", script], cwd=ROOT, text=True).strip()
        self.assertEqual(browser_digest, listening.manifest_digest(experiment))
        numeric_fixture = {"small": -0.000039, "positive": 0.000004, "decimal": -22.999961, "integer_float": -23.0}
        numeric_script = f"""
          import {{ manifestDigest }} from './evals/listening/randomization.js';
          console.log(await manifestDigest({json.dumps(numeric_fixture)}));
        """
        numeric_digest = subprocess.check_output(["node", "--input-type=module", "-e", numeric_script], cwd=ROOT, text=True).strip()
        self.assertEqual(numeric_digest, listening.manifest_digest(numeric_fixture))
        with self.assertRaisesRegex(ValueError, "non-finite"):
            listening.canonical_json({"bad": float("nan")})

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

    def test_trial_order_tamper_is_rejected(self):
        experiment = listening.load_json(EXPERIMENT_PATH)
        digest = listening.manifest_digest(experiment)
        session = copy.deepcopy(listening.load_json(RESULTS_PATH)[0])
        session["trial_order"] = ["not-a-trial"]
        with self.assertRaisesRegex(ValueError, "trial order"):
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

    def test_insufficient_playback_is_declared_and_excluded(self):
        experiment = listening.load_json(EXPERIMENT_PATH)
        session = copy.deepcopy(listening.load_json(RESULTS_PATH)[0])
        session["session_id"] = "no-playback"
        session["trials"][0]["play_counts"]["condition-c"] = 0
        report = listening.analyze(experiment, [session])
        self.assertEqual(report["n_included"], 0)
        self.assertEqual(report["exclusions"], [{"session_id": "no-playback", "reason": "insufficient_playback:synthetic-tone-mushra"}])

    def test_abx_uncertainty_and_ab_preference_are_listener_level(self):
        experiment = {
            "id": "protocol-fixture",
            "trials": [
                {"id": "ab", "protocol": "ab", "stimuli": [{"id": "a", "role": "candidate"}, {"id": "b", "role": "incumbent"}]},
                {"id": "abx", "protocol": "abx", "x_source": "a", "stimuli": [{"id": "a", "role": "candidate"}, {"id": "b", "role": "incumbent"}]},
            ],
            "exclusion_policy": {"min_completed_trials": 2, "hidden_reference_min_score": 90, "min_plays_per_stimulus": 1},
        }
        digest = listening.manifest_digest(experiment)
        sessions = []
        for index, seed in enumerate([11, 22, 33, 44]):
            order = listening.expected_presentations(experiment, seed)
            trial_order = listening.expected_trial_order(experiment, seed)
            responses = {
                "ab": {"trial_id": "ab", "protocol": "ab", "presentation": order["ab"], "response": {"choice": "a" if index < 3 else "b"}, "play_counts": {"a": 1, "b": 1}},
                "abx": {"trial_id": "abx", "protocol": "abx", "presentation": order["abx"], "response": {"choice": "a" if index != 3 else "b"}, "play_counts": {"a": 1, "b": 1, "x": 1}},
            }
            sessions.append({
                "schema_version": "1.0.0", "experiment_id": experiment["id"], "experiment_digest": digest,
                "session_id": f"p-{index}", "evidence_kind": "human",
                "listener": {"id": f"p-{index}", "experience": "test", "hearing_notes": "none"},
                "setup": {"transducer": "headphones", "environment": "test", "device": "test", "volume_check": True},
                "randomization": {"algorithm": listening.RANDOMIZATION_ALGORITHM, "seed": seed},
                "trial_order": trial_order,
                "started_at": "x", "submitted_at": "y",
                "trials": [responses[trial_id] for trial_id in trial_order],
            })
        report = listening.analyze(experiment, sessions)
        self.assertEqual(report["stimuli"]["a"]["preference_count"], 3)
        self.assertEqual(report["stimuli"]["a"]["preference_total"], 4)
        self.assertEqual(report["abx"]["correct"], 3)
        self.assertEqual(report["abx"]["total"], 4)
        self.assertEqual(len(report["abx"]["accuracy_ci95_wilson"]), 2)


class CampaignBundleTests(unittest.TestCase):
    def test_campaign_bundle_is_level_matched_self_contained_and_analyzable(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            baseline = root / "baseline"
            candidate = root / "candidate"
            for path in (baseline, candidate):
                (path / "renders").mkdir(parents=True)
            shutil.copyfile(PILOT / "pilot-reference.wav", baseline / "renders" / "case-a.wav")
            shutil.copyfile(PILOT / "pilot-candidate.wav", candidate / "renders" / "case-a.wav")
            common = {
                "family": "piano",
                "metric_version": "test-metric",
                "manifest": {"sha256": "a" * 64},
                "cases": [{"id": "case-a"}],
            }
            baseline_iteration = {**common, "source": {"commit": "1" * 40}}
            candidate_iteration = {**common, "source": {"commit": "2" * 40}}
            (baseline / "iteration.json").write_text(json.dumps(baseline_iteration))
            (candidate / "iteration.json").write_text(json.dumps(candidate_iteration))
            result = listening.prepare_campaign_bundle(candidate, baseline, candidate / "listening")
            experiment_path = candidate / result["experiment"]
            experiment = listening.validate_experiment(experiment_path)
            self.assertEqual(result["trials"], 1)
            self.assertEqual(result["experiment_digest"], listening.manifest_digest(experiment))
            self.assertIn('content="experiment.json"', (candidate / "listening" / "index.html").read_text())
            roles = {item["role"] for item in experiment["trials"][0]["stimuli"]}
            self.assertEqual(roles, {"candidate", "incumbent"})
            for stimulus in experiment["trials"][0]["stimuli"]:
                self.assertAlmostEqual(stimulus["provenance"]["integrated_lufs_after"], -23.0, places=2)

            seed = 123
            presentation = listening.expected_presentations(experiment, seed)["case-a"]
            session = {
                "schema_version": "1.0.0",
                "experiment_id": experiment["id"],
                "experiment_digest": result["experiment_digest"],
                "session_id": "campaign-round-trip",
                "evidence_kind": "human",
                "listener": {"id": "listener", "experience": "test", "hearing_notes": "none"},
                "setup": {"transducer": "headphones", "environment": "test", "device": "test", "volume_check": True},
                "randomization": {"algorithm": listening.RANDOMIZATION_ALGORITHM, "seed": seed},
                "trial_order": listening.expected_trial_order(experiment, seed),
                "started_at": "x",
                "submitted_at": "y",
                "trials": [{
                    "trial_id": "case-a",
                    "protocol": "ab",
                    "presentation": presentation,
                    "response": {"choice": "case-a-candidate"},
                    "play_counts": {item: 1 for item in presentation},
                }],
            }
            report = listening.analyze(experiment, [session])
            self.assertEqual(report["n_included"], 1)
            self.assertEqual(report["stimuli"]["case-a-candidate"]["preference_count"], 1)
            self.assertIsNone(report["quality_verdict"])


if __name__ == "__main__":
    unittest.main()
