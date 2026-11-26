"""Foundry REST client: Entra ID tokens only, no API keys, standard library only."""

import json
import math
import os
import random
import shutil
import subprocess
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from email.utils import parsedate_to_datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCOPE_RESOURCE = "https://cognitiveservices.azure.com"
MAX_RESPONSE_BYTES = 2_000_000
MAX_RETRY_WAIT_SECONDS = 10.0


def retry_after_seconds(value):
    """Parse Retry-After as seconds or an HTTP date; 0 when absent or invalid."""
    if not value:
        return 0.0
    try:
        return max(0.0, float(value))
    except ValueError:
        pass
    try:
        return max(0.0, parsedate_to_datetime(value).timestamp() - time.time())
    except (TypeError, ValueError, OverflowError):
        return 0.0


class FoundryError(RuntimeError):
    pass


class _RateLimited(Exception):
    def __init__(self, retry_after):
        super().__init__("rate limited")
        self.retry_after = retry_after


def load_config(path=None):
    """Read config.local.json, then apply environment overrides."""
    source = Path(path) if path else ROOT / "config.local.json"
    config = json.loads(source.read_text(encoding="utf-8")) if source.exists() else {}
    if not isinstance(config, dict):
        raise ValueError("Configuration must be a JSON object.")
    for env, key in {
        "FOUNDRY_ENDPOINT": "endpoint",
        "DECISION_DEPLOYMENT": "decision_deployment",
        "EXTRACTION_DEPLOYMENT": "extraction_deployment",
        "FOUNDRY_AUTH_MODE": "auth_mode",
        "AZURE_SUBSCRIPTION_ID": "subscription",
    }.items():
        if os.environ.get(env):
            config[key] = os.environ[env]
    for env, key in {"DAILY_MAX_CALLS": "daily_max_calls", "FOUNDRY_TIMEOUT_SECONDS": "timeout_seconds"}.items():
        if os.environ.get(env):
            try:
                config[key] = int(os.environ[env])
            except ValueError as exc:
                raise ValueError(f"{env} must be an integer.") from exc
    config.setdefault("auth_mode", "azure_cli")
    config.setdefault("timeout_seconds", 60)
    config.setdefault("daily_max_calls", 2000)
    config["endpoint"] = validate_endpoint(config.get("endpoint", ""))
    if not isinstance(config.get("decision_deployment"), str) or not config["decision_deployment"].strip():
        raise ValueError("Configure decision_deployment in config.local.json or DECISION_DEPLOYMENT.")
    if config["auth_mode"] not in {"azure_cli", "managed_identity"}:
        raise ValueError("auth_mode must be azure_cli or managed_identity.")
    for key in ("timeout_seconds", "daily_max_calls"):
        if isinstance(config[key], bool) or not isinstance(config[key], int) or config[key] < 1:
            raise ValueError(f"{key} must be a positive integer.")
    return config


def validate_endpoint(value):
    parsed = urllib.parse.urlsplit(value or "")
    if (parsed.scheme != "https" or not parsed.hostname
            or not parsed.hostname.endswith((".cognitiveservices.azure.com", ".services.ai.azure.com"))
            or parsed.username or parsed.password or parsed.port
            or parsed.path not in ("", "/") or parsed.query or parsed.fragment):
        raise ValueError("Configure a Foundry HTTPS resource endpoint without a path.")
    return value.rstrip("/")


