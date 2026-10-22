"""Read-only exercise discovery and authenticated pass-through video streaming."""
import re

import httpx
from fastapi import APIRouter, HTTPException, Path, Query, Request
from fastapi.responses import StreamingResponse

from commons import limiter
from src.facts.exercises import API_BASE, api_headers, check_status, normalize_exercise, provider_json, video_path

router = APIRouter(prefix="/api/exercises", tags=["exercises"])


@router.get("")
@limiter.limit("30/minute")
async def search_exercises(request: Request, q: str = Query(..., min_length=2, max_length=100)):
    query = q.strip()
    if len(query) < 2:
        raise HTTPException(422, "Enter at least two characters.")
    data = await provider_json('/search', {"q": query, "limit": 6})
    items = data if isinstance(data, list) else data.get('results', []) if isinstance(data, dict) else []
    if not isinstance(items, list):
        raise HTTPException(502, 'The exercise provider returned invalid search results.')
    results = [normalize_exercise(item) for item in items[:6]]
    return {"results": results, "provider": "MuscleWiki"}


@router.get('/{exercise_id}')
@limiter.limit("30/minute")
async def get_exercise(request: Request, exercise_id: int = Path(..., ge=0)):
    item = await provider_json(f'/exercises/{exercise_id}')
    return normalize_exercise(item)


@router.get('/{exercise_id}/videos/{video_index}')
@limiter.limit("120/minute")
async def stream_video(request: Request, exercise_id: int = Path(..., ge=0), video_index: int = Path(..., ge=0, le=30)):
    item = await provider_json(f'/exercises/{exercise_id}')
    if not isinstance(item, dict) or not isinstance(item.get('videos'), list):
        raise HTTPException(502, 'The exercise provider returned invalid video details.')
    videos = item['videos']
    path = video_path(videos[video_index].get('url')) if video_index < len(videos) and isinstance(videos[video_index], dict) else None
    if not path:
        raise HTTPException(404, "This video is unavailable.")
    headers = api_headers()
    headers['Accept'] = 'video/mp4'
    byte_range = request.headers.get('range')
    if byte_range:
        if not re.fullmatch(r'bytes=(?:\d+-\d*|-\d+)', byte_range):
            raise HTTPException(416, "Unsupported video range.")
        headers['Range'] = byte_range
    client = httpx.AsyncClient(timeout=httpx.Timeout(30, connect=10), follow_redirects=False)
    try:
        upstream = await client.send(client.build_request('GET', API_BASE + path, headers=headers), stream=True)
        if upstream.status_code == 416:
            raise HTTPException(416, "The requested video range is unavailable.")
        check_status(upstream.status_code)
        if upstream.status_code not in (200, 206):
            raise HTTPException(502, "The video provider returned an unexpected response.")
    except (httpx.HTTPError, HTTPException) as exc:
        if 'upstream' in locals():
            await upstream.aclose()
        await client.aclose()
        if isinstance(exc, HTTPException):
            raise
        raise HTTPException(502, "The video provider is temporarily unavailable.") from None

    async def chunks():
        try:
            async for chunk in upstream.aiter_raw():
                yield chunk
        finally:
            await upstream.aclose()
            await client.aclose()

    # Preserve upstream playback/cache semantics; never cache video bytes locally.
    forwarded = {key: value for key, value in upstream.headers.items() if key.lower() in {
        'content-type', 'content-length', 'content-range', 'accept-ranges',
        'cache-control', 'expires', 'etag', 'last-modified', 'content-encoding', 'vary',
    }}
    forwarded.setdefault('cache-control', 'no-store')
    return StreamingResponse(chunks(), status_code=upstream.status_code, headers=forwarded)
