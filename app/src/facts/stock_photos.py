"""A common candidate pool; provider failures never discard the other source."""
import asyncio
from . import unsplash_photos, pixabay_photos


async def _combined(calls):
    results = await asyncio.gather(*calls, return_exceptions=True)
    seen, photos = set(), []
    for result in results:
        if isinstance(result, BaseException):
            continue
        for photo in result:
            if photo['source_url'] not in seen:
                seen.add(photo['source_url'])
                photos.append(photo)
    return photos


async def ranking_candidates(query):
    return await _combined([unsplash_photos.ranking_candidates(query), pixabay_photos.ranking_candidates(query)])


async def search(country, query, **kwargs):
    return await _combined([unsplash_photos.search(country, query, **kwargs),
                            pixabay_photos.search(country, query, **kwargs)])
