# Raspberry Pi voice client

Say **"hey vestaboard, dinner is ready"**, then pause. The Pi transcribes speech
using Azure Speech, removes the wake phrase, and posts
`{"message":"Dinner is ready"}` to the existing `vestaboard-app` Azure function.
The function key is sent in the `x-functions-key` header. The Vestaboard token
stays in your existing Azure function.

The microphone streams to Azure Speech for the entire time this program runs,
including before the wake phrase. The wake phrase is matched against cloud
transcripts, not detected locally. Internet access is required and continuous
listening consumes Speech usage. Normal operation does not print transcripts;
`--dry-run` prints matched messages. This client does not save audio.

## 1. Prepare the Pi

These instructions target a 64-bit Raspberry Pi OS Bookworm (Debian 12) setup
with Python 3 and a USB microphone. The Python Speech SDK supports Linux ARM64,
not ARM32. Confirm `uname -m` reports `aarch64`. Microsoft's supported Linux
distributions and native dependencies are listed in the
[Speech SDK setup guide](https://learn.microsoft.com/en-us/azure/ai-services/speech-service/quickstarts/setup-platform?pivots=programming-language-python).
The reSpeaker XVF3800 4-Mic Array has been confirmed working with this client.

Copy this repository onto the Pi (or just this `raspberry-pi` folder), then run
the following in that folder:

```bash
sudo apt-get update
sudo apt-get install -y python3-venv python3-pip libasound2 libssl3 ca-certificates alsa-utils
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
arecord -l
arecord -L
```

`arecord -l` lists recording hardware; `arecord -L` lists ALSA device names.
For the reSpeaker microphone, the hardware listing looks like:

```text
card 2: Array [reSpeaker XVF3800 4-Mic Array], device 0: USB Audio [USB Audio]
```

This means card number `2`, card name `Array`, and device number `0`.
Test that input explicitly, rather than relying on the default capture device:

```bash
arecord -D plughw:CARD=Array,DEV=0 -f S16_LE -r 16000 -c 1 -d 5 /tmp/mic-test.wav
aplay /tmp/mic-test.wav
```

Playback requires a working speaker/output device. The recording command alone
checks whether ALSA can open the microphone.

Use `plughw:CARD=Array,DEV=0` in the configuration below. `plughw:2,0` also
selects this microphone, but the card name avoids depending on card numbers
which may change after reboot. For another microphone, substitute its actual
card name and device number from the listing. See Microsoft's
[audio device selection guide](https://learn.microsoft.com/en-us/azure/ai-services/speech-service/how-to-select-audio-input-devices).

## 2. Configure Azure and the microphone

Create `.env` only on first setup; do not copy over an existing configuration:

```bash
cp .env.example .env
chmod 600 .env
nano .env
```

Fill in:

| Setting | Value |
| --- | --- |
| `AZURE_FUNCTION_URL` | Existing function's HTTPS URL, normally `https://YOUR-APP.azurewebsites.net/api/vestaboard-app`. Remove `?code=...` if copied from the portal. |
| `AZURE_FUNCTION_KEY` | The default function or host key from your existing Function App; the master key is not needed. |
| `AZURE_SPEECH_KEY` | Key from your new Speech resource's **Keys and Endpoint** page. |
| `AZURE_SPEECH_REGION` | Region identifier from that same page, e.g. `westeurope`. |
| `SPEECH_LANGUAGE` | Recognition language; defaults to `en-GB`. |
| `WAKE_PHRASE` | Defaults to `"hey vestaboard"`; keep phrases with spaces quoted. |
| `MICROPHONE_DEVICE` | Set to `plughw:CARD=Array,DEV=0` for the reSpeaker array. Otherwise use your microphone's ALSA device name. |

For the reSpeaker, ensure `.env` contains exactly one active microphone entry:

```dotenv
MICROPHONE_DEVICE=plughw:CARD=Array,DEV=0
```

Replace the example `CARD=Device` value if you uncommented it in `.env.example`.
`Device` is a placeholder, not the name of the reSpeaker card.

The Speech key and function key are separate credentials. `.env` is ignored
by Git. The program reads environment variables; it does not load `.env` itself.
For an interactive terminal, load your configuration with:

```bash
set -a
source .env
set +a
```

Repeat this after editing `.env` or opening a new terminal.

## 3. Test and run

First test the existing Azure function without speech. **This updates the board:**

```bash
python voice_to_vestaboard.py --text "Hello from the Raspberry Pi"
```

Next test the microphone and Speech resource without updating the board:

```bash
python voice_to_vestaboard.py --dry-run
```

Say "hey vestaboard, dinner is ready", then pause. You should see
`Would send: Dinner is ready`. Recognition casing and punctuation may vary.
Press Ctrl+C to stop. Start normal operation with:

```bash
python voice_to_vestaboard.py
```

Only final recognised utterances beginning with the configured phrase trigger
a post. Alternatively, say just "hey vestaboard", pause until the console says
it heard the phrase, then say a message within ten seconds. Each command sends
one utterance; a pause can end that utterance, so speak the whole message before
pausing. The wake window is measured when final transcripts arrive.

The program keeps listening after each post. Begin each new message with the
wake phrase; press Ctrl+C to stop. Use the service below to keep listening after
closing SSH and to start again after a reboot.

If the recogniser consistently spells the name differently, change `WAKE_PHRASE`
to something simpler such as `"hey board"` and reload the configuration.
No automatic HTTP retries are made: after a timeout, check the board before
repeating the command, since the original request might have succeeded.

## 4. Start automatically at boot (optional)

First get normal operation working, then stop the terminal listener. Edit
`vestaboard-voice.service`: change `User=pi` and every `/home/pi/vestaboard`
path to your actual account and checkout. The service account must be able to
read `.env` and access the microphone; the service adds the `audio` group.
An explicit ALSA device can help when running without a desktop session.

For the `dbafromthecold` account with the repository in its home directory,
replace these four settings, leaving the other service settings in place:

```ini
User=dbafromthecold
WorkingDirectory=/home/dbafromthecold/vestaboard/raspberry-pi
EnvironmentFile=/home/dbafromthecold/vestaboard/raspberry-pi/.env
ExecStart=/home/dbafromthecold/vestaboard/raspberry-pi/.venv/bin/python /home/dbafromthecold/vestaboard/raspberry-pi/voice_to_vestaboard.py
```

The service reads `.env` itself and does not inherit variables exported in your
interactive terminal. Save the working microphone setting in `.env` before
starting it. Stop any terminal listener with Ctrl+C so it releases the microphone.

```bash
nano vestaboard-voice.service
sudo cp vestaboard-voice.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now vestaboard-voice
sudo systemctl status vestaboard-voice
journalctl -u vestaboard-voice -f
```

The service restarts an ended Speech session after 15 seconds. After five starts
within five minutes it stops retrying; correct the configuration or connectivity,
then run `sudo systemctl reset-failed vestaboard-voice` and
`sudo systemctl restart vestaboard-voice`. Restart after changing `.env` too.
To disable continuous listening:

```bash
sudo systemctl disable --now vestaboard-voice
```

After editing `.env`, reload it by restarting the service:

```bash
sudo systemctl reset-failed vestaboard-voice
sudo systemctl restart vestaboard-voice
sudo journalctl -u vestaboard-voice --since "1 minute ago" --no-pager
```

Look for `Listening. Say "hey vestaboard, your message"` in the log. Changes to
the service file itself require copying it to `/etc/systemd/system/` again,
running `sudo systemctl daemon-reload`, and restarting the service.

## Troubleshooting and tests

- `SPXERR_MIC_NOT_AVAILABLE` with `capture slave is not defined`: the default
  input may not be configured. Identify the microphone with `arecord -l` and
  `arecord -L`, then set `MICROPHONE_DEVICE` explicitly as above.
- `Cannot get card index for Device`: the example card name is still configured.
  Replace it with `Array` for the reSpeaker, reload `.env` for terminal use, or
  restart the service for background use.
- Microphone still unavailable: check device permissions and stop other copies
  of the listener or recording applications that could hold the device.
- Service shows `activating (auto-restart)` or `status=1/FAILURE`: read the actual
  Python error with `sudo journalctl -u vestaboard-voice -n 60 --no-pager -l`.
  Check its `User`, paths, and microphone setting in the file named by
  `EnvironmentFile`. Remove keys before sharing logs.
- Speech cancellation: check that the Speech key and region belong to the same
  resource, the resource has quota, and the Pi has internet access.
- HTTP 401/403: check the function key and Function App access settings.
- HTTP 500/502: check Azure function logs and its `VESTABOARD_TOKEN` setting.
- Delivery timeout: inspect the board before retrying.

Run local tests without hardware, credentials, or the Speech SDK installed:

```bash
python -m unittest discover -s . -p 'test_*.py' -v
```

These tests cover command parsing and mocked HTTP delivery. They do not verify
real microphone capture, Azure recognition, or physical board delivery.
