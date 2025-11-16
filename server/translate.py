# server/translate.py
from transformers import MarianMTModel, MarianTokenizer
from typing import Optional
import threading

# Simple thread-safe cache
_MODEL_LOCK = threading.Lock()
_MODEL_CACHE = {}  # key: "src-tgt" -> (tokenizer, model)

# Map common language codes to Marian model names (expand as needed)
# This mapping is not exhaustive. Add model IDs for the language pairs you need.
MARIAN_MAP = {
    # source -> { target: model_name }
    "en": {
        "hi": "Helsinki-NLP/opus-mt-en-hi",
        "bn": "Helsinki-NLP/opus-mt-en-bn",
        "ta": "Helsinki-NLP/opus-mt-en-ta",
        "mr": "Helsinki-NLP/opus-mt-en-mr",
        # add others...
    },
    # If translating from Hindi to English
    "hi": {
        "en": "Helsinki-NLP/opus-mt-hi-en"
    },
    # add direct inter-Indian pairs if available
    # "bn": {"hi": "Helsinki-NLP/opus-mt-bn-hi"}, etc.
}

def get_marian_model(src: str, tgt: str):
    key = f"{src}-{tgt}"
    with _MODEL_LOCK:
        if key in _MODEL_CACHE:
            return _MODEL_CACHE[key]
        # Find model id from mapping
        model_id = None
        if src in MARIAN_MAP and tgt in MARIAN_MAP[src]:
            model_id = MARIAN_MAP[src][tgt]
        # If direct model not found, try src->en and then en->tgt (pivot) — we will do pivot translation in caller
        if model_id:
            tokenizer = MarianTokenizer.from_pretrained(model_id)
            model = MarianMTModel.from_pretrained(model_id)
            _MODEL_CACHE[key] = (tokenizer, model)
            return tokenizer, model
        return None

def translate_text(src_text: str, src_lang: str, tgt_lang: str) -> dict:
    """
    Returns { translation: str, used_model: str or None, method: "direct"|"pivot"|"none" }
    """
    src = src_lang[:2].lower() if src_lang else "en"
    tgt = tgt_lang[:2].lower() if tgt_lang else "en"

    # Try direct model
    direct = get_marian_model(src, tgt)
    if direct:
        tokenizer, model = direct
        inputs = tokenizer([src_text], return_tensors="pt", padding=True)
        translated = model.generate(**inputs)
        out = tokenizer.decode(translated[0], skip_special_tokens=True)
        return {"translation": out, "used_model": f"{src}-{tgt}", "method": "direct"}

    # Pivot via English: src -> en -> tgt
    if src != "en" and tgt != "en":
        # src -> en
        s_en = get_marian_model(src, "en")
        en_t = get_marian_model("en", tgt)
        if s_en and en_t:
            tkn1, mdl1 = s_en
            inputs1 = tkn1([src_text], return_tensors="pt", padding=True)
            mid = mdl1.generate(**inputs1)
            mid_text = tkn1.decode(mid[0], skip_special_tokens=True)
            # en -> tgt
            tkn2, mdl2 = en_t
            inputs2 = tkn2([mid_text], return_tensors="pt", padding=True)
            out = mdl2.generate(**inputs2)
            final = tkn2.decode(out[0], skip_special_tokens=True)
            return {"translation": final, "used_model": "pivot-en", "method": "pivot"}
    # If src is en to other and mapping not found, try english direct
    if src == "en":
        en_t = get_marian_model("en", tgt)
        if en_t:
            tkn, mdl = en_t
            inputs = tkn([src_text], return_tensors="pt", padding=True)
            translated = mdl.generate(**inputs)
            out = tkn.decode(translated[0], skip_special_tokens=True)
            return {"translation": out, "used_model": f"en-{tgt}", "method": "direct"}

    # No model found
    return {"translation": "(no offline model available for this language pair)", "used_model": None, "method": "none"}
