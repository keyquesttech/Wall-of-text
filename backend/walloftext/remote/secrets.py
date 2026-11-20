"""Channel secrets in `<data_dir>/secrets.json` (mode 0600). Never in the password
file, never in backups, never in logs (BUILD_PLAN 9.2)."""
from __future__ import annotations

import json
import os
import tempfile
import threading
from pathlib import Path


class Secrets:
    def __init__(self, path: Path):
        self.path = Path(path)
        self._lock = threading.Lock()

    def _read(self) -> dict:
        try:
            return json.loads(self.path.read_text())
        except (OSError, ValueError):
            return {}

    def get(self, channel: str) -> dict:
        return dict(self._read().get(channel, {}))

    def set(self, channel: str, values: dict) -> None:
        with self._lock:
            data = self._read()
            cur = data.get(channel, {})
            for k, v in values.items():
                if v is None or v == "":
                    cur.pop(k, None)
                else:
                    cur[k] = v
            data[channel] = cur
            self.path.parent.mkdir(parents=True, exist_ok=True)
            fd, tmp = tempfile.mkstemp(prefix=".secrets.", dir=str(self.path.parent))
            with os.fdopen(fd, "w") as fh:
                json.dump(data, fh)
            os.chmod(tmp, 0o600)
            os.replace(tmp, self.path)

    def clear(self, channel: str) -> None:
        with self._lock:
            data = self._read()
            data.pop(channel, None)
            self.path.write_text(json.dumps(data))
            os.chmod(self.path, 0o600)

    def has(self, channel: str, *keys: str) -> bool:
        c = self.get(channel)
        return all(c.get(k) for k in keys)
