# Windows Environment Notes

MapGen is a Windows-first project. Do not assume Linux or WSL.

## Current Python State

The checked local `.venv` currently points at:

```text
C:\Users\YOUR_USERNAME\AppData\Local\Programs\Python\Python312\python.exe
```

That interpreter was not available during the latest export work, so the `.venv` launcher could not start. For non-training scripts, the Codex bundled Python 3.12 runtime was used successfully:

```text
C:\Users\YOUR_USERNAME\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe
```

That bundled runtime has NumPy and Pillow and is good enough for inventory, reports, tensor inspection, and FAF export tooling. It should not be treated as the long-term ML training environment.

## Recommended Repair

Install or restore Python `3.12.x`, then recreate the project venv:

```powershell
Remove-Item -Recurse -Force .venv
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -e ".[dev,ml]"
```

Then install PyTorch with the CUDA wheel appropriate for the local NVIDIA setup. Keep this as an explicit command in your local notes because the right PyTorch CUDA index may change over time.

## Temporary Script Runner

Until the venv is repaired, this project can run pure NumPy/Pillow tools with:

```powershell
$env:PYTHONPATH='src'
C:\Users\YOUR_USERNAME\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe -m supmapai.tools.dataset_quality_report --help
```
