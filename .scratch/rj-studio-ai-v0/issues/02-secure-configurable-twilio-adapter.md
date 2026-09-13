# 02: Secure and configure the Twilio adapter

**What to build:** The operator can configure the Sandbox webhook through `.env`, and RJ Studio AI accepts authentic Twilio callbacks while rejecting invalid signatures when verification is enabled.

**Blocked by:** 01: Deliver the Sandbox Conversation flow.

**Status:** ready-for-agent

- [ ] Runtime configuration loads from `.env` with safe defaults for local development.
- [ ] The adapter verifies Twilio signatures against the externally visible webhook URL.
- [ ] Invalid signatures return a clear HTTP rejection and do not persist Messages.
- [ ] HTTP-level tests cover enabled and disabled verification.
