from __future__ import annotations

import json
import unittest
from unittest.mock import Mock

from agent.rag_operations import RAG_OPERATION_NAMES, execute_rag_operation


class TestRAGOperations(unittest.TestCase):
    def test_supported_operation_executes_fixed_command_with_payload_on_stdin(self):
		site = Mock()
		site.bench_execute.return_value = {
			"status": "success",
			"output": '>>> __QRIIB_RAG_RESULT__{"status":"verified"}',
            "returncode": 0,
        }

        result = execute_rag_operation(
            site,
            "verify",
            {"endpoint_url": "https://rag.example.com", "service_token": "payload-token-123"},
        )

        self.assertEqual(result, {"status": "verified"})
        site.bench_execute.assert_called_once()
		command = site.bench_execute.call_args.args[0]
		script = site.bench_execute.call_args.kwargs["input"]
		self.assertEqual(command, "console")
		self.assertNotIn("python3", command)
		self.assertIn("payload-token-123", script)
		self.assertIn('"operation": "verify"', script)
		self.assertTrue(script.startswith("import json\n"))

    def test_unknown_operation_is_rejected_before_execution(self):
        site = Mock()

        with self.assertRaises(ValueError):
            execute_rag_operation(site, "shell", {})

        site.bench_execute.assert_not_called()

    def test_failed_tenant_execution_does_not_return_raw_output(self):
        site = Mock()
        site.bench_execute.return_value = {
            "status": "failed",
            "output": "service_token=secret",
            "returncode": 1,
        }

        result = execute_rag_operation(site, "verify", {})

        self.assertEqual(result["status"], "failed")
        self.assertNotIn("payload-token-123", str(result))


if __name__ == "__main__":
    unittest.main()
