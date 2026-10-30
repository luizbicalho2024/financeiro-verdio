import unittest

from app_core.sugesp_credentials import resolve_configuration
from app_core.sigyo_api import SIGYO_BASE_URL


class SugespCredentialsTests(unittest.TestCase):
    def test_secret_is_prioritized_even_if_environment_has_another_token(self):
        token, source, url = resolve_configuration(
            {"SIGYO_API_TOKEN": "Bearer token-secret"},
            {"SIGYO_API_TOKEN": "Bearer token-antigo"},
        )
        self.assertEqual(token, "token-secret")
        self.assertEqual(source, "Secrets do Streamlit")
        self.assertEqual(url, SIGYO_BASE_URL)

    def test_uses_environment_without_streamlit_secret(self):
        token, source, _ = resolve_configuration({}, {"SIGYO_API_TOKEN": "token-ambiente"})
        self.assertEqual(token, "token-ambiente")
        self.assertEqual(source, "variavel de ambiente")

    def test_missing_secrets_requires_manual_token_in_page(self):
        token, source, _ = resolve_configuration({}, {})
        self.assertEqual(token, "")
        self.assertEqual(source, "nao configurado")

    def test_configured_base_url(self):
        token, source, url = resolve_configuration(
            {"SIGYO_API_TOKEN": "Authorization: Bearer t", "SIGYO_API_BASE_URL": "https://sigyo.uzzipay.com/api/"},
            {},
        )
        self.assertEqual(token, "t")
        self.assertEqual(source, "Secrets do Streamlit")
        self.assertEqual(url, SIGYO_BASE_URL)

    def test_missing_secrets_file_is_handled(self):
        class MissingSecrets:
            def get(self, key, default=None):
                raise FileNotFoundError("Sem arquivo secrets")
        token, source, url = resolve_configuration(MissingSecrets(), {})
        self.assertEqual(token, "")
        self.assertEqual(source, "nao configurado")
        self.assertEqual(url, SIGYO_BASE_URL)


if __name__ == "__main__":
    unittest.main()