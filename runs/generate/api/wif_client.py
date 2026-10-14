#!/usr/bin/env python3
import os, sys
ORGS = ("batch", "loprio", "hiprio")
def wif_ids(org="batch"):
    assert org in ORGS, f"unknown org {org!r}: one of {ORGS}"
    ids = {}
    p = os.path.join(os.environ.get("ANTHROPIC_WIF_DIR", "."), f"wif-{org}.env")
    with open(p) as f:
        for line in f:
            if "=" in line and not line.startswith("#"):
                k, v = line.strip().split("=", 1); ids[k] = v
    for k in ("ANTHROPIC_FEDERATION_RULE_ID_GCP", "ANTHROPIC_ORGANIZATION_ID", "ANTHROPIC_SERVICE_ACCOUNT_ID", "ANTHROPIC_WORKSPACE_ID"):
        assert ids.get(k), f"{p} lacks {k}"
    return ids
def google_token():
    import google.auth.transport.requests, google.oauth2.id_token
    return google.oauth2.id_token.fetch_id_token(google.auth.transport.requests.Request(), "https://api.anthropic.com")
def client(org="batch", **kw):
    """the SDK client signed in by federation for <org>; kw passes through to Anthropic(...) (timeouts, max_retries) — never api_key"""
    assert "api_key" not in kw, "never a key"
    for _v in ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN"): os.environ.pop(_v, None)
    from anthropic import Anthropic, WorkloadIdentityCredentials
    ids = wif_ids(org)
    return Anthropic(credentials=WorkloadIdentityCredentials(identity_token_provider=google_token, federation_rule_id=ids["ANTHROPIC_FEDERATION_RULE_ID_GCP"], organization_id=ids["ANTHROPIC_ORGANIZATION_ID"], service_account_id=ids["ANTHROPIC_SERVICE_ACCOUNT_ID"], workspace_id=ids["ANTHROPIC_WORKSPACE_ID"]), **kw)
if __name__ == "__main__":
    org = sys.argv[1] if len(sys.argv) > 1 else "batch"; import time; t0 = time.time()
    m = client(org).models.list(limit=1); print(f"{org}: WIF auth ok — models.list answered in {time.time() - t0:.1f}s, first model {m.data[0].id if m.data else None}")
