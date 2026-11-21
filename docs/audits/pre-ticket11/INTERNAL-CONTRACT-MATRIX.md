# Matriz independente de contratos internos

Baseline: `07c1b7dc150d7eb1776b97d891cd29347adffd37`. Revisão direta por
`architecture_review`, 20/11/2026 (America/Sao_Paulo). Fontes normativas: specs
T01–10 e ADRs 0010–0018. Os tipos em memória não substituem autenticação, escopo
verificado ou transações. “Teste” abaixo identifica evidência inspecionada; a
execução própria de 403 passed/1 skipped está em `ARCHITECTURE-REVIEW.md`.

| Contrato / fronteira | Invariante e identidade | Validação real | Campos opcionais / entrada semanticamente perigosa | Teste e saldo |
| --- | --- | --- | --- | --- |
| ProviderWebhookRequest | Bytes brutos e contexto de transporte antes do parser | Dataclass em `providers/base.py:7–14`; autenticador específico em `providers/telnyx.py` | `headers` é dict mutável e já perde duplicatas da camada HTTP. Body já está carregado. O tipo não prova HTTP válido nem assinatura. | Auth tests para bytes/assinatura e ambiguidades observáveis; raw ASGI/streaming continuam CX-24, não implementados. |
| ProviderEventMetadata | `event_id` distinto do Message ID; origin explícita; timestamps aware | `domain.py:29–57` exige IDs não vazios, enum, awareness e aliases como tupla de MessageReference | Metadata é proveniência fornecida pelo adapter, não evidência criptográfica por si. `message_occurred_at=None` preserva legado, mas não concede janela/resume. | Contract tests de origem/timestamp/immutability; source validada em parser, receipt e policy. |
| ProviderWebhookEvent / batch | Seis categorias; só Customer input gera Message | `classify_provider_event`, `domain.py:241–267`, tipos exatos | Batch dataclass não valida tupla/conteúdo; store valida antes de gravar. Subclasse inbound é recusada pelo classificador e pelo ingresso estrito Telnyx, mas aceita no store genérico. | `test_runtime_never_autoresponds_to_operational_events`; AR-02 reproduz limite interno, P3. |
| InboundMessage / InboundMessageReceived | Provider + logical Message ID; Customer separado do canal; body Customer | `domain.py:60–78`; parser Telnyx valida scope/identidade/texto; `inbound_events.py:10–66` protege replay | Classe base não faz validação própria dos campos; metadata opcional no legado. Chamar store sem seam estrito não comprova autenticação. Identidade é provider+Customer, não identidade cross-provider. | Provider/contracts/messages tests; duas identidades phone/BSUID não são fundidas. |
| MessageReference / aliases | Namespace explícito; alias nunca escolhe Conversation | `domain.py:18–26`; journal guarda conjunto ordenado; `validate_message_scope` | Um alias plausível ou original opaco não é chave canônica. Mesma string em namespaces diferentes não prova mesma pessoa. | `test_distinct_events_sharing_message_original_or_alias_are_preserved`, testes de hidden phone e alias. |
| HumanMessageObserved / MessageEdited / MessageRevoked | Observação sem texto gerador; human echo aplica pausa uma vez por identidade lógica | `domain.py:125–178`, `operational_events.py`, `generation_pause.py` | Origem enum não autentica humano. Novo echo antigo após resume repausa conservadoramente; edit/revoke não cancelam resposta original. | Generation pause/messages tests; ausência/atraso de echo continua CX-02/03. |
| DeliveryStatusReceived / ProviderDeliveryEvidence | Status != acceptance; scope provider/canal/Customer/org/profile e event/Message distintos | `domain.py:89–122`; `delivery_status_events.py:23–154`; parser valida evento/status | Campos de scope opcionais para legado; Telnyx exige metadata/evidence/channel/Customer. `account_id` deste DTO recebe organization_id do payload, não WABA. Não reutilizar como WABA sem adaptação explícita. | `test_early_scope_does_not_admit_arbitrary_canonical_telnyx_status`, ordem/conflito/acceptance tests. |
| ChannelAvailabilityChanged / binding | Lifecycle de conta não identifica Conversation; reconnect não ativa | `domain.py:181–219`, `channel_lifecycle.py:11–94`, migration0020 | DTO representa blocked/verification_required, não active. Binding ausente nega. Estado active do banco exige evidência explícita; nenhum comando de ativação existe. | Lifecycle tests de absence/restart/SQL REPLACE. Proveniência real/epoch futuros CX-11/33. |
| OutboundMessage | Conteúdo canônico e submission_key por entrega, não por tentativa | `domain.py:277–284`; comparação exata com durable em `telnyx_submission.py:172–187` | Dataclass sem post_init aceita campos vazios/tipos errados e key None; os adapters/gates devem validar. Body fingerprint não prova bytes HTTP, query, path, método ou organização. | `test_claim_payload_or_key_collision_denies`, runner recebe chave durável; CX-35. |
| EligibilityDecision / ConsentEvidence / TemplateEvidence | Consentimento distinto da janela; template é modalidade/prova própria | `whatsapp_policy.py:23–172`, `_aware`, `_consent_valid` e políticas determinísticas | DTOs podem receber datetime inválido/None apesar das anotações; funções negam. Referência opaca não verifica consentimento real; propósito/template são dados confiados à futura operação. Template decision nunca converte body free-form. | WhatsApp policy tests; 24h exatas nega, revogação/futuro/escopo/template negam. CX-36. |
| SubmissionAssessment | Consulta de elegibilidade não consome autorização | `persistence.py:1098–1118`; `telnyx_submission.py:51–223` | `eligible=True` pode ficar obsoleto imediatamente; clock high-water pode ser atualizado inclusive por consulta negada. `message=None` compara fingerprint durável, não é credencial de um sender. | Rechecagem de revogação e concurrent one-use; autorizado somente por writer transaction, não pelo assessment. |
| OutboundDeliveryRecord / schema | Uma entrega por reply; provider/channel/recipient imutáveis; UUID4/fingerprint e primeiro marker estáveis | `persistence.py:162–183`, `_insert_delivery:2664–2730`, migrations0007/0021 e triggers | Dataclass é projeção de leitura, não state machine. `body`, endereços e chave estão no repr padrão; não logar o objeto. `first_submission_at=None` não prova histórico sem envio. | Outbound/submission/migration tests de unique, histórico ausente, replacement e reuso de IDs. |
| DeliveryAttemptRecord / RetryEvidence | Owner e attempt number fixam tentativa; retry só com prova local de não submissão | `persistence.py:196–205`, `finalize_delivery:1315–1528`, migration0021:86–137 | `retryable` neutro ou diagnóstico não basta para Telnyx; marker prévio impede prova retroativa. `RetryEvidence.NOT_SUBMITTED` é afirmação de componente interno confiável, não verificação de rede. | `test_historical_terminal_attempt_cannot_gain_retroactive_submission_proof`, missing-history/replace tests; sender não pode fabricar prova. |
| ProviderAcceptance | Provider aceitou e atribuiu ID; não significa sent/delivered/read | `providers/base.py:44–48`, `finalize_delivery` exige ID não vazio e reconcilia status atomicamente | DTO não valida formato/escopo de ID. Store confia na classificação fornecida pelo sender, inclusive sem HTTP real; futuro sender deve validar resposta antes de construir. | Acceptance separation e early correlation tests; nenhum evento cria acceptance a partir de queued/sending. |
| HumanHandoff / ConversationAutomationControl | Handoff e pausa independentes; owner/episode/revision não são credenciais | `persistence.py:186–193`, `automation_operations.py`, migrations0009/0015/0017 | Resume não resolve handoff/unknown/failed/canal. Resposta de replay é histórica. Meta/Twilio sem source confiável após resume ficam suppressed. | Human_handoff/automation/pause tests; API e workflow operacional são camadas distintas. |
| Geração / GeneratedReply / LLMDecision | Modelo propõe; finalizador valida fatos/política; completion persiste uma vez | `generation.py`, `grounding.py:32–259`, `application.py:164–302`, `persistence.py:2470–2661` | `trusted_reply` contorna finalização somente por configuração determinística/testes; adapters LLM atuais deixam unset. DTO não é sandbox de código malicioso. Owner adquirido pode consumir LLM após pausa; resultado é cercado. | Grounded/persona/intake/handoff tests e probe AR-01; nenhuma regressão de persistência reproduzida. |

