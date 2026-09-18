"""Send transcribed text to the existing Vestaboard Azure function."""

import json
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener


class NoRedirects(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        # Never forward the function key to a redirected destination.
        return None


def validate_config(url, key):
    parsed = urlsplit(url)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError("AZURE_FUNCTION_URL must be an HTTPS URL without credentials.")
    if parsed.query or parsed.fragment:
        raise ValueError("Use the function URL without a query string; set AZURE_FUNCTION_KEY separately.")
    if not key.strip():
        raise ValueError("Set AZURE_FUNCTION_KEY to the Azure function key.")


def post_message(message, url, key, timeout=20):
    validate_config(url, key)
    message = message.strip()
    if not message:
        raise ValueError("No speech was recognised; nothing was sent.")
    request = Request(
        url,
        data=json.dumps({"message": message}).encode("utf-8"),
        headers={"Content-Type": "application/json", "x-functions-key": key},
        method="POST",
    )
    try:
        with build_opener(NoRedirects()).open(request, timeout=timeout) as response:
            result = json.load(response)
    except HTTPError as exc:
        code = exc.code
        exc.close()
        raise RuntimeError(f"Azure returned HTTP {code}. Check the function key and Azure logs.") from None
    except (URLError, TimeoutError, OSError):
        raise RuntimeError(
            "Could not confirm delivery. Check the connection and board before retrying."
        ) from None
    except (ValueError, UnicodeError):
        raise RuntimeError("Azure returned an unreadable response; check the board before retrying.") from None
    if not isinstance(result, dict) or result.get("success") is not True:
        raise RuntimeError("Azure did not confirm success; check the board before retrying.")
    return result
