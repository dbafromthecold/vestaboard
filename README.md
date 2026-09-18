# Voice-controlled Vestaboard

This repository connects a Raspberry Pi microphone to a Vestaboard through
Azure Speech and a PowerShell Azure function. Say **"hey vestaboard, dinner is
ready"**, pause, and the recognised message is sent to the board.

## How it works

```text
Microphone → Raspberry Pi → Azure Speech
                                ↓ recognised text
                         Pi checks wake phrase
                                ↓ POST {"message":"..."}
                         Azure Function → Vestaboard
```

The Pi listens continuously, uses Azure Speech to transcribe audio, and checks
final transcripts for a configurable wake phrase. It removes that phrase and
sends the message to the existing HTTP function. The function converts it to
Vestaboard's text payload and authenticates with the Vestaboard token.

Each message starts with the wake phrase. The listener stays running after a
post, and an optional systemd service starts it at boot and keeps it running
after an SSH session closes.

## Components and setup

| Component | Guide |
| --- | --- |
| `vestaboard-app/` | [Azure function configuration, request format, and responses](vestaboard-app/README.md) |
| `raspberry-pi/` | [Pi installation, microphone selection, credentials, testing, and startup service](raspberry-pi/README.md) |
| Root configuration | `host.json`, `profile.ps1`, and `requirements.psd1` form the PowerShell Azure Functions project. |

You need a Raspberry Pi running a compatible 64-bit Linux setup, a microphone,
an Azure Speech resource with its key and region, a deployed PowerShell Function
App, and a Vestaboard token. The reSpeaker XVF3800 4-Mic Array has been confirmed
working; the Pi guide includes its ALSA device configuration.

1. Configure and deploy the [Azure function](vestaboard-app/README.md), including
   its `VESTABOARD_TOKEN` application setting.
2. Create an Azure Speech resource and obtain its key and region.
3. Clone this repository on the Pi and follow the [Pi guide](raspberry-pi/README.md)
   to install dependencies, identify the microphone, and create `.env`.
4. Test HTTP delivery with `--text`, test recognition with `--dry-run`, then
   run normally to send voice messages. The text test updates the board.
5. Configure the systemd service after both tests work.

## Credentials and continuous listening

The Pi's `.env` contains the Speech key and region, the function URL and key,
and microphone settings. `.env` is ignored by Git. The Vestaboard token stays
in the Azure Function App. The function's default key is sufficient; a master
key is not needed.

Audio streams to Azure Speech for the entire time the listener runs, including
before the wake phrase. Wake phrase matching happens on cloud transcripts,
so continuous listening requires internet access and consumes Speech usage.
The client does not save audio. Dry-run mode still uses Azure Speech but does
not post messages to the board.

## Development checks

From the repository root, run the client tests without hardware or credentials:

```bash
python -m unittest discover -s raspberry-pi -p 'test_*.py' -v
```

These tests cover wake phrase handling and mocked HTTP delivery. Real microphone
recognition and board delivery are checked using the Pi guide's manual steps.
The Raspberry Pi folder is excluded from Azure Functions deployment.
