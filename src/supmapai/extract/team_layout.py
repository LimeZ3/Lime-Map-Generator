"""Infer likely team layouts from spawn geometry and assigned resources."""

from __future__ import annotations

import argparse
import csv
import json
import math
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any

TEAM_LAYOUT_COLUMNS = [
    "map_dir",
    "spawn_count",
    "predicted_layout",
    "predicted_team_setting",
    "predicted_team_count",
    "predicted_team_size",
    "prediction_confidence",
    "prediction_score",
    "prediction_strategy",
    "predicted_resource_fairness",
    "compatible_team_settings_json",
    "ffa_resource_fairness",
    "best_non_ffa_layout",
    "best_non_ffa_score",
    "best_non_ffa_resource_fairness",
    "second_layout",
    "second_score",
    "team_spawn_indices_json",
    "team_spawn_names_json",
    "team_mex_counts_json",
    "team_hydro_counts_json",
    "team_reclaim_counts_json",
    "top_candidates_json",
    "warnings",
]

RESOURCE_WEIGHTS = {
    "mex": 0.55,
    "hydro": 0.15,
    "reclaim": 0.30,
}


@dataclass(frozen=True)
class Spawn:
    index: int
    name: str
    x: float
    z: float


@dataclass
class Candidate:
    layout: str
    team_count: int
    team_size: int
    strategy: str
    teams: list[list[int]]
    score: float
    resource_fairness: float
    geometry_score: float
    prior_score: float
    team_totals: dict[str, list[float]]


def _set_csv_field_limit() -> None:
    limit = 2**31 - 1
    while True:
        try:
            csv.field_size_limit(limit)
            return
        except OverflowError:
            limit //= 10


def _read_resource_rows(path: Path) -> dict[str, dict[str, str]]:
    _set_csv_field_limit()
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return {row["map_dir"]: row for row in csv.DictReader(handle) if row.get("map_dir")}


def _read_spawns(path: Path) -> dict[str, list[Spawn]]:
    spawns: dict[str, list[Spawn]] = defaultdict(list)
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            if row.get("kind") != "spawn" or row.get("in_playable_area") != "true":
                continue
            try:
                x = float(row["norm_x"])
                z = float(row["norm_z"])
            except (KeyError, ValueError):
                continue
            map_spawns = spawns[row["map_dir"]]
            map_spawns.append(
                Spawn(
                    index=len(map_spawns),
                    name=row.get("name") or f"spawn_{len(map_spawns) + 1}",
                    x=x,
                    z=z,
                )
            )
    return dict(spawns)


def _parse_counts(row: dict[str, str], prefix: str, spawn_count: int) -> list[float]:
    raw = row.get(f"{prefix}_assigned_spawn_counts_json", "")
    try:
        values = json.loads(raw) if raw else []
    except json.JSONDecodeError:
        values = []
    counts = [float(value) for value in values[:spawn_count]]
    if len(counts) < spawn_count:
        counts.extend([0.0] * (spawn_count - len(counts)))
    return counts


def _cv_fairness(values: list[float]) -> float:
    if not values:
        return 0.0
    mean = sum(values) / len(values)
    if mean <= 0:
        return 1.0
    variance = sum((value - mean) ** 2 for value in values) / len(values)
    return max(0.0, 1.0 - math.sqrt(variance) / mean)


def _weighted_resource_fairness(team_totals: dict[str, list[float]]) -> float:
    weighted = 0.0
    total_weight = 0.0
    for resource, weight in RESOURCE_WEIGHTS.items():
        values = team_totals[resource]
        if not values or sum(values) <= 0:
            continue
        weighted += _cv_fairness(values) * weight
        total_weight += weight
    return weighted / total_weight if total_weight else 1.0


def _team_totals(
    teams: list[list[int]],
    resource_counts: dict[str, list[float]],
) -> dict[str, list[float]]:
    return {
        resource: [sum(counts[index] for index in team) for team in teams]
        for resource, counts in resource_counts.items()
    }


