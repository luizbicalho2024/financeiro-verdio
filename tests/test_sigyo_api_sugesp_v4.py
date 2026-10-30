"""Testes isolados do cliente SIGYO / SUGESP V4, sem usar token real."""
import unittest
from unittest.mock import Mock, patch

import requests

from app_core.sugesp_api import (
    SigyoApiError,
    _build_headers,
    _http_get,
    get_json,
)


def fake_response(status=200, text="[]", payload=None, headers=None):
    response = Mock()
    response.status_code = status
    response.content = text.encode("utf-8")
    response.text = text
    response.reason = "OK" if status == 200 else "Forbidden"
    response.headers = headers or {}
    response.json.return_value = [] if payload is None else payload
    return response


class SigyoApiSugespV4Tests(unittest.TestCase):
    def test_default_headers_match_validated_local_client(self):
        # V5 replica intencionalmente os headers do teste.py que funcionou no Windows.
        headers = _build_headers("https://sigyo.uzzipay.com/api")
        self.assertEqual(headers["User-Agent"], "SIGYO-API-Client/1.0")
        self.assertEqual(headers["Accept"], "application/json")
        self.assertEqual(headers["Content-Type"], "application/json")
        self.assertEqual(headers["Cache-Control"], "no-cache")
        for key in ("Referer", "Origin", "X-Requested-With", "Cookie", "Authorization", "Host"):
            self.assertNotIn(key, headers)

    def test_header_overrides_do_not_change_authorization(self):
        with patch("app_core.sugesp_api._headers_from_streamlit", return_value={"Referer": "https://sigyo.uzzipay.com/"}), patch("app_core.sugesp_api._http_get") as get:
            get.return_value = fake_response()
            get_json(
                "Bearer token-correto",
                "fatura-recebimentos",
                params={"expand": "cliente,status"},
                request_headers={"User-Agent": "Python-Integracao/1.0", "Authorization": "token-falso", "Cookie": "segredo", "Host": "example.com"},
            )
            _, kwargs = get.call_args
            self.assertEqual(kwargs["headers"]["Authorization"], "Bearer token-correto")
            self.assertEqual(kwargs["headers"]["User-Agent"], "Python-Integracao/1.0")
            self.assertEqual(kwargs["headers"]["Referer"], "https://sigyo.uzzipay.com/")
            self.assertNotIn("Cookie", kwargs["headers"])
            self.assertNotIn("Host", kwargs["headers"])
            self.assertEqual(kwargs["params"], {"expand": "cliente,status"})
            self.assertFalse(kwargs["allow_redirects"])
            self.assertTrue(kwargs["verify"])

    def test_default_override_does_not_overwrite_secret_header(self):
        with patch("app_core.sugesp_api._headers_from_streamlit", return_value={"Referer": "https://sigyo.uzzipay.com/"}), patch("app_core.sugesp_api._http_get") as get:
            get.return_value = fake_response()
            get_json("token", "produtos", request_headers={"Accept": "application/json"})
            self.assertEqual(get.call_args.kwargs["headers"]["Referer"], "https://sigyo.uzzipay.com/")

    def test_blocked_cloudflare_is_not_retried_by_app(self):
        html = "<html>Attention Required! Sorry, you have been blocked.</html>"
        with patch("app_core.sugesp_api._headers_from_streamlit", return_value={}), patch("app_core.sugesp_api._http_get") as get:
            resp = fake_response(403, html, headers={"cf-ray": "a52c70cabca37e6e-SJC"})
            resp.json.side_effect = ValueError("not json")
            get.return_value = resp
            with self.assertRaises(SigyoApiError) as raised:
                get_json("token-sensivel", "produtos")
            self.assertEqual(get.call_count, 1)
            self.assertIn("Cloudflare", raised.exception.user_message())
            self.assertIn("a52c70cabca37e6e-SJC", raised.exception.detail)
            self.assertNotIn("token-sensivel", raised.exception.detail)
            self.assertNotIn("<html>", raised.exception.detail)

    def test_get_uses_session(self):
        with patch("app_core.sugesp_api._session_for_thread") as factory:
            factory.return_value.get.return_value = fake_response()
            response = _http_get("https://sigyo.uzzipay.com/api/produtos", timeout=(15, 180))
            self.assertEqual(response.status_code, 200)
            factory.return_value.get.assert_called_once()

    def test_invalid_endpoint(self):
        with self.assertRaises(SigyoApiError):
            get_json("token", "https://outro.site/segredo")

    def test_date_filter_preserved(self):
        with patch("app_core.sugesp_api._headers_from_streamlit", return_value={}), patch("app_core.sugesp_api._http_get") as get:
            get.return_value = fake_response()
            get_json("token", "transacoes", params={"TransacaoSearch[data_cadastro]": "01/09/2026 - 07/09/2026"})
            self.assertEqual(get.call_args.kwargs["params"], {"TransacaoSearch[data_cadastro]": "01/09/2026 - 07/09/2026"})


if __name__ == "__main__":
    unittest.main()
