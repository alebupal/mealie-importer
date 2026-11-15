import json
import os
import re
import sys
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
import uuid
from collections import Counter
from pathlib import Path

STOP_WORDS = {"de", "del", "la", "el", "los", "las", "y"}

UNIT_SYN = {
    "g": ["g", "gr", "grs", "gramo", "gram", "gramos"],
    "kg": ["kg", "kilo", "kilogramo", "kilogram", "kilos"],
    "mg": ["mg", "miligramo", "milligram"],
    "ml": ["ml", "mililitro", "milliliter", "millilitre", "mililitros"],
    "cl": ["cl", "centilitro", "centiliter"],
    "l": ["l", "litro", "liter", "litre", "litros"],
    "cucharada": ["cucharada", "cda", "cs", "c s", "cucharada sopera", "tablespoon", "tbsp", "cucharadas"],
    "cucharadita": ["cucharadita", "cdta", "cdita", "cc", "cucharadita de cafe", "teaspoon", "tsp", "cucharaditas"],
    "pizca": ["pizca", "pinch"],
    "pellizco": ["pellizco"],
    "taza": ["taza", "cup", "tazas"],
    "vaso": ["vaso", "glass", "vasos"],
    "sobre": ["sobre", "packet", "sachet", "sobres"],
    "hoja": ["hoja", "sheet", "leaf", "hojas"],
    "chorrito": ["chorrito", "chorro", "splash", "dash"],
    "puñado": ["punado", "puñado", "handful", "puñados"],
    "diente": ["diente", "clove", "dientes"],
    "rama": ["rama", "ramita", "sprig", "ramas"],
    "lata": ["lata", "can", "latas"],
    "unidad": ["unidad", "ud", "uds", "unit", "piece", "pieza", "unidades"],
}

UNIT_ABBR = {
    "g": "g", "kg": "kg", "mg": "mg", "ml": "ml", "cl": "cl", "l": "l",
    "cucharada": "cda", "cucharadita": "cdta", "unidad": "ud"
}


def strip_acc(s: str) -> str:
    if not s:
        return ""
    return "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn")


def singular(w: str) -> str:
    if len(w) <= 3:
        return w
    if w.endswith("ces"):
        return w[:-3] + "z"
    if w.endswith(("ones", "ales", "eles", "ares", "eres", "ores", "anes", "ines", "unes")):
        return w[:-2]
    if w.endswith("es") and w[-3] in "dlnrjy":
        return w[:-2]
    if w.endswith("s") and not w.endswith("ss"):
        return w[:-1]
    return w


def key(s: str) -> str:
    s = strip_acc((s or "").lower()).replace("®", "").replace("™", "")
    s = re.sub(r"[^a-z0-9% ]", " ", s)
    return " ".join(singular(w) for w in s.split() if w not in STOP_WORDS)


def unit_canon(u: str) -> str:
    if not u:
        return ""
    k = key(u)
    for canon, syns in UNIT_SYN.items():
        if k in {key(s) for s in syns}:
            return canon
    return u.strip()


CONFIG_FILE = Path(__file__).resolve().parent.parent / "data" / "config.json"


def get_settings() -> dict:
    url = os.environ.get("MEALIE_URL", "http://127.0.0.1:9000").rstrip("/")
    token = os.environ.get("MEALIE_TOKEN", "").strip()

    if CONFIG_FILE.exists():
        try:
            d = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
            if d.get("url"):
                url = d["url"].rstrip("/")
            if d.get("token"):
                token = d["token"].strip()
        except Exception:
            pass

    if not token:
        f = Path("~/.mealie_token").expanduser()
        if f.exists():
            txt = f.read_text().strip()
            token = txt.split("=", 1)[1].strip() if txt.startswith("MEALIE_TOKEN=") else txt

    if not token:
        for p in [
            Path("/host/home/abueno/Proyectos/alebupal/docker/homepage/config/services.yaml"),
            Path("/home/abueno/Proyectos/alebupal/docker/homepage/config/services.yaml"),
        ]:
            if p.exists():
                lines = p.read_text().splitlines()
                for n, line in enumerate(lines):
                    if "type: mealie" in line:
                        for l2 in lines[n:n + 6]:
                            if l2.strip().startswith("key:"):
                                token = l2.split(":", 1)[1].strip().strip("'\"")
                                break
                    if token:
                        break
            if token:
                break

    return {"url": url, "token": token}


def save_settings(url: str, token: str):
    CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
    payload = {"url": url.rstrip("/"), "token": token.strip()}
    CONFIG_FILE.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def get_token(default_path: Path | None = None) -> str:
    return get_settings()["token"]


class MealieClient:
    def __init__(self, url: str | None = None, token: str | None = None):
        cfg = get_settings()
        self.url = (url or cfg["url"]).rstrip("/")
        self.token = token or cfg["token"]

    def test_connection(self) -> dict:
        group = self.call("GET", "/api/groups/self")
        return {"ok": True, "group": group.get("slug", "general"), "url": self.url}

    def call(self, method: str, path: str, body=None, params=None):
        url = self.url + path + ("?" + urllib.parse.urlencode(params) if params else "")
        data = json.dumps(body).encode() if body is not None else None
        headers = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        req = urllib.request.Request(url, data=data, method=method, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                raw = r.read()
                return json.loads(raw) if raw else None
        except urllib.error.HTTPError as e:
            err_msg = e.read().decode("utf-8", errors="replace")[:600]
            raise RuntimeError(f"{method} {path} -> {e.code}: {err_msg}") from None

    def all(self, path: str):
        return self.call("GET", path, params={"page": 1, "perPage": -1})["items"]

    def upload_image(self, slug: str, image_bytes: bytes, ext: str = "jpg"):
        ext = ext.lstrip(".").lower() or "jpg"
        ctype = {
            "jpg": "image/jpeg",
            "jpeg": "image/jpeg",
            "png": "image/png",
            "webp": "image/webp",
        }.get(ext, "application/octet-stream")
        b = uuid.uuid4().hex
        body = (
            f"--{b}\r\nContent-Disposition: form-data; name=\"extension\"\r\n\r\n{ext}\r\n"
            f"--{b}\r\nContent-Disposition: form-data; name=\"image\"; filename=\"image.{ext}\"\r\n"
            f"Content-Type: {ctype}\r\n\r\n"
        ).encode() + image_bytes + f"\r\n--{b}--\r\n".encode()

        req = urllib.request.Request(
            f"{self.url}/api/recipes/{slug}/image",
            data=body,
            method="PUT",
            headers={
                "Authorization": f"Bearer {self.token}",
                "Content-Type": f"multipart/form-data; boundary={b}",
            },
        )
        with urllib.request.urlopen(req, timeout=120) as r:
            return r.status