def _mean_pair_distance(points: list[tuple[float, float]]) -> float:
    if len(points) < 2:
        return 0.0
    total = 0.0
    pairs = 0
    for left_index, left in enumerate(points):
        for right in points[left_index + 1 :]:
            total += math.dist(left, right)
            pairs += 1
    return total / pairs if pairs else 0.0


def _geometry_score(teams: list[list[int]], spawns: list[Spawn]) -> float:
    if not spawns:
        return 0.0
    if all(len(team) == 1 for team in teams):
        distances = _mean_pair_distance([(spawn.x, spawn.z) for spawn in spawns])
        return min(distances / 0.55, 1.0)

    intra_distances = []
    centroids = []
    for team in teams:
        points = [(spawns[index].x, spawns[index].z) for index in team]
        intra_distances.append(_mean_pair_distance(points))
        if points:
            centroids.append(
                (
                    sum(point[0] for point in points) / len(points),
                    sum(point[1] for point in points) / len(points),
                )
            )
    compactness = 1.0 - min((sum(intra_distances) / len(intra_distances)) / 0.70, 1.0)
    separation = min(_mean_pair_distance(centroids) / 0.45, 1.0) if len(centroids) > 1 else 0.5
    return max(0.0, min(1.0, compactness * 0.55 + separation * 0.45))


def _layout_label(team_count: int, team_size: int) -> str:
    return "v".join(str(team_size) for _ in range(team_count))


def _prior_score(spawn_count: int, team_count: int, team_size: int, strategy: str) -> float:
    if team_size == 1:
        return 0.90 if spawn_count <= 4 else 0.62
    if team_count == 2:
        return 0.85
    if team_size in {2, 3, 4}:
        return 0.72
    if strategy in {"x_chunks", "z_chunks", "angle_chunks"}:
        return 0.62
    return 0.50


def _canonical_teams(teams: list[list[int]]) -> tuple[tuple[int, ...], ...]:
    return tuple(sorted(tuple(sorted(team)) for team in teams))


def _contiguous_chunks(order: list[int], team_size: int, offset: int = 0) -> list[list[int]]:
    if not order or team_size <= 0:
        return []
    rotated = order[offset:] + order[:offset]
    return [
        sorted(rotated[index : index + team_size])
        for index in range(0, len(rotated), team_size)
    ]


def _candidate_partitions(spawns: list[Spawn]) -> list[tuple[str, int, int, list[list[int]]]]:
    spawn_count = len(spawns)
    partitions: list[tuple[str, int, int, list[list[int]]]] = []
    seen: set[tuple[tuple[int, ...], ...]] = set()

    def add(strategy: str, team_count: int, team_size: int, teams: list[list[int]]) -> None:
        if not teams or any(len(team) != team_size for team in teams):
            return
        canonical = _canonical_teams(teams)
        if canonical in seen:
            return
        seen.add(canonical)
        partitions.append((strategy, team_count, team_size, teams))

    add("per_spawn_ffa", spawn_count, 1, [[index] for index in range(spawn_count)])

    if spawn_count < 2:
        return partitions

    orders = {
        "x_chunks": sorted(range(spawn_count), key=lambda index: spawns[index].x),
        "z_chunks": sorted(range(spawn_count), key=lambda index: spawns[index].z),
        "diag_chunks": sorted(
            range(spawn_count),
            key=lambda index: spawns[index].x + spawns[index].z,
        ),
        "anti_diag_chunks": sorted(
            range(spawn_count), key=lambda index: spawns[index].x - spawns[index].z
        ),
        "angle_chunks": sorted(
            range(spawn_count),
            key=lambda index: math.atan2(spawns[index].z - 0.5, spawns[index].x - 0.5),
        ),
    }

    for team_size in range(2, spawn_count + 1):
        if spawn_count % team_size != 0:
            continue
        team_count = spawn_count // team_size
        if team_count < 2:
            continue
        max_offsets = team_size if team_count > 2 else 1
        for strategy, order in orders.items():
            for offset in range(max_offsets):
                teams = _contiguous_chunks(order, team_size, offset)
                add(strategy, team_count, team_size, teams)

    return partitions


