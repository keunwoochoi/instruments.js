#!/usr/bin/env python3
"""Generate the deterministic hidden-reference/anchor harness pilot."""

from __future__ import annotations

import argparse
import json
import math
import shutil
import tempfile
from pathlib import Path

import numpy as np
import pyloudnorm
import soundfile as sf

import listening


ROOT = Path(__file__).resolve().parents[2]
DESTINATION = ROOT / "evals" / "listening" / "pilot"
SR = 48000
TARGET_LUFS = -23.0


def envelope(length: int) -> np.ndarray:
    time = np.arange(length) / SR
    attack = np.minimum(1.0, time / 0.025)
    release = np.minimum(1.0, (length / SR - time) / 0.12)
    return np.sin(0.5 * np.pi * np.minimum(attack, release).clip(0, 1)) ** 2


def normalize_loudness(audio: np.ndarray) -> np.ndarray:
    meter = pyloudnorm.Meter(SR)
    loudness = meter.integrated_loudness(audio)
    return np.asarray(pyloudnorm.normalize.loudness(audio, loudness, TARGET_LUFS), dtype=np.float64)


def audio_set() -> dict[str, np.ndarray]:
    length = int(0.8 * SR)
    time = np.arange(length) / SR
    env = envelope(length)
    reference = env * (0.72 * np.sin(2 * np.pi * 220 * time) + 0.22 * np.sin(2 * np.pi * 440 * time) + 0.08 * np.sin(2 * np.pi * 660 * time))
    candidate = env * (0.72 * np.sin(2 * np.pi * 220 * time) + 0.20 * np.sin(2 * np.pi * 441.5 * time) + 0.10 * np.sin(2 * np.pi * 660 * time))
    anchor_source = reference.copy()
    anchor = np.zeros_like(anchor_source)
    coefficient = 1.0 - math.exp(-2 * math.pi * 900 / SR)
    state = 0.0
    for index, sample in enumerate(anchor_source):
        state += coefficient * (sample - state)
        anchor[index] = round(state * 31) / 31
    return {"pilot-reference.wav": normalize_loudness(reference), "pilot-candidate.wav": normalize_loudness(candidate), "pilot-anchor.wav": normalize_loudness(anchor)}


def write_audio(out: Path) -> dict[str, str]:
    out.mkdir(parents=True, exist_ok=True)
    digests: dict[str, str] = {}
    for name, audio in audio_set().items():
        path = out / name
        sf.write(path, audio, SR, subtype="PCM_16")
        digests[name] = listening.sha256_bytes(path.read_bytes())
    return digests


def experiment(digests: dict[str, str]) -> dict:
    return {
        "schema_version": listening.SCHEMA_VERSION,
        "id": "hidden-reference-anchor-pilot",
        "title": "Hidden-reference and anchor harness pilot",
        "purpose": "harness_validation",
        "instructions": "Rate the fidelity of every anonymous condition against the explicit reference. These synthetic tones validate only the listening harness, not an instrument or release.",
        "sample_rate": SR,
        "level_matching": {"method": "bs1770_integrated", "target_lufs": TARGET_LUFS, "tolerance_lu": 0.1},
        "randomization": {"algorithm": listening.RANDOMIZATION_ALGORITHM, "seed_policy": "fixed_pilot"},
        "exclusion_policy": {"min_completed_trials": 1, "hidden_reference_min_score": 90, "min_plays_per_stimulus": 1},
        "trials": [
            {
                "id": "synthetic-tone-mushra",
                "protocol": "mushra",
                "prompt": "Rate fidelity to the explicit reference.",
                "reference": {"id": "explicit-reference", "path": "pilot-reference.wav", "sha256": digests["pilot-reference.wav"]},
                "stimuli": [
                    {"id": "condition-h", "path": "pilot-reference.wav", "sha256": digests["pilot-reference.wav"], "role": "hidden_reference"},
                    {"id": "condition-c", "path": "pilot-candidate.wav", "sha256": digests["pilot-candidate.wav"], "role": "candidate"},
                    {"id": "condition-a", "path": "pilot-anchor.wav", "sha256": digests["pilot-anchor.wav"], "role": "anchor"}
                ]
            }
        ]
    }


def sessions(value: dict) -> list[dict]:
    digest = listening.manifest_digest(value)
    rows = [
        (0x10010001, 98, 82, 21),
        (0x20020002, 96, 79, 18),
        (0x30030003, 100, 85, 24),
        (0x40040004, 95, 76, 27),
        (0x50050005, 97, 81, 20),
        (0x60060006, 65, 88, 12),
    ]
    out = []
    for index, (seed, hidden, candidate, anchor) in enumerate(rows, 1):
        presentation = listening.expected_presentations(value, seed)["synthetic-tone-mushra"]
        out.append({
            "schema_version": listening.SCHEMA_VERSION,
            "experiment_id": value["id"],
            "experiment_digest": digest,
            "session_id": f"synthetic-pilot-{index}",
            "evidence_kind": "synthetic_harness_pilot",
            "listener": {"id": f"simulated-{index}", "experience": "synthetic fixture", "hearing_notes": "not a human listener"},
            "setup": {"transducer": "other", "environment": "deterministic test fixture", "device": "none", "volume_check": True},
            "randomization": {"algorithm": listening.RANDOMIZATION_ALGORITHM, "seed": seed},
            "trial_order": listening.expected_trial_order(value, seed),
            "started_at": f"2026-07-12T12:0{index}:00Z",
            "submitted_at": f"2026-07-12T12:0{index}:30Z",
            "trials": [{
                "trial_id": "synthetic-tone-mushra",
                "protocol": "mushra",
                "presentation": presentation,
                "response": {"ratings": {"condition-h": hidden, "condition-c": candidate, "condition-a": anchor}},
                "play_counts": {"condition-h": 2, "condition-c": 2, "condition-a": 2, "reference": 2}
            }]
        })
    return out


def generate(out: Path) -> None:
    digests = write_audio(out)
    value = experiment(digests)
    (out / "experiment.json").write_text(json.dumps(value, indent=2) + "\n")
    result = sessions(value)
    (out / "synthetic-results.json").write_text(json.dumps(result, indent=2) + "\n")
    report = listening.analyze(value, result)
    (out / "synthetic-analysis.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    (out / "synthetic-analysis.md").write_text(listening.render_markdown(report))


def check() -> None:
    with tempfile.TemporaryDirectory() as directory:
        generated = Path(directory) / "pilot"
        generate(generated)
        expected = sorted(path.relative_to(generated) for path in generated.rglob("*") if path.is_file())
        actual = sorted(path.relative_to(DESTINATION) for path in DESTINATION.rglob("*") if path.is_file())
        if expected != actual:
            raise SystemExit(f"pilot file set differs: generated={expected}, committed={actual}")
        for relative in expected:
            if (generated / relative).read_bytes() != (DESTINATION / relative).read_bytes():
                raise SystemExit(f"pilot artifact stale: {relative}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    if args.check:
        check()
    else:
        if DESTINATION.exists():
            shutil.rmtree(DESTINATION)
        generate(DESTINATION)
        print(f"wrote {DESTINATION}")


if __name__ == "__main__":
    main()
