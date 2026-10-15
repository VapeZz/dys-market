"""Shared Shopify Admin API client (client-credentials or admin token)."""
import json
import os
import time
import urllib.error
import urllib.request

API_VERSION = os.environ.get("SHOPIFY_API_VERSION", "2026-01")


class Shopify:
    def __init__(self, shop):
        self.shop = shop
        self.token = os.environ.get("SHOPIFY_ADMIN_TOKEN") or self._client_credentials()

    def _post(self, url, body, headers):
        req = urllib.request.Request(url, data=json.dumps(body).encode(), headers={"Content-Type": "application/json", **headers})
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                return json.loads(resp.read().decode())
        except urllib.error.HTTPError as err:
            detail = err.read().decode(errors="replace")[:300]
            where = url.split("/admin/")[-1]
            raise RuntimeError(f"HTTP {err.code} from Shopify ({where}): {detail}") from None

    def _client_credentials(self):
        cid, secret = os.environ.get("SHOPIFY_CLIENT_ID"), os.environ.get("SHOPIFY_CLIENT_SECRET")
        if not (cid and secret):
            print("::warning title=Missing secret::SHOPIFY_CLIENT_ID / SHOPIFY_CLIENT_SECRET not set")
            raise SystemExit(0)
        out = self._post(f"https://{self.shop}/admin/oauth/access_token",
                         {"grant_type": "client_credentials", "client_id": cid, "client_secret": secret}, {})
        return out["access_token"]

    def gql(self, query, variables=None):
        for attempt in range(4):
            out = self._post(f"https://{self.shop}/admin/api/{API_VERSION}/graphql.json",
                             {"query": query, "variables": variables or {}}, {"X-Shopify-Access-Token": self.token})
            errs = out.get("errors")
            if errs and any("THROTTLED" in json.dumps(e) for e in errs):
                time.sleep(2 * (attempt + 1))
                continue
            if errs:
                raise RuntimeError(f"Shopify error: {errs}")
            return out["data"]
        raise RuntimeError("Shopify: throttled too many times")
