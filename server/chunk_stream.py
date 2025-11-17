# server/chunk_stream.py
import os
import io
import time
import tempfile
import threading
import subprocess
import wave
import math
from flask import Blueprint, request, jsonify
from werkzeug.utils import secure_filename
from stt import WHISPER_AVAILABLE, whisper_model

# Blueprint
chunk_bp = Blueprint("chunk", __name__)

# Globals: buffers per session
_BUFFERS = {}         # session_id -> bytearray (raw PCM 16-bit LE)
_BUFFERS_META = {}    # session_id -> { "last_active": ts, "speech_active": bool, "silence_frames": int, "calibration": {...} }
_LOCK = threading.Lock()

# VAD params (energy-based)
FRAME_MS = 30             # frame size in ms
SAMPLE_RATE = 16000       # expected sample rate
BYTES_PER_SAMPLE = 2

# Global baseline values (very low floor)
MIN_SILENCE_THRESHOLD = 1.0    # global minimum threshold (very small)
DEFAULT_SILENCE_MS_THRESHOLD = 300    # ms of silence to finalize
SILENCE_FRAMES_THRESHOLD = max(1, int(DEFAULT_SILENCE_MS_THRESHOLD / FRAME_MS))

# Fallback (force finalize) config
FALLBACK_MAX_BUFFER_SECONDS = 6  # if buffer exceeds this, force finalize

ALLOWED_EXTS = {".wav", ".mp3", ".m4a", ".ogg", ".flac", ".aac", ".caf", ".webm"}

def ffmpeg_to_wav_bytes(src_path, target_rate=SAMPLE_RATE):
    tmp_wav = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
    tmp_wav_path = tmp_wav.name
    tmp_wav.close()
    cmd = [
        "ffmpeg", "-y", "-i", src_path,
        "-ar", str(target_rate),
        "-ac", "1",
        "-sample_fmt", "s16",
        tmp_wav_path
    ]
    try:
        subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    except subprocess.CalledProcessError as e:
        raise RuntimeError(f"ffmpeg failed: {e.stderr.decode('utf-8', errors='ignore')}")
    return tmp_wav_path

def wav_to_pcm_bytes(wav_path):
    with wave.open(wav_path, 'rb') as wf:
        sampwidth = wf.getsampwidth()
        channels = wf.getnchannels()
        fr = wf.getframerate()
        if sampwidth != 2:
            raise RuntimeError(f"Unexpected sample width: {sampwidth}")
        if channels != 1:
            raise RuntimeError(f"Expected mono WAV but got {channels} channels")
        if fr != SAMPLE_RATE:
            raise RuntimeError(f"Expected {SAMPLE_RATE}Hz but got {fr}Hz")
        frames = wf.readframes(wf.getnframes())
    return frames

def frames_from_pcm(raw_pcm_bytes, sample_rate=SAMPLE_RATE, frame_ms=FRAME_MS):
    bytes_per_frame = int(sample_rate * (frame_ms / 1000.0) * BYTES_PER_SAMPLE)
    for i in range(0, len(raw_pcm_bytes), bytes_per_frame):
        yield raw_pcm_bytes[i:i+bytes_per_frame]

def rms_from_frame(frame_bytes):
    # frame_bytes is bytes of 16-bit PCM little-endian samples
    if not frame_bytes:
        return 0.0
    count = len(frame_bytes) // 2
    if count == 0:
        return 0.0
    total_squares = 0
    for i in range(0, len(frame_bytes), 2):
        sample = int.from_bytes(frame_bytes[i:i+2], byteorder='little', signed=True)
        total_squares += sample * sample
    mean_squares = total_squares / count
    rms = math.sqrt(mean_squares)
    return rms

def _append_to_buffer(session_id, pcm_bytes):
    with _LOCK:
        if session_id not in _BUFFERS:
            _BUFFERS[session_id] = bytearray()
            _BUFFERS_META[session_id] = {
                "last_active": time.time(),
                "speech_active": False,
                "silence_frames": 0,
                # calibration structure
                "calibration": {
                    "samples": [],   # list of rms_avg values until calibrated
                    "calibrated": False,
                    "session_threshold": None
                }
            }
        _BUFFERS[session_id].extend(pcm_bytes)
        _BUFFERS_META[session_id]["last_active"] = time.time()

