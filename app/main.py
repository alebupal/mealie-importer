import json
import os
import re
import time
import urllib.request
import uuid
from pathlib import Path

from fastapi import FastAPI, HTTPException, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from .extractor import extract_video, clean_emojis
from .mealie_client import MealieClient, key, unit_canon, UNIT_ABBR, get_settings, save_settings
from .parser import parse_recipe_from_info, analyze_with_mealie

HERE = Path(__file__).resolve().parent.parent
STATIC_DIR = HERE / "static"
DATA_DIR = HERE / "data"
IMAGES_DIR = DATA_DIR / "images"
IMAGES_DIR.mkdir(parents=True, exist_ok=True)
HISTORY_FILE = DATA_DIR / "history.json"
SYNONYMS_FILE = HERE / "alimentos_sinonimos.json"

app = FastAPI(title="Mealie Importer Web", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


def get_synonyms() -> dict:
    if SYNONYMS_FILE.exists():
        try:
            return json.loads(SYNONYMS_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}


class ExtractRequest(BaseModel):
    url: str


class ImportRequest(BaseModel):
    name: str
    description: str = ""
    yield_text: str = ""
    prepTime: str | None = None
    cookTime: str | None = None
    totalTime: str | None = None
    categories: list[str] = []
    tags: list[str] = []
    source: str = ""
    orgURL: str = ""
    image_file: str | None = None
    ingredients: list[dict]
    instructions: list[dict]
    notes: list[dict] = []
    update_if_exists: bool = False


class ConfigUpdateRequest(BaseModel):
    url: str
    token: str


@app.get("/api/config")
def get_config():
    cfg = get_settings()
    tok = cfg.get("token", "")
    masked_token = (tok[:6] + "..." + tok[-4:]) if len(tok) > 10 else ("***" if tok else "")
    return {
        "url": cfg.get("url", ""),
        "configured": bool(tok),
        "token_preview": masked_token,
    }


@app.post("/api/config")
def update_config(req: ConfigUpdateRequest):
    url = req.url.strip().rstrip("/")
    token = req.token.strip()
    if not url:
        raise HTTPException(status_code=400, detail="La URL de Mealie no puede estar vacía")
    
    # Probar conexión antes de guardar
    client = MealieClient(url=url, token=token)
    try:
        res = client.test_connection()
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"No se pudo conectar a Mealie: {e}")

    save_settings(url, token)
    return {"success": True, "group": res["group"], "url": res["url"]}


@app.get("/api/test-connection")
def test_connection_endpoint():
    try:
        client = MealieClient()
        return client.test_connection()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Fallo de conexión con Mealie: {e}")


