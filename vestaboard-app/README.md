# Vestaboard Azure function

This PowerShell HTTP function accepts a text message and forwards it to
Vestaboard. It is the backend used by the [Raspberry Pi voice client](../raspberry-pi/README.md),
but any HTTP client can send it text. Speech recognition happens separately
through Azure Speech; this function accepts JSON, not audio.

## Configuration

The Azure Functions project root is the repository root (the folder containing
`host.json`), not this `vestaboard-app` subfolder. Deploy it to an Azure Function
App configured for the PowerShell worker. The repository's `.funcignore`
excludes the Raspberry Pi client from function deployment.

Set this application setting on the Function App:

| Setting | Purpose |
| --- | --- |
| `VESTABOARD_TOKEN` | Token used to authenticate requests to the Vestaboard cloud endpoint. |

The token belongs in the Function App configuration, not in source control or
the Pi's `.env`. The Function App also needs its normal Azure Functions runtime
and storage configuration. No Speech key or region is required by this function.

## Call the function

The route is:

```text
https://<function-app-hostname>/api/vestaboard-app
```

Use the complete hostname shown by Azure; it can include a generated suffix
and region. The trigger uses `authLevel: function`. Send a function-specific
key or the default host key in the `x-functions-key` header. The master key is
not required. Keep the URL without a `?code=...` query when configuring the Pi;
the client sends its key separately.

Send a POST with `Content-Type: application/json` and this body:

```json
{
  "message": "Dinner is ready"
}
```

For example, from the Pi after loading its `.env` (this updates the board):

```bash
curl --fail-with-body "$AZURE_FUNCTION_URL" \
  -H "Content-Type: application/json" \
  -H "x-functions-key: $AZURE_FUNCTION_KEY" \
  --data '{"message":"Hello from the Raspberry Pi"}'
```

Although `function.json` permits GET as well as POST, the implementation reads
`message` from the request body. Use POST JSON; query-string messages are not
handled.

## Processing and responses

The function checks for its token and a non-empty message, then sends
`{"text":"Dinner is ready"}` to `https://cloud.vestaboard.com/`, using the
`X-Vestaboard-Token` header. It returns a JSON response:

| HTTP status | Meaning |
| --- | --- |
| `200` | The upstream request succeeded. Body includes `success: true`, `message`, and `vestaboardResponse`. |
| `400` | The request has a missing, empty, or whitespace-only message. |
| `500` | `VESTABOARD_TOKEN` is missing or blank. This check runs before message validation. |
| `502` | The upstream request threw an exception. Body includes `success: false`, `error`, and exception `detail`. |

Authentication failures can be returned by the Functions host before this code
runs. Check the key if you receive HTTP 401/403. For HTTP 500/502, check the
Function App settings and logs. A 502 can also reflect connectivity trouble,
not just a rejected token. After a timeout, inspect the board before retrying:
the request might already have been processed.

## Source files

- [run.ps1](run.ps1): validates the message, calls Vestaboard, and builds the response.
- [function.json](function.json): HTTP trigger, authentication level, and response binding.
- [../host.json](../host.json): shared Functions host configuration.
- [../requirements.psd1](../requirements.psd1): managed PowerShell dependencies;
  no additional modules are currently enabled.

See the [repository overview](../README.md) for the complete voice-to-board flow.
