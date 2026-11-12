"""Voice-over for the short videos: one spoken line per frame, laid out on the video's timeline.

    python tools/voice.py out.wav "First line." "Second line."      # quick test

The voice is Kokoro-82M, an open text-to-speech model (Apache 2.0 licence, commercial use allowed), run on
the CPU through the kokoro-onnx package. No account, no API key, no cost per video. Its two model files
(about 350 MB) are downloaded once into VOICE_DIR; the nightly job caches that folder.

    say(lines)          one clip per line (float32, 24 kHz, silence trimmed); None for an empty line
    lay(clips, floors)  seconds per frame (a frame lasts as long as its line, never less than its floor)
                        and the voice track for the whole video
    write(path, track)  16-bit mono WAV
    name(card_name)     a card name the way it is read aloud ("Mega Gengar ex - 269/217" -> "Mega Gengar E X")

Card names: the model's dictionary gets many Pokémon names wrong (Gengar with a soft G, "Ray-kwah-za").
SAY holds the right sounds (IPA) for the names checked so far; add to it when a name sounds off.
"""
import os
import re
import sys
import urllib.request
import wave

import numpy as np

SR = 24000
VOICE = os.environ.get("DYS_VOICE", "af_heart")   # Keo picked this one from the Nov 12 preview
SPEED = float(os.environ.get("DYS_VOICE_SPEED", "1.2"))   # a little faster than normal speech: short-video pace
VOICE_DIR = os.environ.get("DYS_VOICE_DIR", os.path.join(os.path.expanduser("~"), ".cache", "dys-voice"))
OURS = "https://github.com/VapeZz/dys-market/releases/download/voice-kokoro-v1/"            # our own copy (kept for good)
THEIRS = "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/"   # where it was copied from
FILES = {"kokoro-v1.0.onnx": 300_000_000, "voices-v1.0.bin": 20_000_000}   # file: smallest size that can be right
UA = {"User-Agent": "DriveYourStyleMarket/1.0 (+https://driveyourstyle.net)"}

