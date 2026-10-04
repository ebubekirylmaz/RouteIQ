import logging

from routeiq.integrations.base import record_from_row

logger = logging.getLogger(__name__)


def deliver(store, target, request_id):
    row = store.get(request_id)
    try:
        target.send(record_from_row(row))
    except Exception as e:
        logger.warning("delivery of request %s failed: %s", request_id, e)
        store.mark_delivery(request_id, "failed", str(e))
    else:
        store.mark_delivery(request_id, "sent")