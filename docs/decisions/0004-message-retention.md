# Retain raw Messages for 90 days with explicit purge

Status: accepted

Keep raw inbound and outbound Message rows for 90 days by default. An operator
may change the period through `MESSAGE_RETENTION_DAYS`.

Deletion occurs only through `rj-studio-maintenance purge-messages` or the
explicit single-Conversation deletion command. Purge removes Messages older
than the cutoff and then removes empty Conversations in one transaction.
Commands report counts without Message bodies or customer addresses.

V0.1 adds no deletion during startup or webhook processing, scheduler, worker,
or public administration endpoint. This is an initial product policy rather
than a complete legal or regulatory program.