SAY = {   # lower-case word: sounds (IPA, US English, the symbols espeak uses)
    "pokémon": "pˈoʊkeɪmˌɑːn", "pokemon": "pˈoʊkeɪmˌɑːn",
    "pikachu": "pˈiːkətʃˌuː", "alakazam": "ˌæləkəzˈæm",
    "ogerpon": "ˈoʊɡɚpˌɑːn", "gengar": "ɡˈɛŋɡɑːɹ", "greninja": "ɡɹɛnˈɪndʒə", "iono": "iːˈoʊnoʊ",
    "latias": "lˈæɾiəs", "latios": "lˈæɾioʊs", "ampharos": "ˈæmfɚɹˌɑːs", "terapagos": "tɛɹˈæpəɡˌoʊs",
    "rayquaza": "ɹeɪkwˈeɪzə", "golurk": "ɡˈoʊlɜːk", "zorua": "zˈɔːɹuːə", "riolu": "ɹiːˈoʊluː",
    "reshiram": "ɹˈɛʃɪɹˌæm", "hawlucha": "hɔːlˈuːtʃə", "kangaskhan": "kˈæŋɡəskˌɑːn", "hydreigon": "haɪdɹˈaɪɡən",
    "archaludon": "ɑːɹkˈæluːdˌɑːn", "braviary": "bɹˈeɪviˌɛɹi", "dachsbun": "dˈɑːksbʌn", "raikou": "ɹˈaɪkuː",
    "fuecoco": "fweɪkˈoʊkoʊ", "miraidon": "mɪɹˈaɪdɑːn", "koraidon": "kɔːɹˈaɪdɑːn", "moltres": "mˈoʊltɹeɪz",
    "scizor": "sˈaɪzɚ", "leafeon": "lˈiːfiˌɑːn", "flareon": "flˈɛɹiˌɑːn", "glaceon": "ɡlˈeɪsiˌɑːn",
    "diancie": "diːˈɑːnsi", "absol": "ˈæbsɑːl", "growlithe": "ɡɹˈaʊlɪθ", "tyranitar": "taɪɹˈænɪtˌɑːɹ",
    "torchic": "tˈɔːɹtʃɪk", "rowlet": "ɹˈaʊlɪt", "clefable": "klɛfˈeɪbəl", "alolan": "ɐlˈoʊlən",
    "cinccino": "tʃɪntʃˈiːnoʊ", "meganium": "mɪɡˈeɪniəm", "celebi": "sˈɛlɪbi", "lucario": "luːkˈɑːɹioʊ",
    "mimikyu": "mˈɪmɪkjuː", "zeraora": "zɛɹˈɔːɹə", "giratina": "ɡˌɪɹətˈiːnə", "gyarados": "ɡˈɪɹədˌoʊs",
    "arceus": "ˈɑːɹkiəs", "suicune": "swˈiːkuːn", "gible": "ɡˈɪbəl", "regigigas": "ɹˌɛdʒiɡˈɪɡəs",
    "kyogre": "kaɪˈoʊɡɚ", "yveltal": "iːvˈɛltɑːl", "gallade": "ɡəlˈeɪd", "pidgeot": "pˈɪdʒiˌɑːt",
    "feraligatr": "fəɹˈælɪɡˌeɪɾɚ", "typhlosion": "taɪflˈoʊʒən", "blaziken": "blˈeɪzɪkən", "togekiss": "tˈoʊɡəkˌɪs",
    "lugia": "lˈuːdʒiə", "tinkaton": "tˈɪŋkətˌɑːn", "deoxys": "diːˈɑːksɪs", "entei": "ˈɛnteɪ", "dialga": "daɪˈælɡə",
    "salamence": "sˈæləmˌɛns", "golisopod": "ɡoʊlˈɪsəpˌɑːd", "jirachi": "dʒɪɹˈɑːtʃi",
    "bastiodon": "bˈæstioʊdˌɑːn", "meloetta": "mˌɛloʊˈɛɾə", "drifloon": "dɹˈɪfluːn", "cobalion": "koʊbˈeɪliən",
    "tirtouga": "tɪɹtˈuːɡə", "musharna": "muːʃˈɑːɹnə", "maractus": "məɹˈæktəs", "simisage": "sˈɪmisˌeɪdʒ",
    "simipour": "sˈɪmipˌɔːɹ", "simisear": "sˈɪmisˌɪɹ", "escavalier": "ɛskˈævəlˌɪɹ", "duosion": "duːˈoʊʒən",
    "morpeko": "mɔːɹpˈɛkoʊ", "tatsugiri": "tˌɑːtsuːɡˈɪɹi", "applin": "ˈæplɪn", "maushold": "mˈaʊshoʊld",
    "zapdos": "zˈæpdoʊs", "charmeleon": "tʃɑːɹmˈiːliən", "raichu": "ɹˈaɪtʃuː", "liepard": "lˈaɪpɚd",
    "leavanny": "liːvˈæni", "cofagrigus": "kˌɔfəɡɹˈiːɡəs", "garbodor": "ɡɑːɹbˈoʊdɔːɹ", "archen": "ˈɑːɹkən",
    "archeops": "ˈɑːɹkiˌɑːps", "deino": "dˈaɪnoʊ", "zweilous": "zwˈaɪləs", "volcanion": "vɑːlkˈeɪniən",
    "ribombee": "ɹɪbˈɑːmbiː", "tangela": "tˈæŋɡələ", "mawile": "mˈɔːwaɪl", "numel": "nˈʌməl", "milotic": "maɪlˈoʊɾɪk",
    "lisia": "lˈɪsiə", "vivillon": "vˈɪviˌɑːn", "shiinotic": "ʃiːnˈɑːɾɪk", "zarude": "zəɹˈuːd", "munna": "mˈuːnə",
    "pansage": "pˈænseɪdʒ", "thundurus": "θˈʌndɚɹəs", "pokegear": "pˈoʊkeɪɡˌɪɹ", "sinistcha": "sɪnˈɪstʃə",
    "hisuian": "hˈɪswiən", "phione": "fiːˈoʊni", "chimecho": "tʃaɪmˈɛkoʊ", "heliolisk": "hˈiːlioʊlˌɪsk",
    "horsea": "hˈɔːɹsi", "hitmonchan": "hˈɪtməntʃˌæn", "sewaddle": "səwˈɑːdəl", "gothitelle": "ɡˈɑːθɪtˌɛl",
    "salvatore": "sˈælvətˌɔːɹ", "cutiefly": "kjˈuːɾiflˌaɪ", "relicanth": "ɹˈɛlɪkˌænθ", "noctowl": "nˈɑːktaʊl",
    "aromatisse": "əɹˈoʊmətˌiːs", "hippowdon": "hɪpˈaʊdən", "nidoking": "nˈiːdoʊkˌɪŋ", "nidoqueen": "nˈiːdoʊkwˌiːn",
    "nidorina": "nˌiːdɚɹˈiːnə", "nidorino": "nˌiːdɚɹˈiːnoʊ", "zamazenta": "zˌɑːməzˈɛntə", "solgaleo": "sˌoʊlɡəlˈeɪoʊ",
    "uxie": "jˈuːksi", "dedenne": "dɛdˈɛneɪ", "dragalge": "dɹəɡˈældʒi", "floette": "floʊˈɛt", "lechonk": "lətʃˈɑːŋk",
    "chi-yu": "tʃˈiː jˈuː", "kadabra": "kədˈæbɹə", "pachirisu": "pˌætʃiɹˈiːsuː", "staryu": "stˈɑːɹjuː",
    "baxcalibur": "bækskˈælɪbɚ", "doduo": "doʊdˈuːoʊ", "dodrio": "doʊdɹˈiːoʊ", "skwovet": "skwˈʌvɪt",
    "kingambit": "kɪŋɡˈæmbɪt",
}
_WORD = re.compile(r"[A-Za-zÀ-ÿ][A-Za-zÀ-ÿ'’\-]*")
_engine = None


