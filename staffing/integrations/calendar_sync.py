"""
Calendar sync extension point (NOT WIRED UP YET).

Today, developer availability is fully manual: a PM (or, once auth is
enforced, an admin approving a DeveloperLeave via
DeveloperLeaveViewSet.approve) is the only source of truth for whether
someone is on leave. There is no live feed from Google Calendar, Outlook,
or any HRIS -- so if someone books time off only on their calendar and
never enters a DeveloperLeave record, the solver will treat them as fully
available.

This module defines the shape a real integration would take, so it can be
plugged in later without redesigning the DeveloperLeave model or the
eligibility/solver code that already consumes it. It deliberately does NOT
ship working OAuth/API calls -- that requires real credentials, a token
storage strategy, and a decision about which calendar provider(s) to
support, which is a product decision, not something to fake here.

Intended usage once implemented:

    from staffing.integrations.calendar_sync import sync_developer_leaves

    class Command(BaseCommand):
        def handle(self, *args, **kwargs):
            for developer in Developer.objects.filter(is_active=True):
                sync_developer_leaves(developer)

and scheduled with `python manage.py sync_calendars` on a cron / Celery
beat job, e.g. every 15-30 minutes.
"""

from dataclasses import dataclass
from datetime import date


@dataclass
class ExternalBusyBlock:
    """One out-of-office / busy period read from an external calendar."""
    start_date: date
    end_date: date
    reason: str
    source: str  # e.g. "google_calendar", "outlook"


def fetch_busy_blocks(developer) -> list[ExternalBusyBlock]:
    """
    Fetch this developer's out-of-office blocks from their connected
    calendar provider.

    Not implemented. Wiring this up for real requires, at minimum:
      1. An OAuth2 flow so each Developer can link their own calendar
         (per-user Google/Microsoft OAuth tokens, not one shared service
         account -- otherwise BenchZero can only see one person's calendar).
      2. A place to store refresh tokens (a new model, e.g.
         DeveloperCalendarCredential), encrypted at rest.
      3. A decision on what counts as "busy" (e.g. only events explicitly
         marked out-of-office / free-busy status, not every meeting).
    """
    raise NotImplementedError(
        "Calendar sync is not implemented. This is an extension point -- "
        "see the module docstring for what's needed before this can be "
        "wired up to a real provider."
    )


def sync_developer_leaves(developer) -> int:
    """
    Pull busy blocks for `developer` and upsert them into DeveloperLeave.

    Design intent for when this is implemented: leaves created this way
    should be auto-approved (is_approved=True, approved_by=None) *only* if
    they come from a verified, per-user OAuth-linked calendar -- since the
    calendar itself is the source of truth in that case, unlike a
    leave record typed in manually by any API caller. They should also be
    tagged (e.g. reason="Synced: <source>") so they're distinguishable
    from manually-entered leave in the UI and admin.

    Returns the number of DeveloperLeave records created or updated.
    """
    fetch_busy_blocks(developer)  # will raise until implemented
    return 0
