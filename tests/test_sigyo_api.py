import unittest
from unittest.mock import Mock, patch

from app_core.sigyo_api import (
    SigyoApiError,
    get_json,
    normalize_token,
)


class SigyoApiTests(unittest.TestCase):

    def test_token_puro(self):
        self.assertEqual(
            normalize_token("abc123"),
            "abc123",
        )

    def test_bearer(self):
        self.assertEqual(
            normalize_token(
                "Bearer abc123"
            ),
            "abc123",
        )

    def test_bearer_duplicado(self):
        self.assertEqual(
            normalize_token(
                "Bearer Bearer abc123"
            ),
            "abc123",
        )

    def test_authorization_completo(self):
        self.assertEqual(
            normalize_token(
                "Authorization: Bearer abc123"
            ),
            "abc123",
        )

    @patch(
        "app_core.sigyo_api.requests.get"
    )
    def test_transacao_params(
        self,
        request_get,
    ):
        response = Mock()
        response.status_code = 200
        response.content = b"[]"
        response.json.return_value = []
        response.headers = {}
        response.reason = "OK"

        request_get.return_value = response

        get_json(
            "Bearer token",
            "transacoes",
            params={
                "TransacaoSearch[data_cadastro]":
                    "01/09/2026 - 07/09/2026"
            },
        )

        _, kwargs = request_get.call_args

        self.assertEqual(
            kwargs["headers"][
                "Authorization"
            ],
            "Bearer token",
        )

        self.assertEqual(
            kwargs["params"][
                "TransacaoSearch[data_cadastro]"
            ],
            "01/09/2026 - 07/09/2026",
        )

    @patch(
        "app_core.sigyo_api.requests.get"
    )
    def test_403(
        self,
        request_get,
    ):
        response = Mock()
        response.status_code = 403
        response.content = (
            b'{"message":"Forbidden"}'
        )
        response.json.return_value = {
            "message": "Forbidden"
        }
        response.text = (
            '{"message":"Forbidden"}'
        )
        response.headers = {}
        response.reason = "Forbidden"

        request_get.return_value = response

        with self.assertRaises(
            SigyoApiError
        ) as context:
            get_json(
                "token",
                "empenhos",
            )

        self.assertEqual(
            context.exception.status_code,
            403,
        )


if __name__ == "__main__":
    unittest.main()