def name(n):
    """A card name the way it is read aloud: no card number, no brackets, "ex" spelled out."""
    n = re.sub(r"\s*\(.*$", "", n)                       # "(30th Celebration)", "(Reverse Holo)"
    n = re.sub(r"\s+-\s+[\w/]*\d[\w/]*\s*$", "", n)      # " - 106", " - 137/103", " - SV107"
    n = n.replace("&", " and ")
    for a, b in ((r"\bex\b", "E X"), (r"\bEX\b", "E X"), (r"\bGX\b", "G X"), (r"\bVMAX\b", "V max"),
                 (r"\bVSTAR\b", "V star"), (r"\bV-UNION\b", "V union"), (r"\bLV\.?\s*X\b", "level X")):
        n = re.sub(a, b, n)
    return re.sub(r"\s+", " ", n).strip()


def dollars(cents):
    """A price in words the voice reads right ("$7.45" is read as "dollar seven point four five")."""
    if cents >= 2000:
        whole = round(cents / 100)
        return f"{'' if cents % 100 == 0 else 'about '}{whole:,} dollars".replace(",", "")
    d, c = divmod(int(cents), 100)
    return f"{d} dollar{'' if d == 1 else 's'}" + (f" {c:02d}" if c else "")


def engine():
    """The loaded model. Downloads its two files the first time (checked by size, written in one move)."""
    global _engine
    if _engine is None:
        from kokoro_onnx import Kokoro
        os.makedirs(VOICE_DIR, exist_ok=True)
        paths = []
        for fn, least in FILES.items():
            p = os.path.join(VOICE_DIR, fn)
            if not os.path.exists(p) or os.path.getsize(p) < least:
                tmp, err = p + ".part", None
                for base in (OURS, THEIRS):
                    try:
                        with urllib.request.urlopen(urllib.request.Request(base + fn, headers=UA), timeout=300) as r, open(tmp, "wb") as f:
                            while True:
                                chunk = r.read(1 << 20)
                                if not chunk:
                                    break
                                f.write(chunk)
                        if os.path.getsize(tmp) >= least:
                            err = None
                            break
                        err = f"{fn} came back too small from {base}"
                    except Exception as e:
                        err = f"{fn} from {base}: {e!r}"
                if err:
                    if os.path.exists(tmp):
                        os.remove(tmp)
                    raise RuntimeError("voice: " + err[:200])
                os.replace(tmp, p)
            paths.append(p)
        _engine = Kokoro(*paths)
    return _engine


def sounds(text):
    """The line as phonemes: the model's own reading, with SAY's sounds for the names it gets wrong."""
    k = engine()
    out, pos = [], 0

    def plain(part):
        if re.search(r"[A-Za-z0-9]", part):
            out.append(k.tokenizer.phonemize(part.strip(), "en-us"))
        elif part.strip() and out:                      # only punctuation: keep it on the word before
            out[-1] += re.sub(r"\s+", "", part)

    for m in _WORD.finditer(text):
        w = m.group(0).lower().replace("’", "'")
        base, tail = (w[:-2], "z") if w.endswith("'s") else (w, "")
        if base in SAY:
            plain(text[pos:m.start()])
            out.append(SAY[base] + tail)
            pos = m.end()
    plain(text[pos:])
    return " ".join(out)


def trim(x, keep=0.03):
    """Cut the silence the model leaves before and after a line."""
    loud = np.flatnonzero(np.abs(x) > 0.02 * max(float(np.abs(x).max()), 1e-6))
    if not len(loud):
        return x[:0]
    pad = int(keep * SR)
    return x[max(loud[0] - pad, 0): loud[-1] + pad]


def say(lines, voice=None, speed=None):
    k = engine()
    clips = []
    for line in lines:
        if not (line or "").strip():
            clips.append(None)
            continue
        x, sr = k.create(sounds(line), voice=voice or VOICE, speed=speed or SPEED, is_phonemes=True,
                          sentence_pause=0.12, clause_pause=0.05)
        if sr != SR:
            raise RuntimeError(f"voice: unexpected sample rate {sr}")
        clips.append(trim(np.asarray(x, dtype=np.float32)))
    return clips


def lay(clips, floors, lead=0.12, tail=0.1):
    """(seconds per frame, voice track). Frame i shows from the sum of the frames before it; its line starts
    `lead` seconds in (after the cut) and the frame stays `tail` seconds after the last word."""
    pers = []
    for c, floor in zip(clips, floors):
        need = 0 if c is None else lead + len(c) / SR + tail
        pers.append(round(max(floor, need), 2))
    track = np.zeros(int((sum(pers) + 1) * SR), dtype=np.float32)
    t = 0.0
    for c, per in zip(clips, pers):
        if c is not None:
            a = int((t + lead) * SR)
            track[a:a + len(c)] += c
        t += per
    peak = float(np.abs(track).max())
    return pers, (track * (0.9 / peak) if peak > 0 else track)


def write(path, track):
    with wave.open(path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes((np.clip(track, -1, 1) * 32767).astype("<i2").tobytes())


if __name__ == "__main__":
    got = say(sys.argv[2:])
    pers, tr = lay(got, [0.5] * len(got))
    write(sys.argv[1], tr)
    for line, per in zip(sys.argv[2:], pers):
        print(f"{per:5.2f}s  {line}  [{sounds(line)}]")
