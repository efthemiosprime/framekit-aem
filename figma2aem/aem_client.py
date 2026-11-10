"""AEM author access over HTTP.

Read-only helpers (Sling JSON) plus the Package Manager calls used by the
``backup`` command, which is the only code path that writes to AEM.
"""
import json
import time
import urllib.parse
import uuid

from . import net


class AemClient:
    def __init__(self, base_url, user, password, fetch=net.request):
        self.base_url = base_url.rstrip("/")
        self._headers = net.basic_auth(user, password)
        self._fetch = fetch

    # -- read ----------------------------------------------------------------
    def json(self, path, selector="infinity"):
        """Sling JSON of a node; selector None = the node's own properties only."""
        suffix = f".{selector}.json" if selector else ".json"
        url = f"{self.base_url}{urllib.parse.quote(path, safe='/:')}{suffix}"
        raw = self._fetch(url, headers=self._headers)
        try:
            return json.loads(raw)
        except json.JSONDecodeError as exc:
            raise net.HttpError(f"{url} did not return JSON — is the path right and are you logged in?") from exc

    def page_content(self, page_path):
        return self.json(f"{page_path}/jcr:content")

    def policies(self, conf_policies_root):
        return self.json(conf_policies_root)

    # -- write (Package Manager) -------------------------------------------------
    def backup_package(self, group, name, version, filter_roots):
        """Create, build and download a package. WRITES to /etc/packages."""
        service = f"{self.base_url}/crx/packmgr/service/.json"
        pkg_path = f"/etc/packages/{group}/{name}-{version}.zip"
        self._post(service + urllib.parse.quote(f"/etc/packages/{group}/{name}"),
                   {"cmd": "create", "packageName": name, "groupName": group, "packageVersion": version})
        filters = json.dumps([{"root": r, "rules": []} for r in filter_roots])
        self._post_multipart(f"{self.base_url}/crx/packmgr/update.jsp",
                             {"path": pkg_path, "packageName": name, "groupName": group,
                              "version": version, "filter": filters, "_charset_": "UTF-8"})
        self._post(service + urllib.parse.quote(pkg_path), {"cmd": "build"})
        time.sleep(1)
        return self._fetch(f"{self.base_url}{pkg_path}", headers=self._headers)

    def _post(self, url, fields):
        body = urllib.parse.urlencode(fields).encode()
        raw = self._fetch(url, headers={**self._headers, "Content-Type": "application/x-www-form-urlencoded"},
                          data=body, method="POST")
        self._check_packmgr(url, raw)

    def _post_multipart(self, url, fields):
        boundary = uuid.uuid4().hex
        parts = [f'--{boundary}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n' for k, v in fields.items()]
        body = ("".join(parts) + f"--{boundary}--\r\n").encode()
        raw = self._fetch(url, headers={**self._headers, "Content-Type": f"multipart/form-data; boundary={boundary}"},
                          data=body, method="POST")
        self._check_packmgr(url, raw)

    @staticmethod
    def _check_packmgr(url, raw):
        try:
            result = json.loads(raw)
        except json.JSONDecodeError:
            return  # some endpoints answer HTML on success
        if result.get("success") is False:
            raise net.HttpError(f"Package Manager rejected {url}: {result.get('msg')}")
