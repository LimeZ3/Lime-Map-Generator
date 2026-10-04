"""Create family-safe train/validation/test splits from dataset audit rows."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

SPLIT_COLUMNS = [
    "map_id",
    "map_dir",
    "split",
    "split_group_key",
    "audit_status",
    "size_class",
    "player_slots",
    "predicted_team_setting",
    "duplicate_family_key",
]


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def _stable_random_unit(key: str, seed: int) -> float:
    digest = hashlib.sha256(f"{seed}:{key}".encode()).digest()
    return int.from_bytes(digest[:8], "big") / 2**64


def _split_group_key(row: dict[str, str]) -> str:
    family_key = row.get("duplicate_family_key", "").strip()
    return f"family:{family_key}" if family_key else f"map:{row['map_dir']}"


def _split_targets(total: int, train: float, val: float, test: float) -> dict[str, int]:
    ratio_sum = train + val + test
    if ratio_sum <= 0:
        raise ValueError("split ratios must sum to more than zero")
    train /= ratio_sum
    val /= ratio_sum
    test /= ratio_sum
    train_count = round(total * train)
    val_count = round(total * val)
    test_count = max(0, total - train_count - val_count)
    return {"train": train_count, "val": val_count, "test": test_count}


def _choose_split(counts: dict[str, int], targets: dict[str, int]) -> str:
    deficits = {
        split: targets[split] - counts.get(split, 0)
        for split in ("train", "val", "test")
    }
    return max(deficits, key=lambda split: (deficits[split], split == "train"))


def build_splits(
    audit_rows: list[dict[str, str]],
    statuses: set[str],
    seed: int,
    train_ratio: float,
    val_ratio: float,
    test_ratio: float,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    eligible = [row for row in audit_rows if row.get("audit_status") in statuses]
    groups: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in eligible:
        groups[_split_group_key(row)].append(row)

    ordered_groups = sorted(
        groups.items(),
        key=lambda item: (
            -len(item[1]),
            _stable_random_unit(item[0], seed),
            item[0],
        ),
    )
    targets = _split_targets(len(eligible), train_ratio, val_ratio, test_ratio)
    counts = {"train": 0, "val": 0, "test": 0}
    rows = []
    for group_key, members in ordered_groups:
        split = _choose_split(counts, targets)
        counts[split] += len(members)
        for row in sorted(members, key=lambda item: item["map_dir"].lower()):
            rows.append(
                {
                    "map_id": row.get("map_id", ""),
                    "map_dir": row.get("map_dir", ""),
                    "split": split,
                    "split_group_key": group_key,
                    "audit_status": row.get("audit_status", ""),
                    "size_class": row.get("size_class", ""),
                    "player_slots": row.get("player_slots", ""),
                    "predicted_team_setting": row.get("predicted_team_setting", ""),
                    "duplicate_family_key": row.get("duplicate_family_key", ""),
                }
            )

    status_counts = Counter(row["audit_status"] for row in rows)
    split_counts = Counter(row["split"] for row in rows)
    size_by_split: dict[str, Counter[str]] = defaultdict(Counter)
    for row in rows:
        size_by_split[row["split"]][row["size_class"] or "unknown"] += 1
    summary = {
        "seed": seed,
        "eligible_statuses": sorted(statuses),
        "input_map_count": len(audit_rows),
        "eligible_map_count": len(eligible),
        "split_group_count": len(groups),
        "target_counts": targets,
        "actual_counts": dict(sorted(split_counts.items())),
        "audit_status_counts": dict(sorted(status_counts.items())),
        "size_class_counts_by_split": {
            split: dict(sorted(counter.items()))
            for split, counter in sorted(size_by_split.items())
        },
    }
    return rows, summary


def write_outputs(
    rows: list[dict[str, Any]],
    summary: dict[str, Any],
    out: Path,
    summary_out: Path,
) -> None:
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=SPLIT_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)
    summary_out.parent.mkdir(parents=True, exist_ok=True)
    summary_out.write_text(json.dumps(summary, indent=2), encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Create family-safe dataset splits.")
    parser.add_argument("--audit-maps", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--summary-out", required=True, type=Path)
    parser.add_argument(
        "--status",
        action="append",
        help="Audit status to include. Repeat for multiple statuses. Defaults to ready + review.",
    )
    parser.add_argument("--seed", default=20260711, type=int)
    parser.add_argument("--train-ratio", default=0.8, type=float)
    parser.add_argument("--val-ratio", default=0.1, type=float)
    parser.add_argument("--test-ratio", default=0.1, type=float)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    rows, summary = build_splits(
        audit_rows=_read_csv(args.audit_maps),
        statuses=set(args.status or ["ready", "review"]),
        seed=args.seed,
        train_ratio=args.train_ratio,
        val_ratio=args.val_ratio,
        test_ratio=args.test_ratio,
    )
    write_outputs(rows, summary, args.out, args.summary_out)
    print(f"Wrote {len(rows)} split row(s) to {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
