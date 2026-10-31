"""
Daily Learning Facts API routes.

Endpoints:
    GET /api/facts/random?category=food  — generate a random educational fact
    GET /api/facts/categories            — list supported categories
"""

import asyncio
import hmac
import logging
import re
import time
import uuid
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Header, HTTPException, Query, Request, Depends
from fastapi.responses import JSONResponse

from commons import limiter
from configs.config import get_config
from security import safe_error_response, validate_category, require_facts_api_key
from src.database.fact_jobs_repository import (
    create_fact_job,
    get_fact_job,
    update_fact_job,
)
from src.database.facts_repository import (
    get_facts_list,
    get_random_cached_fact,
    get_recent_topic_keys,
    store_fact,
    delete_fact,
    get_fact_by_hash,
    _compute_content_hash,
    start_fact_images,
    set_fact_image_state,
    finish_fact_images,
    claim_country_photo_enrichment,
    finish_country_photo_enrichment,
    set_fact_photo_selection,
)
from src.facts.fact_generator import (
    SUPPORTED_CATEGORIES,
    generate_daily_fact,
)
from src.facts.lifecycle import expected_image_keys, fact_image_keys, image_generation_state
from src.facts.visual_prompts import IMAGE_SECTION_BRIEFS, build_section_image_context
from src.facts.country_photos import find_country_photos, find_subject_photo, country_scene_queries, country_scene_plan
from src.facts.country_media_plan import country_photo_entries
from src.facts.unsplash_photos import track_selection
from src.facts.photo_ranking import select_india_photos,select_country_photos,select_food_photos,select_fashion_photos,select_geography_photos,PhotoRankingUnavailable
from src.facts.image_generator import generate_and_save_image

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["facts"])

cfg = get_config()


# ── Helpers ──────────────────────────────────────────────────────────────


def _has_valid_bypass_key(request: Request) -> bool:
    """
    Check if the request carries a valid X-Facts-Key header
    that bypasses the daily rate limit.

    Uses constant-time comparison to prevent timing attacks.
    """
    provided_key = request.headers.get("X-Facts-Key", "")
    if not provided_key:
        return False
    return hmac.compare_digest(provided_key, cfg.FACTS_API_KEY)


# ── Endpoints ────────────────────────────────────────────────────────────


@router.get("/facts/categories")
@limiter.limit("30/minute")
async def list_categories(request: Request) -> dict:
    """List all supported fact categories with their descriptions."""
    from src.facts.fact_generator import CATEGORY_HINTS

    categories = []
    for key in sorted(CATEGORY_HINTS.keys()):
        categories.append({
            "id": key,
            "name": key.replace("_", " ").title()
        })

    return {
        "success": True,
        "categories": categories,
        "total": len(categories),
    }


async def process_fact_generation_task(
    job_id: str, category: str, blocklist: list
) -> None:
    """Background task to generate a fact and update job state."""
    logger.info("Starting fact generation task for job %s", job_id)
    start_time = time.monotonic()
    
    generation_metadata = {}
    cached = None
    try:
        fact = await asyncio.wait_for(
            generate_daily_fact(category, blocklist, generation_metadata=generation_metadata),
            timeout=cfg.FACT_JOB_TIMEOUT_SECONDS - 5,
        )
        if not fact:
            raise RuntimeError("All generation attempts failed")
    except Exception:
        logger.exception("Fact generation failed for job %s", job_id)
        try:
            cached = get_random_cached_fact(category, include_metadata=True)
            if not cached or not cached.get("full_response"):
                update_fact_job(job_id, "failed", error="Generation failed and no cached facts available.")
                return
            fact = dict(cached["full_response"])
            fact["images"] = cached.get("images") or fact.get("images") or {}
            generation_metadata = cached.get("generation_metadata") or {}
        except Exception:
            logger.exception("Cached fallback failed for job %s", job_id)
            update_fact_job(job_id, "failed", error="Generation failed and cached facts are unavailable.")
            return

    content_hash = cached.get("content_hash") if cached else None
    stored = cached
    image_work=None
    if not cached:
        try:
            content_hash = store_fact(fact, category, generation_metadata=generation_metadata)
            if content_hash:
                keys = fact_image_keys(fact)
                if keys:
                    start_fact_images(content_hash, keys)
                    image_work=(fact["visual_suggestions"],content_hash,fact)
            else:
                # Exact duplicates still reference their existing images and state.
                content_hash = _compute_content_hash(fact["headline_fact"])
            stored = get_fact_by_hash(content_hash)
        except Exception:
            logger.exception("Failed to store fact for job %s", job_id)
    if stored and stored.get("images"):
        fact["images"] = stored["images"]
        fact['image_credits'] = stored.get('image_credits') or {}
        fact['country_photo_galleries'] = stored.get('country_photo_galleries') or {}
        fact['photo_selection']=stored.get('photo_selection') or {}
    image_state = image_generation_state(stored or {"full_response": fact}, cfg.FACT_IMAGE_TIMEOUT_SECONDS)
    fact_response = {
        "success": True,
        "fact": fact,
        "content_hash": content_hash,
        "image_generation": image_state,
        "meta": {
            "source": "cache" if cached else generation_metadata.get("provider", "unknown"),
            "provider": generation_metadata.get("provider"),
            "model": generation_metadata.get("model"),
            "cached": cached is not None,
            "generation_time_ms": int((time.monotonic() - start_time) * 1000),
            "category_requested": category,
        },
    }
    if not update_fact_job(job_id, "completed", fact_data=fact_response):
        logger.error("Job %s could not be marked completed", job_id)
        return
    if image_work:
        visuals,stored_hash,article=image_work
        asyncio.create_task(_background_image_task(visuals,stored_hash,article=article))


