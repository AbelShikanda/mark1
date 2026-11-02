import os
from pathlib import Path

DATA_DIRS = [
    "data",
    "whatsapp_session",
    "logs",
]

def setup() -> None:
    for d in DATA_DIRS:
        Path(d).mkdir(parents=True, exist_ok=True)
    print("data dirs ready")
