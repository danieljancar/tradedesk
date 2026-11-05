"""Questions to the desk from the dashboard, answered by a short headless Claude Code session
that can read the latest run and search the web, and can't trade or change anything."""

import json
import subprocess
import threading
import uuid
from datetime import UTC, datetime
from pathlib import Path

TIMEOUT = 240
TOOLS = ["Read", "Grep", "Glob", "WebSearch", "WebFetch", "Bash(uv run desk status)"]
PROMPT = """You answer questions from the owner of a small crypto trading desk.
The latest run folder is {run_dir}. book.md has the account, open positions and plans,
snapshot.md the market numbers, news.md the headlines, technical.md and decision.md the desk's
own reads. Read only what the question needs. Use web search for anything current that the
files don't cover, and say where a number comes from. Answer in a few plain sentences or a short
table, no headings, no filler, no advice wording. You can't place, change or approve trades.

Earlier in this conversation:
{history}

Question: {question}"""


class Asks:
    def __init__(self, root: Path, store: Path):
        self.root, self.store = root, store
        self.lock = threading.Lock()
        self.items: list[dict] = json.loads(store.read_text()) if store.exists() else []
        for i in self.items:
            if i["status"] == "thinking":
                i.update(status="error", answer="Stopped when the dashboard restarted.")

    def _save(self) -> None:
        self.store.parent.mkdir(parents=True, exist_ok=True)
        self.store.write_text(json.dumps(self.items[-50:], indent=1))

    def recent(self) -> list[dict]:
        return self.items[-30:]

    def busy(self) -> bool:
        with self.lock:
            return any(i["status"] == "thinking" for i in self.items)

    def start(self, question: str, run_dir: Path | None) -> dict:
        item = {
            "id": uuid.uuid4().hex[:10],
            "question": question.strip()[:1000],
            "answer": "",
            "status": "thinking",
            "asked_at": datetime.now(UTC).isoformat(timespec="seconds"),
        }
        history = "\n".join(
            f"Q: {i['question']}\nA: {i['answer'][:600]}"
            for i in self.items[-4:]
            if i["status"] == "done"
        )
        prompt = PROMPT.format(
            run_dir=run_dir or "none yet",
            history=history or "nothing yet",
            question=item["question"],
        )
        with self.lock:
            self.items.append(item)
            self._save()
        threading.Thread(target=self._run, args=(item, prompt), daemon=True).start()
        return item

    def _run(self, item: dict, prompt: str) -> None:
        cmd = ["claude", "-p", prompt, "--output-format", "json", "--permission-mode", "dontAsk"]
        cmd += ["--allowedTools", *TOOLS]
        try:
            res = subprocess.run(
                cmd, cwd=self.root, capture_output=True, text=True, timeout=TIMEOUT
            )
            out = json.loads(res.stdout or "{}")
            answer, ok = out.get("result") or res.stderr.strip()[:500], not out.get("is_error")
        except subprocess.TimeoutExpired:
            answer, ok = "No answer within four minutes.", False
        except Exception as e:
            answer, ok = f"Couldn't ask: {e}", False
        with self.lock:
            item.update(answer=answer or "No answer.", status="done" if ok else "error")
            self._save()
