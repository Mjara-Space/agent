import json
import sys
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from agent.site_metadata import _build_language_script, _build_user_language_script, execute_site_metadata_operation


class TestSiteMetadata(unittest.TestCase):
	def _execute_console_script(self, script, language):
		database = SimpleNamespace(
			get_single_value=Mock(return_value=language),
			get_value=Mock(return_value=language),
		)
		output = []
		with patch.dict(sys.modules, {"frappe": SimpleNamespace(db=database)}):
			with patch("builtins.print", side_effect=output.append):
				exec(script, {})
		return json.loads(output[-1].split("__QRIIB_SITE_METADATA_RESULT__", 1)[1])

	def test_outputs_supported_site_languages_as_base_language(self):
		for value, expected in (("ar", "ar"), ("ar-SA", "ar"), ("en", "en"), ("en-US", "en")):
			with self.subTest(value=value):
				self.assertEqual(self._execute_console_script(_build_language_script(), value), {"status": "ok", "language": expected})

	def test_outputs_malformed_site_languages_as_english(self):
		for value in ("arSA", "arabic", "ar-", "ar_SA", "unknown"):
			with self.subTest(value=value):
				self.assertEqual(self._execute_console_script(_build_language_script(), value), {"status": "ok", "language": "en"})

	def test_outputs_supported_user_languages_as_base_language(self):
		for value, expected in (("ar", "ar"), ("ar-SA", "ar"), ("en", "en"), ("en-US", "en")):
			with self.subTest(value=value):
				self.assertEqual(
					self._execute_console_script(_build_user_language_script("person@example.com"), value),
					{"status": "ok", "language": expected},
				)

	def test_outputs_malformed_user_languages_as_english(self):
		for value in ("arSA", "arabic", "ar-", "ar_SA", "unknown"):
			with self.subTest(value=value):
				self.assertEqual(
					self._execute_console_script(_build_user_language_script("person@example.com"), value),
					{"status": "ok", "language": "en"},
				)

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

	def test_defaults_invalid_tenant_language_to_english(self):
		site = SimpleNamespace(
			bench_execute=Mock(
				return_value={
					"status": "success",
					"output": '__QRIIB_SITE_METADATA_RESULT__{"status":"ok","language":"en"}',
				}
			)
		)

		self.assertEqual(execute_site_metadata_operation(site, "language"), {"status": "ok", "language": "en"})

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
			{"status": "failed", "reason_code": "user_required"},
		)
