"""Text clean-up so OmniVoice speaks Hindi clearly (no 'totla' sound):
digits -> Hindi words, symbols -> words, odd unicode removed, sentences end with '।'."""
import re

_U = ("शून्य एक दो तीन चार पाँच छह सात आठ नौ दस ग्यारह बारह तेरह चौदह पंद्रह सोलह सत्रह अठारह उन्नीस "
      "बीस इक्कीस बाईस तेईस चौबीस पच्चीस छब्बीस सत्ताईस अट्ठाईस उनतीस तीस इकतीस बत्तीस तैंतीस चौंतीस पैंतीस "
      "छत्तीस सैंतीस अड़तीस उनतालीस चालीस इकतालीस बयालीस तैंतालीस चवालीस पैंतालीस छियालीस सैंतालीस अड़तालीस "
      "उनचास पचास इक्यावन बावन तिरपन चौवन पचपन छप्पन सत्तावन अट्ठावन उनसठ साठ इकसठ बासठ तिरसठ चौंसठ पैंसठ "
      "छियासठ सड़सठ अड़सठ उनहत्तर सत्तर इकहत्तर बहत्तर तिहत्तर चौहत्तर पचहत्तर छिहत्तर सतहत्तर अठहत्तर उन्यासी "
      "अस्सी इक्यासी बयासी तिरासी चौरासी पचासी छियासी सत्तासी अट्ठासी नवासी नब्बे इक्यानवे बानवे तिरानवे चौरानवे "
      "पचानवे छियानवे सत्तानवे अट्ठानवे निन्यानवे").split()
assert len(_U) == 100


def num_hi(n: int) -> str:
    if n < 100: return _U[n]
    out = []
    for val, name in ((10 ** 7, "करोड़"), (10 ** 5, "लाख"), (1000, "हज़ार"), (100, "सौ")):
        if n >= val:
            q, n = divmod(n, val)
            out.append(f"{num_hi(q)} {name}")
    if n: out.append(_U[n])
    return " ".join(out)


def _num(m):
    s = m.group(0).replace(",", "")
    if re.fullmatch(r"(19|20)\d\d", s):           # years: 2026 -> दो हज़ार छब्बीस
        return num_hi(int(s))
    if "." in s:
        a, b = s.split(".", 1)
        return f"{num_hi(int(a or 0))} दशमलव " + " ".join(_U[int(d)] for d in b if d.isdigit())
    return num_hi(int(s))


LATIN = {"plus": "प्लस", "vs": "बनाम", "test": "टेस्ट", "odi": "वनडे", "t20i": "टी ट्वेंटी", "t20": "टी ट्वेंटी", "ipl": "आई पी एल",
         "wtc": "डब्ल्यू टी सी", "icc": "आई सी सी", "bcci": "बी सी सी आई", "runs": "रन", "run": "रन", "wickets": "विकेट", "wicket": "विकेट",
         "century": "शतक", "record": "रिकॉर्ड", "india": "भारत", "the": "द", "sports": "स्पोर्ट्स", "gyan": "ज्ञान", "ai": "ए आई"}
SYMBOLS = {"%": " प्रतिशत", "+": " प्लस", "&": " और", "@": " ऐट ", "₹": " रुपये ", "#": " "}


def for_voice(text: str) -> str:
    t = str(text)
    t = re.sub(r"[\u2010-\u2015\u2212]", "-", t)              # odd dashes / non-breaking hyphen
    t = re.sub(r"[\U0001F000-\U0001FAFF\u2600-\u27BF\uFE0F\u200d\u200c\u00a0]", " ", t)
    t = re.sub(r"(\d+)\s*/\s*(\d+)", lambda m: f"{m.group(1)} पर {m.group(2)}", t)   # 6/45 -> 6 पर 45
    t = re.sub(r"(\d)-(\d)", r"\1 से \2", t)
    t = re.sub(r"(\d)(st|nd|rd|th)\b", r"\1", t)
    for k, v in SYMBOLS.items(): t = t.replace(k, v)
    t = re.sub(r"\d[\d,]*(\.\d+)?", _num, t)
    t = re.sub(r"[A-Za-z0-9]+", lambda m: LATIN.get(m.group(0).lower(), m.group(0)), t)
    t = t.replace("-", " ").replace('"', "").replace("'", "")
    t = re.sub(r"\s+", " ", t).strip()
    if t and t[-1] not in "।!?.": t += "।"
    return t


def for_screen(text: str) -> str:
    t = re.sub(r"[\u2010-\u2015\u2212]", "-", str(text))
    t = re.sub(r"[\U0001F000-\U0001FAFF\u2600-\u27BF\uFE0F\u200d\u200c]", "", t)
    return t.replace("\u00a0", " ").strip()


if __name__ == "__main__":
    for s in ["भारत ने 720/9 पर पारी घोषित की", "352 रन की बढ़त, 7 बार 50+ साझेदारी", "2026 में 12,345 रन", "700‑plus इन्निंग्स", "स्ट्राइक रेट 145.5%"]:
        print(for_voice(s))
