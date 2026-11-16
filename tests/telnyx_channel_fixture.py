"""Explicit verified synthetic baseline for pre-lifecycle behavior tests.

No application API grants activation. These isolated SQLite fixtures represent a
previously verified connection, allowing Tickets 07/08 behavior and transitions
to be exercised. New Ticket 09 tests separately require fail-closed defaults.
"""

import sqlite3

from test_telnyx_authentication import ORG, PHONE, PROFILE, WABA


def verified_channel(path, *, channel=PHONE):
    with sqlite3.connect(path) as connection:
        connection.execute(
            "INSERT INTO channel_lifecycle(provider,waba_id,channel_id,organization_id,profile_id,"
            "state,revision,updated_at,verification_evidence) "
            "VALUES ('telnyx',?,?,?,?,'active',0,'2000-01-01T00:00:00+00:00',"
            "'synthetic-test-only')",
            (WABA, channel, ORG, PROFILE),
        )
