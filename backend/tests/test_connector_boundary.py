import unittest
import httpx
from june.errors import JuneError


class ConnectorBoundary(unittest.IsolatedAsyncioTestCase):
    async def test_disabled_connector_does_not_make_request(self):
        from june.connector_http import ConnectorHTTP
        calls = []
        service = ConnectorHTTP('weather', {'api.open-meteo.com'}, enabled=lambda: False,
            transport=httpx.MockTransport(lambda request: calls.append(request)))
        with self.assertRaises(JuneError):
            await service.json('GET', 'https://api.open-meteo.com/v1/forecast')
        self.assertFalse(calls)

    async def test_only_exact_hosts_and_https_without_redirects(self):
        from june.connector_http import ConnectorHTTP
        calls = []
        def reply(request):
            calls.append(request)
            return httpx.Response(302, headers={'Location':'https://evil.example/token'})
        service = ConnectorHTTP('weather', {'api.open-meteo.com'}, enabled=lambda: True,
            transport=httpx.MockTransport(reply))
        for url in ('http://api.open-meteo.com/v1/forecast', 'https://api.open-meteo.com.evil.example/',
                    'https://user:secret@api.open-meteo.com/', 'https://api.open-meteo.com:8443/',
                    'https://127.0.0.1/', 'https://api.open-meteo.com/#token'):
            with self.assertRaises(JuneError):
                await service.json('GET', url)
        self.assertEqual(calls, [])
        with self.assertRaises(JuneError):
            await service.json('GET', 'https://api.open-meteo.com/v1/forecast')
        self.assertEqual(len(calls), 1)

    async def test_size_bound_and_provider_errors_do_not_expose_content(self):
        from june.connector_http import ConnectorHTTP
        for response in (httpx.Response(200, content=b'x'*262145),
                         httpx.Response(403, text='private credential in provider message'),
                         httpx.Response(200, text='private invalid json')):
            service = ConnectorHTTP('weather', {'api.open-meteo.com'}, enabled=lambda: True,
                transport=httpx.MockTransport(lambda request: response))
            with self.assertRaises(JuneError) as caught:
                await service.json('GET', 'https://api.open-meteo.com/v1/forecast')
            self.assertNotIn('private', caught.exception.message)

    async def test_valid_structured_reply_and_no_environment_proxy(self):
        from june.connector_http import ConnectorHTTP
        service = ConnectorHTTP('weather', {'api.open-meteo.com'}, enabled=lambda: True,
            transport=httpx.MockTransport(lambda request: httpx.Response(200, json={'temperature':25})))
        self.assertEqual(await service.json('GET', 'https://api.open-meteo.com/v1/forecast'), {'temperature':25})
