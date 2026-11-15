# Ticket 08 — status Telnyx e correlação antecipada

Entrega offline: 2026-11-15. Autorização original: 2026-11-12, Ticket 08 somente.
Baseline aprovada: `5f0592d268916c6eee042de2fd73ee171030e47b` (Ticket 07).
Branch: `codex/telnyx-coexistence-08-status`.
Candidato de código e testes: `fc5a11c9a2aaef912e7dcf7986ef80ce37bb4a94`.
Comparação final com Ticket 07: 3 commits à frente, 0 atrás, 27 arquivos alterados
(incluindo este relatório). Publicação por push normal somente da branch Ticket 08;
sem PR/merge ou alteração da baseline. Main local/remoto permanece
`af1c9eb862a4180ca6b9e537349e4f8abaa2bb29`; a branch Baileys permanece em
`efde945c793733c0ddac9298687151d749e95e30`, sem escrita nesta worktree externa.

## Resultado e comparação com Ticket 07

O adapter offline agora interpreta status autenticado, registra evidência mínima
em SQLite e reconcilia callbacks antecipados na transação de Provider Acceptance.
Reutiliza TelnyxWebhookAuthenticator sem alteração. Não há sender, lifecycle,
janela de atendimento, rota Telnyx, seleção runtime, readiness de canal ou conta real.
Os módulos Meta/Twilio, main/configuração e inteligência V1 não mudaram.

A migration 0019 acrescenta o ledger `delivery_status_events` e a marca
`status_conflict` no outbox. Preserva a inbox `pending_delivery_statuses` e todos os
dados legados; Telnyx nunca consome suas linhas sem escopo. A verificação estrutural
de migrations exige os novos campos, índice e guards, sem habilitar canal Telnyx.

## Matriz de eventos/status

O status é lido exclusivamente de `payload.to[0].status`, com exatamente um
recipient E.164, sem CC. `data.id` identifica o evento; `payload.id`, a Message.

| Evento | Status do recipient | Evidência e efeito |
| --- | --- | --- |
| message.sent | sent | sent; não implica delivered |
| message.sent / message.finalized | queued, sending | unknown; somente observação durável |
| message.finalized | sent, delivered, read | sucesso correspondente |
| message.finalized | sending_failed, delivery_failed, failed | failed; motivo fixo provider_delivery_failed |
| message.finalized | delivery_unconfirmed, expired | unknown; não comprova falha ou retry |
| message.read | read | read |
| Combinação incompatível, status desconhecido/accepted, múltiplos recipients, CC, escopo incorreto | qualquer | rejeição; sem ACK de sucesso |
| message.echo humano | não aplicável | fluxo Ticket 07; nunca delivery da IA |

Assinatura sobre bytes originais precede parsing. Organização, profile, tipo,
direção e business number passam pelo autenticador existente; WABA, quando presente,
também deve corresponder. Nenhum código/título/detalhe externo de erro é persistido,
registrado em log ou inserido na exceção. Campos de conteúdo/aliases não são usados
na correlação e não são copiados para o ledger.

Fontes oficiais verificadas em 2026-11-12:

- [Receiving webhooks](https://developers.telnyx.com/docs/messaging/messages/receiving-webhooks): estrutura de recipient e significado de sent, delivered e falhas explícitas.
- [Coexistence](https://developers.telnyx.com/docs/messaging/whatsapp/coexistence): status WhatsApp failed, echo e limites da evidência operacional.
- [OpenAPI oficial](https://raw.githubusercontent.com/team-telnyx/openapi/master/openapi/spec3.json): MessagingOutboundMessage e MessagingOutboundMessagePayload, incluindo message.read, WHATSAPP e to[].

O schema genérico admite read, mas estes testes não provam disponibilidade/frequência
de recibos reais na conta WhatsApp. `failed` é documentado no guia de Coexistence,
embora não conste no enum genérico. Expired é conservadoramente unknown por falta
de semântica suficiente para classificá-lo como falha definitiva/retry.

## Correlação, precedência e atomicidade

Antes da aceitação, somente receipts são persistidos. Não surgem Conversation,
Message, processamento, tentativa, intenção de entrega ou envio. Todo evento de uma
Message mantém provider, canal, recipient, organização e profile consistentes.
Evento repetido precisa preservar a evidência canônica; conflito aborta a transação.
Aliases Meta nunca servem de lookup. Identidade já observada como inbound/humano
não pode passar como status de AI Reply, inclusive em replay na ordem inversa.

Na aceitação, o outbox precisa corresponder exatamente ao provider, Message ID,
canal e recipient dos receipts. Validação, finalização da tentativa, vínculo e
agregação de status fazem parte do mesmo BEGIN IMMEDIATE. Incompatibilidade ou
falha de banco reverte tudo; nenhum receipt é consumido parcialmente. O vínculo
também guarda o owner token da tentativa aceita para impedir reassociação após
expurgo e reutilização de IDs numéricos SQLite. Esse token é interno e não autentica
webhook, operador ou envio.

Sucesso cresce sent < delivered < read, sem depender da ordem de chegada ou de
relógio remoto. Falha sem confirmação delivered/read resulta em failed. Falha e
confirmação delivered/read preservam a confirmação mais forte e marcam conflito
persistente, com reason provider_status_conflict. Ambas as evidências permanecem
no ledger. O resultado converge nas duas ordens de chegada, incluindo reconciliação
antecipada. Não há downgrade read → failed para Telnyx; Meta/Twilio conservam a
política legada. Unknown/cancelled locais não voltam a estado enviável por callback.

O conflito aparece em list-blocked-deliveries e unresolved_delivery, impede a
próxima geração ordenada e a autorização de submissão, inclusive de entrega já
adquirida. Pause/resume não limpa conflito. Purge/deleção legada não pode esconder
conflito não resolvido. A janela já existente autorização→HTTP continua sem recall.
Não foi implementada resolução automática nem manual de conflito neste ticket.

ACK offline 204 somente depois do commit observado por outra conexão. Falha de
statement/commit, lock ou deadline impede sucesso. ACK perdido é replay idempotente;
restart antes/depois da reconciliação preserva a evidência. O limite contratual de
2 s, streaming e cabeçalhos ASGI brutos continuam CX-24/CX-30, sem rota habilitada.

## Evidência de testes

Todos os testes usam dados sintéticos e SQLite real em arquivos temporários.
A suíte integral roda com ambiente saneado e audit hook Python bloqueando
socket.connect/sendto IP, inclusive subprocessos Python. Nenhuma credencial
comercial, banco de cliente ou API Telnyx foi usada.

Os primeiros runs completos do candidato 41344f7 encontraram **10 failed, 1682
passed, 1 skipped** (local 140,53 s; independente 137,96 s). As dez falhas eram
fixtures/assertions de migrations históricas: preparação com SQL do runtime novo
sobre schema antigo, coluna nova default 0 e trigger legitimamente alterado.
O commit fc5a11c prepara fixtures antigas diretamente com SQL, verifica todos os
campos preexistentes e o default novo, e mantém testes de rollback. Não adiciona
bypass ao runtime. Subsuíte histórica corrigida: **222 passed em 17,51 s**.

Validação final do candidato fc5a11c:

| Check | Resultado |
| --- | --- |
| pytest completo local | **1692 passed, 1 skipped, 133,08 s** |
| pytest completo independente (Spec) | **1692 passed, 1 skipped, 139,66 s** |
| pytest independente expandido (Standards) | **339 passed, 0 skipped, 44,85 s** |
| Ticket 08 específico | **99 passed, 7,21 s** |
| Ruff check | PASS |
| Ruff format --check | PASS, 281 arquivos Python |
| compileall src tests | PASS |
| pip check | PASS, nenhuma dependência quebrada |
| git diff --check | PASS |
| Gitleaks 8.30.1 | PASS, nenhum segredo; redaction 100%, sem exceções |

O único skip é `test_historical_v8_record_remains_loadable`, em
`tests/test_commercial_steering.py:430`: “Local history evidence is not checked
into Git”. Nenhum teste Telnyx, autenticação, migração ou compatibilidade foi pulado.
Ambiente: Python 3.14.7, SQLite 3.50.4, pytest 8.4.2, Ruff 0.17.5,
PyNaCl 1.6.2, cryptography 50.0.2 e Alembic 1.20.1. Nenhuma dependência do projeto
foi alterada. O commit de entrega após fc5a11c acrescenta somente este relatório.

## Standards Review independente

**PASS**, diff 5f0592d...fc5a11c. Zero P1/P2, violações documentadas ou smells
acionáveis. O revisor verificou AGENTS.md, regras locais, arquitetura/ADRs e a
correção das fixtures: todos os campos antigos continuam comparados e a coluna
nova é verificada com default zero. Executou independentemente 339 testes,
sem falhas/skips. A revisão inicial de 41344f7 também passou com 217 testes;
a rodada final ampliou a cobertura após as correções históricas.

## Spec Review independente

**PASS**, diff 5f0592d...fc5a11c. Zero P1/P2, requisitos faltantes ou expansão
não autorizada identificados. O revisor conferiu o pedido do usuário, spec, ADR,
CX-31 e schema oficial. Confirmou identidade/escopo, receipts sem criação de
trabalho, reconciliação atômica, precedência com conflito, unknown/cancelled e
privacidade. Executou a suíte completa: 1692 aprovados, um skip histórico.

Nenhum P1/P2 de implementação permaneceu pendente. As dez falhas de fixtures da
primeira suíte completa foram corrigidas e reexecutadas. As revisões são agentes
independentes, não uma segunda autodeclaração do implementador.

## Matriz de cobertura

| Cobertura exigida | Evidência principal em test_telnyx_delivery_status.py |
| --- | --- |
| Assinatura válida/inválida e contrato oficial sintético | official_shape_minimal_evidence_and_ack; invalid_signature_precedes_status_parsing |
| sent/delivered/read/failed e unknown | matriz parametrizada; event_type_is_not_a_status_fallback |
| Escopo número/profile/organização/WABA, recipient/Message/provider | bad_scope_or_shape_has_no_ack; outbox_scope_mismatch_never_correlates; provider_namespace_and_shared_meta_alias_never_join |
| Antes/depois de aceitação, restart, fora de ordem | early_late_order_restart_replay; concurrent_acceptance_and_callback_converge |
| Duplicatas, ACK perdido, conflito de mesmo evento | concurrent_duplicates_have_one_durable_receipt; lost_ack_restart_replay_and_commit_visibility; conflicting_same_event_is_rejected |
| Falha contraditória e terminalidade | permutações early_late_order_restart_replay; local_terminal_states_are_not_revived_by_callbacks |
| Falha visível e bloqueio persistente | conflict_is_visible_and_blocks_next_generation_and_resume; conflict_fences_already_claimed_next_delivery |
| Echo humano e aliases Meta | human_or_inbound_identity_cannot_be_ai_status; event_id_shared_across_event_kinds_is_rejected |
| SQLite/rollback/ACK | database_failure_rolls_back_entire_mixed_batch_and_redacts; reconciliation_failure_rolls_back_acceptance_and_link; commit_failure_has_no_ack_or_receipt; sqlite_writer_lock_deadline_prevents_ack |
| Migração, purge, identidade durável | migration_preserves_legacy_inbox_and_does_not_promote_telnyx_rows; migration_interruption_preserves_data_and_old_schema; status_receipts_survive_raw_message_purge; purged_receipt_cannot_bind_to_reused_sqlite_ids |
| Privacidade/visibilidade | sentinelas em payload, errors, SQL trigger e traceback; CLI redigida no teste de conflito |
| Tickets 01–07 e Meta/Twilio | suíte completa, inclusive testes legados de delivery status sem alteração |

## Ressalvas / issue #11

- **CX-31:** resolvido tecnicamente no escopo offline com a correlação exata,
  receipts duráveis, reconciliação atômica, teste de reuso de PK e política explícita
  de contradição. Checkbox permanece aberto até auditoria/aprovação do orquestrador.
- **CX-14:** acrescentadas interpretação e evidência de status antecipado, replay,
  ordem, terminalidade e falhas. Accepted nunca vira delivered por inferência.
- **CX-01:** ledger e tokens internos também estão em retenção sem expiração;
  política de expurgo/erasure e deduplicação segura segue bloqueadora antes do piloto.
- **CX-13/CX-17:** escopo offline protegido; não resolve migração de identidade,
  vários canais, sender, composição, lifecycle ou integração real.
- **CX-19/CX-21:** checks e revisões independentes são evidência local; não substituem
  CI, auditoria direta do orquestrador nem aprovação de merge/release.
- **CX-24/CX-29/CX-30:** seguem bloqueadores de composição. Outros formatos/eventos
  ainda rejeitados podem provocar retries; status suportado reduz somente essa parcela.
- **Novo CX-32 — BLOQUEADOR operacional antes do piloto:** não existe procedimento
  implementado/aprovado de resolução de conflitos de entrega ou correlação precoce
  rejeitada. O estado seguro é bloqueado, visível e sem reenvio. Responsáveis:
  recuperação/operação em Tickets 12–13, com autorização própria. Fechamento exige
  política explícita, operador autenticado, evidência auditável e testes de restart,
  concorrência e não duplicação; nunca limpar flag ou reenviar implicitamente.

Não há exceção de risco aceita. Demais itens do issue #11 permanecem nos seus donos
e gates; inteligência/SaaS/multimodelo não foram abordados. Nenhum checkbox é fechado
nesta entrega. Ticket 09 continua não iniciado e exige nova auditoria direta e
autorização explícita. Main, Baileys, Meta/Twilio e a inteligência V1 foram preservados.

## Arquivos alterados

- `docs/ARCHITECTURE.md`
- `docs/architecture/v1-ticket08-validation.md`
- `docs/automation-operations.md`
- `docs/decisions/0016-scoped-delivery-status-evidence.md`
- `docs/decisions/README.md`
- `docs/specs/README.md`
- `docs/specs/V1-telnyx-coexistence-ticket-08.md`
- `src/rj_studio_ai/automation_operations.py`
- `src/rj_studio_ai/delivery_status_events.py`
- `src/rj_studio_ai/domain.py`
- `src/rj_studio_ai/inbound_events.py`
- `src/rj_studio_ai/migrations/__init__.py`
- `src/rj_studio_ai/migrations/versions/0019_scoped_delivery_status.py`
- `src/rj_studio_ai/persistence.py`
- `src/rj_studio_ai/providers/telnyx_messages.py`
- `tests/historical_delivery.py`
- `tests/test_agentic_intake_migration.py`
- `tests/test_appointment_intake_migration.py`
- `tests/test_automation_operations.py`
- `tests/test_conversational_intake_migration.py`
- `tests/test_generation_pause.py`
- `tests/test_migrations.py`
- `tests/test_openai_metadata_migration.py`
- `tests/test_operational_event_journal.py`
- `tests/test_outbound_pause.py`
- `tests/test_telnyx_delivery_status.py`
- `tests/test_telnyx_messages.py`