def _build_candidate(
    strategy: str,
    team_count: int,
    team_size: int,
    teams: list[list[int]],
    spawns: list[Spawn],
    resource_counts: dict[str, list[float]],
) -> Candidate:
    totals = _team_totals(teams, resource_counts)
    resource_fairness = _weighted_resource_fairness(totals)
    geometry = _geometry_score(teams, spawns)
    prior = _prior_score(len(spawns), team_count, team_size, strategy)
    score = resource_fairness * 0.68 + geometry * 0.22 + prior * 0.10
    return Candidate(
        layout=_layout_label(team_count, team_size),
        team_count=team_count,
        team_size=team_size,
        strategy=strategy,
        teams=teams,
        score=score,
        resource_fairness=resource_fairness,
        geometry_score=geometry,
        prior_score=prior,
        team_totals=totals,
    )


def _choose_candidate(candidates: list[Candidate]) -> Candidate | None:
    if not candidates:
        return None
    candidates = sorted(candidates, key=lambda candidate: candidate.score, reverse=True)
    ffa = next((candidate for candidate in candidates if candidate.team_size == 1), None)
    best = candidates[0]

    if ffa is None or best.team_size == 1:
        return best

    # Small all-vs-all maps are common. Do not invent a team layout unless grouping
    # players gives a meaningful resource-balance improvement.
    if ffa.team_count <= 4 and ffa.resource_fairness >= 0.90:
        improvement = best.resource_fairness - ffa.resource_fairness
        if improvement <= 0.04:
            return ffa

    return best


def _candidate_to_summary(candidate: Candidate) -> dict[str, Any]:
    return {
        "layout": candidate.layout,
        "team_count": candidate.team_count,
        "team_size": candidate.team_size,
        "strategy": candidate.strategy,
        "score": round(candidate.score, 6),
        "resource_fairness": round(candidate.resource_fairness, 6),
        "geometry_score": round(candidate.geometry_score, 6),
        "teams": candidate.teams,
        "mex": [round(value, 3) for value in candidate.team_totals["mex"]],
        "hydro": [round(value, 3) for value in candidate.team_totals["hydro"]],
        "reclaim": [round(value, 3) for value in candidate.team_totals["reclaim"]],
    }


def _compatible_team_settings(
    prediction: Candidate | None,
    candidates: list[Candidate],
) -> list[str]:
    if prediction is None:
        return []

    settings = [prediction.layout]
    if prediction.team_size != 1:
        return settings

    for candidate in candidates:
        if candidate.team_size == 1:
            continue
        if candidate.resource_fairness < 0.92:
            continue
        if candidate.score < prediction.score - 0.12:
            continue
        if candidate.layout not in settings:
            settings.append(candidate.layout)
        if len(settings) >= 4:
            break
    return settings


def _team_setting_label(settings: list[str]) -> str:
    if not settings:
        return ""
    return "_or_".join(settings)


