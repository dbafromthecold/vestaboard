#!/usr/bin/env python3
"""Continuously recognise speech and send wake-prefixed messages to Azure."""

import argparse
import os
import queue
import re
import signal
import sys
import threading
import time

from azure_client import post_message, validate_config


class WakeCommands:
    """Accept a wake-prefixed utterance, or the next utterance within a deadline."""

    def __init__(self, phrase, timeout=10):
        words = re.findall(r"\w+", phrase)
        if not words:
            raise ValueError("WAKE_PHRASE must contain words.")
        self.pattern = re.compile(r"^\W*" + r"\W*".join(map(re.escape, words)) + r"\b", re.I)
        self.timeout = timeout
        self.deadline = 0

    def consume(self, text, now):
        match = self.pattern.match(text)
        if match:
            message = text[match.end():].strip(" \t\n,.:;!?—-")
            self.deadline = 0 if message else now + self.timeout
            return message or None
        if self.deadline and now <= self.deadline:
            self.deadline = 0
            return text.strip() or None
        self.deadline = 0
        return None


def listen(args, url, key):
    import azure.cognitiveservices.speech as speechsdk

    speech_key = os.environ.get("AZURE_SPEECH_KEY", "").strip()
    region = os.environ.get("AZURE_SPEECH_REGION", "").strip()
    if not speech_key or not region:
        raise ValueError("Set AZURE_SPEECH_KEY and AZURE_SPEECH_REGION.")
    config = speechsdk.SpeechConfig(subscription=speech_key, region=region)
    config.speech_recognition_language = os.environ.get("SPEECH_LANGUAGE", "en-GB")
    device = os.environ.get("MICROPHONE_DEVICE", "").strip()
    audio = (speechsdk.audio.AudioConfig(device_name=device) if device
             else speechsdk.audio.AudioConfig(use_default_microphone=True))
    recognizer = speechsdk.SpeechRecognizer(speech_config=config, audio_config=audio)
    phrase = os.environ.get("WAKE_PHRASE", "hey vestaboard")
    commands = WakeCommands(phrase)
    # Bias recognition towards the board's name without restricting dictation.
    speechsdk.PhraseListGrammar.from_recognizer(recognizer).addPhrase(phrase)
    events = queue.Queue(maxsize=32)
    stopped = threading.Event()
    failed = threading.Event()

    def recognised(event):
        if event.result.reason == speechsdk.ResultReason.RecognizedSpeech:
            try:
                events.put_nowait((event.result.text, time.monotonic()))
            except queue.Full:
                print("Recognition queue full; stopping to avoid sending stale commands.", file=sys.stderr)
                failed.set()
                stopped.set()

    def cancelled(event):
        # Do not log SDK error details, which can contain connection information.
        print(f"Speech recognition cancelled ({event.reason}). Check Speech credentials and connectivity.", file=sys.stderr)
        failed.set()
        stopped.set()

    recognizer.recognized.connect(recognised)
    recognizer.canceled.connect(cancelled)
    def session_stopped(event):
        if not stopped.is_set():
            print("Speech session ended; restart the listener to reconnect.", file=sys.stderr)
            failed.set()
        stopped.set()

    recognizer.session_stopped.connect(session_stopped)
    previous = signal.signal(signal.SIGTERM, lambda *_: stopped.set())
    started = False
    try:
        recognizer.start_continuous_recognition_async().get()
        started = True
        print(f'Listening. Say "{phrase}, your message", then pause. Ctrl+C to stop.', flush=True)
        while not stopped.is_set():
            try:
                text, received = events.get(timeout=0.2)
            except queue.Empty:
                continue
            if time.monotonic() - received > 10:
                commands.deadline = 0
                print("Discarded stale speech.", file=sys.stderr)
                continue
            message = commands.consume(text, received)
            if message:
                if args.dry_run:
                    print(f"Would send: {message}", flush=True)
                else:
                    try:
                        post_message(message, url, key)
                        print("Message sent to Vestaboard.", flush=True)
                    except (ValueError, RuntimeError) as exc:
                        print(str(exc), file=sys.stderr, flush=True)
            elif commands.deadline:
                print("Wake phrase heard. Say your message within 10 seconds.", flush=True)
    except KeyboardInterrupt:
        stopped.set()
    finally:
        stopped.set()
        if started:
            recognizer.stop_continuous_recognition_async().get()
        signal.signal(signal.SIGTERM, previous)
    return 1 if failed.is_set() or not stopped.is_set() else 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--dry-run", action="store_true", help="Transcribe and display commands without posting")
    group.add_argument("--text", help="Send text once without using the microphone or Speech service")
    args = parser.parse_args()
    url = os.environ.get("AZURE_FUNCTION_URL", "").strip()
    key = os.environ.get("AZURE_FUNCTION_KEY", "").strip()
    try:
        if not args.dry_run:
            validate_config(url, key)
        if args.text is not None:
            post_message(args.text, url, key)
            print("Message sent to Vestaboard.")
            return 0
        return listen(args, url, key)
    except (ValueError, RuntimeError) as exc:
        print(str(exc), file=sys.stderr)
        return 1
    except ImportError:
        print("Install dependencies with: python -m pip install -r requirements.txt", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
