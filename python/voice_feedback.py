"""
voice_feedback.py

Implements the Voice Micro-Feedback system for the ambient intelligence inventory.
Provides Text-to-Speech (TTS) via the system `espeak` binary and Speech-to-Text (STT) 
via the `SpeechRecognition` library.

Dependencies:
    sudo apt install espeak portaudio19-dev python3-pyaudio
    pip install SpeechRecognition --break-system-packages

Design Note:
    Imports for STT are deferred (lazy-loaded) within functions to prevent 
    the Streamlit dashboard from crashing if audio hardware is unavailable.
"""

from __future__ import annotations

import subprocess
import queue
import threading

# ── Keyword → Canonical Level Mapping ────────────────────────────────────────

# A dictionary mapping spoken heuristic phrases to their canonical quantity labels.
# Used for fuzzy matching of user voice inputs.
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
    """
    Map a raw transcription string to a canonical quantity level.
    
    Performs a substring search against the predefined _KEYWORD_MAP.
    Evaluates longer phrases first to prevent partial word collisions.

    Args:
        text (str): The raw text transcribed from the user's voice.

    Returns:
        str | None: The canonical level ("A LOT", "MEDIUM", "LITTLE", "SKIP") 
                    if a match is found, otherwise None.
    """
    text = text.lower().strip()
    # Sort keys by length descending to match multi-word phrases first
    for phrase in sorted(_KEYWORD_MAP, key=len, reverse=True):
        if phrase in text:
            return _KEYWORD_MAP[phrase]
    return None


# ── TTS via espeak (Zero Python Dependencies) ─────────────────────────────────

def _speak(text: str) -> None:
    """
    Execute blocking Text-to-Speech using the system-level `espeak` binary.

    Args:
        text (str): The string phrase to be spoken.
    """
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


# ── STT via SpeechRecognition (Lazy Import) ───────────────────────────────────

def _listen(timeout: int = 6, phrase_limit: int = 5) -> str | None:
    """
    Capture an audio utterance from the default microphone and transcribe it.

    Args:
        timeout (int, optional): Seconds to wait for speech to start. Defaults to 6.
        phrase_limit (int, optional): Maximum seconds the user is allowed to speak. Defaults to 5.

    Returns:
        str | None: The transcribed text string, or None if transcription fails.
    """
    try:
        import speech_recognition as sr  # Lazy import to isolate dependency failure
    except ImportError:
        print("[VoiceFeedback] SpeechRecognition not installed — pip install SpeechRecognition")
        return None

    recognizer = sr.Recognizer()
    recognizer.pause_threshold = 0.8

    try:
        with sr.Microphone() as source:
            # Calibrate dynamically to ambient laboratory noise
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
    Execute an interactive voice loop to query the user for the residual quantity 
    of a specific substance.

    The function speaks a prompt, listens for a response, and attempts to classify 
    the response into a canonical quantity level. If the response is unrecognized, 
    it prompts the user again up to `max_attempts`.

    Args:
        substance_name (str): The name of the chemical substance to query.
        max_attempts (int, optional): The maximum number of retry loops. Defaults to 2.

    Returns:
        str: The determined canonical level ("A LOT", "MEDIUM", "LITTLE"). Returns "SKIP" 
             if the user explicitly skips or if the system times out/fails.
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
            
            # If the user spoke but the phrase wasn't classified, prompt them to try again
            if attempt < max_attempts:
                _speak("Sorry, I didn't catch that. Please say: a lot, medium, little, or skip.")
        else:
            print("[VoiceFeedback] No speech detected.")

    print("[VoiceFeedback] Falling back to SKIP.")
    return "SKIP"