#!/usr/bin/env python3
"""Validate, randomize, and analyze local blind-listening evidence.

This module deliberately emits diagnostics and uncertainty, never a release
verdict. Human listeners remain the authority for sound quality.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import random
import statistics
import sys
from pathlib import Path
from typing import Any, Iterable

import jsonschema


ROOT = Path(__file__).resolve().parents[2]
LISTENING_ROOT = ROOT / "evals" / "listening"
SCHEMA_VERSION = "1.0.0"
RANDOMIZATION_ALGORITHM = "xorshift32-fisher-yates-v1"


def canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def manifest_digest(manifest: dict[str, Any]) -> str:
    return sha256_bytes(canonical_json(manifest).encode())


def load_json(path: Path | str) -> Any:
    return json.loads(Path(path).read_text())


def _require_keys(value: dict[str, Any], required: set[str], allowed: set[str], context: str) -> None:
    missing = required - value.keys()
    extra = value.keys() - allowed
    if missing:
        raise ValueError(f"{context}: missing keys {sorted(missing)}")
    if extra:
        raise ValueError(f"{context}: unknown keys {sorted(extra)}")


def _safe_audio_path(base: Path, relative: str) -> Path:
    candidate = (base / relative).resolve()
    try:
        candidate.relative_to(base.resolve())
    except ValueError as exc:
        raise ValueError(f"unsafe stimulus path: {relative}") from exc
    if candidate.suffix.lower() != ".wav":
        raise ValueError(f"stimulus must be WAV: {relative}")
    return candidate


def validate_experiment(path: Path | str, verify_files: bool = True) -> dict[str, Any]:
    path = Path(path)
    value = load_json(path)
    jsonschema.validate(value, load_json(LISTENING_ROOT / "experiment-schema-v1.json"))
    _require_keys(
        value,
        {"schema_version", "id", "title", "purpose", "instructions", "sample_rate", "level_matching", "randomization", "exclusion_policy", "trials"},
        {"schema_version", "id", "title", "purpose", "instructions", "sample_rate", "level_matching", "randomization", "exclusion_policy", "trials"},
        "experiment",
    )
    if value["schema_version"] != SCHEMA_VERSION:
        raise ValueError(f"unsupported experiment schema: {value['schema_version']}")
    if value["purpose"] not in {"harness_validation", "iteration", "release_gate"}:
        raise ValueError("experiment purpose is invalid")
    if value["sample_rate"] not in {44100, 48000}:
        raise ValueError("sample_rate must be 44100 or 48000")
    _require_keys(value["randomization"], {"algorithm", "seed_policy"}, {"algorithm", "seed_policy"}, "randomization")
    if value["randomization"]["algorithm"] != RANDOMIZATION_ALGORITHM:
        raise ValueError("unsupported randomization algorithm")
    if value["randomization"]["seed_policy"] not in {"per_listener", "fixed_pilot"}:
        raise ValueError("seed_policy is invalid")
    _require_keys(value["level_matching"], {"method", "target_lufs", "tolerance_lu"}, {"method", "target_lufs", "tolerance_lu"}, "level_matching")
    if value["level_matching"]["method"] not in {"bs1770_integrated", "declared_prematched"}:
        raise ValueError("level matching method is invalid")
    _require_keys(value["exclusion_policy"], {"min_completed_trials", "hidden_reference_min_score"}, {"min_completed_trials", "hidden_reference_min_score"}, "exclusion_policy")
    if not isinstance(value["trials"], list) or not value["trials"]:
        raise ValueError("experiment must contain trials")

    trial_ids: set[str] = set()
    base = path.parent
    for trial in value["trials"]:
        _require_keys(trial, {"id", "protocol", "prompt", "stimuli"}, {"id", "protocol", "prompt", "stimuli", "reference", "x_source"}, f"trial {trial.get('id', '?')}")
        trial_id = trial["id"]
        if trial_id in trial_ids:
            raise ValueError(f"duplicate trial id: {trial_id}")
        trial_ids.add(trial_id)
        protocol = trial["protocol"]
        if protocol not in {"ab", "abx", "mushra"}:
            raise ValueError(f"{trial_id}: unsupported protocol {protocol}")
        stimuli = trial["stimuli"]
        if not isinstance(stimuli, list):
            raise ValueError(f"{trial_id}: stimuli must be an array")
        if protocol in {"ab", "abx"} and len(stimuli) != 2:
            raise ValueError(f"{trial_id}: {protocol} requires exactly two stimuli")
        if protocol == "mushra" and len(stimuli) < 3:
            raise ValueError(f"{trial_id}: MUSHRA requires at least three conditions")
        stimulus_ids: set[str] = set()
        roles: list[str] = []
        for stimulus in stimuli:
            _require_keys(stimulus, {"id", "path", "sha256", "role"}, {"id", "path", "sha256", "role"}, f"{trial_id} stimulus")
            if stimulus["id"] in stimulus_ids:
                raise ValueError(f"{trial_id}: duplicate stimulus id {stimulus['id']}")
            stimulus_ids.add(stimulus["id"])
            roles.append(stimulus["role"])
            audio = _safe_audio_path(base, stimulus["path"])
            if verify_files:
                if not audio.is_file():
                    raise ValueError(f"missing stimulus: {audio}")
                actual = sha256_bytes(audio.read_bytes())
                if actual != stimulus["sha256"]:
                    raise ValueError(f"stimulus digest mismatch: {stimulus['id']}")
        if protocol == "abx" and trial.get("x_source") not in stimulus_ids:
            raise ValueError(f"{trial_id}: x_source must name an A/B stimulus")
        if protocol == "mushra":
            if "reference" not in trial:
                raise ValueError(f"{trial_id}: MUSHRA requires an explicit reference")
            reference = trial["reference"]
            _require_keys(reference, {"id", "path", "sha256"}, {"id", "path", "sha256"}, f"{trial_id} reference")
            reference_path = _safe_audio_path(base, reference["path"])
            if verify_files:
                if not reference_path.is_file() or sha256_bytes(reference_path.read_bytes()) != reference["sha256"]:
                    raise ValueError(f"{trial_id}: reference digest mismatch")
            hidden = [item for item in stimuli if item["role"] == "hidden_reference"]
            anchors = [item for item in stimuli if item["role"] == "anchor"]
            if len(hidden) != 1 or not anchors:
                raise ValueError(f"{trial_id}: MUSHRA requires exactly one hidden reference and at least one anchor")
            if hidden[0]["sha256"] != reference["sha256"]:
                raise ValueError(f"{trial_id}: hidden reference must be bit-identical to reference")
    return value


def xorshift32(state: int) -> int:
    state &= 0xFFFFFFFF
    if state == 0:
        state = 0x6D2B79F5
    state ^= (state << 13) & 0xFFFFFFFF
    state ^= state >> 17
    state ^= (state << 5) & 0xFFFFFFFF
    return state & 0xFFFFFFFF


def shuffled_ids(ids: Iterable[str], seed: int) -> list[str]:
    out = list(ids)
    state = seed & 0xFFFFFFFF
    for index in range(len(out) - 1, 0, -1):
        state = xorshift32(state)
        swap = state % (index + 1)
        out[index], out[swap] = out[swap], out[index]
    return out


def trial_seed(session_seed: int, trial_index: int) -> int:
    state = session_seed & 0xFFFFFFFF
    for _ in range(trial_index + 1):
        state = xorshift32(state ^ 0x9E3779B9)
    return state


def expected_presentations(experiment: dict[str, Any], seed: int) -> dict[str, list[str]]:
    return {
        trial["id"]: shuffled_ids((item["id"] for item in trial["stimuli"]), trial_seed(seed, index))
        for index, trial in enumerate(experiment["trials"])
    }


def validate_session(session: dict[str, Any], experiment: dict[str, Any], digest: str) -> None:
    jsonschema.validate(session, load_json(LISTENING_ROOT / "session-schema-v1.json"))
    _require_keys(
        session,
        {"schema_version", "experiment_id", "experiment_digest", "session_id", "evidence_kind", "listener", "setup", "randomization", "started_at", "submitted_at", "trials"},
        {"schema_version", "experiment_id", "experiment_digest", "session_id", "evidence_kind", "listener", "setup", "randomization", "started_at", "submitted_at", "trials"},
        "session",
    )
    if session["schema_version"] != SCHEMA_VERSION or session["experiment_id"] != experiment["id"] or session["experiment_digest"] != digest:
        raise ValueError(f"{session.get('session_id', '?')}: experiment identity/digest mismatch")
    if session["evidence_kind"] not in {"human", "synthetic_harness_pilot"}:
        raise ValueError("invalid evidence_kind")
    _require_keys(session["listener"], {"id", "experience", "hearing_notes"}, {"id", "experience", "hearing_notes"}, "listener")
    _require_keys(session["setup"], {"transducer", "environment", "device", "volume_check"}, {"transducer", "environment", "device", "volume_check"}, "setup")
    if session["setup"]["transducer"] not in {"headphones", "studio_monitors", "speakers", "other"}:
        raise ValueError("invalid transducer")
    randomization = session["randomization"]
    _require_keys(randomization, {"algorithm", "seed"}, {"algorithm", "seed"}, "session randomization")
    if randomization["algorithm"] != RANDOMIZATION_ALGORITHM or not isinstance(randomization["seed"], int):
        raise ValueError("session randomization is invalid")
    expected = expected_presentations(experiment, randomization["seed"])
    trials_by_id = {trial["id"]: trial for trial in experiment["trials"]}
    seen: set[str] = set()
    for response in session["trials"]:
        _require_keys(response, {"trial_id", "protocol", "presentation", "response", "play_counts"}, {"trial_id", "protocol", "presentation", "response", "play_counts"}, "trial response")
        trial_id = response["trial_id"]
        if trial_id in seen or trial_id not in trials_by_id:
            raise ValueError(f"invalid or duplicate response trial: {trial_id}")
        seen.add(trial_id)
        trial = trials_by_id[trial_id]
        if response["protocol"] != trial["protocol"] or response["presentation"] != expected[trial_id]:
            raise ValueError(f"{trial_id}: presentation/randomization mismatch")
        slots = set(response["presentation"])
        expected_play_slots = slots | ({"reference"} if trial["protocol"] == "mushra" else set()) | ({"x"} if trial["protocol"] == "abx" else set())
        if set(response["play_counts"]) != expected_play_slots or any(not isinstance(count, int) or count < 0 for count in response["play_counts"].values()):
            raise ValueError(f"{trial_id}: play_counts invalid")
        answer = response["response"]
        if trial["protocol"] == "mushra":
            if set(answer.get("ratings", {})) != slots or any(not isinstance(score, int) or not 0 <= score <= 100 for score in answer["ratings"].values()):
                raise ValueError(f"{trial_id}: MUSHRA ratings invalid")
        elif trial["protocol"] == "ab":
            if answer.get("choice") not in slots | {"tie"}:
                raise ValueError(f"{trial_id}: A/B choice invalid")
        elif answer.get("choice") not in slots:
            raise ValueError(f"{trial_id}: ABX choice invalid")


def _percentile(values: list[float], q: float) -> float:
    ordered = sorted(values)
    if not ordered:
        return math.nan
    position = (len(ordered) - 1) * q
    lo = math.floor(position)
    hi = math.ceil(position)
    if lo == hi:
        return ordered[lo]
    return ordered[lo] + (ordered[hi] - ordered[lo]) * (position - lo)


def bootstrap_mean_ci(values: list[float], seed: int, iterations: int = 2000) -> list[float] | None:
    if not values:
        return None
    rng = random.Random(seed)
    means = [statistics.fmean(rng.choice(values) for _ in values) for _ in range(iterations)]
    return [round(_percentile(means, 0.025), 3), round(_percentile(means, 0.975), 3)]


def wilson_interval(successes: int, total: int) -> list[float] | None:
    if total == 0:
        return None
    z = 1.959963984540054
    p = successes / total
    denom = 1 + z * z / total
    center = (p + z * z / (2 * total)) / denom
    radius = z * math.sqrt(p * (1 - p) / total + z * z / (4 * total * total)) / denom
    return [round(max(0.0, center - radius), 4), round(min(1.0, center + radius), 4)]


def analyze(experiment: dict[str, Any], sessions: list[dict[str, Any]]) -> dict[str, Any]:
    digest = manifest_digest(experiment)
    for session in sessions:
        validate_session(session, experiment, digest)
    trials_by_id = {trial["id"]: trial for trial in experiment["trials"]}
    policy = experiment["exclusion_policy"]
    included: list[dict[str, Any]] = []
    exclusions: list[dict[str, str]] = []
    for session in sessions:
        reasons: list[str] = []
        if len(session["trials"]) < policy["min_completed_trials"]:
            reasons.append("incomplete")
        for response in session["trials"]:
            trial = trials_by_id[response["trial_id"]]
            if trial["protocol"] == "mushra":
                hidden = next(item["id"] for item in trial["stimuli"] if item["role"] == "hidden_reference")
                if response["response"]["ratings"][hidden] < policy["hidden_reference_min_score"]:
                    reasons.append(f"hidden_reference_below_threshold:{trial['id']}")
        if reasons:
            exclusions.append({"session_id": session["session_id"], "reason": ";".join(reasons)})
        else:
            included.append(session)

    stimulus_meta = {
        item["id"]: {"role": item["role"], "trial_id": trial["id"]}
        for trial in experiment["trials"]
        for item in trial["stimuli"]
    }
    scores: dict[str, list[float]] = {key: [] for key in stimulus_meta}
    ab_choices: dict[str, int] = {key: 0 for key in stimulus_meta}
    ab_total: dict[str, int] = {key: 0 for key in stimulus_meta}
    abx_correct = 0
    abx_total = 0
    for session in included:
        for response in session["trials"]:
            trial = trials_by_id[response["trial_id"]]
            answer = response["response"]
            if trial["protocol"] == "mushra":
                for stimulus_id, score in answer["ratings"].items():
                    scores[stimulus_id].append(float(score))
            elif trial["protocol"] == "ab" and answer["choice"] != "tie":
                for stimulus_id in response["presentation"]:
                    ab_total[stimulus_id] += 1
                ab_choices[answer["choice"]] += 1
            elif trial["protocol"] == "abx":
                abx_total += 1
                abx_correct += int(answer["choice"] == trial["x_source"])

    stimulus_results: dict[str, Any] = {}
    for index, (stimulus_id, meta) in enumerate(sorted(stimulus_meta.items())):
        values = scores[stimulus_id]
        result: dict[str, Any] = {**meta, "n": len(values)}
        if values:
            result.update({"mean": round(statistics.fmean(values), 3), "median": round(statistics.median(values), 3), "mean_ci95_bootstrap": bootstrap_mean_ci(values, 0x4C340000 + index)})
        if ab_total[stimulus_id]:
            result.update({"preference_count": ab_choices[stimulus_id], "preference_total": ab_total[stimulus_id], "preference_ci95_wilson": wilson_interval(ab_choices[stimulus_id], ab_total[stimulus_id])})
        stimulus_results[stimulus_id] = result

    return {
        "schema_version": SCHEMA_VERSION,
        "experiment_id": experiment["id"],
        "experiment_digest": digest,
        "evidence_kind_counts": {kind: sum(session["evidence_kind"] == kind for session in sessions) for kind in ["human", "synthetic_harness_pilot"]},
        "n_submitted": len(sessions),
        "n_included": len(included),
        "exclusions": exclusions,
        "stimuli": stimulus_results,
        "abx": {"correct": abx_correct, "total": abx_total, "accuracy_ci95_wilson": wilson_interval(abx_correct, abx_total)},
        "raw_sessions": sessions,
        "quality_verdict": None,
        "interpretation": "Listening evidence with uncertainty; a human owner applies the declared gate. Synthetic pilot sessions validate only the harness.",
    }


def render_markdown(report: dict[str, Any]) -> str:
    lines = [
        f"# Listening analysis: {report['experiment_id']}",
        "",
        f"Submitted: {report['n_submitted']}; included: {report['n_included']}; excluded: {len(report['exclusions'])}.",
        "",
        "This report does not contain a release verdict. Synthetic pilot sessions validate only the harness.",
        "",
        "| Stimulus | Role | n | Mean | 95% bootstrap CI |",
        "|---|---:|---:|---:|---:|",
    ]
    for stimulus_id, row in sorted(report["stimuli"].items()):
        ci = row.get("mean_ci95_bootstrap")
        lines.append(f"| {stimulus_id} | {row['role']} | {row['n']} | {row.get('mean', '—')} | {ci if ci else '—'} |")
    if report["exclusions"]:
        lines.extend(["", "## Exclusions", ""] + [f"- `{item['session_id']}`: {item['reason']}" for item in report["exclusions"]])
    lines.extend(["", "Raw listener-level sessions are retained in the JSON report.", ""])
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    validate = sub.add_parser("validate")
    validate.add_argument("experiment")
    validate.add_argument("--no-files", action="store_true")
    analyze_parser = sub.add_parser("analyze")
    analyze_parser.add_argument("experiment")
    analyze_parser.add_argument("results", nargs="+")
    analyze_parser.add_argument("--out", required=True)
    analyze_parser.add_argument("--markdown")
    args = parser.parse_args(argv)
    experiment = validate_experiment(args.experiment, verify_files=not getattr(args, "no_files", False))
    if args.command == "validate":
        print(json.dumps({"experiment": experiment["id"], "digest": manifest_digest(experiment), "trials": len(experiment["trials"])}))
        return 0
    sessions: list[dict[str, Any]] = []
    for result_path in args.results:
        loaded = load_json(result_path)
        sessions.extend(loaded if isinstance(loaded, list) else [loaded])
    report = analyze(experiment, sessions)
    Path(args.out).write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    if args.markdown:
        Path(args.markdown).write_text(render_markdown(report))
    print(json.dumps({"out": args.out, "submitted": report["n_submitted"], "included": report["n_included"], "quality_verdict": None}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
