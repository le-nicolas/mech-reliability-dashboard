$ErrorActionPreference = "Stop"

Set-Location (Join-Path $PSScriptRoot "..")

$args = @(
  "--noconfirm"
  "--clean"
  "--windowed"
  "--name"
  "ReliabilityDashboard"
  "--add-data"
  "sample_data;sample_data"
  "--add-data"
  "assets;assets"
  "--exclude-module"
  "torch"
  "--exclude-module"
  "tensorflow"
  "--exclude-module"
  "sklearn"
  "--exclude-module"
  "cv2"
  "--exclude-module"
  "av"
  "--exclude-module"
  "onnxruntime"
  "--exclude-module"
  "transformers"
  "--exclude-module"
  "numba"
  "--exclude-module"
  "scipy"
  "--exclude-module"
  "pyarrow"
  "--exclude-module"
  "pytest"
  "app/main.py"
)

python -m PyInstaller @args

Write-Host "Build complete. Output: dist/ReliabilityDashboard/"
