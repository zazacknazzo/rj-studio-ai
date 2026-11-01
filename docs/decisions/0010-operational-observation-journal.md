# Keep operational observations separate from Messages and their effects

Status: accepted for the explicitly authorized Ticket 02 scope.

The Ticket 01 contracts distinguish human activity, edits, revocations and
channel lifecycle from Customer Messages. Store them in side tables, without
creating Conversations, processing work or AI Replies and without rebuilding
existing parent tables. One ingress transaction commits journal observations,
their aliases, and any existing inbound/status work before acknowledgement.

Event identity is provider + scope kind + scope ID + event ID. It is not a
Message identity. Reuse with contradictory evidence is an error, while identical
replay leaves the first receipt unchanged. Namespaced aliases and original
references remain observations; they are not unique global Message mappings.
This preserves out-of-order and ambiguous evidence without guessing associations.
Future effect application must resolve logical duplication with verified identity
and atomically record its own progress; an existing receipt is not proof of pause.

The journal contains no Message bodies or raw provider payloads. Its identifiers
are still private data. Ticket 02 holds operational evidence without expiry,
including beyond the 90-day minimum, until explicit retention/erasure is built
and reviewed before production. Existing raw-Message purge and Conversation
commands do not erase this separate journal. This costs unbounded storage in the
offline stage but avoids silently admitting a replay or dropping unresolved
operational evidence. ADR 0004 continues to govern raw Messages. No production
retention guarantee or anonymization claim follows from this temporary hold.
