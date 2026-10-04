"""PyTorch dataset for exported MapGen tensor manifests."""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Any

import numpy as np
import torch
from torch.utils.data import Dataset


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


class MapTensorDataset(Dataset[dict[str, Any]]):
    """Load tensors from a tensor manifest, optionally filtered by split."""

    def __init__(
        self,
        tensor_manifest: Path,
        splits_csv: Path | None = None,
        split: str | None = None,
        max_maps: int | None = None,
    ) -> None:
        rows = [row for row in _read_csv(tensor_manifest) if row.get("tensor_path")]
        if splits_csv is not None and split is not None:
            split_by_map = {
                row["map_dir"]: row["split"]
                for row in _read_csv(splits_csv)
                if row.get("map_dir") and row.get("split")
            }
            rows = [row for row in rows if split_by_map.get(row.get("map_dir", "")) == split]
        if max_maps is not None:
            rows = rows[:max_maps]
        self.rows = rows

    def __len__(self) -> int:
        return len(self.rows)

    def __getitem__(self, index: int) -> dict[str, Any]:
        row = self.rows[index]
        archive = np.load(row["tensor_path"])
        tensor = torch.from_numpy(archive["tensor"].astype(np.float32))
        return {
            "tensor": tensor,
            "map_id": row.get("map_id", ""),
            "map_dir": row.get("map_dir", ""),
        }
