"""
test_voice.py — run this directly on the UNO Q to diagnose TTS and STT.

    python3 test_voice.py

It tests each component in isolation and prints exactly what fails.
"""

import subprocess
import sys

# ── 1. Test espeak ────────────────────────────────────────────────────────────
print("\n[1/4] Testing espeak TTS...")
try:
    result = subprocess.run(
        ["espeak", "-s", "140", "-v", "en", "Hello. Espeak is working."],
        capture_output=True, text=True
    )
    if result.returncode == 0:
        print("      ✓ espeak ran without error (did you hear it?)")
    else:
        print(f"      ✗ espeak returned code {result.returncode}")
        print(f"        stderr: {result.stderr}")
except FileNotFoundError:
    print("      ✗ espeak binary not found — run: sudo apt install espeak")

# ── 2. List audio output devices ─────────────────────────────────────────────
print("\n[2/4] Listing audio output devices (aplay)...")
try:
    result = subprocess.run(["aplay", "-l"], capture_output=True, text=True)
    print(result.stdout or "(no output devices found)")
except FileNotFoundError:
    print("      aplay not found — run: sudo apt install alsa-utils")

# ── 3. List audio input devices ───────────────────────────────────────────────
print("\n[3/4] Listing audio input (microphone) devices (arecord)...")
try:
    result = subprocess.run(["arecord", "-l"], capture_output=True, text=True)
    print(result.stdout or "(no input devices found)")
    if "no soundcards found" in result.stdout.lower() or not result.stdout.strip():
        print("      ✗ No microphone detected — is a USB mic plugged in?")
except FileNotFoundError:
    print("      arecord not found — run: sudo apt install alsa-utils")

# ── 4. Test SpeechRecognition + microphone ────────────────────────────────────
print("\n[4/4] Testing SpeechRecognition (will listen for 5 seconds)...")
try:
    import speech_recognition as sr
    r = sr.Recognizer()
    with sr.Microphone() as source:
        print("      Adjusting for ambient noise...")
        r.adjust_for_ambient_noise(source, duration=1)
        print("      >>> SPEAK NOW (you have 5 seconds) <<<")
        audio = r.listen(source, timeout=5, phrase_time_limit=5)
    print("      Audio captured. Sending to Google STT...")
    text = r.recognize_google(audio)
    print(f"      ✓ Recognised: '{text}'")
except ImportError:
    print("      ✗ SpeechRecognition not installed — pip install SpeechRecognition")
except sr.WaitTimeoutError:
    print("      ✗ No speech detected within 5 seconds (mic may be working but silent)")
except sr.UnknownValueError:
    print("      ✗ Speech detected but could not understand it")
except sr.RequestError as e:
    print(f"      ✗ Google STT API error: {e}")
except OSError as e:
    print(f"      ✗ Microphone OS error: {e}")
    print("        Likely cause: no input device found or wrong ALSA device index.")
    print("        Try: python3 -c \"import speech_recognition as sr; print(sr.Microphone.list_microphone_names())\"")
except Exception as e:
    print(f"      ✗ Unexpected error: {type(e).__name__}: {e}")

print("\nDone. Share the output above to diagnose the issue.\n")