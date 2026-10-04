"""Print a small PyTorch CUDA smoke-test report."""

from __future__ import annotations

import platform
import sys


def main() -> int:
    print(f"Python: {sys.version.split()[0]} ({platform.platform()})")

    try:
        import torch
    except ImportError:
        print("PyTorch: not installed")
        print("Install it with the Windows CUDA command from README.md, then rerun this check.")
        return 1

    print(f"PyTorch: {torch.__version__}")
    print(f"CUDA available: {torch.cuda.is_available()}")
    print(f"PyTorch CUDA runtime: {torch.version.cuda}")

    if not torch.cuda.is_available():
        print("No CUDA device is visible to PyTorch.")
        return 1

    device_count = torch.cuda.device_count()
    print(f"CUDA device count: {device_count}")
    for index in range(device_count):
        print(f"GPU {index}: {torch.cuda.get_device_name(index)}")

    device = torch.device("cuda:0")
    tensor = torch.arange(8, dtype=torch.float32, device=device)
    result = (tensor * 2).sum().item()
    print(f"CUDA tensor smoke test: ok ({result})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