def infer_team_layout_rows(markers_csv: Path, resource_balance_csv: Path) -> list[dict[str, Any]]:
    resource_rows = _read_resource_rows(resource_balance_csv)
    spawns_by_map = _read_spawns(markers_csv)
    rows: list[dict[str, Any]] = []

    for map_dir, resource_row in sorted(resource_rows.items()):
        spawns = spawns_by_map.get(map_dir, [])
        spawn_count = len(spawns)
        warnings = []
        if not spawns:
            warnings.append("missing_playable_spawns")

        resource_counts = {
            "mex": _parse_counts(resource_row, "mex", spawn_count),
            "hydro": _parse_counts(resource_row, "hydro", spawn_count),
            "reclaim": _parse_counts(resource_row, "reclaim", spawn_count),
        }
        candidates = [
            _build_candidate(strategy, team_count, team_size, teams, spawns, resource_counts)
            for strategy, team_count, team_size, teams in _candidate_partitions(spawns)
        ]
        candidates.sort(key=lambda candidate: candidate.score, reverse=True)
        prediction = _choose_candidate(candidates)
        non_ffa = next((candidate for candidate in candidates if candidate.team_size > 1), None)
        ffa = next((candidate for candidate in candidates if candidate.team_size == 1), None)
        second = next((candidate for candidate in candidates if candidate is not prediction), None)

        row = {column: "" for column in TEAM_LAYOUT_COLUMNS}
        row["map_dir"] = map_dir
        row["spawn_count"] = spawn_count
        row["warnings"] = "|".join(warnings)
        if prediction is not None:
            confidence = prediction.score - (second.score if second is not None else 0.0)
            compatible_settings = _compatible_team_settings(prediction, candidates)
            row.update(
                {
                    "predicted_layout": prediction.layout,
                    "predicted_team_setting": _team_setting_label(compatible_settings),
                    "predicted_team_count": prediction.team_count,
                    "predicted_team_size": prediction.team_size,
                    "prediction_confidence": round(max(0.0, confidence), 6),
                    "prediction_score": round(prediction.score, 6),
                    "prediction_strategy": prediction.strategy,
                    "predicted_resource_fairness": round(prediction.resource_fairness, 6),
                    "compatible_team_settings_json": json.dumps(compatible_settings),
                    "team_spawn_indices_json": json.dumps(prediction.teams),
                    "team_spawn_names_json": json.dumps(
                        [[spawns[index].name for index in team] for team in prediction.teams]
                    ),
                    "team_mex_counts_json": json.dumps(
                        [round(value, 3) for value in prediction.team_totals["mex"]]
                    ),
                    "team_hydro_counts_json": json.dumps(
                        [round(value, 3) for value in prediction.team_totals["hydro"]]
                    ),
                    "team_reclaim_counts_json": json.dumps(
                        [round(value, 3) for value in prediction.team_totals["reclaim"]]
                    ),
                }
            )
        if ffa is not None:
            row["ffa_resource_fairness"] = round(ffa.resource_fairness, 6)
        if non_ffa is not None:
            row["best_non_ffa_layout"] = non_ffa.layout
            row["best_non_ffa_score"] = round(non_ffa.score, 6)
            row["best_non_ffa_resource_fairness"] = round(non_ffa.resource_fairness, 6)
        if second is not None:
            row["second_layout"] = second.layout
            row["second_score"] = round(second.score, 6)
        row["top_candidates_json"] = json.dumps(
            [_candidate_to_summary(candidate) for candidate in candidates[:8]],
            sort_keys=True,
        )
        rows.append(row)

    return rows


def write_csv(rows: list[dict[str, Any]], out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=TEAM_LAYOUT_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)


def write_summary(rows: list[dict[str, Any]], out_path: Path) -> None:
    layout_counts: dict[str, int] = defaultdict(int)
    setting_counts: dict[str, int] = defaultdict(int)
    low_confidence = 0
    for row in rows:
        layout_counts[str(row.get("predicted_layout", ""))] += 1
        setting_counts[str(row.get("predicted_team_setting", ""))] += 1
        try:
            if float(row.get("prediction_confidence") or 0.0) < 0.03:
                low_confidence += 1
        except ValueError:
            low_confidence += 1
    summary = {
        "row_count": len(rows),
        "predicted_layout_counts": dict(sorted(layout_counts.items())),
        "predicted_team_setting_counts": dict(sorted(setting_counts.items())),
        "low_confidence_count": low_confidence,
    }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Infer likely team layouts from spawn positions and assigned resources."
    )
    parser.add_argument("--markers", required=True, type=Path)
    parser.add_argument("--resource-balance", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--summary-out", type=Path)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    rows = infer_team_layout_rows(args.markers, args.resource_balance)
    write_csv(rows, args.out)
    if args.summary_out:
        write_summary(rows, args.summary_out)
    print(f"Wrote {len(rows)} team layout row(s) to {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
