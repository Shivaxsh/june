"""Explicit outbound boundary for enabled connectors; never follows redirects."""
import json
from urllib.parse import urlsplit
import httpx
from .errors import JuneError


class ConnectorHTTP:
    def __init__(self, connector, hosts, *, enabled, transport=None):
        # Registry-owned hosts, not values supplied by model text or remote tools.
        self.connector = connector
        self.hosts = frozenset(hosts)
        self.enabled = enabled
        self.transport = transport

    async def json(self, method, url, *, headers=None, body=None, form=None, allow_empty=False):
        try:
            target = urlsplit(url)
            permitted = (target.scheme == 'https' and target.hostname in self.hosts
                and target.port in (None, 443) and not target.username and not target.password
                and not target.fragment and method in ('GET', 'POST'))
        except (ValueError, TypeError):
            permitted = False
        if not permitted or not self.enabled():
            raise JuneError('connector-disabled', 'Enable this connection and use its approved service endpoint.', 403)
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(15, connect=5), trust_env=False,
                    follow_redirects=False, transport=self.transport) as client:
                async with client.stream(method, url, headers=headers, json=body, data=form) as reply:
                    if not 200 <= reply.status_code < 300:
                        if reply.status_code == 401 or (reply.status_code == 400 and target.hostname == 'oauth2.googleapis.com' and target.path == '/token'):
                            raise JuneError('connector-auth', 'The service authorisation expired or was refused.', 401)
                        raise JuneError('connector-response', 'The service did not return a successful result. Check its connection.', 502)
                    raw = bytearray()
                    async for chunk in reply.aiter_bytes():
                        raw.extend(chunk)
                        if len(raw) > 262144:
                            raise JuneError('connector-response', 'The service returned more data than June can safely process.', 502)
                    return {} if not raw and allow_empty else json.loads(raw)
        except (httpx.HTTPError, ValueError, UnicodeError, RecursionError):
            raise JuneError('connector-response', 'The service response could not be verified. Nothing was retried.', 502) from None
