"""Tiny HTTP helpers (stdlib urllib) shared by the Figma and AEM clients."""
import base64
import json
import urllib.error
import urllib.request

DEFAULT_TIMEOUT = 60
USER_AGENT = "figma2aem/0.1"


class HttpError(RuntimeError):
    pass


def request(url, headers=None, data=None, method=None, timeout=DEFAULT_TIMEOUT):
    req = urllib.request.Request(url, data=data, method=method,
                                 headers={"User-Agent": USER_AGENT, **(headers or {})})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read()
    except urllib.error.HTTPError as exc:
        body = exc.read()[:300].decode("utf-8", "replace")
        raise HttpError(f"{method or 'GET'} {url} → HTTP {exc.code}: {body}") from exc
    except urllib.error.URLError as exc:
        raise HttpError(f"{method or 'GET'} {url} → {exc.reason}") from exc


def get_json(url, headers=None, timeout=DEFAULT_TIMEOUT):
    raw = request(url, headers=headers, timeout=timeout)
    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        raise HttpError(f"GET {url} did not return JSON (got {raw[:80]!r})") from exc


def basic_auth(user, password):
    token = base64.b64encode(f"{user}:{password}".encode()).decode()
    return {"Authorization": f"Basic {token}"}
