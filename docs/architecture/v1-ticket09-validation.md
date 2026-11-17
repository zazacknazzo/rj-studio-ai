# Ticket 09 — evidência de lifecycle e bloqueio durável offline

Data da validação final: 17/11/2026. Escopo autorizado pelo usuário e pela auditoria
registrada na issue #11: apenas Ticket 09 offline; Tickets 10–13 não iniciados.

## A–D. Escopo, baseline, branch e diff

Baseline exata: `2e66cd86bf6842bdb3eeee2c9e5faf3d15f21335`, Ticket 08 aprovado.
Branch: `codex/telnyx-coexistence-09-lifecycle`.
Código e testes revisados: `5cd9a1d472de42e721437740ca28009b9edb1e82`.
O commit posterior de entrega acrescenta somente este relatório. SHA de publicação
fica no registro da issue e no artefato de entrega para evitar referência circular.

[Comparação com Ticket 08](https://github.com/zazacknazzo/rj-studio-ai/compare/2e66cd86bf6842bdb3eeee2c9e5faf3d15f21335...codex/telnyx-coexistence-09-lifecycle).
Dois commits de implementação, zero atrás da baseline; relatório em commit separado.
O diff final contém 22 arquivos; a lista completa consta ao final.

Implementação: `whatsapp.account.update` autenticado pelo Ticket 06 antes do parsing;
WABA validada e vinculada explicitamente à configuração comercial; journal/effect
receipt, estado do canal, supressão e cancelamento na mesma transação. Gate de
canal independente da pausa por Conversation, aplicado aos caminhos de geração,
conclusão, aquisição, autorização proactive/legacy e resultados tardios.

## E. Matriz de lifecycle

| Entrada/condição | Registro/estado | Geração e envio |
| --- | --- | --- |
| Canal sem vínculo ou validação positiva | Ausência é inelegível; primeiro vínculo é verification_required | Bloqueados |
| ACCOUNT_OFFBOARDED | Observação account/WABA; blocked, reason offboarded | Bloqueados |
| PARTNER_REMOVED | Observação account/WABA; blocked, reason disconnected | Bloqueados; sem reconexão |
| ACCOUNT_RECONNECTED | Observação account/WABA; verification_required, reason reconnected | Bloqueados; sem resume ou resend |
| Mesmo event_id/evidência | Replay sem novo efeito/revisão; primeira recepção preservada | Não muda o gate |
| Mesmo event_id/evidência conflitante | Transação rejeitada | Sem ACK ou efeito parcial |
| Transição desconhecida/timestamp ambíguo/WABA incorreta | Rejeição; sem ACK de sucesso | Nenhuma autorização concedida |

Contrato oficial consultado em 16–17/11/2026:
[Coexistence Webhooks](https://developers.telnyx.com/docs/messaging/whatsapp/coexistence/webhooks).
`data.id` é identidade do evento; `payload.waba_id` é conta, nunca Message,
Conversation, número ou profile. Transição vem exclusivamente de `payload.event`.
Campos extras não são usados para inferir destinatário ou reativar o canal.

## F. Persistência e gates

Migration aditiva `0020_channel_lifecycle`, a partir de `0019_scoped_delivery_status`:

- `channel_lifecycle`: uma linha Telnyx single-business, WABA/número/org/profile
  imutáveis, estado, revisão, data local e referência da última observação aplicada.
- `channel_lifecycle_effects`: recibos com FK RESTRICT ao journal; deduplicam efeitos
  e impedem que purge de Message apague a decisão de bloqueio.
- `operational_events`: observações account/WABA reutilizam o journal existente,
  sem criar Conversation nem guardar conteúdo bruto.
- `eligible_telnyx_channels`: única projeção da autoridade para os gates. Ausência,
  blocked e verification_required não autorizam. `active` exige evidência explícita;
  a aplicação não contém API/command que a conceda. As fixtures de regressão dos
  Tickets 07/08 representam uma conexão sintética anteriormente verificada.

Não há estado active inferido por ausência de bloqueios. Guards impedem UPDATE,
DELETE e INSERT OR REPLACE de contornar o vínculo/estado; não protegem contra um
administrador que deliberadamente remova/reescreva o schema, fora desse contrato.

O bloqueio suprime gerações retryable/processing e invalida owners sem zerar
attempt_count. Cancela pending/retryable/sending sem submission_started_at, após
finalizar a tentativa local iniciada com código fixo channel_lifecycle_cancelled.
Uma tentativa comprovadamente retryable que chega depois do bloqueio conserva
sua evidência e termina com entrega cancelada, inclusive ao esgotar tentativas.

Tentativas já autorizadas, unknown, accepted, sent/delivered/read, failed e legado
ambíguo são preservadas. Status callbacks continuam autenticados e persistidos;
não concedem elegibilidade. A autorização legacy também exige o gate atual mesmo
quando há autorização anterior. Handoff release não converte ambiguidade em retry.

`BEGIN IMMEDIATE` resolve concorrência de writers; nenhuma transação cobre LLM,
rede ou HTTP de saída. Falha de statement/commit faz rollback conjunto e não gera
ACK. ACK perdido admite replay. Prazo vencido após commit pode exigir replay,
sem negar que o commit ocorreu. O ingresso continua disponível com canal bloqueado.

## G. Duplicatas, ordenação e relógios

A ordem persistida é de inserção no journal local. Ela não afirma cronologia remota.
Cada evento inédito válido altera a indicação local blocked/verification_required,
ambas inelegíveis; reconnect atrasado jamais ativa. Offboard atrasado após reconnect
bloqueia; replay antigo conhecido não reverte a última observação aplicada.

Não se ordenam IDs textuais e não se escolhe estado por occurred_at. Tempo antigo,
futuro ou relógio corrigido não abrem o gate. Timestamp sem timezone é rejeitado;
evidência canônica conflitante para o mesmo evento aborta. Identidades de envelope
não podem migrar entre Message/status/account. WABA não é usada para identificar
Customer ou criar Conversation. Rebinding exige trabalho posterior autorizado.

Transição desconhecida é rejeitada sem observação/ACK; os valores brutos não são
logados. Essa escolha conserva CX-29 (retries de formatos não suportados) aberto.
Não há descarte silencioso por sucesso vazio.

## H. Concorrência, migração e limites

Testes usam SQLite real, conexões independentes e Barrier/Events, não mocks de
transação. Disputas cobrem lifecycle contra claim, conclusão, autorização, status
e duplicata. Conclusão primeiro conserva reply e cancela a entrega ainda não
submetida; lifecycle primeiro impede reply. Autorização primeiro conserva sending
como potencialmente submetido; lifecycle primeiro cancela e a autorização falha.

Bloqueio durante LLM não segura writer lock e impede resultado/reply/outbox. Outra
regressão insere lifecycle entre claim/contexto e chamada do gerador e prova zero
chamadas. Ainda existe janela entre a última consulta e o início físico do LLM;
pode haver custo de chamada já autorizada, mas a conclusão permanece bloqueada.
A janela autorização→HTTP existente também permanece: não é possível recolher
submissão já autorizada/iniciada nem prometer exactly-once externo.

Migration não reconstrói tabelas-pai nem promove histórico a active. Preserva
Messages/status/attempts, suprimindo apenas trabalho Telnyx inelegível. Falha
injetada em DDL restaura schema0019 e dados; backup0019 restaurado remigra com a
mesma supressão. Backup após offboard/reconnect mantém bloqueio e replay. FKs e
readiness estrutural são verificados. Main e adapters Meta/Twilio não mudam.

## I. Validação

| Check | Resultado |
| --- | --- |
| Pytest completo local final | 1760 passed, 1 skip histórico, 143,53 s |
| Pytest completo independente Spec | 1760 passed, 1 skip histórico, 167,59 s |
| Regressões focadas após correções | 87 passed, 0 skipped, 9,58 s |
| Standards independente | 379 passed/0 skips (38,78 s); final SHA: 68 passed/0 skips (10,99 s) |
| Ruff check | PASS |
| Ruff format --check | PASS; 288 arquivos |
| compileall src/tests | PASS |
| pip check | PASS; nenhuma dependência quebrada |
| git diff --check | PASS |
| Gitleaks 8.30.1 | PASS; nenhum segredo; commits Ticket09, sem ignores |

Os comandos pytest foram executados em ambiente saneado, com variáveis de
credenciais removidas e conexões IP bloqueadas. As fixtures assinam payloads
sintéticos Ed25519 e usam bancos temporários; nenhuma API Telnyx/LLM real foi chamada.
Python 3.14.7, SQLite 3.50.4 e dependências instaladas no venv da branch.

O skip histórico é `test_historical_v8_record_remains_loadable`: fixture local não
versionada. Primeira execução local: 4 failed, 1736 passed, 1 skipped (117,31 s).
Primeira independente Spec: mesmo resultado (135,42 s). As quatro falhas eram
asserts do head0019 em testes de migração; foram atualizados para head0020 mantendo
as comparações históricas e os asserts de rollback. Não houve relaxamento de
asserts de comportamento para esconder regressão. A fixture ativa sintética dos
Tickets07/08 agora é explícita; a regressão de correlação errada mantém todos os
asserts e testa o seam de status após parsing autenticado, sem contornar o gate no
runtime. Tests novos verificam separadamente o default bloqueado e o rebinding.

### Matriz de evidências em tests/test_telnyx_lifecycle.py

| Requisito | Testes principais |
| --- | --- |
| Assinatura/contrato/WABA/3 transições/unknown | contract_commit_before_ack_restart_and_duplicate; bad_contract_no_ack_no_effect; bad_signature_precedes_json_and_lifecycle |
| Sem active implícito | absence_of_verification_is_never_active |
| Replay/conflito/ordem/clock | conflicting_replay_rolls_back_whole_batch; reordering_and_wrong_clock_never_enable |
| Separação account/Message | event_identity_cannot_cross_message_and_account_scopes |
| Pending/claim/recovery/LLM | pending_or_owned_generation_suppressed_without_resetting_attempts; block_during_llm_has_no_writer_lock_or_reply; block_between_claim_and_llm_never_calls_generator |
| Delivery adquirido/authorizado/legacy/retry tardio | block_cancels_only_unsubmitted_delivery; previously_authorized_result_is_preserved_and_never_resends; legacy_authorization_and_handoff_release_cannot_bypass; expired_authorized_delivery_becomes_unknown_never_retry |
| Admin pause/resume e handoff | pause_resume_independent_of_lifecycle; legacy_authorization_and_handoff_release_cannot_bypass |
| Atomicidade/commit/ACK perdido/lock | sqlite_failure_rolls_back_observation_effect_and_cancellation; lost_ack_restart_and_replay; lock_deadline_no_ack_then_retry |
| Concorrência real | writer_concurrency_has_atomic_outcomes (5 competidores) |
| Migração/restore/manutenção | migration_from_0019_is_atomic_and_preserves_history; restored_backup_retains_block_and_replay; maintenance_and_restart_preserve_account_block |
| Guards SQL e schema | no_sql_shortcut_can_release_or_erase_channel; sql_replace_cannot_bypass_immutable_binding; schema_damage_fails_local_readiness |
| Privacidade | sentinelas em payload desconhecido/erro SQL/traceback/logs; zero raw payload no journal |
| Tickets01–08/Meta/Twilio | suíte integral, contratos e adapters anteriores preservados |

## J. Revisão independente Standards

PASS no candidato `5cd9a1d472de42e721437740ca28009b9edb1e82`.

O P2 encontrado foi corrigido pelo trigger channel_binding_rejects_replacement,
executado antes do INSERT. O revisor repetiu a reprodução original: INSERT OR
REPLACE agora falha e mantém vínculo e bloqueio. Regressões cobrem offboard e
reconnect com recursive_triggers=0; schema inspection exige o novo guard.

Validação independente: 379 passed/0 skips (38,78 s) na suíte ampliada de lifecycle,
mensagens/status e pausa; 68 passed/0 skips (10,99 s) de lifecycle reexecutados na
SHA final. Ambiente saneado e conexões IP bloqueadas. Nenhuma violação documentada,
smell acionável ou P1/P2 pendente confirmado. As alterações de expectations de
migration preservam dados históricos e rollback. Parecer exclusivamente offline.

## K. Revisão independente Spec

PASS no commit `5cd9a1d472de42e721437740ca28009b9edb1e82`, comparado à baseline
exata do Ticket08. Nenhum requisito implementado incorretamente, ampliação indevida
de escopo ou P1/P2 pendente confirmado. O revisor inspecionou autenticação anterior
ao parsing, vínculo WABA/configuração, separação conta/Conversation, journal/effects,
transações/ACK, gates de geração/submissão, recovery, maintenance e migrations.

Reconexão permanece verification_required; ausência de validação não produz active.
Replay idêntico não reaplica efeitos, conflitos abortam atomicamente e timestamps
não liberam o canal. Submissões anteriores são preservadas. Resume e handoff release
não contornam o bloqueio. A correção REPLACE e as regressões de pré-LLM, identidade,
manutenção, expiry e backup0019/remigration foram confirmadas. Os quatro ajustes de
head preservam comparações históricas e asserts de rollback.

Validação independente final: 1760 passed, 1 skipped, 167,59 s; ambiente saneado e
IP bloqueado. O relatório foi conferido sem divergência material. Evidência apenas
offline; sem prova de conta real, sincronização, prazo 2 s ou readiness.

## L. Ressalvas e registro central

Nenhum risco é encerrado nesta entrega; auditoria/aprovação do orquestrador seguem
necessárias. CX-31 permanece como foi aprovado no Ticket08, sem reabrir ou fechar
outros checkboxes por conveniência.

| Riscos | Revalidação e gate restante |
| --- | --- |
| CX-01 | Channel binding/effect receipts também permanecem sem expiração. Retenção/erasure/backup seguro: Ticket13, antes do piloto. |
| CX-02/CX-03 | Echo continua best-effort, pausa prévia à ação humana continua necessária; conversa e canal são gates independentes. Operação/Tickets12–13. |
| CX-05 | occurred_at não libera canal; ordem remota/clock real não provados. Operação/Tickets12–13. |
| CX-06 | Autorização→HTTP e resultado tardio preservados; sem recall. Sender/composição/Tickets11–13. |
| CX-10 | Onboarding/elegibilidade/Coexistence real não realizados. Operação, antes de conta/piloto. |
| CX-11 | Bloqueio/replay/restart offline implementados; validação positiva de sync e elegibilidade ainda ausente. Composição Ticket12 e autorização própria. |
| CX-17 | Lifecycle offline não constitui integração real; sem rota/sender/readiness. Tickets10–13 mediante autorização. |
| CX-19 | Suítes/revisores locais independentes são evidência offline, não CI nem aceite do orquestrador. Ticket13. |
| CX-21 | Push normal só branch09, sem merge/main/Baileys; auditoria de segredos passou. Release exige autorização separada. |
| CX-24/CX-29/CX-30 | HTTP bruto, streaming, política de unknown/retries e orçamento real 2 s permanecem abertos. Tickets12–13. |
| CX-32 | Conflitos de delivery continuam bloqueadores; lifecycle não os resolve nem apaga. Operação/Tickets12–13. |
| CX-33 — novo BLOQUEADOR | Ativação/rebinding operacional não existem. Dono operação/composição, Tickets12–13 sob autorização específica. Antes de ativação/piloto: política e interface autenticada, evidência positiva de sync/elegibilidade, epoch/cutoff para impedir reviver trabalho antigo, auditoria e testes concorrentes/restart. Origem ADR0017/5cd9a1d. |
| CX-34 — novo REVISAR | Janela consulta→LLM pode iniciar chamada já autorizada após bloqueio; saída não persiste, mas pode haver custo. Dono runtime/operação, Tickets12–13. Antes do piloto: política documentada de custo/cancelamento, testes concorrentes e aceite operacional explícito; não prometer recall de LLM. Origem ADR0017/5cd9a1d. |

A Telnyx documenta resposta 2xx em até 2 s:
[Receiving Webhooks](https://developers.telnyx.com/docs/messaging/messages/receiving-webhooks).
O deadline injetado offline não comprova essa latência no HTTP, fsync/carga ou rede.
Demais riscos mantêm responsáveis e gates. Nenhuma exceção de risco foi aceita.

## M. Limites e preservação

Nada externo foi ativado: nenhuma rota pública, sender Telnyx, credencial comercial,
conta WhatsApp, onboarding/reconexão, alteração de modelo/persona/grounding ou merge.
Main segue `af1c9eb862a4180ca6b9e537349e4f8abaa2bb29`; Ticket08 segue a SHA baseline.
Baileys permanece no worktree separado, branch experimental e alterações locais
intocadas. Seu código não faz parte do diff. A mudança em application.py é somente
o gate antes da geração; política/inteligência V1 não foi alterada.
Ticket10 não iniciado. A próxima etapa depende de auditoria direta e autorização.

## Arquivos alterados

- `docs/ARCHITECTURE.md`
- `docs/architecture/v1-ticket09-validation.md`
- `docs/automation-operations.md`
- `docs/decisions/0017-durable-channel-lifecycle.md`
- `docs/decisions/README.md`
- `docs/specs/README.md`
- `docs/specs/V1-telnyx-coexistence-ticket-09.md`
- `src/rj_studio_ai/application.py`
- `src/rj_studio_ai/channel_lifecycle.py`
- `src/rj_studio_ai/inbound_events.py`
- `src/rj_studio_ai/migrations/__init__.py`
- `src/rj_studio_ai/migrations/versions/0020_channel_lifecycle.py`
- `src/rj_studio_ai/persistence.py`
- `src/rj_studio_ai/providers/telnyx_messages.py`
- `src/rj_studio_ai/webhook_ingress.py`
- `tests/telnyx_channel_fixture.py`
- `tests/test_agentic_intake_migration.py`
- `tests/test_migrations.py`
- `tests/test_openai_metadata_migration.py`
- `tests/test_telnyx_delivery_status.py`
- `tests/test_telnyx_lifecycle.py`
- `tests/test_telnyx_messages.py`
