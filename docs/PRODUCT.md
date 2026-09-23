# Product

## Purpose

RJ Studio AI helps RJ Studio turn WhatsApp conversations into trusted customer service, appointments, completed services, and attributable revenue. It should sound natural, protect factual accuracy, improve commercial follow-through, and transfer control to a person when automation is uncertain or inappropriate.

## Initial operating model

V0–V6 are a single-business product for RJ Studio de Beleza. Product decisions may be tailored to the salon, but salon-specific facts, tone, offers, and policies must remain localized so they do not spread through generic orchestration logic.

V7 is a separate product phase that may turn the proven system into a multi-business SaaS platform. Earlier versions preserve a migration path without building tenant routing, tenant administration, generic onboarding, or multi-business configuration.

## Primary actors

- **Customer**: contacts RJ Studio, considers Services, and manages Appointments.
- **RJ Studio team member**: receives Human Handoffs and handles cases automation should not complete.
- **RJ Studio operator**: maintains Salon Knowledge, policies, integrations, and commercial workflows.

## Product principles

- Helpful and human communication comes before automation volume.
- Factual claims must come from approved Salon Knowledge or explicit integration results.
- Uncertainty should produce a clarifying question or Human Handoff, never an invented answer.
- Commercial behavior should be consultative and policy-bound.
- Every version must remain usable as an end-to-end vertical slice.
- Customer data should be collected only when it supports service, sales, scheduling, or attribution.

## Current product

The implemented baseline through V1 Ticket 08 and Messaging Migration 05 handles
Twilio Sandbox callbacks, durable generation claims and outbound delivery,
durable ingress, automatic AI processing, proactive Twilio REST submission,
delivery-status callbacks, Claude or
deterministic generation, approved Salon Knowledge, bounded Conversation
Context, structured Intent decisions, and Lívia persona rules. The legacy
delivery mode remains synchronous for controlled rollback. CRM behavior,
scheduling, multimodal processing, and advertising integration remain absent.

Version scope and status live in `ROADMAP.md`. Detailed acceptance criteria live only in `specs/`.
