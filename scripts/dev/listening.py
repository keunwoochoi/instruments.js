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
import shutil
import statistics
import sys
from pathlib import Path
from typing import Any, Iterable

import jsonschema
import numpy as np
import pyloudnorm
import soundfile as sf


ROOT = Path(__file__).resolve().parents[2]
LISTENING_ROOT = ROOT / "evals" / "listening"
SCHEMA_VERSION = "1.0.0"
RANDOMIZATION_ALGORITHM = "xorshift32-fisher-yates-v1"
CAMPAIGN_BUNDLE_VERSION = "campaign-ab-v1"
CAMPAIGN_TARGET_LUFS = -23.0
CAMPAIGN_TOLERANCE_LU = 0.1


def canonical_json(value: Any) -> str:
    def encode(item: Any) -> str:
        if isinstance(item, dict):
            return "{" + ",".join(
                f"{json.dumps(key, ensure_ascii=False)}:{encode(item[key])}" for key in sorted(item)
            ) + "}"
        if isinstance(item, list):
            return "[" + ",".join(encode(child) for child in item) + "]"
        if item is None or isinstance(item, (str, bool)):
            return json.dumps(item, ensure_ascii=False, separators=(",", ":"))
        if isinstance(item, int):
            if abs(item) > 9_007_199_254_740_991:
                raise ValueError("canonical JSON integer exceeds the browser-safe range")
            return str(item)
        if isinstance(item, float):
            if not math.isfinite(item):
                raise ValueError("canonical JSON does not permit non-finite numbers")
            if item.is_integer():
                integer = int(item)
                if abs(integer) > 9_007_199_254_740_991:
                    raise ValueError("canonical JSON integer exceeds the browser-safe range")
                return str(integer)
            mantissa, exponent = format(item, ".16e").split("e")
            return f"{mantissa}e{int(exponent)}"
        raise TypeError(f"unsupported canonical JSON value: {type(item).__name__}")

    return encode(value)


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


