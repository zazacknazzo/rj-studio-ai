# 02: Secure and configure the Twilio adapter

**What to build:** The operator can configure the Sandbox webhook through `.env`, and RJ Studio AI accepts authentic Twilio callbacks while rejecting invalid signatures when verification is enabled.

**Blocked by:** 01: Deliver the Sandbox Conversation flow.

**Status:** done

- [x] Runtime configuration loads from `.env` with safe defaults for local development.
- [x] The adapter verifies Twilio signatures against the externally visible webhook URL.
- [x] Invalid signatures return a clear HTTP rejection and do not persist Messages.
- [x] HTTP-level tests cover enabled and disabled verification.
