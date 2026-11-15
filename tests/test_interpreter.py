from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from chromantis.app import ApplicationService, CommandQueryInterpreter, RuleQueryInterpreter
from chromantis.db.repository import Repository


class QueryInterpreterTests(unittest.TestCase):
    def make_interpreter(self, code: str, timeout: float = 2.0) -> CommandQueryInterpreter:
        return CommandQueryInterpreter((sys.executable, "-c", code), timeout)

    def test_application_accepts_a_local_model_adapter(self) -> None:
        script = """
import json
import sys
request = json.load(sys.stdin)
assert request["text"] == "find the blue umbrella"
json.dump({"action": "images", "query": "umbrella 2021", "count": 2, "confidence": 0.87}, sys.stdout)
"""
        with TemporaryDirectory() as temp_dir:
            repository = Repository(str(Path(temp_dir) / "chromantis.db"))
            service = ApplicationService(repository, interpreter=self.make_interpreter(script))
            result = service.interpret_text("find the blue umbrella")

        self.assertEqual((result.action, result.query, result.count), ("images", "umbrella 2021", 2))
        self.assertEqual(result.confidence, 0.87)
        self.assertFalse(result.needs_clarification)

    def test_low_confidence_asks_instead_of_running_a_guess(self) -> None:
        response = json.dumps({"action": "images", "query": "guess", "count": 1, "confidence": 0.2})
        interpreter = self.make_interpreter(f"print({response!r})")

        result = interpreter.interpret("perhaps some photos")

        self.assertTrue(result.needs_clarification)
        self.assertEqual((result.clarification, result.query), ("model_uncertain", ""))
        self.assertEqual(result.confidence, 0.2)

    def test_bad_or_unavailable_adapter_uses_rules(self) -> None:
        text = "show me 2 city photos from 2021"
        expected = RuleQueryInterpreter().interpret(text)
        for script, timeout in (
            ("print('not JSON')", 2.0),
            ("raise SystemExit(4)", 2.0),
            ("import time; time.sleep(1)", 0.02),
            ("print('{\"confidence\": 1.0, \"action\": \"delete\"}')", 2.0),
        ):
            with self.subTest(script=script), self.assertLogs("chromantis.app.interpreter", level="WARNING"):
                self.assertEqual(self.make_interpreter(script, timeout).interpret(text), expected)
