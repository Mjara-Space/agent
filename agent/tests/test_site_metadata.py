import unittest
from types import SimpleNamespace
from unittest.mock import Mock

from agent.site_metadata import execute_site_metadata_operation


class TestSiteMetadata(unittest.TestCase):
	def test_returns_normalized_arabic_language(self):
		site = SimpleNamespace(
			bench_execute=Mock(
				return_value={
					"status": "success",
					"output": '__QRIIB_SITE_METADATA_RESULT__{"status":"ok","language":"ar"}',
				}
			)
		)

		self.assertEqual(execute_site_metadata_operation(site, "language"), {"status": "ok", "language": "ar"})
		site.bench_execute.assert_called_once()
		self.assertIn('System Settings", "language', site.bench_execute.call_args.kwargs["input"])

	def test_rejects_invalid_tenant_language_without_exposing_output(self):
		site = SimpleNamespace(
			bench_execute=Mock(
				return_value={
					"status": "success",
					"output": '__QRIIB_SITE_METADATA_RESULT__{"status":"failed","reason_code":"invalid_language"}',
				}
			)
		)

		self.assertEqual(execute_site_metadata_operation(site, "language"), {"status": "failed", "reason_code": "invalid_language"})

	def test_rejects_unsupported_operation(self):
		with self.assertRaises(ValueError):
			execute_site_metadata_operation(SimpleNamespace(), "config")

	def test_reads_tenant_user_language(self):
		site = SimpleNamespace(
			bench_execute=Mock(
				return_value={
					"status": "success",
					"output": '__QRIIB_SITE_METADATA_RESULT__{"status":"ok","language":"ar"}',
				}
			)
		)

		self.assertEqual(
			execute_site_metadata_operation(site, "user_language", user="person@example.com"),
			{"status": "ok", "language": "ar"},
		)
		script = site.bench_execute.call_args.kwargs["input"]
		self.assertIn('frappe.db.get_value("User", user, "language")', script)
		self.assertIn("person@example.com", script)

	def test_requires_user_for_user_language(self):
		site = SimpleNamespace(bench_execute=Mock())
		self.assertEqual(
			execute_site_metadata_operation(site, "user_language"),
