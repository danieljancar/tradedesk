import json
import subprocess
import time

from tradedesk import ask


class Done:
    def __init__(self, out: dict):
        self.stdout, self.stderr = json.dumps(out), ""


def wait(asks):
    for _ in range(100):
        if not asks.busy():
            return
        time.sleep(0.01)


def test_answer_is_stored_and_tools_stay_read_only(tmp_path, monkeypatch):
    seen = {}

    def fake(cmd, **kw):
        seen["cmd"] = cmd
        return Done({"result": "Nasdaq fell 5.5%.", "is_error": False})

    monkeypatch.setattr(subprocess, "run", fake)
    asks = ask.Asks(tmp_path, tmp_path / "asks.json")
    item = asks.start("what happened to the nasdaq?", tmp_path / "run")
    wait(asks)
    assert asks.recent()[-1]["answer"] == "Nasdaq fell 5.5%."
    assert item["status"] == "done"
    assert "Bash(uv run desk execute)" not in seen["cmd"]
    assert str(tmp_path / "run") in seen["cmd"][2]
    assert json.loads((tmp_path / "asks.json").read_text())[0]["status"] == "done"


def test_history_goes_into_the_next_prompt(tmp_path, monkeypatch):
    prompts = []

    def fake(cmd, **kw):
        prompts.append(cmd[2])
        return Done({"result": f"answer {len(prompts)}"})

    monkeypatch.setattr(subprocess, "run", fake)
    asks = ask.Asks(tmp_path, tmp_path / "asks.json")
    asks.start("first", None)
    wait(asks)
    asks.start("second", None)
    wait(asks)
    assert "Q: first" in prompts[1] and "A: answer 1" in prompts[1]
