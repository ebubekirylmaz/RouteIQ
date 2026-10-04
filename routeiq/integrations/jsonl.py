import json
import threading
from pathlib import Path


class JsonlExport:
    def __init__(self, path):
        self.path = Path(path)
        self._lock = threading.Lock()

    def send(self, record):
        line = json.dumps(record, ensure_ascii=False)
        with self._lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open("a", encoding="utf-8") as f:     
                f.write(line + "\n")