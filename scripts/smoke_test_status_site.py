from pathlib import Path

required = [
    "status-site/index.html",
    "status-site/assets/app.js",
    "status-site/assets/app.css",
]
for path in required:
    assert Path(path).exists(), f"missing {path}"
print("status-site smoke test passed")