def _flush_buffer(session_id):
    with _LOCK:
        buf = _BUFFERS.pop(session_id, None)
        meta = _BUFFERS_META.pop(session_id, None)
    if not buf:
        return None
    tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
    tmp_path = tmp.name
    tmp.close()
    with wave.open(tmp_path, 'wb') as wf:
        wf.setnchannels(1)
        wf.setsampwidth(BYTES_PER_SAMPLE)
        wf.setframerate(SAMPLE_RATE)
        wf.writeframes(bytes(buf))
    return tmp_path

def _transcribe_file(path):
    if not WHISPER_AVAILABLE or whisper_model is None:
        return {"error": "whisper_unavailable"}
    try:
        res = whisper_model.transcribe(path, fp16=False)
        return {"transcript": res.get("text","").strip(), "raw": res}
    except Exception as e:
        return {"error": "whisper_failed", "detail": str(e)}

# cleanup daemon to purge old sessions
def _cleanup_worker():
    while True:
        now = time.time()
        to_delete = []
        with _LOCK:
            for sid, meta in list(_BUFFERS_META.items()):
                if now - meta["last_active"] > 60:
                    to_delete.append(sid)
            for sid in to_delete:
                _BUFFERS.pop(sid, None)
                _BUFFERS_META.pop(sid, None)
        time.sleep(15)

cleanup_thread = threading.Thread(target=_cleanup_worker, daemon=True)
cleanup_thread.start()

# @chunk_bp.route("/chunk", methods=["POST"])
# def receive_chunk():
#     session_id = request.form.get("session_id") or request.args.get("session_id") or "default"
#     if "file" not in request.files:
#         return jsonify({"error":"no_file"}), 400
#     file = request.files["file"]
#     filename = secure_filename(file.filename or "chunk")
#     ext = os.path.splitext(filename)[1].lower()
#     tmp = tempfile.NamedTemporaryFile(delete=False, suffix=ext)
#     tmp_path = tmp.name
#     tmp.close()
#     file.save(tmp_path)

#     # convert to mono 16k wav via ffmpeg
#     try:
#         wav_path = ffmpeg_to_wav_bytes(tmp_path, target_rate=SAMPLE_RATE)
#     except Exception as e:
#         try: os.remove(tmp_path)
#         except: pass
#         return jsonify({"error":"ffmpeg_failed", "detail": str(e)}), 500
#     finally:
#         try: os.remove(tmp_path)
#         except: pass

#     # read PCM bytes
#     try:
#         pcm = wav_to_pcm_bytes(wav_path)
#     except Exception as e:
#         try: os.remove(wav_path)
#         except: pass
#         return jsonify({"error":"wav_read_failed", "detail": str(e)}), 500
#     finally:
#         try: os.remove(wav_path)
#         except: pass

#     # energy-based VAD on frames (compute RMS and collect stats)
#     rms_values = []
#     frame_count = 0
#     for frame in frames_from_pcm(pcm):
#         if len(frame) < 4:
#             continue
#         frame_count += 1
#         rms = rms_from_frame(frame)
#         rms_values.append(rms)

#     # compute RMS stats for this chunk
#     if rms_values:
#         rms_min = min(rms_values)
#         rms_max = max(rms_values)
#         rms_avg = sum(rms_values) / len(rms_values)
#     else:
#         rms_min = rms_max = rms_avg = 0.0

#     # ensure session meta exists
#     with _LOCK:
#         if session_id not in _BUFFERS_META:
#             _BUFFERS_META[session_id] = {
#                 "last_active": time.time(),
#                 "speech_active": False,
#                 "silence_frames": 0,
#                 "calibration": {"samples": [], "calibrated": False, "session_threshold": None}
#             }
#         meta = _BUFFERS_META[session_id]

#     # calibration: collect a few quiet chunk rms averages to compute a baseline
#     calib = meta.get("calibration", {})
#     if not calib:
#         calib = {"samples": [], "calibrated": False, "session_threshold": None}
#         meta["calibration"] = calib

#     # If not calibrated, and this chunk looks like silence (low rms), add to samples
#     # We'll use these to compute baseline noise floor
#     if not calib["calibrated"]:
#         # only add if chunk rms is not obviously speechy (conservative: rms_avg < a small value)
#         if rms_avg < 8.0 and len(calib["samples"]) < 3:
#             calib["samples"].append(rms_avg)
#         # if we have 3 samples, compute threshold
#         if len(calib["samples"]) >= 3:
#             baseline = sum(calib["samples"]) / len(calib["samples"])
#             # session threshold: baseline + delta (delta tuned low for low-RMS devices)
#             session_threshold = max(MIN_SILENCE_THRESHOLD, baseline + 1.0)
#             calib["session_threshold"] = session_threshold
#             calib["calibrated"] = True
#             print(f"[CALIBRATE] session={session_id} baseline={baseline:.2f} session_threshold={session_threshold:.2f}")

