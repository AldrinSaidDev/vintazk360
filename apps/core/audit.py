"""
The one way to write an audit entry.

Every feature calls this rather than building ``AuditLog`` rows by hand, so the
trail stays uniform enough to read as a single feed::

    from apps.core.audit import log_action

    log_action(
        request,
        action=AuditLog.Action.CREATED,
        entity=kpi,                 # any model instance
        entity_type='kpi_definition',
        team=kpi.team,
        new_values={'name': kpi.name, 'target_display': kpi.target_display},
    )

Logging must never break the action being logged, so failures are swallowed
after being reported to the normal Django logger.
"""

import logging

from .models import AuditLog

logger = logging.getLogger(__name__)

__all__ = ['log_action', 'client_ip']


def client_ip(request):
    """Best-effort client IP, honouring one layer of proxy.

    Render (like most PaaS) terminates TLS in front of the app, so the direct
    peer address is the proxy — the real client is first in X-Forwarded-For.
    """
    if request is None:
        return None
    forwarded = request.META.get('HTTP_X_FORWARDED_FOR', '')
    if forwarded:
        return forwarded.split(',')[0].strip() or None
    return request.META.get('REMOTE_ADDR') or None


def log_action(
    request=None,
    *,
    action,
    entity_type,
    entity=None,
    entity_id=None,
    entity_name='',
    team=None,
    old_values=None,
    new_values=None,
    user=None,
):
    """Append one row to the audit log and return it (or None if it failed).

    ``entity`` is a convenience: pass a model instance and its pk and ``str()``
    are used for ``entity_id`` / ``entity_name`` unless given explicitly.
    """
    if entity is not None:
        entity_id = entity_id if entity_id is not None else entity.pk
        entity_name = entity_name or str(entity)[:120]

    if user is None and request is not None:
        candidate = getattr(request, 'user', None)
        # AnonymousUser has no pk and cannot be stored as a FK.
        user = candidate if getattr(candidate, 'is_authenticated', False) else None

    try:
        return AuditLog.objects.create(
            user=user,
            team=team,
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            entity_name=entity_name,
            old_values=old_values,
            new_values=new_values,
            ip_address=client_ip(request),
            user_agent=(request.META.get('HTTP_USER_AGENT', '') if request else ''),
        )
    except Exception:  # pragma: no cover - never break the caller
        logger.exception('Failed to write audit log entry (%s %s)', action, entity_type)
        return None
