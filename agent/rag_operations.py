from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any


RAG_OPERATION_NAMES = frozenset({"install", "enable", "disable", "remove", "verify", "verify_scope"})
_RESULT_MARKER = "__QRIIB_RAG_RESULT__"

# Fixed command: tenant values and secrets are sent on stdin, never embedded
# in a shell command, URL, Agent Job, Redis value, or log message.
RAG_TENANT_COMMAND = (
    "python3 -c \"import json,sys; import frappe; "
    "from frappe.installer import update_site_config; "
    "p=json.load(sys.stdin); op=p.get('operation'); "
    "conf=getattr(frappe,'conf',{}) or {}; "
    "cfg=(conf.get('arif_rag') if isinstance(conf,dict) else getattr(conf,'arif_rag',{})) or {}; "
    "result={}; "
    "if op=='install': "
    " from arif.press_provisioning import configure_tenant_site; "
    " configure_tenant_site(central_url=p['central_url'],tenant_id=p['tenant_id'],tenant_secret=p['tenant_secret']); "
    " update_site_config('arif_rag',{'enabled':False,'endpoint_url':p['endpoint_url'],'endpoint_provenance':'press_provisioning','service_token':p['service_token']},validate=False); "
    " result={'status':'installed','runtime_enabled':False}; "
    "elif op in ('enable','disable'): "
    " cfg=dict(cfg); "
    " result=({'status':'failed','runtime_enabled':False,'reason_code':'rag_credentials_missing'} if not cfg.get('endpoint_url') or not cfg.get('service_token') else {'status':'installed','runtime_enabled':op=='enable'}); "
    " update_site_config('arif_rag',{**cfg,'enabled':op=='enable'},validate=False) if result['status']!='failed' else None; "
    "elif op=='remove': update_site_config('arif_rag',None,validate=False); result={'status':'disabled','runtime_enabled':False}; "
    "elif op=='verify': "
    " from arif.rag.provisioning_client import RAGProvisioningClient; "
    " result=({'status':'failed','reason_code':'rag_credentials_missing'} if not cfg.get('endpoint_url') or not cfg.get('service_token') else {'status':'verified'}); "
    " RAGProvisioningClient(cfg['endpoint_url']).verify_service_token(cfg['service_token']) if result['status']=='verified' else None; "
    "elif op=='verify_scope': "
    " from arif.rag.scope_contract import verify_scope_contract; "
    " previous=cfg.get('enabled'); "
    " update_site_config('arif_rag',{**cfg,'enabled':True},validate=False); "
    " status=verify_scope_contract(); "
    " cfg=dict((getattr(frappe,'conf',{}) or {}).get('arif_rag') or {}); "
    " update_site_config('arif_rag',{**cfg,'enabled':previous},validate=False); "
    " result={'status':'verified' if status.verified else 'unverified','reason_code':status.reason}; "
    "print('" + _RESULT_MARKER + "'+json.dumps(result,separators=(',',':')))\""
)


def execute_rag_operation(site: Any, operation: str, payload: Mapping[str, Any]) -> dict[str, Any]:
    operation = str(operation or "").strip()
    if operation not in RAG_OPERATION_NAMES:
        raise ValueError("unsupported RAG operation")

    request_payload = dict(payload or {})
    request_payload["operation"] = operation
    result = site.bench_execute(
        RAG_TENANT_COMMAND,
        json.dumps(request_payload, separators=(",", ":")),
    )
    status = str(result.get("status") or "").lower()
    output = str(result.get("output") or "")
    if status not in {"success", "succeeded"} or int(result.get("returncode") or 0) != 0:
        return {"status": "failed", "reason_code": "tenant_command_failed"}

    for line in reversed(output.splitlines()):
        if line.startswith(_RESULT_MARKER):
            try:
                parsed = json.loads(line[len(_RESULT_MARKER) :])
            except (TypeError, ValueError):
                break
            if isinstance(parsed, dict):
                return parsed
    return {"status": "failed", "reason_code": "invalid_tenant_result"}
