import unittest
from unittest.mock import Mock, patch

from app_core.sugesp_api import SigyoApiError, get_json, normalize_token


def fake_response(status=200, body="[]", data=None, headers=None):
    response = Mock()
    response.status_code = status
    response.content = body.encode("utf-8")
    response.text = body
    response.reason = "OK" if status == 200 else "Forbidden"
    response.headers = headers or {}
    response.json.return_value = [] if data is None else data
    return response


class SUGESPApiV2Tests(unittest.TestCase):
    @patch("app_core.sugesp_api._headers_from_streamlit", return_value={})
    @patch("app_core.sugesp_api._http_get")
    def test_headers_in_each_request_and_token_protected(self, mock_get, _):
        mock_get.return_value = fake_response()
        result = get_json(
            "Bearer token-valido", "fatura-recebimentos",
            params={"expand": "cliente,status"},
            request_headers={
                "User-Agent": "Python-Validado/1.0",
                "Accept-Language": "pt-BR",
                "Authorization": "Bearer token-falso",
                "Host": "outro-host",
                "Cookie": "outro-cookie",
            },
        )
        self.assertEqual(result, [])
        _, kwargs = mock_get.call_args
        self.assertEqual(kwargs["headers"]["Authorization"], "Bearer token-valido")
        self.assertEqual(kwargs["headers"]["User-Agent"], "Python-Validado/1.0")
        self.assertEqual(kwargs["headers"]["Accept-Language"], "pt-BR")
        self.assertNotIn("Cookie", kwargs["headers"])
        self.assertNotIn("Host", kwargs["headers"])
        self.assertEqual(kwargs["params"]["expand"], "cliente,status")
        self.assertFalse(kwargs["allow_redirects"])

    @patch("app_core.sugesp_api._headers_from_streamlit", return_value={})
    @patch("app_core.sugesp_api._http_get")
    def test_403_cloudflare_exposes_only_safe_diagnostic(self, mock_get, _):
        response = fake_response(403, "<html>Attention Required! Sorry, you have been blocked.</html>", headers={"cf-ray": "ray-123"})
        response.json.side_effect = ValueError("not json")
        mock_get.return_value = response
        with self.assertRaises(SigyoApiError) as raised:
            get_json("token-valido", "fatura-recebimentos")
        self.assertIn("Cloudflare", raised.exception.user_message())
        self.assertIn("ray-123", raised.exception.detail)
        self.assertNotIn("<html", raised.exception.detail)
        self.assertNotIn("token-valido", raised.exception.detail)

    @patch("app_core.sugesp_api._headers_from_streamlit", return_value={})
    @patch("app_core.sugesp_api._http_get")
    def test_403_from_api_keeps_permission_message(self, mock_get, _):
        mock_get.return_value = fake_response(403, '{"message":"Forbidden"}', {"message":"Forbidden"})
        with self.assertRaises(SigyoApiError) as raised:
            get_json("token", "empenhos")
        self.assertEqual(raised.exception.status_code, 403)
        self.assertNotIn("Cloudflare", raised.exception.user_message())

    @patch("app_core.sugesp_api._headers_from_streamlit", return_value={})
    @patch("app_core.sugesp_api._http_get")
    def test_transacoes_date_filter_is_preserved(self, mock_get, _):
        mock_get.return_value = fake_response()
        get_json("token", "transacoes", params={"TransacaoSearch[data_cadastro]": "01/10/2026 - 07/10/2026"})
        _, kwargs = mock_get.call_args
        self.assertEqual(kwargs["params"]["TransacaoSearch[data_cadastro]"], "01/10/2026 - 07/10/2026")

    @patch("app_core.sugesp_api._headers_from_streamlit", return_value={})
    @patch("app_core.sugesp_api._http_get")
    def test_empty_response_204(self, mock_get, _):
        mock_get.return_value = fake_response(204, "")
        self.assertEqual(get_json("token", "produtos"), [])


if __name__ == "__main__":
    unittest.main()