class Foundry:
    def __init__(self, config):
        self.config = config
        self.endpoint = config["endpoint"]
        self._token, self._expires = None, 0.0
        self._lock = threading.Lock()

    def _fetch_token(self):
        if self.config["auth_mode"] == "managed_identity":
            endpoint, header = os.environ.get("IDENTITY_ENDPOINT"), os.environ.get("IDENTITY_HEADER")
            if not endpoint or not header:
                raise FoundryError("Managed identity is not available in this environment.")
            query = {"resource": SCOPE_RESOURCE, "api-version": "2019-08-01"}
            if os.environ.get("AZURE_CLIENT_ID"):
                query["client_id"] = os.environ["AZURE_CLIENT_ID"]
            request = urllib.request.Request(f"{endpoint}?{urllib.parse.urlencode(query)}",
                                             headers={"X-IDENTITY-HEADER": header})
            try:
                with urllib.request.urlopen(request, timeout=15) as response:
                    data = json.load(response)
                return data["access_token"], float(data["expires_on"])
            except (urllib.error.URLError, KeyError, TypeError, ValueError, OSError) as exc:
                raise FoundryError("Managed identity token request failed.") from exc
        az = shutil.which("az")
        if not az:
            raise FoundryError("Azure CLI not found. Install it and run az login.")
        command = [az, "account", "get-access-token", "--resource", SCOPE_RESOURCE, "-o", "json"]
        if self.config.get("subscription"):
            command += ["--subscription", self.config["subscription"]]
        try:
            result = subprocess.run(command, capture_output=True, text=True, timeout=60, check=False)
            data = json.loads(result.stdout) if result.returncode == 0 else None
            return data["accessToken"], float(data["expires_on"])
        except (OSError, subprocess.TimeoutExpired, json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
            raise FoundryError("Azure CLI token request failed. Run az login.") from exc

    def token(self):
        with self._lock:
            if not self._token or self._expires < time.time() + 120:
                self._token, self._expires = self._fetch_token()
            return self._token

    def post(self, path, body, timeout=None, retries=2):
        """POST JSON; return (payload, latency_ms). Retries only rate limiting (HTTP 429), and
        only when the service's Retry-After (if any) is short; never earlier than it asks."""
        for attempt in range(retries + 1):
            try:
                return self._post_once(path, body, timeout)
            except _RateLimited as limited:
                wait = limited.retry_after if limited.retry_after else (1.5 * (attempt + 1) + random.uniform(0, 1))
                if attempt == retries or wait > MAX_RETRY_WAIT_SECONDS:
                    raise FoundryError("Foundry returned HTTP 429: rate limited. Try again shortly.") from limited
                time.sleep(wait)

    def _post_once(self, path, body, timeout):
        request = urllib.request.Request(
            self.endpoint + path, data=json.dumps(body).encode("utf-8"), method="POST",
            headers={"Content-Type": "application/json", "Authorization": f"Bearer {self.token()}"},
        )
        started = time.perf_counter()
        try:
            with urllib.request.urlopen(request, timeout=timeout or self.config["timeout_seconds"]) as response:
                raw = response.read(MAX_RESPONSE_BYTES + 1)
        except urllib.error.HTTPError as exc:
            if exc.code == 429:
                raise _RateLimited(retry_after_seconds(exc.headers.get("Retry-After"))) from exc
            detail = exc.read(500).decode("utf-8", "replace") if exc.code in (400, 413, 422) else ""
            raise FoundryError(f"Foundry returned HTTP {exc.code}. {detail}".strip()) from exc
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise FoundryError("Foundry connection failed or timed out.") from exc
        latency_ms = round((time.perf_counter() - started) * 1000, 1)
        if len(raw) > MAX_RESPONSE_BYTES:
            raise FoundryError("Foundry response was unexpectedly large.")
        try:
            payload = json.loads(raw)
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise FoundryError("Foundry returned invalid JSON.") from exc
        if not isinstance(payload, dict):
            raise FoundryError("Foundry returned an unexpected response.")
        return payload, latency_ms


def probability(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not 0 <= value <= 1:
        raise FoundryError("Model returned an invalid probability.")
    return float(value)


def usage_of(payload):
    usage = payload.get("usage")
    if not isinstance(usage, dict):
        raise FoundryError("Model response omitted usage.")
    tokens = {"input_tokens": usage.get("input_tokens", usage.get("prompt_tokens")),
              "output_tokens": usage.get("output_tokens", usage.get("completion_tokens"))}
    if any(isinstance(v, bool) or not isinstance(v, int) or v < 0 for v in tokens.values()):
        raise FoundryError("Model response returned invalid usage.")
    return tokens
