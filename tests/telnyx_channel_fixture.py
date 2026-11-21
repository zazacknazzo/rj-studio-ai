"""Explicit verified synthetic baseline for pre-lifecycle behavior tests.

No application API grants activation. These isolated SQLite fixtures represent a
previously verified connection, allowing Tickets 07/08 behavior and transitions
to be exercised. New Ticket 09 tests separately require fail-closed defaults.
"""

import sqlite3
from datetime import timedelta

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


def verified_consent(path, *, customer, now, channel=PHONE):
    """Synthetic prior opt-in only; runtime exposes no consent collection interface."""
    with sqlite3.connect(path) as connection:
        connection.execute(
            "INSERT INTO telnyx_consent(channel_id,customer_address,evidence_ref,"
            "granted_at,expires_at) VALUES (?,?,?,?,?) ON CONFLICT DO NOTHING",
            (
                channel,
                customer,
                "synthetic-opt-in-only",
                (now - timedelta(days=1)).isoformat(),
                (now + timedelta(days=2)).isoformat(),
            ),
        )