def _prepare_level_matched_audio(source: Path, destination: Path, target_lufs: float) -> dict[str, Any]:
    audio, sample_rate = sf.read(source, dtype="float64", always_2d=True)
    if audio.size == 0 or not np.isfinite(audio).all():
        raise ValueError(f"invalid campaign listening source: {source}")
    meter = pyloudnorm.Meter(sample_rate)
    before = float(meter.integrated_loudness(audio))
    if not math.isfinite(before):
        raise ValueError(f"campaign listening source has no measurable loudness: {source}")
    prepared = np.asarray(pyloudnorm.normalize.loudness(audio, before, target_lufs), dtype=np.float64)
    peak = float(np.max(np.abs(prepared)))
    if not np.isfinite(prepared).all() or peak >= 1.0:
        raise ValueError(f"campaign listening normalization clips {source}: peak={peak}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    sf.write(destination, prepared, sample_rate, subtype="FLOAT")
    round_trip, written_rate = sf.read(destination, dtype="float64", always_2d=True)
    after = float(pyloudnorm.Meter(written_rate).integrated_loudness(round_trip))
    if abs(after - target_lufs) > CAMPAIGN_TOLERANCE_LU:
        raise ValueError(f"campaign listening loudness missed target for {source}: {after} LUFS")
    return {
        "source_sha256": sha256_bytes(source.read_bytes()),
        "gain_db": round(target_lufs - before, 6),
        "integrated_lufs_before": round(before, 6),
        "integrated_lufs_after": round(after, 6),
    }


def prepare_campaign_bundle(iteration_dir: Path | str, baseline_dir: Path | str, out: Path | str) -> dict[str, Any]:
    iteration_dir = Path(iteration_dir).resolve()
    baseline_dir = Path(baseline_dir).resolve()
    out = Path(out).resolve()
    if out.exists() and any(out.iterdir()):
        raise FileExistsError(f"listening bundle directory is not empty: {out}")
    candidate = load_json(iteration_dir / "iteration.json")
    baseline = load_json(baseline_dir / "iteration.json")
    if candidate["family"] != baseline["family"]:
        raise ValueError("candidate and baseline listening families differ")
    baseline_cases = {item["id"]: item for item in baseline["cases"]}
    candidate_ids = [item["id"] for item in candidate["cases"]]
    if set(candidate_ids) != set(baseline_cases):
        raise ValueError("candidate and baseline listening case matrices differ")

    out.mkdir(parents=True, exist_ok=True)
    for name in ("app.js", "randomization.js", "style.css"):
        shutil.copyfile(LISTENING_ROOT / name, out / name)
    index = (LISTENING_ROOT / "index.html").read_text()
    index = index.replace(
        '<meta name="ij-listening-experiment" content="pilot/experiment.json">',
        '<meta name="ij-listening-experiment" content="experiment.json">',
    )
    (out / "index.html").write_text(index)

    sample_rates: set[int] = set()
    trials: list[dict[str, Any]] = []
    for case in candidate["cases"]:
        case_id = case["id"]
        if not case_id or any(character not in "abcdefghijklmnopqrstuvwxyz0123456789-" for character in case_id):
            raise ValueError(f"unsafe listening case id: {case_id}")
        sources = {
            "incumbent": baseline_dir / "renders" / f"{case_id}.wav",
            "candidate": iteration_dir / "renders" / f"{case_id}.wav",
        }
        stimuli = []
        for role, source in sources.items():
            if not source.is_file():
                raise FileNotFoundError(f"missing campaign listening source: {source}")
            sample_rates.add(sf.info(source).samplerate)
            stimulus_id = f"{case_id}-{role}"
            relative = Path("audio") / f"{stimulus_id}.wav"
            provenance = _prepare_level_matched_audio(source, out / relative, CAMPAIGN_TARGET_LUFS)
            stimuli.append({
                "id": stimulus_id,
                "path": relative.as_posix(),
                "sha256": sha256_bytes((out / relative).read_bytes()),
                "role": role,
                "provenance": provenance,
            })
        trials.append({
            "id": case_id,
            "protocol": "ab",
            "prompt": f"Which rendering better matches the intended {candidate['family']} sound for {case_id}?",
            "stimuli": stimuli,
        })
    if len(sample_rates) != 1 or next(iter(sample_rates)) not in {44100, 48000}:
        raise ValueError(f"campaign listening bundle requires one browser sample rate, got {sorted(sample_rates)}")

    experiment = {
        "schema_version": SCHEMA_VERSION,
        "id": f"{candidate['family']}-{candidate['source']['commit'][:12]}-iteration",
        "title": f"Blind {candidate['family']} iteration",
        "purpose": "iteration",
        "instructions": "Keep playback volume fixed. Compare realism, articulation, and artifacts; use no preference when neither rendering is clearly better.",
        "sample_rate": next(iter(sample_rates)),
        "level_matching": {
            "method": "bs1770_integrated",
            "target_lufs": CAMPAIGN_TARGET_LUFS,
            "tolerance_lu": CAMPAIGN_TOLERANCE_LU,
        },
        "randomization": {"algorithm": RANDOMIZATION_ALGORITHM, "seed_policy": "per_listener"},
        "exclusion_policy": {"min_completed_trials": len(trials), "hidden_reference_min_score": 90, "min_plays_per_stimulus": 1},
        "provenance": {
            "generator": CAMPAIGN_BUNDLE_VERSION,
            "candidate_commit": candidate["source"]["commit"],
            "baseline_commit": baseline["source"]["commit"],
            "metric_version": candidate["metric_version"],
            "case_manifest_sha256": candidate["manifest"]["sha256"],
        },
        "trials": trials,
    }
    experiment_path = out / "experiment.json"
    experiment_path.write_text(json.dumps(experiment, indent=2, sort_keys=True) + "\n")
    validated = validate_experiment(experiment_path)
    return {
        "experiment": str(experiment_path.relative_to(iteration_dir)),
        "experiment_digest": manifest_digest(validated),
        "protocol": "ab",
        "trials": len(trials),
    }


def validate_experiment(path: Path | str, verify_files: bool = True) -> dict[str, Any]:
    path = Path(path)
    value = load_json(path)
    jsonschema.validate(value, load_json(LISTENING_ROOT / "experiment-schema-v1.json"))
    _require_keys(
        value,
        {"schema_version", "id", "title", "purpose", "instructions", "sample_rate", "level_matching", "randomization", "exclusion_policy", "trials"},
        {"schema_version", "id", "title", "purpose", "instructions", "sample_rate", "level_matching", "randomization", "exclusion_policy", "trials", "provenance"},
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
    if "provenance" in value:
        _require_keys(
            value["provenance"],
            {"generator", "candidate_commit", "baseline_commit", "metric_version", "case_manifest_sha256"},
            {"generator", "candidate_commit", "baseline_commit", "metric_version", "case_manifest_sha256"},
            "experiment provenance",
        )
        if value["provenance"]["generator"] != CAMPAIGN_BUNDLE_VERSION:
            raise ValueError("unsupported campaign listening generator")
    _require_keys(
        value["exclusion_policy"],
        {"min_completed_trials", "hidden_reference_min_score", "min_plays_per_stimulus"},
        {"min_completed_trials", "hidden_reference_min_score", "min_plays_per_stimulus"},
        "exclusion_policy",
    )
    if not isinstance(value["trials"], list) or not value["trials"]:
        raise ValueError("experiment must contain trials")

    trial_ids: set[str] = set()
    experiment_stimulus_ids: set[str] = set()
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
            _require_keys(stimulus, {"id", "path", "sha256", "role"}, {"id", "path", "sha256", "role", "provenance"}, f"{trial_id} stimulus")
            if stimulus["id"] in stimulus_ids:
                raise ValueError(f"{trial_id}: duplicate stimulus id {stimulus['id']}")
            if stimulus["id"] in experiment_stimulus_ids:
                raise ValueError(f"stimulus id must be globally unique: {stimulus['id']}")
            stimulus_ids.add(stimulus["id"])
            experiment_stimulus_ids.add(stimulus["id"])
            roles.append(stimulus["role"])
            audio = _safe_audio_path(base, stimulus["path"])
            if verify_files:
                if not audio.is_file():
                    raise ValueError(f"missing stimulus: {audio}")
                actual = sha256_bytes(audio.read_bytes())
                if actual != stimulus["sha256"]:
                    raise ValueError(f"stimulus digest mismatch: {stimulus['id']}")
                info = sf.info(audio)
                if info.samplerate != value["sample_rate"]:
                    raise ValueError(f"{trial_id}: stimulus sample rate mismatch")
                samples, rate = sf.read(audio, dtype="float64", always_2d=True)
                loudness = float(pyloudnorm.Meter(rate).integrated_loudness(samples))
                target = value["level_matching"]["target_lufs"]
                tolerance = value["level_matching"]["tolerance_lu"]
                if not math.isfinite(loudness) or abs(loudness - target) > tolerance:
                    raise ValueError(f"{trial_id}: stimulus loudness outside declared tolerance: {loudness}")
                if "provenance" in stimulus:
                    _require_keys(
                        stimulus["provenance"],
                        {"source_sha256", "gain_db", "integrated_lufs_before", "integrated_lufs_after"},
                        {"source_sha256", "gain_db", "integrated_lufs_before", "integrated_lufs_after"},
                        f"{trial_id} stimulus provenance",
                    )
                    if abs(stimulus["provenance"]["integrated_lufs_after"] - loudness) > 0.01:
                        raise ValueError(f"{trial_id}: prepared loudness provenance mismatch")
        if protocol == "abx" and trial.get("x_source") not in stimulus_ids:
            raise ValueError(f"{trial_id}: x_source must name an A/B stimulus")
        if protocol in {"ab", "abx"} and sorted(roles) != ["candidate", "incumbent"]:
            raise ValueError(f"{trial_id}: {protocol} requires one candidate and one incumbent")
        if protocol == "mushra":
            if "reference" not in trial:
                raise ValueError(f"{trial_id}: MUSHRA requires an explicit reference")
            reference = trial["reference"]
            _require_keys(reference, {"id", "path", "sha256"}, {"id", "path", "sha256"}, f"{trial_id} reference")
            reference_path = _safe_audio_path(base, reference["path"])
            if verify_files:
                if not reference_path.is_file() or sha256_bytes(reference_path.read_bytes()) != reference["sha256"]:
                    raise ValueError(f"{trial_id}: reference digest mismatch")
                reference_audio, reference_rate = sf.read(reference_path, dtype="float64", always_2d=True)
                reference_loudness = float(pyloudnorm.Meter(reference_rate).integrated_loudness(reference_audio))
                if reference_rate != value["sample_rate"] or abs(reference_loudness - value["level_matching"]["target_lufs"]) > value["level_matching"]["tolerance_lu"]:
                    raise ValueError(f"{trial_id}: explicit reference violates sample-rate or loudness contract")
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


def expected_trial_order(experiment: dict[str, Any], seed: int) -> list[str]:
    return shuffled_ids((trial["id"] for trial in experiment["trials"]), trial_seed(seed, len(experiment["trials"])))


def validate_session(session: dict[str, Any], experiment: dict[str, Any], digest: str) -> None:
    jsonschema.validate(session, load_json(LISTENING_ROOT / "session-schema-v1.json"))
    _require_keys(
        session,
        {"schema_version", "experiment_id", "experiment_digest", "session_id", "evidence_kind", "listener", "setup", "randomization", "trial_order", "started_at", "submitted_at", "trials"},
        {"schema_version", "experiment_id", "experiment_digest", "session_id", "evidence_kind", "listener", "setup", "randomization", "trial_order", "started_at", "submitted_at", "trials"},
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
    trial_order = expected_trial_order(experiment, randomization["seed"])
    if session["trial_order"] != trial_order:
        raise ValueError("session trial order/randomization mismatch")
    if [response["trial_id"] for response in session["trials"]] != trial_order[:len(session["trials"])]:
        raise ValueError("response order does not match randomized trial order")
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


def _percentile(ordered: list[float], q: float) -> float:
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
    means = [statistics.fmean(rng.choices(values, k=len(values))) for _ in range(iterations)]
    means.sort()
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
            if any(count < policy["min_plays_per_stimulus"] for count in response["play_counts"].values()):
                reasons.append(f"insufficient_playback:{trial['id']}")
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
    prepare = sub.add_parser("prepare-campaign")
    prepare.add_argument("iteration")
    prepare.add_argument("--baseline", required=True)
    prepare.add_argument("--out", required=True)
    args = parser.parse_args(argv)
    if args.command == "prepare-campaign":
        result = prepare_campaign_bundle(args.iteration, args.baseline, args.out)
        print(json.dumps(result, sort_keys=True))
        return 0
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