#     # decide which threshold to use
#     session_threshold = calib.get("session_threshold") if calib.get("session_threshold") else MIN_SILENCE_THRESHOLD

#     # determine if any frame exceeds threshold -> speech_detected
#     speech_detected = any(r > session_threshold for r in rms_values)

#     # For debugging print values
#     with _LOCK:
#         # Append pcm to buffer (always)
#         if session_id not in _BUFFERS:
#             _BUFFERS[session_id] = bytearray()
#         _BUFFERS[session_id].extend(pcm)
#         meta["last_active"] = time.time()

#     # update silence frames and speech_active state
#     with _LOCK:
#         if speech_detected:
#             meta["speech_active"] = True
#             meta["silence_frames"] = 0
#         else:
#             meta["silence_frames"] = meta.get("silence_frames", 0) + int((len(rms_values) or 0))
#         # compute buffered seconds for fallback decision
#         buf_len = len(_BUFFERS.get(session_id, b""))
#         seconds_buffered = buf_len / (SAMPLE_RATE * BYTES_PER_SAMPLE)

#     # log chunk stats
#     print(f"[CHUNK] session={session_id} frames={frame_count} rms_min={rms_min:.2f} rms_avg={rms_avg:.2f} rms_max={rms_max:.2f} session_threshold={session_threshold:.2f} speech_detected={speech_detected} silence_frames={meta.get('silence_frames')} buffered_s={seconds_buffered:.2f}")

#     # If silence frames exceed threshold and speech was active => finalize
#     if meta.get("speech_active") and meta.get("silence_frames", 0) >= SILENCE_FRAMES_THRESHOLD:
#         file_path = _flush_buffer(session_id)
#         if not file_path:
#             return jsonify({"status":"buffered"})
#         result = _transcribe_file(file_path)
#         try: os.remove(file_path)
#         except: pass
#         with _LOCK:
#             _BUFFERS_META.pop(session_id, None)
#         if "transcript" in result:
#             print(f"[CHUNK] session={session_id} finalized by VAD, transcript_len={len(result['transcript'])}")
#             return jsonify({"status":"final", "transcript": result["transcript"], "raw": result.get("raw")})
#         else:
#             return jsonify({"status":"error", **result}), 500

#     # Fallback: force finalize if buffer grows too long
#     if seconds_buffered >= FALLBACK_MAX_BUFFER_SECONDS:
#         print(f"[CHUNK] session={session_id} fallback finalize after {seconds_buffered:.1f}s")
#         file_path = _flush_buffer(session_id)
#         if not file_path:
#             return jsonify({"status":"buffered"})
#         result = _transcribe_file(file_path)
#         try: os.remove(file_path)
#         except: pass
#         with _LOCK:
#             _BUFFERS_META.pop(session_id, None)
#         if "transcript" in result:
#             print(f"[CHUNK] session={session_id} finalized by fallback, transcript_len={len(result['transcript'])}")
#             return jsonify({"status":"final", "transcript": result["transcript"], "raw": result.get("raw")})
#         else:
#             return jsonify({"status":"error", **result}), 500

#     # otherwise still buffering
#     return jsonify({"status":"buffered"})


@chunk_bp.route("/chunk", methods=["POST"])
def receive_chunk_test_transcribe_every_chunk():
    session_id = request.form.get("session_id") or request.args.get("session_id") or "default"
    if "file" not in request.files:
        return jsonify({"error":"no_file"}), 400
    file = request.files["file"]
    filename = secure_filename(file.filename or "chunk")
    ext = os.path.splitext(filename)[1].lower()
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=ext)
    tmp_path = tmp.name
    tmp.close()
    file.save(tmp_path)

    try:
        wav_path = ffmpeg_to_wav_bytes(tmp_path, target_rate=SAMPLE_RATE)
    except Exception as e:
        try: os.remove(tmp_path)
        except: pass
        return jsonify({"error":"ffmpeg_failed", "detail": str(e)}), 500
    finally:
        try: os.remove(tmp_path)
        except: pass

    # directly transcribe the single chunk file (no buffering)
    try:
        result = _transcribe_file(wav_path)
    except Exception as e:
        result = {"error": "transcription_exception", "detail": str(e)}
    finally:
        try: os.remove(wav_path)
        except: pass

    if "transcript" in result:
        return jsonify({"status":"final", "transcript": result["transcript"], "raw": result.get("raw")}), 200
    else:
        return jsonify({"status":"error", **result}), 500
