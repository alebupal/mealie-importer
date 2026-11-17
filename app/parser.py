import re
from pathlib import Path
from .mealie_client import (
    key,
    strip_acc,
    unit_canon,
    UNIT_SYN,
)

EMOJI_PATTERN = re.compile(
    r"[\U00010000-\U0010ffff]|[\u2600-\u27ff]|[\u2300-\u23ff]|[\u2b50-\u2b55]|[\ufe0f]",
    flags=re.UNICODE,
)

UNIT_PATTERN = (
    r"(?:g|gr|grs|gramos?|kg|kilos?|mg|ml|cl|l|litros?|cda|cdas|cucharadas?|"
    r"cdta|cdtas|cucharaditas?|pizca|pellizco|taza|tazas|vaso|vasos|sobre|sobres|"
    r"hoja|hojas|chorrito|puñado|diente|dientes|rama|ramas|lata|latas|ud|uds|unidades?|piezas?)"
)

TIME_RE = re.compile(
    r"(\d+(?:[.,]\d+)?)(?:\s*(?:-|–|a|o)\s*(\d+(?:[.,]\d+)?))?\s*(minutos|minuto|min\b|horas|hora|h\b)",
    re.I,
)


def clean_emojis(text: str) -> str:
    return EMOJI_PATTERN.sub("", text).strip()


def bake_time(steps):
    for st in steps:
        text = st.get("text") or ""
        for sent in re.split(r"(?<=[.!?])\s+", text):
            for hm in re.finditer(r"\bhorne\w*|\bal horno\b", sent, re.I):
                tail = sent[hm.end():hm.end() + 90]
                mt = TIME_RE.search(tail)
                if not mt or re.search(r"repos|nevera|congel|enfri|frigor|templ", tail[:mt.start()].lower()):
                    continue
                a, b, u = mt.group(1), mt.group(2), mt.group(3).lower()
                unit = "minutos" if u.startswith("min") else ("hora" if a == "1" and not b else "horas")
                return f"{a}-{b} {unit}" if b else f"{a} {unit}"
    return None


def deduce_category(title: str, text: str):
    lower = f"{title} {text}".lower()
    title_lower = title.lower()
    cats = []

    # Prioridad si el título especifica el tipo de elaboración
    if any(k in title_lower for k in ["cookie", "galleta", "brookie", "crookie"]):
        cats.append("Cookies")
    elif any(k in title_lower for k in ["dónut", "donut", "berlina", "croissant", "brioche", "cinnamon roll", "bollo"]):
        cats.append("Bollería")
    elif "cheesecake" in lower or "tarta de queso" in lower:
        cats.append("Cheesecakes")
    elif "cookie" in lower or "galleta" in lower or "brookie" in lower or "crookie" in lower:
        cats.append("Cookies")
    elif any(k in lower for k in ["dónut", "donut", "berlina", "croissant", "brioche", "cinnamon roll", "bollo"]):
        cats.append("Bollería")
    elif "brownie" in lower:
        cats.append("Brownies")
    elif "tarta" in lower or "cake" in lower or "pastel" in lower:
        cats.append("Tartas y pasteles")
    elif "bizcocho" in lower or "muffin" in lower or "magdalena" in lower:
        cats.append("Bizcochos")
    elif "pan" in lower:
        cats.append("Panadería")
    else:
        cats.append("Postres")

    # Detección de relleno para cookies, bollería o recetas explícitas
    is_filled = False
    if "rellen" in title_lower:
        is_filled = True
    elif "Cookies" in cats or "Bollería" in cats:
        if any(k in lower for k in [
            "rellen",
            "para el relleno",
            "corazón de",
            "núcleo de",
            "bola congelada",
            "disco congelado",
            "congelar el relleno",
            "meter en el centro",
            "cerrar la bola",
        ]):
            is_filled = True

    if is_filled and "Rellenas" not in cats:
        cats.append("Rellenas")

    return cats


