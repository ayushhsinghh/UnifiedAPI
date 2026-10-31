"""Durable MongoDB queue with expiring, fenced leases for Gemini translation."""
from datetime import datetime, timedelta
from uuid import uuid4

from pymongo import ReturnDocument
from configs.config import get_config
from src.database.connection import get_db

ENGINE = 'gemini_translate'


class LeaseLost(Exception):
    pass


class JobCancelled(Exception):
    pass


def collection():
    return get_db()[get_config().JOBS_COLLECTION]


def enqueue(job_id, email, data):
    now = datetime.utcnow()
    doc = dict(data, job_id=job_id, user_email=email, engine=ENGINE, status='pending',
               stage='queued', sections=[], processed_duration_seconds=0,
               progress_percentage=0, completed_segments=0, total_segments=0,
               artifacts={}, warnings=[], error=None, cancel_requested=False,
               delete_requested=False, created_at=now, updated_at=now)
    collection().insert_one(doc)
    return doc


def claim():
    now = datetime.utcnow()
    return collection().find_one_and_update(
        {'engine': ENGINE, '$or': [{'status': 'pending'},
         {'status': 'running', 'lease_until': {'$lte': now}}]},
        {'$set': {'status': 'running', 'lease_token': uuid4().hex,
                  'lease_until': now + timedelta(seconds=get_config().GEMINI_TRANSLATION_LEASE_SECONDS),
                  'updated_at': now}}, sort=[('created_at', 1)], return_document=ReturnDocument.AFTER)


def lease_filter(job_id, token, allow_cancel=False):
    query = {'job_id': job_id, 'engine': ENGINE, 'status': 'running',
             'lease_token': token, 'lease_until': {'$gt': datetime.utcnow()}}
    if not allow_cancel:
        query['cancel_requested'] = False
    return query


def check(job_id, token):
    doc = collection().find_one(lease_filter(job_id, token, allow_cancel=True))
    if not doc:
        raise LeaseLost('Worker lease expired or changed.')
    if doc.get('cancel_requested'):
        raise JobCancelled('Job cancelled.')
    return doc


def heartbeat(job_id, token):
    result = collection().update_one(lease_filter(job_id, token, allow_cancel=True), {'$set': {
        'lease_until': datetime.utcnow() + timedelta(seconds=get_config().GEMINI_TRANSLATION_LEASE_SECONDS),
        'updated_at': datetime.utcnow()}})
    if not result.matched_count:
        raise LeaseLost('Worker lease expired or changed.')


def update(job_id, token, **fields):
    fields['updated_at'] = datetime.utcnow()
    if not collection().update_one(lease_filter(job_id, token), {'$set': fields}).matched_count:
        check(job_id, token)
        raise LeaseLost('Worker cannot update this job.')


def checkpoint(job_id, token, section, total_samples):
    query = lease_filter(job_id, token)
    query['sections'] = {'$size': section['index']}
    processed = section['end_sample'] / 16000
    result = collection().update_one(query, {'$push': {'sections': section}, '$set': {
        'completed_segments': section['index'] + 1, 'processed_duration_seconds': processed,
        'progress_percentage': min(99, int(section['end_sample'] / total_samples * 100)),
        'updated_at': datetime.utcnow()}})
    if not result.matched_count:
        check(job_id, token)
        raise LeaseLost('Checkpoint order changed.')


def finish_cancel(job_id, token):
    return collection().find_one_and_update(lease_filter(job_id, token, allow_cancel=True),
        {'$set': {'status': 'cancelled', 'stage': 'cancelled', 'updated_at': datetime.utcnow()}},
        return_document=ReturnDocument.AFTER)


def request_cancel(job_id, email, delete=False):
    # Keep a leased job running until its worker has actually stopped.
    return collection().find_one_and_update(
        {'job_id': job_id, 'user_email': email, 'engine': ENGINE},
        [{'$set': {'cancel_requested': True, 'delete_requested': delete, 'updated_at': datetime.utcnow(),
                   'status': {'$cond': [{'$eq': ['$status', 'running']}, 'running', 'cancelled']},
                   'stage': {'$cond': [{'$eq': ['$status', 'running']}, '$stage', 'cancelled']}}}],
        return_document=ReturnDocument.AFTER)



def retry(job_id, email):
    return collection().find_one_and_update({'job_id': job_id, 'user_email': email, 'engine': ENGINE,
        'status': {'$in': ['failed', 'cancelled']}, 'delete_requested': False}, {'$set': {
        'status': 'pending', 'stage': 'queued', 'cancel_requested': False, 'error': None,
        'updated_at': datetime.utcnow()}}, return_document=ReturnDocument.AFTER)


def public_job(job):
    """No filesystem paths, lease tokens, or provider credentials in public payloads."""
    keys = ('job_id', 'engine', 'status', 'stage', 'original_filename', 'progress_percentage',
            'completed_segments', 'total_segments', 'language', 'detected_language', 'translate',
            'model', 'target_language', 'generate_subtitles', 'source_duration_seconds',
            'processed_duration_seconds', 'warnings', 'error', 'created_at', 'updated_at', 'cancel_requested')
    result = {key: job[key] for key in keys if key in job}
    result['artifacts'] = {key: bool(value) for key, value in job.get('artifacts', {}).items()}
    return result
