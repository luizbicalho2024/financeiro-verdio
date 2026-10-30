import unittest
from unittest.mock import Mock, patch

import requests

from app_core import sugesp_api as api


class SigyoHttpV5Tests(unittest.TestCase):
    @patch("app_core.sugesp_api._headers_from_streamlit", return_value={})
    @patch("app_core.sugesp_api._http_get")
    def test_mesmos_headers_do_teste_local(self, mock_get, _):
        response = Mock()
        response.status_code = 200
        response.content = b"[]"
        response.json.return_value = []
        mock_get.return_value = response

        api.get_json(
            "Bearer token-testado",
            "clientes",
            params={
                "expand": "municipio,municipio.estado,modulos,organizacao,tipo",
                "page": 1,
                "per-page": 100,
            },
            request_headers={"Authorization": "Bearer invalido", "Cookie": "x"},
        )
        args, kwargs = mock_get.call_args
        self.assertTrue(args[0].endswith("/api/clientes"))
        self.assertEqual(kwargs["headers"]["Authorization"], "Bearer token-testado")
        self.assertEqual(kwargs["headers"]["Accept"], "application/json")
        self.assertEqual(kwargs["headers"]["Content-Type"], "application/json")
        self.assertEqual(kwargs["headers"]["User-Agent"], "SIGYO-API-Client/1.0")
        self.assertEqual(kwargs["headers"]["Cache-Control"], "no-cache")
        self.assertNotIn("Cookie", kwargs["headers"])
        self.assertEqual(kwargs["params"]["page"], 1)
        self.assertEqual(kwargs["params"]["per-page"], 100)
        self.assertFalse(kwargs["allow_redirects"])
        self.assertTrue(kwargs["verify"])

    @patch("app_core.sugesp_api.requests.Session")
    def test_politica_de_retentativas_igual_ao_teste_local(self, session_cls):
        previous = getattr(api._thread, "session", None)
        try:
            api._thread.session = None
            sessao = api._session_for_thread()
            self.assertIs(sessao, session_cls.return_value)
            mount_args, _ = sessao.mount.call_args
            self.assertEqual(mount_args[0], "https://")
            adapter = mount_args[1]
            retry = adapter.max_retries
            self.assertEqual(retry.total, 3)
            self.assertEqual(retry.connect, 3)
            self.assertEqual(retry.read, 2)
            self.assertEqual(retry.backoff_factor, 1)
            self.assertIn(500, retry.status_forcelist)
            self.assertNotIn(403, retry.status_forcelist)
            self.assertEqual(retry.allowed_methods, frozenset({"GET"}))
            self.assertTrue(retry.respect_retry_after_header)
        finally:
            api._thread.session = previous

    def test_get_nao_define_token_na_sessao(self):
        # O token deve ser acrescentado exclusivamente a cada requisicao.
        headers = api._build_headers(api.SIGYO_BASE_URL)
        self.assertNotIn("Authorization", headers)
        self.assertNotIn("Cookie", headers)
        self.assertNotIn("Referer", headers)
        self.assertNotIn("Origin", headers)


if __name__ == "__main__":
    unittest.main()