def parse_recipe_from_info(info: dict) -> dict:
    text = info.get("description", "").strip()
    url = info.get("url", "")
    author = info.get("author", "").strip()
    platform = info.get("platform", "video")

    lines = [l.strip() for l in text.splitlines() if l.strip()]
    if not lines:
        raw_title = info.get("title", "Receta de vídeo")
        lines = [raw_title]

    raw_title = lines[0]
    clean_title = clean_emojis(raw_title)
    clean_title = re.sub(
        r"^(?:RECETA|RECET[OÓ]N|NUEVA RECETA)\s*[:|–-]?\s*",
        "",
        clean_title,
        flags=re.I,
    ).strip()
    if not clean_title and len(lines) > 1:
        clean_title = clean_emojis(lines[1])

    if clean_title.isupper():
        clean_title = clean_title.title()

    categories = deduce_category(clean_title, text)

    tags = []
    if author:
        tags.append(author.lower())
    if platform:
        tags.append(platform.lower())
    if "Rellenas" in categories:
        tags.append("rellena")

    recipe = {
        "name": clean_title,
        "description": "",
        "yield": "1 molde" if "molde" in text.lower() else "1 unidad",
        "prepTime": None,
        "cookTime": None,
        "totalTime": None,
        "tags": list(dict.fromkeys(tags)),
        "categories": categories,
        "source": f"{platform.capitalize()} — @{author}" if author else platform.capitalize(),
        "orgURL": url,
        "author": author,
        "thumbnail": info.get("thumbnail"),
        "ingredients": [],
        "instructions": [],
        "notes": [],
    }

    current_section = None
    state = "HEADER"

    i = 1
    while i < len(lines):
        line = lines[i]
        line_clean = clean_emojis(line).strip()
        line_lower = line_clean.lower()

        if re.match(r"^ingredientes\b", line_lower):
            state = "INGREDIENTS"
            i += 1
            continue

        if re.match(
            r"^(?:elaboraci[oó]n|preparaci[oó]n|pasos|paso a paso|instrucciones|procedimiento|modo de empleo)\b",
            line_lower,
        ):
            state = "INSTRUCTIONS"
            current_section = None
            i += 1
            continue

        if re.search(
            r"\b(?:pregunta importante|sois m[aá]s de|si te ha gustado|comparte|etiqueta|gu[aá]rdate|s[ií]gueme|deja tu comentario)\b",
            line_lower,
        ):
            state = "OUTRO"
            recipe["notes"].append({"title": "Nota", "text": line})
            i += 1
            continue

        if state == "OUTRO":
            recipe["notes"].append({"title": "Nota", "text": line})
            i += 1
            continue

        sub_sec_match = re.match(
            r"^(?:(?:para\s+(?:el|la|los|las)?\s*|decoraci[oó]n|frosting|cobertura|relleno|base|masa)\b.*)[:]?$",
            line_clean,
            re.I,
        )
        if sub_sec_match or (
            line_clean.isupper()
            and len(line_clean.split()) <= 4
            and any(w in line_clean for w in ["FROSTING", "BASE", "RELLENO", "COBERTURA", "CREMA"])
        ):
            sec_name = line_clean.rstrip(":").strip()
            sec_name = re.sub(r"^Para\s+(?:el|la|los|las)?\s*", "", sec_name, flags=re.I).strip().capitalize()
            current_section = sec_name
            i += 1
            continue

        is_bullet = bool(re.match(r"^[\*\-•▪▫]\s*", line))
        raw_item = re.sub(r"^[\*\-•▪▫]\s*", "", line).strip()
        step_num_match = re.match(r"^(\d+)[\.\-\)]\s*(.*)", line)

        if step_num_match:
            recipe["instructions"].append(
                {"title": None, "text": step_num_match.group(2).strip()}
            )
            i += 1
            continue

        if is_bullet or (state == "INGREDIENTS" and re.match(r"^\d", raw_item)):
            raw_item = re.sub(r"@maizena(?:_es)?\b", "maicena", raw_item, flags=re.I)
            raw_item = re.sub(r"@\w+\s*", "", raw_item)

            note = ""
            note_match = re.search(r"\((.*?)\)", raw_item)
            if note_match:
                note = note_match.group(1).strip()
                raw_clean = re.sub(r"\(.*?\)", "", raw_item).strip()
            else:
                raw_clean = raw_item

            qty = None
            unit = None
            food = raw_clean

            m_qty = re.match(r"^(\d+(?:[.,]\d+)?|\d+\s*/\s*\d+)\s*(.*)", raw_clean)
            if m_qty:
                q_str, rest = m_qty.group(1), m_qty.group(2).strip()
                if "/" in q_str:
                    num, den = q_str.split("/")
                    qty = float(num.strip()) / float(den.strip())
                else:
                    qty = float(q_str.replace(",", "."))

                m_unit = re.match(r"^(" + UNIT_PATTERN + r")\b\s*(?:de\s+|del\s+)?(.*)", rest, re.I)
                if m_unit:
                    unit = m_unit.group(1).lower()
                    food = m_unit.group(2).strip()
                else:
                    food = re.sub(r"^(?:de|del)\s+", "", rest).strip()

            if "rallada" in food.lower():
                food = re.sub(r"\brallad[ao]s?\b", "", food, flags=re.I).strip()
                note = f"{note}, rallada".strip(", ")
            if "picadas" in food.lower() or "picada" in food.lower():
                food = re.sub(r"\bpicad[ao]s?\b", "", food, flags=re.I).strip()
                note = f"{note}, picada".strip(", ")
            if "en polvo" in food.lower() and not any(k in food.lower() for k in ["canela", "matcha"]):
                food = re.sub(r"\ben polvo\b", "", food, flags=re.I).strip()
                note = f"{note}, en polvo".strip(", ")

            recipe["ingredients"].append(
                {
                    "section": current_section,
                    "quantity": qty,
                    "unit": unit,
                    "food": food,
                    "note": note,
                    "original": line.strip("* -•"),
                }
            )
            i += 1
            continue

        if state in ("INSTRUCTIONS", "HEADER") or current_section:
            step_title = current_section if state != "INSTRUCTIONS" else None
            recipe["instructions"].append({"title": step_title, "text": line})
            i += 1
            continue

        i += 1

    recipe["cookTime"] = bake_time(recipe["instructions"])
    return recipe