## Cadeia de confiança que o sender precisa preservar

```text
bytes externos → autenticação/escopo → canonical event → writer transaction
→ recibo/proveniência durável → geração cercada → outbox/identidade estável
→ assessment consultivo → autorização one-shot + markers no commit
→ futuro transporte → resposta validada ou unknown → finalização + status atômicos
```

A assinatura só autentica quem assinou aqueles bytes; não prova consentimento,
janela, sincronização, readiness ou delivered. Um `ProviderAcceptance` criado
por componente interno também não autentica uma resposta HTTP. Essas distinções
são necessárias para evitar que dados estruturalmente válidos ganhem significado
operacional não comprovado.

## Pontos de aceitação semântica a manter explícitos

- Chamadas diretas a `record_webhook_events` pressupõem adapter autenticado;
  `require_message_provenance=False` é compatibilidade, não alternativa autorizada
  de composição Telnyx. A composição offline usa True e fornece binding.
- `InboundWindowEvidence` precisa ser a primeira recepção autenticada do Message;
  um construtor Python ou linha inserida por fixture não prova sua origem.
- `now` injetado é seam de teste confiado. Em operação precisa ser relógio local
  correto; high-water não detecta rollback para snapshot antigo sem evidência externa.
- `submission_key` estável não concede retry: unknown permanece bloqueado mesmo
  dentro da janela máxima documentada de idempotência externa.
- `safe_error_code` é um campo interno controlado. Não passar detalhe arbitrário
  de erro externo; os parsers atuais descartam errors[].detail/content.
- O DTO `OutboundMessage` não carrega organização, path, método, query ou bytes.
  O sender precisa vincular configuração/request à identidade sem enfraquecer
  a comparação do store. A ausência atual é gate conhecido CX-35.
- `delivery_claim_is_current` é consulta auxiliar de owner/lease/gates e não
  autorização de envio. O único seam que marca possível submissão é
  `authorize_delivery_submission`.
- Dados de estado em DTOs não são autorização administrativa. Admin exige Bearer
  próprio, permissão e scope; allowlist `*` é uma decisão explícita single-business.

Não foi demonstrado bypass de autenticação ou envio não autorizado por estas
observações. As lacunas operacionais e de transporte acima precisam permanecer
gates verificáveis; não são resolvidas por anotações de tipo ou número de testes.