async def _background_image_task(visual_suggestions: dict, content_hash: str, existing_images: dict = None, article: dict = None, photos_only: bool = False):
    if existing_images is None:
        existing_images = {}
    images = existing_images.copy()
    is_india = (article or {}).get('article_type') == 'india_lesson'
    is_food = (article or {}).get('article_type') == 'food_lesson'
    is_fashion = (article or {}).get('article_type') == 'fashion_lesson'
    is_geography = (article or {}).get('article_type') == 'geography_lesson'
    is_country = (article or {}).get('article_type') == 'country_profile'
    ranked_country=is_country and (article or {}).get('country_media',{}).get('photo_ranking_version')==1
    country = (article or {}).get('country_profile') if is_country else None
    hybrid = is_country and (article or {}).get('country_media',{}).get('version') == 2
    contextual = hybrid and (article or {}).get('country_media',{}).get('photo_layout') in ('contextual_v1','contextual_v2')
    extended = (article or {}).get('country_media',{}).get('photo_layout') == 'contextual_v2'
    generated_keys = {'cover','overview','how_it_works','explanation_2'}
    claimed = set(images.values())
    previous_photos=[photo for group in (article or {}).get('country_photo_galleries',{}).values() if isinstance(group,list) for photo in group if isinstance(photo,dict)]
    claimed_sources = {p.get('source_url') for p in previous_photos if p.get('source_url')}
    if ranked_country:claimed_sources={p.get('source_url') for p in previous_photos if p.get('subject_kind') and p.get('source_url')}
    if is_india:
        claimed_sources.update(p.get('source_url') for p in (article or {}).get('image_credits',{}).values() if isinstance(p,dict) and p.get('source_url'))
    claimed_photographers = {p.get('author') for p in previous_photos if p.get('provider')=='unsplash'}
    claimed_descriptions = [set(p.get('description','').casefold().split()) for p in previous_photos if p.get('provider')=='unsplash']
    subject_semaphore = asyncio.Semaphore(3)
    scenes = dict(zip(('explanation_3','explanation_4','explanation_5','explanation_6'), country_scene_queries(country))) if contextual else {}
    expanded_scenes = country_scene_plan(country, extended=True) if extended else {}
    scene_semaphore = asyncio.Semaphore(3)
    legacy_scene_counts={}

    async def process_scene(key, query):
        """Documentary photo search only. This function never calls image generation."""
        gallery=list((article or {}).get('country_photo_galleries',{}).get(key,[]))
        if len(gallery)>=2:return
        try:
            async with scene_semaphore:
                candidates=await asyncio.wait_for(find_country_photos(country['identity']['name'],query,scene_only=True,scene_fallback=True),timeout=50)
                for item in candidates:
                    if len(gallery)>=2:break
                    if item['url'] in claimed or item['source_url'] in claimed_sources:continue
                    words=set(item.get('description','').casefold().split())
                    if any(len(words & other)/max(1,len(words | other))>.55 for other in claimed_descriptions):continue
                    # Reserve before yielding so concurrent topics cannot select the same photo.
                    claimed.add(item['url']);claimed_sources.add(item['source_url']);claimed_descriptions.append(words)
                    if item.get('provider')=='unsplash' and not await track_selection(item):continue
                    gallery.append({**{k:v for k,v in item.items() if k!='download_location'},'scene_query':query})
            photo=gallery[0] if gallery else None
            legacy_scene_counts[key]=len(gallery)
            if photo:images[key]=photo['url']
            logger.info('Country scene %s/%s (%s): %d selected',content_hash,key,query,len(gallery))
            set_fact_image_state(content_hash,key,'ready' if photo else 'failed',photo['url'] if photo else None,credit=photo,gallery=gallery)
        except Exception:
            logger.exception('Country scene search failed for %s/%s',content_hash,key)
            if not gallery:set_fact_image_state(content_hash,key,'failed',gallery=[])
    
    async def process_image(key: str, filename: str, prompt: str, aspect_ratio: str, context: str):
        if key in existing_images:
            return
        try:
            if is_country and not (isinstance(country,dict) and country.get('identity',{}).get('name')):
                raise ValueError('Country image job has no validated country identity')
            if is_country and not (hybrid and key in generated_keys):
                people = [p.get('name','') for p in country.get('notable_people',[]) if isinstance(p,dict)]
                candidates = await asyncio.wait_for(find_country_photos(country['identity']['name'], scenes.get(key,prompt), protected_names=people, scene_only=contextual), timeout=35)
                gallery=[]
                for item in candidates:
                    if item['url'] in claimed or item['source_url'] in claimed_sources:continue
                    if hybrid and item.get('author') in claimed_photographers:continue
                    words=set(item.get('description','').casefold().split())
                    if hybrid and any(len(words & other)/max(1,len(words | other))>.55 for other in claimed_descriptions):continue
                    claimed.add(item['url']);claimed_sources.add(item['source_url']);gallery.append(item)
                    if hybrid:
                        claimed_photographers.add(item.get('author'));claimed_descriptions.append(words)
                    if len(gallery)>=(1 if contextual else 2 if hybrid else 6):break
                # Track only selected article assets, never previews or every page render.
                tracked = await asyncio.gather(*(track_selection(item) for item in gallery if item.get('provider')=='unsplash'))
                outcomes = iter(tracked)
                gallery = [item for item in gallery if item.get('provider')!='unsplash' or next(outcomes)]
                gallery = [{k:v for k,v in item.items() if k!='download_location'} for item in gallery]
                if hybrid:
                    gallery = [{**item,'scene_query':scenes.get(key,prompt)} for item in gallery]
                photo = gallery[0] if gallery else None
                if photo:
                    images[key] = photo['url']
                set_fact_image_state(content_hash, key, 'ready' if photo else 'failed', photo['url'] if photo else None, credit=photo, gallery=gallery)
                return
            url = await asyncio.wait_for(
                generate_and_save_image(prompt, filename, aspect_ratio=aspect_ratio, extra_context=context),
                timeout=cfg.FACT_IMAGE_TIMEOUT_SECONDS,
            )
            if url:
                images[key] = url
            if hybrid or is_india or is_food or is_fashion or is_geography:
                detail=next((d for d in (article or {}).get('image_details',[]) if d.get('slot')==key),{})
                subject=(article or {}).get('topic') or (country or {}).get('identity',{}).get('name','the topic')
                credit={'kind':'generated','url':url,'title':detail.get('caption') or f"Illustration of {subject}",
                    'description':detail.get('alt') or f"Generated illustration of {subject}"} if url else None
                set_fact_image_state(content_hash,key,'ready' if url else 'failed',url,credit=credit)
            else:
                set_fact_image_state(content_hash, key, "ready" if url else "failed", url)
        except Exception:
            logger.exception("Image generation failed for %s/%s", content_hash, key)
            set_fact_image_state(content_hash, key, "failed")

    async def process_subject(kind, index, subject, title, queries):
        key=f'country_{kind}_{index}'
        prior=next((p for p in previous_photos if p.get('entry_title')==title and p.get('subject_kind')==kind and p.get('photo_search_version')==2),None)
        if key in existing_images and (not photos_only or prior):return
        try:
            async with subject_semaphore:
                matches=await asyncio.wait_for(find_subject_photo(country['identity']['name'],subject,kind,queries=queries),timeout=25)
            own_sources={p.get('source_url') for p in (article or {}).get('country_photo_galleries',{}).get(key,[]) if isinstance(p,dict)}
            photo=next((p for p in matches if p['source_url'] not in claimed_sources or p['source_url'] in own_sources),None)
            if photo:
                photo={**photo,'entry_title':title,'photo_search_version':2}
                claimed_sources.add(photo['source_url']);images[key]=photo['url']
            set_fact_image_state(content_hash,key,'ready' if photo else 'failed',photo['url'] if photo else None,
                credit=photo,gallery=[photo] if photo else [])
        except Exception:
            logger.exception('Country subject photo failed for %s/%s',content_hash,key)
            set_fact_image_state(content_hash,key,'failed',gallery=[])

    tasks = []
    for key, brief in IMAGE_SECTION_BRIEFS.items():
        if photos_only:continue
        if (is_india or is_food or is_fashion or is_geography) and key not in ('cover','overview'):continue
        if key in expanded_scenes:continue
        if is_country and key not in {'cover','overview','how_it_works','explanation_2','explanation_3','explanation_4','explanation_5','explanation_6'}:
            continue
        prompt = scenes.get(key) or visual_suggestions.get(key)
        if key == "overview":
            prompt = prompt or visual_suggestions.get("history")
        if prompt:
            tasks.append(process_image(
                key, f"{content_hash}_{key}.jpg", prompt, brief["ratio"],
                build_section_image_context(key, article),
            ))

    if is_food or is_fashion or is_geography:
        from src.facts.food import food_photo_entries
        from src.facts.fashion import fashion_photo_entries
        from src.facts.geography import geography_photo_entries
        prefix='geography' if is_geography else 'fashion' if is_fashion else 'food'
        select_photos={'food':select_food_photos,'fashion':select_fashion_photos,'geography':select_geography_photos}[prefix]
        async def process_editorial_photos():
            entries={'food':food_photo_entries,'fashion':fashion_photo_entries,'geography':geography_photo_entries}[prefix](article)
            keys=[p['key'] for p in entries]+[f'{prefix}_scene_{n}' for n in range(6)]
            state={}
            def report(value):
                state.update(value);set_fact_photo_selection(content_hash,dict(state))
            async def finalize():
                selected=await select_photos(article,report=report,excluded=claimed_sources)
                used=set();ready=set();extras=[]
                for p in selected:
                    if p['source_url'] in used:continue
                    if p.get('provider')=='unsplash' and not await track_selection(p):continue
                    used.add(p['source_url'])
                    item=next((entry for entry in entries if entry['id'] in p.get(prefix+'_request_ids',[]) and entry['key'] not in ready),None)
                    photo={**{k:v for k,v in p.items() if k!='download_location'},prefix+'_photo':True,
                        'selection_mode':state.get('mode','text_ranking'),'ranking_model':'gpt-6-luna' if state.get('mode')!='metadata_fallback' else None}
                    if item:
                        photo.update(section_id=item['section_id'],photo_id=item['id']);key=item['key']
                        if is_fashion:photo['feature_id']=item.get('feature_id')
                        if is_geography:photo['location_id']=item.get('location_id')
                    elif len(extras)<6:
                        key=f'{prefix}_scene_{len(extras)}';photo[prefix+'_carousel']=True;extras.append(photo)
                    else:continue
                    ready.add(key);images[key]=photo['url']
                    set_fact_image_state(content_hash,key,'ready',photo['url'],credit=photo)
                for key in keys:
                    if key not in ready:set_fact_image_state(content_hash,key,'not_requested',clear=True)
                report({'status':'completed' if ready else 'insufficient','selected_count':len(ready)})
            try:await asyncio.wait_for(finalize(),timeout=720)
            except Exception as error:
                logger.warning('%s photo selection failed (%s)',prefix,type(error).__name__)
                for key in keys:
                    if key not in images:set_fact_image_state(content_hash,key,'failed')
                report({'status':'insufficient','reason':'photo_lookup_failed'})
        tasks.append(process_editorial_photos())

    if is_india:
        from src.facts.india import india_photo_entries
        async def process_india_photo(item):
            key=item['key']
            if key in existing_images:return
            try:
                async with subject_semaphore:
                    kind={'person':'people','place':'places','object':'products'}.get(item['kind'])
                    if kind:
                        candidates=await asyncio.wait_for(find_subject_photo('India',item['subject'],kind,
                            queries=[item['subject'],item['query']]),timeout=25)
                    else:
                        candidates=await asyncio.wait_for(find_country_photos('India',item['query']),timeout=35)
                        terms={w.casefold() for w in re.findall(r'[^\W_]+',item['query']) if len(w)>=3 and w.casefold() not in ('india','indian','photo','photograph','the','and','for','with')}
                        candidates=[p for p in candidates if terms and any(re.search(r'\b'+re.escape(term)+r'\b',p['title']+' '+p['description'],re.I) for term in terms)]
                    photo=None
                    for candidate in candidates:
                        if candidate['url'] in claimed or candidate.get('source_url') in claimed_sources:continue
                        claimed.add(candidate['url']);claimed_sources.add(candidate.get('source_url'))
                        if candidate.get('provider')=='unsplash' and not await track_selection(candidate):continue
                        photo={**{k:v for k,v in candidate.items() if k!='download_location'},
                            'section_id':item['section_id'],'subject':item['subject'],'photo_id':item['id']}
                        break
                if photo:images[key]=photo['url']
                set_fact_image_state(content_hash,key,'ready' if photo else 'failed',photo['url'] if photo else None,credit=photo)
            except Exception:
                logger.exception('India topic photo failed for %s/%s',content_hash,key)
                set_fact_image_state(content_hash,key,'failed')
        tasks.extend(process_india_photo(item) for item in india_photo_entries(article))

        async def process_india_carousel():
            """Subject-matched documentary carousel. No image-generation fallback."""
            from src.facts.india import india_carousel_queries,india_carousel_keys,india_carousel_matches,india_carousel_searches,india_carousel_per_query,india_carousel_tag_matches,india_carousel_accepted
            from src.facts.unsplash_photos import search
            keys=india_carousel_keys(article)
            per_query=india_carousel_per_query(article)
            retained=set(existing_images)
            for number,key in enumerate(keys):
                if key not in retained:continue
                prior=(article or {}).get('image_credits',{}).get(key) or {}
                queries=india_carousel_queries(article)
                query=queries[min(number//per_query,len(queries)-1)] if queries else ''
                if not india_carousel_accepted(prior,prior.get('scene_query',query),article):
                    retained.discard(key);images.pop(key,None)
                    set_fact_image_state(content_hash,key,'failed',clear=True)
            search_cache={}
            for index,query in enumerate(india_carousel_queries(article)):
                slots=keys[index*per_query:index*per_query+per_query]
                if not slots:break
                if all(key in retained for key in slots):continue
                try:
                    eligible=[]
                    searches=india_carousel_searches(query,article)
                    for phrase in searches:
                        cache_key=phrase.casefold()
                        if cache_key not in search_cache:
                            search_cache[cache_key]=await asyncio.wait_for(search('India',phrase,exact_query=True,
                                match=lambda p:india_carousel_tag_matches(p,phrase,article),popular_fallback=True),timeout=55)
                        candidates=search_cache[cache_key]
                        eligible.extend({**p,'matched_query':phrase} for p in candidates if india_carousel_accepted(p,phrase,article))
                        if len({p['source_url'] for p in eligible if p['source_url'] not in claimed_sources and p['url'] not in claimed})>=per_query:break
                    if len({p['source_url'] for p in eligible if p['source_url'] not in claimed_sources and p['url'] not in claimed})<per_query:
                        candidates=await asyncio.wait_for(find_subject_photo('India',searches[-1],'culture',queries=searches[::-1]),timeout=25)
                        eligible.extend(p for p in candidates if india_carousel_matches(p,p.get('matched_query',searches[-1]),article))
                    for key in slots:
                        if key in retained:continue
                        photo=None
                        for p in eligible:
                            if p['url'] in claimed or p['source_url'] in claimed_sources:continue
                            claimed.add(p['url']);claimed_sources.add(p['source_url'])
                            if p.get('provider')=='unsplash' and not await track_selection(p):continue
                            photo={**{k:v for k,v in p.items() if k!='download_location'},'india_carousel':True,'scene_query':p.get('matched_query',query)}
                            break
                        if photo:images[key]=photo['url']
                        set_fact_image_state(content_hash,key,'ready' if photo else 'failed',photo['url'] if photo else None,credit=photo)
                except Exception:
                    logger.exception('India carousel search failed for %s/%s',content_hash,index)
                    for key in slots:
                        if key not in images:set_fact_image_state(content_hash,key,'failed')
        async def bounded_india_carousel():
            from src.facts.india import india_carousel_keys,india_carousel_queries
            selection_state={}
            def report(state):
                selection_state.update(state)
                set_fact_photo_selection(content_hash,dict(selection_state))
            ranked=(article or {}).get('india_media',{}).get('photo_ranking_version')==1
            try:
                async def finalize():
                    if ranked:
                        report({'status':'collecting','mode':'text_ranking'})
                        try:
                            selected=await select_india_photos(article,report=report,excluded=claimed_sources)
                        except Exception as error:
                            logger.warning('Photo text ranking unavailable; using legacy selection (%s)',type(error).__name__)
                            report({'status':'collecting','mode':'legacy_fallback'})
                            await process_india_carousel()
                            attempted=len(india_carousel_queries(article))*3
                            for key in india_carousel_keys(article)[attempted:]:
                                if key not in images:set_fact_image_state(content_hash,key,'not_requested',clear=True)
                            report({'status':'completed','mode':'legacy_fallback','selected_count':sum(key in images for key in india_carousel_keys(article))})
                            return
                        async def track(photo):
                            async with subject_semaphore:
                                if photo['source_url'] in claimed_sources:return None
                                claimed_sources.add(photo['source_url'])
                                return photo if photo.get('provider')!='unsplash' or await track_selection(photo) else None
                        photos=[p for p in await asyncio.gather(*(track(p) for p in selected)) if p]
                        keys=india_carousel_keys(article)
                        if len(photos)<10:
                            report({'status':'insufficient','mode':'text_ranking','selected_count':len(photos),'minimum':10,
                                'reason':'tracking_failed' if len(selected)>=10 else selection_state.get('reason','not_enough_relevant_metadata')})
                            for key in keys:set_fact_image_state(content_hash,key,'failed',clear=True)
                            return
                        for index,key in enumerate(keys):
                            if index>=len(photos):
                                set_fact_image_state(content_hash,key,'not_requested',clear=True);continue
                            p=photos[index]
                            photo={**{k:v for k,v in p.items() if k!='download_location'},'india_carousel':True,
                                'selection_mode':'llm_ranked','ranking_model':'gpt-6-luna','scene_query':p.get('search_query','')}
                            images[key]=photo['url']
                            set_fact_image_state(content_hash,key,'ready',photo['url'],credit=photo)
                        report({'status':'completed','mode':'text_ranking','selected_count':len(photos)})
                        return
                    await process_india_carousel()
                timeout=720 if ranked else max(1,min(240,cfg.FACT_IMAGE_TIMEOUT_SECONDS-10))
                await asyncio.wait_for(finalize(),timeout=timeout)
            except asyncio.TimeoutError:
                logger.warning('India carousel lookup budget expired for %s',content_hash)
                if ranked:report({'status':'insufficient','mode':'text_ranking','selected_count':0,'minimum':10,'reason':'photo_lookup_timeout'})
                for key in india_carousel_keys(article):
                    if key not in images:set_fact_image_state(content_hash,key,'failed')
        tasks.append(bounded_india_carousel())

    # Scene slots have a separate photo-only path; the GenAI key set stays unchanged.
    async def process_ranked_country():
        keys=[f'country_ranked_{n}' for n in range(18)]
        def report(state):set_fact_photo_selection(content_hash,state)
        async def finalize():
            report({'status':'collecting','mode':'text_ranking'})
            try:
                selected=await select_country_photos(article,report=report,excluded=claimed_sources)
            except Exception as error:
                logger.warning('Country photo text ranking unavailable; using legacy selection (%s)',type(error).__name__)
                report({'status':'collecting','mode':'legacy_fallback'})
                for key in keys:
                    images.pop(key,None)
                    set_fact_image_state(content_hash,key,'not_requested',clear=True,gallery=[])
                await asyncio.gather(*(process_scene(key,query) for key,query in expanded_scenes.items()))
                report({'status':'completed','mode':'legacy_fallback','selected_count':sum(legacy_scene_counts.values())})
                return
            async def track(photo):
                async with scene_semaphore:
                    if photo['source_url'] in claimed_sources:return None
                    claimed_sources.add(photo['source_url'])
                    return photo if await track_selection(photo) else None
            photos=[p for p in await asyncio.gather(*(track(p) for p in selected)) if p]
            if len(photos)<10:
                for key in keys:set_fact_image_state(content_hash,key,'failed',clear=True,gallery=[])
                report({'status':'insufficient','mode':'text_ranking','selected_count':len(photos),'minimum':10})
                return
            for index,key in enumerate(keys):
                if index>=len(photos):
                    set_fact_image_state(content_hash,key,'not_requested',clear=True,gallery=[]);continue
                p=photos[index]
                photo={**{k:v for k,v in p.items() if k!='download_location'},'country_carousel':True,
                    'selection_mode':'llm_ranked','ranking_model':'gpt-6-luna','scene_query':p.get('search_query','')}
                images[key]=photo['url']
                set_fact_image_state(content_hash,key,'ready',photo['url'],credit=photo,gallery=[photo])
            report({'status':'completed','mode':'text_ranking','selected_count':len(photos)})
        try:await asyncio.wait_for(finalize(),timeout=720)
        except asyncio.TimeoutError:
            for key in keys:
                if key not in images:set_fact_image_state(content_hash,key,'failed',gallery=[])
            report({'status':'insufficient','mode':'text_ranking','selected_count':0,'minimum':10})

    if ranked_country:tasks.append(process_ranked_country())
    else:tasks.extend(process_scene(key,query) for key,query in expanded_scenes.items())
    if contextual:
        for item in country_photo_entries(country,extended=extended):
            tasks.append(process_subject(item['kind'],item['index'],item['subject'],item['title'],item['queries']))
    if tasks:
        await asyncio.gather(*tasks)

    if ranked_country:finish_country_photo_enrichment(content_hash)
    if not photos_only:finish_fact_images(content_hash)
    logger.info("Background image generation finished for %s with %d images", content_hash, len(images))



def _country_photo_payload(document):
    fact=document.get('full_response',{})
    state=document.get('country_photo_enrichment') or {}
    status=state.get('status','not_started')
    if state.get('version',0)<4:status='not_started'
    if status=='processing' and state.get('started_at'):
        from datetime import datetime,timezone
        started=state['started_at']
        if started.tzinfo is None:started=started.replace(tzinfo=timezone.utc)
        if (datetime.now(timezone.utc)-started).total_seconds()>900:status='failed'
    if not state and fact.get('country_media',{}).get('photo_layout')=='contextual_v2' and image_generation_state(document,cfg.FACT_IMAGE_TIMEOUT_SECONDS)['status']=='processing':
        status='processing'
    return {'status':status,'country_photo_enrichment':{'version':state.get('version',4),'status':status},
        'photo_selection':document.get('photo_selection') or {},'country_media':fact.get('country_media') or {},
        'images':document.get('images') or fact.get('images') or {},
        'image_credits':document.get('image_credits') or fact.get('image_credits') or {},
        'country_photo_galleries':document.get('country_photo_galleries') or fact.get('country_photo_galleries') or {}}

def _country_photo_document(content_hash):
    document=get_fact_by_hash(content_hash)
    fact=(document or {}).get('full_response',{})
    if not document or fact.get('article_type')!='country_profile' or not fact.get('country_profile',{}).get('identity',{}).get('name'):
        raise HTTPException(status_code=404,detail='Country article not found')
    return document

@router.get('/facts/{content_hash}/country-photos')
@limiter.limit('60/minute')
async def country_photo_status(request: Request,content_hash: str):
    return _country_photo_payload(_country_photo_document(content_hash))

@router.post('/facts/{content_hash}/country-photos')
@limiter.limit('30/hour')
async def ensure_country_photos(request: Request,content_hash: str,background_tasks: BackgroundTasks):
    document=_country_photo_document(content_hash)
    payload=_country_photo_payload(document)
    if payload['status'] in ('completed','processing'):return payload
    if claim_country_photo_enrichment(content_hash):
        article={**document['full_response'],'country_media':{**document['full_response'].get('country_media',{}),
            'version':2,'photo_layout':'contextual_v2','photo_ranking_version':1,'photo_timeout_seconds':720},
            'country_photo_galleries':document.get('country_photo_galleries') or {}}
        background_tasks.add_task(_background_image_task,{},content_hash,document.get('images') or {},article=article,photos_only=True)
        payload['status']='processing';payload['country_photo_enrichment']={'version':4,'status':'processing'}
        payload['country_media']=article['country_media']
    else:payload=_country_photo_payload(_country_photo_document(content_hash))
    return payload

@router.post("/facts/generate", dependencies=[Depends(require_facts_api_key)])
@limiter.limit("10/day")
async def generate_fact_job(
    request: Request,
    background_tasks: BackgroundTasks,
    category: str = Query(
        ...,
        min_length=1,
        max_length=50,
        description="Fact category (e.g., 'food', 'space', 'indian_politics')",
    ),
) -> dict:
    """
    Start an asynchronous job to generate a random, structured, educational fact.

    Rate limited to 10 requests/day per IP.
    Returns a job_id. Use GET /api/facts/status/{job_id} to poll for completion.
    """
    category = validate_category(category)

    # Fetch dedup blocklist (category-scoped)
    try:
        blocklist = get_recent_topic_keys(category)
    except Exception as exc:
        logger.warning("Failed to fetch blocklist: %s", exc)
        blocklist = []

    # Create job state
    job_id = str(uuid.uuid4())
    create_fact_job(job_id, category)

    # Queue background task
    background_tasks.add_task(process_fact_generation_task, job_id, category, blocklist)

    return {
        "success": True,
        "job_id": job_id,
        "status": "processing",
        "timeout_seconds": cfg.FACT_JOB_TIMEOUT_SECONDS,
        "poll_after_seconds": 4,
        "message": "Fact generation started. Poll /api/facts/status/{job_id} for completion."
    }


@router.get("/facts/status/{job_id}")
async def get_fact_job_status(job_id: str) -> dict:
    """
    Check the status of a fact generation job.
    Returns status: 'processing', 'completed', or 'failed'.
    If 'completed', it includes the fact_data payload.
    Images are generated asynchronously, so we merge them from the
    facts collection on every poll until they arrive.
    """
    job = get_fact_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    response = {
        "success": True,
        "job_id": job_id,
        "status": job["status"],
    }
    
    if job["status"] == "completed":
        fact_data = job["fact_data"]
        # Merge images from the facts collection (they arrive after job completes)
        content_hash = fact_data.get("content_hash") if fact_data else None
        if content_hash:
            stored = get_fact_by_hash(content_hash)
            if stored:
                fact_data["fact"]["images"] = stored.get("images") or {}
                fact_data['fact']['image_credits'] = stored.get('image_credits') or {}
                fact_data['fact']['country_photo_galleries'] = stored.get('country_photo_galleries') or {}
                fact_data['fact']['photo_selection']=stored.get('photo_selection') or {}
                fact_data["image_generation"] = image_generation_state(stored, cfg.FACT_IMAGE_TIMEOUT_SECONDS)
        response["data"] = fact_data
    elif job["status"] == "failed":
        response["error"] = job.get("error", "Unknown error")
        
    return response


@router.get("/facts/history")
async def get_facts_history(
    category: Optional[str] = Query(None, description="Filter by category"),
    limit: int = Query(20, ge=1, le=100, description="Number of facts to return"),
    skip: int = Query(0, ge=0, description="Number of facts to skip (pagination)")
) -> dict:
    """
    Retrieve a list of all previously generated facts, sorted by newest first.
    Includes pagination (limit/skip) and optional category filtering.
    """
    if category:
        # Validate using our existing helper to ensure format is safe
        category = validate_category(category)
        
    facts = get_facts_list(category=category, limit=limit, skip=skip)
    
    return {
        "success": True,
        "count": len(facts),
        "limit": limit,
        "skip": skip,
        "category_filter": category,
        "facts": facts,
    }

@router.delete("/facts/{content_hash}")
async def delete_fact_endpoint(content_hash: str, x_admin_key: str = Header(None)) -> dict:
    """
    Delete a specific fact by its content hash.
    Requires X-Admin-Key header matching the config.
    """
    cfg = get_config()
    if not x_admin_key or x_admin_key != cfg.ADMIN_KEY:
        raise HTTPException(status_code=500, detail="Internal Server Error")

    success = delete_fact(content_hash)
    if not success:
        raise HTTPException(status_code=404, detail="Fact not found")
    return {"status": "success", "message": "Fact deleted"}

@router.post("/facts/{content_hash}/retry-images")
@limiter.limit("10/day")
async def retry_image_generation(
    request: Request,
    background_tasks: BackgroundTasks,
    content_hash: str
) -> dict:
    """
    Retry image generation for a fact, but only if the previous default run failed
    or did not generate all expected images.
    """
    fact_doc = get_fact_by_hash(content_hash)
    if not fact_doc:
        raise HTTPException(status_code=404, detail="Fact not found")
        
    full_response = fact_doc.get("full_response", {})
    visual_suggestions = full_response.get("visual_suggestions", {})
    if not visual_suggestions:
        raise HTTPException(status_code=400, detail="No visual suggestions available for this fact")
        
    existing_images = fact_doc.get("images", {})
    
    expected_keys = fact_image_keys(full_response)
        
    # Check if we have all expected keys
    missing_keys = [k for k in expected_keys if k not in existing_images]
    if full_response.get('article_type')=='india_lesson':
        from src.facts.india import india_carousel_keys,india_carousel_queries,india_carousel_accepted,india_carousel_per_query
        queries=india_carousel_queries(full_response)
        for index,key in enumerate(india_carousel_keys(full_response)):
            credit=(fact_doc.get('image_credits') or {}).get(key) or {}
            query=queries[min(index//india_carousel_per_query(full_response),len(queries)-1)] if queries else ''
            if key in existing_images and not india_carousel_accepted(credit,credit.get('scene_query',query),full_response):
                missing_keys.append(key)
    
    if not missing_keys:
        raise HTTPException(status_code=400, detail="Previous run was successful. All expected images are already generated.")
        
    logger.info("Retrying image generation for %s. Missing keys: %s", content_hash, missing_keys)
    start_fact_images(content_hash, missing_keys)
    retry_article=full_response
    if full_response.get('article_type')=='india_lesson':
        retry_article={**full_response,'image_credits':fact_doc.get('image_credits') or full_response.get('image_credits',{})}
    if full_response.get('country_media',{}).get('photo_layout') in ('contextual_v1','contextual_v2'):
        retry_article={**retry_article,'country_photo_galleries':fact_doc.get('country_photo_galleries') or full_response.get('country_photo_galleries',{})}
    background_tasks.add_task(_background_image_task, visual_suggestions, content_hash, existing_images,article=retry_article)
    
    return {
        "success": True,
        "message": f"Retrying background image generation for missing keys: {missing_keys}"
    }
