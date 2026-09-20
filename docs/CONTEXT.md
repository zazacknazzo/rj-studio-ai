# RJ Studio AI Domain Language

RJ Studio AI manages the relationship between RJ Studio and its Customers, from the first WhatsApp Message through service completion and revenue attribution.

## Customer relationship

**Customer**:
A person who contacts or receives service from RJ Studio.
_Avoid_: User, account, contact

**Lead**:
A Customer's active commercial opportunity with RJ Studio.
_Avoid_: Prospect, contact

**Conversation**:
The continuing exchange between RJ Studio and one Customer under one channel identity. Cross-provider identity is not implied.
_Avoid_: Chat, thread, session

**Message**:
One inbound or outbound communication within a Conversation.
_Avoid_: Event, payload

**Intent**:
The Customer's current purpose in a Message or Conversation, such as asking a question or seeking an Appointment.
_Avoid_: Command, category

**Critical Factual Claim**:
A proposed customer-visible value about price, hours, a Service, a Professional, policy, or availability. It becomes trusted only after deterministic validation against approved Salon Knowledge or an integration result.
_Avoid_: Verified fact, model fact

**Uncertainty**:
The AI Attendant's categorical proposal about whether a response has enough information. It does not replace deterministic factual or Human Handoff policy.
_Avoid_: Confidence score

**Human Handoff**:
The transfer of responsibility for a Conversation from automation to an RJ Studio team member.
_Avoid_: Escalation, takeover

**AI Attendant**:
The automation that converses on behalf of RJ Studio within approved facts and policies. Lívia is the AI Attendant used in V1.
_Avoid_: Bot, agent, assistant

**AI Reply**:
An outbound Message produced by the AI Attendant in response to an inbound Message.
_Avoid_: Automatic Reply, generated output

## Salon operations

**Service**:
A beauty treatment offered by RJ Studio.
_Avoid_: Product, procedure

**Professional**:
An RJ Studio team member qualified to perform one or more Services.
_Avoid_: Provider, employee

**Appointment**:
A reserved time for a Customer to receive one or more planned Services at RJ Studio.
_Avoid_: Booking, schedule

**Completed Service**:
A Service occurrence that RJ Studio actually delivered to a Customer.
_Avoid_: Finished appointment

**Salon Knowledge**:
Approved facts about RJ Studio, including Services, Professionals, hours, prices, policies, and care guidance.
_Avoid_: Prompt context, knowledge base

**Operational/Commercial Fact**:
Salon Knowledge about prices, hours, policies, promotions, location, channels, or operating rules. The project owner gives final approval for publication.
_Avoid_: Technical guidance, prompt rule

**Technical Fact**:
Salon Knowledge about hair, chemistry, treatments, eyebrows, or mega hair that requires appropriate professional validation before publication.
_Avoid_: Model knowledge, general advice

## Commercial behavior

**Next Best Action**:
The most appropriate next commercial or support step for a Lead, based on current evidence and policy.
_Avoid_: Recommendation, automation step

**Lead Stage**:
The Lead's current position in the commercial journey.
_Avoid_: Status, funnel column

**Lead Source**:
The attributable origin of a Lead, such as a campaign, referral, or direct contact.

**Automatic Reply**:
The fixed response returned by V0 after an accepted inbound Message.
_Avoid_: AI response, bot response

## Platform

**WhatsApp Provider**:
The external system that carries WhatsApp Messages between RJ Studio AI and Customers.
_Avoid_: Gateway, vendor

**Tenant**:
A future independently configured business using the V7 SaaS platform. RJ Studio is the only business before V7.
_Avoid_: Customer, account, workspace
