import json
import os
import re
import subprocess
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
BIN_YTDLP = HERE / "bin" / "yt-dlp"

EMOJI_PATTERN = re.compile(
    r"[\U00010000-\U0010ffff]|[\u2600-\u27ff]|[\u2300-\u23ff]|[\u2b50-\u2b55]|[\ufe0f]",
    flags=re.UNICODE,
)


def get_ytdlp_cmd():
    if BIN_YTDLP.exists() and os.access(BIN_YTDLP, os.X_OK):
        return str(BIN_YTDLP)
    cmd = subprocess.run(["which", "yt-dlp"], capture_output=True, text=True)
    if cmd.returncode == 0 and cmd.stdout.strip():
        return cmd.stdout.strip()
    return None


def clean_emojis(text: str) -> str:
    return EMOJI_PATTERN.sub("", text).strip()


def extract_tiktok(url: str) -> dict:
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            ),
            "Accept-Language": "es-ES,es;q=0.9",
        },
    )
    html = None
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            html = resp.read().decode("utf-8", errors="replace")
    except Exception:
        pass

    if html:
        # 1. __UNIVERSAL_DATA_FOR_REHYDRATION__
        m_json = re.search(
            r"<script[^>]*id=[\"\']__UNIVERSAL_DATA_FOR_REHYDRATION__[\"\'][^>]*>(.*?)</script>",
            html,
            re.DOTALL,
        )
        if m_json:
            try:
                data = json.loads(m_json.group(1))
                item = (
                    data.get("__DEFAULT_SCOPE__", {})
                    .get("webapp.video-detail", {})
                    .get("itemInfo", {})
                    .get("itemStruct", {})
                )
                if item:
                    contents = [
                        c.get("desc", "").strip()
                        for c in item.get("contents", [])
                        if c.get("desc", "").strip()
                    ]
                    desc = "\n".join(contents) if contents else item.get("desc", "")
                    cover = (
                        item.get("video", {}).get("cover")
                        or item.get("video", {}).get("originCover")
                        or item.get("video", {}).get("dynamicCover")
                    )
                    author = (
                        item.get("author", {}).get("uniqueId")
                        or item.get("author", {}).get("nickname")
                        or "tiktok"
                    )
                    title = contents[0] if contents else item.get("desc", "").split("\n")[0]
                    return {
                        "platform": "tiktok",
                        "url": url,
                        "description": desc,
                        "thumbnail": cover,
                        "author": author,
                        "title": title or "Receta TikTok",
                    }
            except Exception:
                pass

    # 2. Fallback yt-dlp
    ytdlp = get_ytdlp_cmd()
    if ytdlp:
        res = subprocess.run(
            [ytdlp, "--dump-json", "--no-warnings", url],
            capture_output=True,
            text=True,
        )
        if res.returncode == 0 and res.stdout.strip():
            d = json.loads(res.stdout.strip())
            return {
                "platform": "tiktok",
                "url": url,
                "description": d.get("description", ""),
                "thumbnail": d.get("thumbnail"),
                "author": d.get("uploader") or d.get("uploader_id") or "tiktok",
                "title": d.get("title") or "Receta TikTok",
            }

    raise RuntimeError(f"No se pudieron extraer datos del vídeo de TikTok: {url}")


def extract_instagram(url: str) -> dict:
    ytdlp = get_ytdlp_cmd()
    if ytdlp:
        res = subprocess.run(
            [ytdlp, "--dump-json", "--no-warnings", url],
            capture_output=True,
            text=True,
        )
        if res.returncode == 0 and res.stdout.strip():
            d = json.loads(res.stdout.strip())
            uploader = d.get("uploader") or d.get("channel") or ""
            if not uploader:
                m_user = re.search(r"instagram\.com/([^/]+)/", url)
                if m_user and m_user.group(1) not in ("p", "reel", "reels"):
                    uploader = m_user.group(1)
            return {
                "platform": "instagram",
                "url": url,
                "description": d.get("description", ""),
                "thumbnail": d.get("thumbnail"),
                "author": uploader or "instagram",
                "title": d.get("title") or "Receta Instagram",
            }

    # Fallback embed
    shortcode_match = re.search(r"/(?:p|reel|reels)/([A-Za-z0-9_-]+)", url)
    if shortcode_match:
        embed_url = f"https://www.instagram.com/p/{shortcode_match.group(1)}/embed/captioned/"
        req = urllib.request.Request(embed_url, headers={"User-Agent": "Mozilla/5.0"})
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                html = resp.read().decode("utf-8", errors="replace")
                m_cap = re.search(r'<div class="Caption"[^>]*>(.*?)</div>', html, re.DOTALL)
                caption = re.sub(r"<[^>]+>", "", m_cap.group(1)).strip() if m_cap else ""
                m_img = re.search(r'<img class="EmbeddedMediaImage"[^>]*src="([^"]+)"', html)
                img = m_img.group(1).replace("&amp;", "&") if m_img else None
                m_auth = re.search(r'<a class="UsernameText"[^>]*>([^<]+)</a>', html)
                author = m_auth.group(1).strip() if m_auth else "instagram"
                if caption:
                    return {
                        "platform": "instagram",
                        "url": url,
                        "description": caption,
                        "thumbnail": img,
                        "author": author,
                        "title": caption.split("\n")[0],
                    }
        except Exception:
            pass

    raise RuntimeError(f"No se pudieron extraer datos de Instagram: {url}")


def extract_youtube(url: str) -> dict:
    ytdlp = get_ytdlp_cmd()
    if not ytdlp:
        raise RuntimeError("yt-dlp no está disponible para extraer de YouTube")

    res = subprocess.run(
        [ytdlp, "--dump-json", "--no-warnings", url],
        capture_output=True,
        text=True,
    )
    if res.returncode == 0 and res.stdout.strip():
        d = json.loads(res.stdout.strip())
        uploader = d.get("uploader") or d.get("channel") or d.get("uploader_id") or "youtube"
        # Obtener mejor thumbnail
        thumbnails = d.get("thumbnails") or []
        thumb = d.get("thumbnail")
        if thumbnails:
            thumb = thumbnails[-1].get("url") or thumb

        return {
            "platform": "youtube",
            "url": url,
            "description": d.get("description", ""),
            "thumbnail": thumb,
            "author": uploader,
            "title": d.get("title") or "Receta YouTube Shorts",
        }
    raise RuntimeError(f"No se pudieron extraer datos de YouTube: {url}")


def extract_video(url: str) -> dict:
    url_clean = url.split("?")[0].strip()
    if "tiktok.com" in url_clean:
        return extract_tiktok(url)
    elif "instagram.com" in url_clean:
        return extract_instagram(url)
    elif "youtube.com" in url_clean or "youtu.be" in url_clean:
        return extract_youtube(url)
    else:
        ytdlp = get_ytdlp_cmd()
        if ytdlp:
            res = subprocess.run(
                [ytdlp, "--dump-json", "--no-warnings", url],
                capture_output=True,
                text=True,
            )
            if res.returncode == 0 and res.stdout.strip():
                d = json.loads(res.stdout.strip())
                return {
                    "platform": "video",
                    "url": url,
                    "description": d.get("description", ""),
                    "thumbnail": d.get("thumbnail"),
                    "author": d.get("uploader") or "video",
                    "title": d.get("title") or "Receta de vídeo",
                }
        raise ValueError("URL no soportada. Introduce un enlace de TikTok, Instagram o YouTube Shorts.")
