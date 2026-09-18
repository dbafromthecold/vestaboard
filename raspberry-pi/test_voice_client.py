import io
import json
import unittest
from unittest.mock import MagicMock, patch
from urllib.error import HTTPError, URLError

from azure_client import NoRedirects, post_message, validate_config
from voice_to_vestaboard import WakeCommands


class WakeTests(unittest.TestCase):
    def setUp(self):
        self.commands = WakeCommands("hey vestaboard")

    def test_inline_command_preserves_message(self):
        self.assertEqual(self.commands.consume("Hey, Vestaboard! Dinner at 6.", 1), "Dinner at 6")

    def test_unrelated_speech_and_embedded_phrase_ignored(self):
        for text in ["Dinner is ready", "I said hey vestaboard dinner", "hey vestaboards dinner"]:
            self.assertIsNone(self.commands.consume(text, 1))

    def test_separate_wake_and_message_consumed_once(self):
        self.assertIsNone(self.commands.consume("Hey Vestaboard.", 1))
        self.assertEqual(self.commands.consume("Dinner is ready.", 5), "Dinner is ready.")
        self.assertIsNone(self.commands.consume("Something else", 6))

    def test_expired_wake_does_not_post(self):
        self.commands.consume("hey vestaboard", 1)
        self.assertIsNone(self.commands.consume("Too late", 12))

    def test_repeated_wake_resets_window(self):
        self.commands.consume("hey vestaboard", 1)
        self.commands.consume("hey vestaboard", 9)
        self.assertEqual(self.commands.consume("Hello", 15), "Hello")

    def test_empty_phrase_rejected(self):
        with self.assertRaises(ValueError):
            WakeCommands("!!!")


class HttpTests(unittest.TestCase):
    url = "https://example.azurewebsites.net/api/vestaboard-app"

    def test_payload_authentication_and_timeout(self):
        with patch("azure_client.build_opener") as build:
            build.return_value.open.return_value.__enter__.return_value = io.BytesIO(b'{"success":true}')
            post_message("  Caf\u00e9 at 6  ", self.url, "test-key")
            request = build.return_value.open.call_args.args[0]
            self.assertEqual(request.method, "POST")
            self.assertEqual(json.loads(request.data), {"message": "Caf\u00e9 at 6"})
            self.assertEqual(request.get_header("X-functions-key"), "test-key")
            self.assertEqual(build.return_value.open.call_args.kwargs["timeout"], 20)

    def test_empty_message_never_connects(self):
        with patch("azure_client.build_opener") as build:
            with self.assertRaises(ValueError):
                post_message("  ", self.url, "key")
            build.assert_not_called()

    def test_invalid_configuration(self):
        for url, key in [("http://example.com", "key"), (self.url + "?code=secret", "key"),
                         ("https://user:password@example.com", "key"), (self.url, "")]:
            with self.subTest(url=url), self.assertRaises(ValueError):
                validate_config(url, key)

    def test_failed_delivery_not_retried_and_secrets_not_printed(self):
        errors = [HTTPError(self.url, 401, "secret", {}, None), URLError("secret"), TimeoutError("secret")]
        for error in errors:
            with self.subTest(error=error), patch("azure_client.build_opener") as build:
                build.return_value.open.side_effect = error
                with self.assertRaises(RuntimeError) as caught:
                    post_message("Hello", self.url, "secret")
                self.assertNotIn("secret", str(caught.exception))
                self.assertEqual(build.return_value.open.call_count, 1)

    def test_requires_explicit_success(self):
        for body in [b'{}', b'{"success":false}', b'[]', b'not json']:
            with self.subTest(body=body), patch("azure_client.build_opener") as build:
                build.return_value.open.return_value.__enter__.return_value = io.BytesIO(body)
                with self.assertRaises(RuntimeError):
                    post_message("Hello", self.url, "key")

    def test_redirects_refused(self):
        self.assertIsNone(NoRedirects().redirect_request(MagicMock(), None, 302, "", {}, "https://other.example"))


if __name__ == "__main__":
    unittest.main()
