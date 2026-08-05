"""
Cloudflare R2 object storage wiring.

R2 is S3-compatible, so it is reached with **boto3** pointed at the account's R2
endpoint (`https://<account-id>.r2.cloudflarestorage.com`). This module is the
single place that knows how to build that client, so feature code can later do::

    from apps.core import storage

    storage.upload_fileobj(f, 'operations/2026/08/attrition-<uuid>.csv')
    url = storage.signed_url('operations/2026/08/attrition-<uuid>.csv')

**Uploaded CSVs live in R2; the database only stores a pointer** — the
`kpi_import_batch.storage_provider / storage_bucket / storage_path` columns in
`db_schema.txt`. That is why this is a plain client rather than a Django
`FileField` storage backend: the schema already models the pointer explicitly.

The bucket must be **private**. Downloads go through a Django view that
re-checks team access and hands back a short-lived signed URL from
``signed_url()`` — a public bucket would make every team's raw performance data
world-readable by URL.

Configuration comes from the ``R2_*`` environment variables (see .env.example).
Nothing here runs at import time or at startup: the client is built lazily on
first use, so unconfigured or unreachable storage can never stop the app from
booting.
"""

from functools import lru_cache

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured

__all__ = [
    'R2NotConfigured',
    'is_configured',
    'bucket_name',
    'get_client',
    'upload_fileobj',
    'signed_url',
    'object_exists',
    'delete_object',
    'reset_clients',
]


class R2NotConfigured(ImproperlyConfigured):
    """Raised when the client is requested but the credentials are missing."""


def is_configured():
    """True when endpoint, bucket and both keys are all present."""
    return bool(settings.R2_ENABLED)


def bucket_name():
    """The bucket every helper in this module reads and writes."""
    return settings.R2_BUCKET


@lru_cache(maxsize=1)
def get_client():
    """
    Return the cached boto3 S3 client pointed at Cloudflare R2.

    Raises ``R2NotConfigured`` if the settings are missing, so callers get a
    clear message instead of a confusing HTTP 403 later.
    """
    if not is_configured():
        raise R2NotConfigured(
            'Cloudflare R2 is not configured. Set R2_ACCOUNT_ID, R2_ACCESS_KEY_ID, '
            'R2_SECRET_ACCESS_KEY and R2_BUCKET in your environment (.env) — '
            'see .env.example.'
        )

    try:
        import boto3
        from botocore.config import Config
    except ImportError as exc:  # pragma: no cover - depends on the environment
        raise ImproperlyConfigured(
            'The `boto3` package is not installed. It is pinned in '
            'requirements/base.txt — rebuild the image with '
            '`docker compose up --build`.'
        ) from exc

    config_kwargs = {
        'signature_version': 's3v4',
        'connect_timeout': settings.R2_TIMEOUT,
        'read_timeout': settings.R2_TIMEOUT,
        'retries': {'max_attempts': 3, 'mode': 'standard'},
    }

    # botocore 1.36+ sends a CRC32 checksum on every upload by default, which
    # some S3-compatible providers reject. Asking for checksums only when the
    # operation requires them keeps R2 happy; older botocore has no such knob.
    try:
        config = Config(
            request_checksum_calculation='when_required',
            response_checksum_validation='when_required',
            **config_kwargs,
        )
    except TypeError:  # pragma: no cover - botocore < 1.36
        config = Config(**config_kwargs)

    return boto3.client(
        's3',
        endpoint_url=settings.R2_ENDPOINT_URL,
        aws_access_key_id=settings.R2_ACCESS_KEY_ID,
        aws_secret_access_key=settings.R2_SECRET_ACCESS_KEY,
        # R2 has no regions; the S3 API still demands the field, and `auto` is
        # what Cloudflare's own examples pass.
        region_name=settings.R2_REGION,
        config=config,
    )


def upload_fileobj(fileobj, key, content_type=None, metadata=None):
    """
    Store an open file object at ``key`` and return the key.

    ``key`` is the object path inside the bucket, e.g.
    ``operations/2026/08/attrition-july-<uuid>.csv`` — the value that goes into
    ``kpi_import_batch.storage_path``.
    """
    extra = {}
    if content_type:
        extra['ContentType'] = content_type
    if metadata:
        extra['Metadata'] = {str(k): str(v) for k, v in metadata.items()}

    get_client().upload_fileobj(fileobj, bucket_name(), key, ExtraArgs=extra or None)
    return key


def signed_url(key, expires_in=None, download_name=None):
    """
    Return a short-lived URL that grants read access to one object.

    The bucket is private, so this is the only way a browser reaches a file.
    ``download_name`` sets the filename the browser saves it as.
    """
    params = {'Bucket': bucket_name(), 'Key': key}
    if download_name:
        params['ResponseContentDisposition'] = f'attachment; filename="{download_name}"'

    return get_client().generate_presigned_url(
        'get_object',
        Params=params,
        ExpiresIn=expires_in or settings.R2_SIGNED_URL_TTL,
    )


def object_exists(key):
    """True when an object is present at ``key``."""
    from botocore.exceptions import ClientError

    try:
        get_client().head_object(Bucket=bucket_name(), Key=key)
    except ClientError as exc:
        if exc.response.get('Error', {}).get('Code') in {'404', 'NoSuchKey', '403'}:
            return False
        raise
    return True


def delete_object(key):
    """Remove one object. Deleting a missing key is not an error in S3."""
    get_client().delete_object(Bucket=bucket_name(), Key=key)


def reset_clients():
    """Drop the cached client — for tests, or after changing settings."""
    get_client.cache_clear()
