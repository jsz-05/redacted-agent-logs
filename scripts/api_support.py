"""Portable credential loading and the same locked cumulative spend guard used in the study."""
from __future__ import annotations
import os,json,time,fcntl
from pathlib import Path

def read_key(path: Path | None = None) -> str:
    if os.environ.get("OPENROUTER_API_KEY"):
        return os.environ["OPENROUTER_API_KEY"]
    if path is not None:
        for line in path.read_text().splitlines():
            field, sep, value = line.strip().removeprefix("export ").partition("=")
            if sep and field == "OPENROUTER_API_KEY":
                key = value.strip().strip("\"'")
                if key:
                    return key
    raise RuntimeError("No configured OpenRouter key available")

class CappedClient:
    def _event(self, event: dict, reservation: float = 0.0) -> None:
        with self.budget_file.open("a+") as f:
            fcntl.flock(f, fcntl.LOCK_EX)
            f.seek(0)
            rows = [json.loads(s) for s in f if s.strip()]
            pending = {}
            spent = 0.0
            for row in rows:
                if row["event"] == "reserve":
                    pending[row["request_id"]] = row["reserved_usd"]
                elif row["event"] == "settle":
                    pending.pop(row["request_id"], None)
                    spent += row["charged_usd"]
            if reservation and spent + sum(pending.values()) + reservation > self.cap:
                raise RuntimeError("Research pilot spend cap reached")
            f.seek(0, 2)
            f.write(json.dumps({**event, "time": time.time()}) + "\n")
            f.flush()
            os.fsync(f.fileno())