def analyze_with_mealie(recipe: dict, foods: list, units: list, synonyms: dict) -> dict:
    """Cruza los ingredientes de la receta con lo que hay en Mealie y genera preguntas/dudas."""
    # Indexar alimentos de Mealie
    fidx = {}
    for f in foods:
        names = [f.get("name"), f.get("pluralName")]
        names += [a.get("name") for a in (f.get("aliases") or [])]
        for n in names:
            if n and key(n):
                fidx.setdefault(key(n), f)

    # Indexar unidades
    uidx = {}
    for u in units:
        names = [u.get("name"), u.get("pluralName"), u.get("abbreviation"), u.get("pluralAbbreviation")]
        names += [a.get("name") for a in (u.get("aliases") or [])]
        for n in names:
            if n and key(n):
                uidx.setdefault(key(n), u)

    syn = {key(k): v for k, v in synonyms.items()}

    questions = []
    enriched_ingredients = []

    for ing in recipe.get("ingredients", []):
        raw_food = (ing.get("food") or "").strip()
        raw_unit = (ing.get("unit") or "").strip()
        k_food = key(raw_food)

        # 1. Resolver unidad
        canon_u = unit_canon(raw_unit) if raw_unit else ""
        matched_unit = None
        if canon_u:
            for s in UNIT_SYN.get(canon_u, [canon_u]):
                matched_unit = matched_unit or uidx.get(key(s))
            if not matched_unit:
                questions.append({
                    "id": f"unit_{k_food}",
                    "type": "new_unit",
                    "title": f"Unidad no encontrada: '{raw_unit}'",
                    "description": f"La unidad '{raw_unit}' se creará como nueva en Mealie.",
                    "item": raw_food,
                    "unit": raw_unit,
                })

        # 2. Resolver alimento
        target_name = syn.get(k_food, raw_food)
        matched_food = fidx.get(key(target_name)) or fidx.get(k_food)

        similar_candidates = []
        if not matched_food:
            for ek, f in fidx.items():
                if ek and ek != k_food and (ek in k_food or k_food in ek):
                    if f["name"] not in similar_candidates:
                        similar_candidates.append(f["name"])

        status = "matched"
        suggested_name = matched_food["name"] if matched_food else raw_food

        if matched_food:
            status = "matched"
        elif similar_candidates:
            status = "similar"
            questions.append({
                "id": f"similar_{k_food}",
                "type": "similar_food",
                "title": f"¿Asignar '{raw_food}' a un alimento existente?",
                "description": f"Se parece a: {', '.join(similar_candidates[:3])}",
                "ingredient": raw_food,
                "candidates": similar_candidates[:4],
                "recommended": similar_candidates[0],
            })
        else:
            status = "new"
            questions.append({
                "id": f"new_{k_food}",
                "type": "new_food",
                "title": f"Nuevo alimento: '{raw_food}'",
                "description": f"No se encontró coincidencia en Mealie. Se creará como alimento nuevo si no seleccionas otro.",
                "ingredient": raw_food,
            })

        enriched_ingredients.append({
            "section": ing.get("section"),
            "quantity": ing.get("quantity"),
            "unit": canon_u or raw_unit or None,
            "unit_name": matched_unit["name"] if matched_unit else raw_unit or None,
            "food": suggested_name,
            "raw_food": raw_food,
            "note": ing.get("note") or "",
            "original": ing.get("original") or "",
            "status": status,
            "matched_food_id": matched_food["id"] if matched_food else None,
            "similar_candidates": similar_candidates[:4],
        })

    return {
        "recipe": {
            **recipe,
            "ingredients": enriched_ingredients,
        },
        "questions": questions,
    }
