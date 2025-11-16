# server/process.py
import os
import tempfile
from flask import Blueprint, request, jsonify
from werkzeug.utils import secure_filename
from stt import WHISPER_AVAILABLE, whisper_model, allowed_file
from translate import translate_text
from models import save_transcript  # we'll add this helper

process_bp = Blueprint("process", __name__)

ALLOWED_EXT = {".wav", ".mp3", ".m4a", ".flac", ".ogg"}

@process_bp.route("/process", methods=["POST"])
def process_audio():
    """
    multipart/form-data:
      - file: audio file
      - user_id: optional (string)
      - tgt_lang: target language code (e.g., "hi", "en")
    """
    if "file" not in request.files:
        return jsonify({"error": "no_file"}), 400
    f = request.files["file"]
    filename = secure_filename(f.filename or "upload.wav")
    ext = os.path.splitext(filename)[1].lower()
    if ext not in ALLOWED_EXT:
        return jsonify({"error": "invalid_file"}), 400

    tmp_dir = tempfile.gettempdir()
    tmp_path = os.path.join(tmp_dir, filename)
    f.save(tmp_path)

    # STT: whisper
    if WHISPER_AVAILABLE and whisper_model is not None:
        try:
            result = whisper_model.transcribe(tmp_path, fp16=False)
            transcript = result.get("text", "").strip()
            detected_lang = result.get("language", None)
        except Exception as e:
            return jsonify({"error": "whisper_failed", "detail": str(e)}), 500
    else:
        return jsonify({"error": "whisper_unavailable"}), 500

    # MT: determine target language
    tgt_lang = request.form.get("tgt_lang") or request.args.get("tgt_lang") or "en"
    # translate
    mt = translate_text(transcript, detected_lang or "en", tgt_lang)

    # Save to DB (if user_id provided)
    user_id = request.form.get("user_id")
    try:
        from models import save_transcript  # lazy import
        save_transcript({
            "user_id": user_id,
            "src_text": transcript,
            "tgt_text": mt["translation"],
            "src_lang": detected_lang,
            "tgt_lang": tgt_lang,
            "meta": {
                "mt_method": mt["method"],
                "used_model": mt.get("used_model")
            }
        })
    except Exception as e:
        # non-fatal: continue but log
        print("Failed saving transcript:", e)

    # Remove tmp file
    try:
        os.remove(tmp_path)
    except:
        pass

    return jsonify({
        "transcript": transcript,
        "translation": mt["translation"],
        "language": detected_lang,
        "mt_meta": {"method": mt["method"], "used_model": mt.get("used_model")},
        "raw_result": result
    }), 200
