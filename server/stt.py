# server/stt.py
import os
import tempfile
from flask import Blueprint, request, jsonify
from werkzeug.utils import secure_filename

# Optional: Whisper import (lazy load to avoid startup cost)
try:
    import whisper
    WHISPER_AVAILABLE = True
    # load a lightweight model initially for speed; change "small" -> "tiny" if required
    whisper_model = whisper.load_model("small")
except Exception as e:
    WHISPER_AVAILABLE = False
    whisper_model = None
    print("Whisper not available:", e)

stt_bp = Blueprint("stt", __name__)

ALLOWED_EXT = {".wav", ".mp3", ".m4a", ".flac", ".ogg"}

def allowed_file(filename):
    ext = os.path.splitext(filename)[1].lower()
    return ext in ALLOWED_EXT

@stt_bp.route("/stt", methods=["POST"])
def stt():
    """
    Accepts multipart/form-data with a file field named 'file' (audio).
    Returns JSON: { transcript: "...", lang: "en", duration: 3.2 }
    """
    if "file" not in request.files:
        return jsonify({"error": "no_file"}), 400

    f = request.files["file"]
    filename = secure_filename(f.filename or "upload.wav")
    if not allowed_file(filename):
        return jsonify({"error": "invalid_file_type"}), 400

    # Save to temp file
    tmp_dir = tempfile.gettempdir()
    tmp_path = os.path.join(tmp_dir, filename)
    f.save(tmp_path)

    # If Whisper is installed and loaded, use it to transcribe
    if WHISPER_AVAILABLE and whisper_model is not None:
        try:
            # you can pass language param if known: whisper_model.transcribe(tmp_path, language="hi")
            result = whisper_model.transcribe(tmp_path, fp16=False)  # fp16 False on CPU
            transcript = result.get("text", "").strip()
            # Optionally get detected language:
            lang = result.get("language", None)
            # Clean up temp file
            try:
                os.remove(tmp_path)
            except:
                pass
            return jsonify({"transcript": transcript, "language": lang, "raw_result": result}), 200
        except Exception as e:
            return jsonify({"error": "whisper_failed", "detail": str(e)}), 500
    else:
        # Whisper not available — return a placeholder and the temp file path for manual testing
        return jsonify({
            "transcript": "(whisper not available on server)",
            "note": "saved_temp_file",
            "temp_path": tmp_path
        }), 200
