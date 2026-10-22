"""MuscleWiki adapter. Cache metadata only; never store video bytes or credentials."""
import time
from collections import OrderedDict
from urllib.parse import urlsplit

import httpx
from fastapi import HTTPException

from configs.config import get_config

API_BASE = "https://api.musclewiki.com"
_CACHE = OrderedDict()
_CACHE_SECONDS = 6 * 3600


def api_headers():
    key = get_config().MUSCLEWIKI_API_KEY
    if not key:
        raise HTTPException(503, "Exercise demonstrations are not configured on the server.")
    return {"X-API-Key": key, "Accept": "application/json"}


def check_status(status):
    if status < 400:
        return
    if status == 404:
        raise HTTPException(404, "This exercise or video is unavailable.")
    if status == 429:
        raise HTTPException(429, "Exercise demonstrations have reached their usage limit. Please try later.")
    if status in (401, 403):
        raise HTTPException(503, "Exercise demonstrations are unavailable with the current provider access.")
    raise HTTPException(502, "The exercise provider is temporarily unavailable.")


def video_path(value):
    """Accept only provider-owned branded streams, without query credentials."""
    if not isinstance(value, str):
        return None
    try:
        url = urlsplit(value)
    except ValueError:
        return None
    if url.scheme and url.scheme != "https":
        return None
    if url.netloc and url.netloc != "api.musclewiki.com":
        return None
    if url.query or url.fragment or url.username or url.password:
        return None
    prefix = "/stream/videos/branded/"
    if not url.path.startswith(prefix):
        return None
    filename = url.path[len(prefix):]
    if not filename.endswith('.mp4') or not filename or any(c not in 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_. ' for c in filename):
        return None
    if '..' in filename:
        return None
    return url.path


async def provider_json(path, params=None):
    cache_key = (path, tuple(sorted((params or {}).items())))
    now = time.monotonic()
    cached = _CACHE.get(cache_key)
    if cached and now - cached[0] < _CACHE_SECONDS:
        _CACHE.move_to_end(cache_key)
        return cached[1]
    headers = api_headers()
    try:
        async with httpx.AsyncClient(timeout=15, follow_redirects=False) as client:
            response = await client.get(API_BASE + path, headers=headers, params=params)
        check_status(response.status_code)
        if response.is_redirect:
            raise HTTPException(502, "The exercise provider returned an unexpected redirect.")
        data = response.json()
    except (httpx.HTTPError, ValueError):
        raise HTTPException(502, "The exercise provider is temporarily unavailable.") from None
    _CACHE[cache_key] = (now, data)
    _CACHE.move_to_end(cache_key)
    while len(_CACHE) > 256:
        _CACHE.popitem(last=False)
    return data


def normalize_exercise(item):
    if not isinstance(item, dict) or type(item.get('id')) is not int or not isinstance(item.get('name'), str):
        raise HTTPException(502, "The exercise provider returned an invalid exercise.")
    videos = []
    source_videos = item.get('videos')
    for index, video in enumerate(source_videos if isinstance(source_videos, list) else []):
        if isinstance(video, dict) and video_path(video.get('url')):
            videos.append({"index": index, "angle": video.get('angle') or 'view',
                           "gender": video.get('gender') or '',
                           "path": f"/api/exercises/{item['id']}/videos/{index}"})
    return {"id": item['id'], "name": item['name'],
            "primary_muscles": item.get('primary_muscles') or [],
            "equipment": item.get('category') or '', "difficulty": item.get('difficulty') or '',
            "steps": item.get('steps') or [], "videos": videos, "provider": "MuscleWiki"}
