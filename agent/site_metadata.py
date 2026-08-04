from __future__ import annotations

import json
from typing import Any


SITE_METADATA_OPERATION_NAMES = frozenset({"language", "user_language"})
_RESULT_MARKER = "__QRIIB_SITE_METADATA_RESULT__"


def _build_language_script() -> str:
	return f'''import json
import frappe

value = frappe.db.get_single_value("System Settings", "language")
value = str(value or "").strip().lower()
language = "ar" if value.startswith("ar") else "en" if value.startswith("en") else None
result = {{"status": "ok", "language": language}} if language else {{"status": "failed", "reason_code": "invalid_language"}}
print({_RESULT_MARKER!r} + json.dumps(result, separators=(",", ":")))
'''


def _build_user_language_script(user: str) -> str:
	user_literal = json.dumps(user)
	return f'''import json
import frappe

user = {user_literal}
value = frappe.db.get_value("User", user, "language")
value = str(value or "").strip().lower()
language = "ar" if value.startswith("ar") else "en" if value.startswith("en") else None
result = {{"status": "ok", "language": language}} if language else {{"status": "failed", "reason_code": "user_language_unavailable"}}
print({_RESULT_MARKER!r} + json.dumps(result, separators=(",", ":")))
'''


def execute_site_metadata_operation(site: Any, operation: str, user: str | None = None) -> dict[str, str]:
	if operation not in SITE_METADATA_OPERATION_NAMES:
		raise ValueError("unsupported site metadata operation")
	if operation == "user_language" and not str(user or "").strip():
		return {"status": "failed", "reason_code": "user_required"}

	script = _build_user_language_script(user.strip()) if operation == "user_language" else _build_language_script()
	result = site.bench_execute("console", input=script)
	if str(result.get("status") or "").lower() not in {"success", "succeeded"}:
		return {"status": "failed", "reason_code": "tenant_command_failed"}

	for line in reversed(str(result.get("output") or "").splitlines()):
		marker_index = line.find(_RESULT_MARKER)
		if marker_index < 0:
			continue
		try:
			parsed = json.loads(line[marker_index + len(_RESULT_MARKER) :])
		except (TypeError, ValueError):
			break
		if isinstance(parsed, dict) and parsed.get("status") == "ok" and parsed.get("language") in {"ar", "en"}:
			return {"status": "ok", "language": parsed["language"]}
		if isinstance(parsed, dict) and parsed.get("reason_code"):
			return {"status": "failed", "reason_code": str(parsed["reason_code"])}

	return {"status": "failed", "reason_code": "invalid_tenant_result"}
