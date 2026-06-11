"""
voice_feedback.py — TTS via espeak (subprocess, zero pip deps) + STT via SpeechRecognition.

System deps on Arduino UNO Q (Debian) — run once:
    sudo apt install espeak portaudio19-dev python3-pyaudio
    pip install SpeechRecognition --break-system-packages

No top-level imports of optional packages → dashboard never crashes on import.
"""

from __future__ import annotations

import subprocess
import queue
import threading

# ── Keyword → canonical level mapping ────────────────────────────────────────

_KEYWORD_MAP: dict[str, str] = {
    # A LOT
    "a lot":       "A LOT",
    "alot":        "A LOT",
    "plenty":      "A LOT",
    "full":        "A LOT",
    "enough":      "A LOT",
    "much":        "A LOT",
    "lots":        "A LOT",
    "lot":         "A LOT",
    # MEDIUM
    "medium":      "MEDIUM",
    "half":        "MEDIUM",
    "some":        "MEDIUM",
    "moderate":    "MEDIUM",
    "middle":      "MEDIUM",
    # LITTLE
    "little":      "LITTLE",
    "low":         "LITTLE",
    "few":         "LITTLE",
    "almost empty":"LITTLE",
    "almost":      "LITTLE",
    "running out": "LITTLE",
    "not much":    "LITTLE",
    "nearly":      "LITTLE",
    # SKIP
    "skip":        "SKIP",
    "pass":        "SKIP",
    "ignore":      "SKIP",
    "later":       "SKIP",
    "no":          "SKIP",
}


def _classify(text: str) -> str | None:
    """Map raw transcription to a canonical level, longest match wins."""
    text = text.lower().strip()
    for phrase in sorted(_KEYWORD_MAP, key=len, reverse=True):
        if phrase in text:
            return _KEYWORD_MAP[phrase]
    return None


# ── TTS via espeak (no Python package needed) ─────────────────────────────────

def _speak(text: str) -> None:
    """Blocking TTS using the system espeak binary."""
    try:
        subprocess.run(
            ["espeak", "-s", "140", "-v", "en", text],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except FileNotFoundError:
        print("[VoiceFeedback] espeak not found — install with: sudo apt install espeak")
    except subprocess.CalledProcessError as exc:
        print(f"[VoiceFeedback] espeak error: {exc}")


# ── STT via SpeechRecognition (lazy import) ───────────────────────────────────

def _listen(timeout: int = 6, phrase_limit: int = 5) -> str | None:
    """Capture one utterance; returns transcription or None."""
    try:
        import speech_recognition as sr  # lazy — won't crash dashboard on import
    except ImportError:
        print("[VoiceFeedback] SpeechRecognition not installed — pip install SpeechRecognition")
        return None

    recognizer = sr.Recognizer()
    recognizer.pause_threshold = 0.8

    try:
        with sr.Microphone() as source:
            recognizer.adjust_for_ambient_noise(source, duration=0.5)
            audio = recognizer.listen(source, timeout=timeout, phrase_time_limit=phrase_limit)
        return recognizer.recognize_google(audio)
    except sr.WaitTimeoutError:
        return None
    except sr.UnknownValueError:
        return None
    except sr.RequestError as exc:
        print(f"[VoiceFeedback] STT API error: {exc}")
        return None
    except Exception as exc:
        print(f"[VoiceFeedback] Unexpected STT error: {exc}")
        return None


# ── Public API ────────────────────────────────────────────────────────────────

def ask_quantity_by_voice(substance_name: str, max_attempts: int = 2) -> str:
    """
    Speak the micro-feedback prompt, listen for the answer, return canonical level.
    Returns: "A LOT" | "MEDIUM" | "LITTLE" | "SKIP"
    """
    prompt = (
        f"Quick check for {substance_name}. "
        f"How much {substance_name} is left? "
        "Please say: a lot, medium, little, or skip."
    )

    print(f"[VoiceFeedback] Speaking prompt for '{substance_name}'")
    _speak(prompt)

    for attempt in range(1, max_attempts + 1):
        print(f"[VoiceFeedback] Listening (attempt {attempt}/{max_attempts})…")
        transcription = _listen()

        if transcription:
            print(f"[VoiceFeedback] Heard: '{transcription}'")
            level = _classify(transcription)
            if level:
                print(f"[VoiceFeedback] Classified as: {level}")
                return level
            if attempt < max_attempts:
                _speak("Sorry, I didn't catch that. Please say: a lot, medium, little, or skip.")
        else:
            print("[VoiceFeedback] No speech detected.")

    print("[VoiceFeedback] Falling back to SKIP.")
    return "SKIP"