def load_history() -> list[dict]:
    if HISTORY_FILE.exists():
        try:
            return json.loads(HISTORY_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return []


def add_to_history(entry: dict):
    history = load_history()
    # Evitar duplicados recientes por slug
    history = [h for h in history if h.get("slug") != entry.get("slug")]
    history.insert(0, entry)
    history = history[:20]  # Mantener últimas 20
    HISTORY_FILE.parent.mkdir(parents=True, exist_ok=True)
    HISTORY_FILE.write_text(json.dumps(history, ensure_ascii=False, indent=2), encoding="utf-8")


@app.get("/manifest.json")
def manifest():
    return FileResponse(STATIC_DIR / "manifest.json", media_type="application/manifest+json")


@app.get("/sw.js")
def service_worker():
    return FileResponse(STATIC_DIR / "sw.js", media_type="application/javascript")


@app.get("/api/history")
def get_history():
    return load_history()


@app.post("/api/upload-image")
async def upload_image_endpoint(file: UploadFile = File(...)):
    ext = (file.filename or "").rsplit(".", 1)[-1].lower() if "." in (file.filename or "") else "jpg"
    if ext not in ("jpg", "jpeg", "png", "webp"):
        ext = "jpg"

    filename = f"custom_{uuid.uuid4().hex[:10]}.{ext}"
    target = IMAGES_DIR / filename
    contents = await file.read()
    target.write_bytes(contents)

    return {
        "success": True,
        "filename": filename,
        "url": f"/api/image/{filename}",
    }


@app.get("/")
def index():
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/api/health")
def health():
    return {"status": "ok", "service": "mealie-importer"}


@app.get("/api/foods")
def list_foods():
    try:
        client = MealieClient()
        foods = client.all("/api/foods")
        return [f["name"] for f in foods]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/units")
def list_units():
    try:
        client = MealieClient()
        units = client.all("/api/units")
        return [u["name"] for u in units]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/image/{filename}")
def get_image(filename: str):
    file_path = IMAGES_DIR / filename
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Imagen no encontrada")
    return FileResponse(file_path)


@app.post("/api/extract")
def extract_endpoint(req: ExtractRequest):
    url = req.url.strip()
    if not url:
        raise HTTPException(status_code=400, detail="URL no puede estar vacía")

    try:
        info = extract_video(url)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Error extrayendo el vídeo: {e}")

    try:
        raw_recipe = parse_recipe_from_info(info)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error parseando receta: {e}")

    # Descargar imagen de previsualización
    image_filename = None
    thumb_url = info.get("thumbnail")
    if thumb_url:
        try:
            from .mealie_client import strip_acc
            slug = re.sub(r"[^a-z0-9]+", "-", strip_acc(clean_emojis(raw_recipe["name"]).lower())).strip("-") or "receta"
            target = IMAGES_DIR / f"{slug}.jpg"
            img_req = urllib.request.Request(thumb_url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(img_req, timeout=30) as r, open(target, "wb") as f:
                f.write(r.read())
            image_filename = f"{slug}.jpg"
            raw_recipe["local_image_url"] = f"/api/image/{image_filename}"
            raw_recipe["image_file"] = image_filename
        except Exception:
            pass

    # Consultar Mealie y sinónimos para generar análisis y preguntas
    try:
        client = MealieClient()
        foods = client.all("/api/foods")
        units = client.all("/api/units")
        synonyms = get_synonyms()
        analysis = analyze_with_mealie(raw_recipe, foods, units, synonyms)
        return analysis
    except Exception as e:
        # Si Mealie no está disponible temporalmente, devolvemos la receta sin enriquecer
        return {
            "recipe": raw_recipe,
            "questions": [],
            "warning": f"No se pudo consultar Mealie para comparar alimentos: {e}",
        }


def link_steps(rec):
    def has(text, term):
        return re.search(r"\b" + re.escape(term) + r"(s|es)?\b", text) is not None
    ings = [i for i in rec["recipeIngredient"] if i.get("food") and i.get("referenceId")]
    changed = 0
    for st in rec["recipeInstructions"]:
        if st.get("ingredientReferences"):
            continue
        text = (st.get("text") or "").lower()
        full = [i for i in ings if has(text, (i["food"]["name"] or "").lower())]
        hit = {id(i) for i in full}
        refs = [{"referenceId": i["referenceId"]} for i in ings if id(i) in hit]
        if refs:
            st["ingredientReferences"] = refs
            changed += 1
    return changed


@app.post("/api/import")
def import_endpoint(req: ImportRequest):
    try:
        client = MealieClient()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error conectando a Mealie: {e}")

    try:
        foods = client.all("/api/foods")
        units = client.all("/api/units")
        tags_raw = client.all("/api/organizers/tags")
        cats_raw = client.all("/api/organizers/categories")
        group_slug = client.call("GET", "/api/groups/self")["slug"]

        fidx = {key(f["name"]): f for f in foods}
        uidx = {key(u["name"]): u for u in units}
        tidx = {key(t["name"]): t for t in tags_raw}
        cidx = {key(c["name"]): c for c in cats_raw}

        # 1. Asegurar unidades
        for ing in req.ingredients:
            u_str = (ing.get("unit") or "").strip()
            if u_str:
                canon = unit_canon(u_str)
                k = key(canon)
                if k not in uidx:
                    new_u = client.call("POST", "/api/units", {
                        "name": canon,
                        "abbreviation": UNIT_ABBR.get(canon, ""),
                        "useAbbreviation": canon in UNIT_ABBR,
                        "fraction": True,
                    })
                    uidx[k] = new_u

        # 2. Asegurar alimentos
        for ing in req.ingredients:
            f_str = (ing.get("food") or "").strip()
            if f_str:
                k = key(f_str)
                if k not in fidx:
                    new_f = client.call("POST", "/api/foods", {"name": f_str})
                    fidx[k] = new_f

        # 3. Asegurar tags y categorias
        final_tags = []
        for t in req.tags:
            k = key(t)
            if k not in tidx:
                tidx[k] = client.call("POST", "/api/organizers/tags", {"name": t})
            final_tags.append({"id": tidx[k]["id"], "name": tidx[k]["name"], "slug": tidx[k]["slug"]})

        final_cats = []
        for c in req.categories:
            k = key(c)
            if k not in cidx:
                cidx[k] = client.call("POST", "/api/organizers/categories", {"name": c})
            final_cats.append({"id": cidx[k]["id"], "name": cidx[k]["name"], "slug": cidx[k]["slug"]})

        # 4. Crear o buscar receta
        search_res = client.call("GET", "/api/recipes", params={"search": req.name, "perPage": 10, "page": 1})
        existing_slug = None
        for it in search_res.get("items", []):
            if key(it["name"]) == key(req.name):
                existing_slug = it["slug"]
                break

        if existing_slug and not req.update_if_exists:
            # Añadimos un sufijo o evitamos duplicar
            from .mealie_client import strip_acc
            slug = client.call("POST", "/api/recipes", {"name": req.name})
        elif existing_slug:
            slug = existing_slug
        else:
            slug = client.call("POST", "/api/recipes", {"name": req.name})

        rec = client.call("GET", f"/api/recipes/{slug}")

        # Construir ingredientes para Mealie
        ings = []
        last_sec = None
        for i in req.ingredients:
            f_str = (i.get("food") or "").strip()
            u_str = (i.get("unit") or "").strip()
            canon_u = unit_canon(u_str) if u_str else None
            food_obj = fidx.get(key(f_str)) if f_str else None
            unit_obj = uidx.get(key(canon_u)) if canon_u else None
            sec = i.get("section")

            ings.append({
                "quantity": i.get("quantity") or 0,
                "unit": {"id": unit_obj["id"], "name": unit_obj["name"]} if unit_obj else None,
                "food": {"id": food_obj["id"], "name": food_obj["name"]} if food_obj else None,
                "note": i.get("note") or "",
                "title": sec if sec and sec != last_sec else None,
                "originalText": i.get("original") or f"{i.get('quantity') or ''} {u_str or ''} {f_str}".strip(),
                "display": i.get("original") or f"{i.get('quantity') or ''} {u_str or ''} {f_str}".strip(),
            })
            last_sec = sec

        steps = [
            {"title": s.get("title") or "", "summary": "", "text": s.get("text", ""), "ingredientReferences": []}
            for s in req.instructions if s.get("text")
        ]

        # Rendimiento numérico
        yield_str = req.yield_text.strip()
        y_qty = 1.0
        m_y = re.match(r"^(\d+)", yield_str)
        if m_y:
            y_qty = float(m_y.group(1))

        rec.update({
            "description": req.description or "",
            "recipeYield": yield_str,
            "recipeYieldQuantity": y_qty,
            "prepTime": req.prepTime,
            "performTime": req.cookTime,
            "totalTime": req.totalTime,
            "recipeIngredient": ings,
            "recipeInstructions": steps,
            "notes": [{"title": n.get("title") or "Nota", "text": n.get("text", "")} for n in req.notes if n.get("text")],
            "tags": final_tags,
            "recipeCategory": final_cats,
            "orgURL": req.orgURL,
        })
        if isinstance(rec.get("settings"), dict):
            rec["settings"]["disableAmount"] = False

        client.call("PUT", f"/api/recipes/{slug}", rec)

        # Enlazar pasos
        rec = client.call("GET", f"/api/recipes/{slug}")
        if link_steps(rec):
            client.call("PUT", f"/api/recipes/{slug}", rec)

        # Subir imagen si la hay
        if req.image_file:
            img_path = IMAGES_DIR / req.image_file
            if img_path.exists():
                client.upload_image(slug, img_path.read_bytes(), ext=img_path.suffix.lstrip("."))

        web_url = f"{client.url}/g/{group_slug}/r/{slug}"

        # Guardar en historial
        add_to_history({
            "id": slug,
            "slug": slug,
            "title": req.name,
            "mealie_url": web_url,
            "image_url": f"/api/image/{req.image_file}" if req.image_file else None,
            "source": req.source,
            "orgURL": req.orgURL,
            "timestamp": int(time.time()),
        })

        return {
            "success": True,
            "slug": slug,
            "title": req.name,
            "mealie_url": web_url,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error importando a Mealie: {e}")
