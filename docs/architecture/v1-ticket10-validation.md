# Ticket 10 — elegibilidade WhatsApp e identidade de submissão offline

Data: 20/11/2026. Escopo autorizado: Ticket 10 exclusivamente offline, conforme
pedido do usuário e [aprovação do orquestrador](https://github.com/zazacknazzo/rj-studio-ai/issues/11#issuecomment-6962756307).
Tickets 11–13 dependem de auditoria direta e nova autorização explícita.

## A. Resumo técnico

Implementados contratos determinísticos para free-form, template aprovado e
elegibilidade não comprovada; composição dos gates de canal, Conversation e
tentativa na autorização; chave UUIDv4 estável por Outbound Delivery; fingerprint
do conteúdo canônico; primeiro marco de submissão e evidência por tentativa.
Consentimento é prova separada da janela. Resultado ambíguo permanece unknown.

O futuro sender pode consultar `assess_telnyx_submission`, obter a modalidade e
chave, repetir os gates com `authorize_delivery_submission`, registrar prova local
de não submissão com `RetryEvidence.NOT_SUBMITTED` ou finalizar unknown. Nenhum
sender Telnyx ou HTTP foi implementado. A classificação de template é somente
offline: o outbox de AI Replies continua free-form, sem conversão ou fallback.

## B–D. Baseline, branch, commits e arquivos

Baseline exata aprovada Ticket 09: `c2cc68c0c714d8f8c642f7759f3799a90b3feae4`.
Branch isolada: `codex/telnyx-coexistence-10-eligibility`.
Candidato de código/testes revisado: `7c75d92913e19c0e767543fea71cda7ff22fb023`.
O commit posterior de entrega adiciona somente este relatório; o SHA publicado
fica na issue e no artefato de entrega, evitando referência circular.

- `d612f56`: spec/ADR versionadas antes de implementação.
- `a5b9c30`: implementação, contratos e regressões.
- `914b6db`: guards contra replacement e prova retroativa; fixtures históricas.
- `7c75d92`: continuidade de histórico, retenção de tentativas e purge seguro.

[Comparação com Ticket 09](https://github.com/zazacknazzo/rj-studio-ai/compare/c2cc68c0c714d8f8c642f7759f3799a90b3feae4...codex/telnyx-coexistence-10-eligibility).
O código está quatro commits à frente, zero atrás; a entrega acrescenta um commit
de documentação. O diff final tem 28 arquivos, listados ao final.

Em relação ao Ticket 09, foram acrescentados janela/consentimento, identidade da
submissão e evidências por tentativa. A fonte de lifecycle e sua projeção elegível
permanecem as do Ticket 09. Status/aceitação e reconciliação precoce do Ticket 08
continuam no mesmo writer transaction; os adapters Meta/Twilio não foram editados.

## E. Contratos oficiais verificados

Consulta de documentação pública em 20/11/2026, sem API de conta ou operação comercial:

| Fonte | Evidência aplicável e limite |
| --- | --- |
| [Meta Service messages](https://developers.facebook.com/documentation/business-messaging/whatsapp/messages/send-messages) | Janela de24 h para free-form; templates preaprovados fora dela; opt-in separado. V1 usa somente mensagens legítimas, sem suporte a chamadas. |
| [WhatsApp Policy](https://business.whatsapp.com/policy), [Meta opt-in](https://developers.facebook.com/documentation/business-messaging/whatsapp/getting-opt-in) | Consentimento, respeito à revogação e propósito permitido. Receber texto ou conhecer nome de template não prova todos esses requisitos. |
| [Telnyx WhatsApp send](https://developers.telnyx.com/api-reference/whatsapp-messaging/send-a-whatsapp-message) | POST/v2/messages/whatsapp declara Idempotency-Key opcional, UUIDv4 recomendado, replay de sucesso por até24 h. Não extrapolar a outros endpoints. |
| [Telnyx idempotency](https://developers.telnyx.com/docs/development/api-fundamentals/idempotency) | Escopo organização+método+path, query igual e body byte-identical. 409/10036 indica processamento; 422/10027 indica request divergente. Expiração pode executar novamente. Apenas status HTTP não basta. |
| [Telnyx echo](https://developers.telnyx.com/api-reference/callbacks/whatsapp-business-app-message-echo) | Echo do Business App não abre nem renova a janela. |
| [OpenAPI oficial](https://raw.githubusercontent.com/team-telnyx/openapi/master/openapi/spec3.json), [Meta text webhook](https://developers.facebook.com/documentation/business-messaging/whatsapp/webhooks/reference/messages/text) | body.timestamp é fornecido pela Meta. Não equivale a assinatura, recebimento local nem prova de relógio real correto. |

Snapshot público OpenAPI consultado: SHA256
`fc59cb60a25c5091e73889842c808f1db7b4c0bb36bbb0228ee9ed2f629eca18`.
O guia geral e o pattern do endpoint diferem sobre uso de dois-pontos na chave;
UUIDv4 atende a ambos. “Até24 h” é limite superior; não comprova retenção mínima
integral. O contrato atual não habilita retry baseado em429/5xx ou timeout.
Nenhum resultado HTTP observado foi inventado; cenários HTTP nos testes são
explicitamente hipotéticos. A serialização HTTP real continua gate posterior.

## F. Matriz de elegibilidade

| Evidência/condição | Resultado |
| --- | --- |
| Consentimento válido e source<=event<=primeira recepção<=agora; idade< 24 h | free_form, condicionado a todos os gates operacionais |
| Imediatamente antes de24 h | Permitido se demais provas válidas |
| Exatamente24 h ou imediatamente depois | unproven; free-form negado |
| Timestamp ausente, inválido, naive, contraditório, futuro ou não representável em UTC | Não abre janela; sem substituição por horário local |
| Replay do mesmo Message ou novo envelope do mesmo Message | Usa primeira recepção; não renova source nem recupera proveniência originalmente inválida |
| Echo humano, status, ACK, assinatura, mensagem própria, edit/revoke ou reconnect | Nenhuma nova evidência de janela |
| Clock local anterior ao high-water durável | Negado; restart não remove high-water |
| Consentimento ausente, expirado, revogado ou de outro escopo | Negado, inclusive com janela aberta ou template aprovado |
| Template aprovado, prova vigente ligada a canal/Customer/nome/idioma/fingerprint, propósito service_response | approved_template na classificação offline; nenhum dispatch implementado |
| Template sem prova, pausado/rejeitado, divergente, marketing/follow-up | unproven; negado |
| Canal ausente, blocked ou verification_required | channel_blocked; nenhuma inferência de active |
| Unknown, conflito ou predecessor não resolvido | operational_unknown; bloqueado |
| Owner/lease/attempt incorretos, pausa/revisão divergente ou handoff impeditivo | Negado |
| BSUID namespaced sem contrato de sender | recipient_unproven; não inferir telefone |

O high-water avança apenas pelo relógio local da avaliação, inclusive negativas.
Não é alimentado por timestamps remotos. Um rollback não observado e precisão NTP
real não podem ser provados pelo processo; CX-05 continua aberto. O aceite operacional
de consentimento/templates também não existe nesta entrega.

## G. Idempotência e resultado desconhecido

Uma UUIDv4 é atribuída na criação da entrega lógica e preservada em retry/restart.
Nova entrega recebe nova chave, inclusive quando o SQLite reutiliza IDs após purge.
Fingerprint versionado vincula provider, modalidade free-form, canal, Customer e
body; a autorização compara o snapshot exato usado pelo runner. Chave/fingerprint
e body associado são imutáveis; colisões e replacement falham fechados.

Isso vincula a intenção canônica. Não prova bytes futuros de HTTP, organização,
método, path ou query. O Ticket 11 deverá validar esse contrato antes de usar a
proteção externa. Uma consulta elegível não consome autorização; somente a
transição atômica de submissão a consome, uma vez por tentativa.

| Situação | Política interna |
| --- | --- |
| Falha local com prova NOT_SUBMITTED, tentativa atual sem marcador | retryable; mesma chave no próximo claim, todos os gates reavaliados |
| Repetição da mesma tentativa já autorizada | Negada; não abre segunda submissão |
| Retryable genérico, timeout, resposta perdida ou crash após possível submissão | unknown; sem reenvio automático |
| Timeout sem prova suficiente, mesmo antes do marcador | unknown; não presumir ausência de efeito |
| 409/10036 hipotético validado | unknown/processamento em andamento; nenhum replay automático |
| 422/10027 hipotético validado | key_conflict bloqueador; não gerar chave substituta |
| Outros409/422,429 ou5xx | Sem semântica inventada; unknown por padrão |
| Idade desde primeiro marcador >= 24 h | Fora do limite documentado; nunca renova prazo nem autoriza retry de unknown |
| Histórico antigo, incompleto ou com prova ausente | Bloqueado; migration não fabrica evidência |

Todas as tentativas anteriores devem existir, em sequência positiva única e com
prova de não submissão. Guard de inserção impede replacement/preenchimento de prova
prévia; atribuição de prova exige a finalização da tentativa atual. Prova retroativa
em tentativa terminal é recusada. DELETE de tentativa enquanto parent existe é
recusado; purge terminal apaga parent e usa cascade. Nenhum evento promove unknown
a pending/retryable.

## H. Estados, persistência e concorrência

Preservados pending, sending, accepted, sent, delivered, read, retryable, unknown,
failed, cancelled e accepted_legacy. O caminho legacy Telnyx agora é sempre negado
para não contornar a política; Meta/Twilio mantêm o caminho aprovado anterior.

Migration aditiva 0021 sobre 0020:

- Outbound Delivery: submission_key, payload_fingerprint, first_submission_at.
- Delivery Attempt: submission_started_at e retry_evidence.
- telnyx_consent: escopo, referência opaca e vigência/revogação; sem body adicional.
- telnyx_policy_clock: high-water local durável.
- Índice único, guards de identidade/evidência/replacement/retenção e inspeção estrutural.

BEGIN IMMEDIATE compõe owner/lease, tentativa iniciada, canal verificado,
identidade coerente, janela/consentimento, fingerprint, pause revision, handoff e
conflito/ordenação. O episódio de confirmação de handoff conserva sua exceção já
autorizada. A autorização grava o marcador da entrega, o primeiro marcador lógico
e o marcador da tentativa na mesma transação. SQLite/commit failure reverte todos.
Nenhum lock cobre rede/LLM; o fake obtém outro BEGIN IMMEDIATE durante sua chamada.

Concorrência em conexões SQLite independentes demonstra uma única autorização
para o mesmo owner. Gates são reavaliados após consulta, incluindo revogação. Os
testes anteriores protegem corridas de pausa/lifecycle/handoff/status. Permanece a
janela autorização→HTTP (CX-06), inclusive expiração/desconexão posterior ao marker:
uma chamada autorizada não pode ser recolhida. CX-34 também permanece.

Backup 0020/remigration preserva dados e não inventa garantia de submissões antigas.
Backup após upgrade preserva chaves/evidências; falhas injetadas de DDL/backfill
restauram schema e dados. Readiness estrutural exige colunas/índice/guards novos,
mas não comprova readiness operacional. Consentimento/chaves e clock participam
do problema de retenção CX-01; downgrade exige restore explícito de backup.

## I. Testes e checks

| Check final | Resultado |
| --- | --- |
| Pytest completo local, SHA7c75d92 | **1983 passed, 1 skipped, 191,73 s** |
| Pytest completo independente Spec, mesma SHA | **1983 passed, 1 skipped, 190,41 s** |
| Standards independente | **677 passed/0skips, 70,67 s**, mais **1 passed/0skips, 2,10 s** |
| Ruff check | PASS |
| Ruff format --check | PASS;298 arquivos |
| compileall src/tests | PASS |
| pip check | PASS; nenhuma dependência quebrada |
| git diff --check | PASS |
| Gitleaks8.30.1 | PASS;4 commits de código/spec auditados, zero segredos; repetido incluindo o commit de relatório antes de push |

Execuções completas finais ocorreram com código/testes congelados na SHA revisada;
somente documentação de entrega foi preparada durante elas.

O skip único é `test_historical_v8_record_remains_loadable`, fixture de histórico
local não versionada (`tests/test_commercial_steering.py`). Nenhum novo skip foi
introduzido. Ambiente saneado sem credenciais comerciais, sockets IP bloqueados
no processo e nos filhos Python; SQLite real, assinaturas e payloads sintéticos.
Python 3.14.7, SQLite 3.50.4 e venv de dependências já instalado; nenhuma dependência
de runtime foi acrescentada.

Primeira suíte local:7failed/1967passed/1skip,160,96s; independente Spec:
7failed/1967passed/1skip,136,77s. Falhas eram projeções históricas de colunas e uso de
consulta do schema atual contra0015. Correções mantêm igualdade de todos os campos
antigos, verificam novos campos NULL e usam leitura SQL histórica antes do upgrade.
Não foi introduzido fallback de runtime para schema antigo. Duas suítes intermediárias
aprovadas ocorreram durante correções e não substituem as execuções finais da SHA
fixa. Regressões focadas:87passed/0skip,10,08s; continuidade/retention:
67passed/0skip,12,75s; purge/reuso de ID:1passed/0skip,1,99s.

| Requisito | Evidências principais |
| --- | --- |
| Tempo, consentimento, templates, resultado HTTP hipotético | test_whatsapp_policy.py:159 casos |
| Fronteira24 h, first receipt/replay/clock/restart, gates | test_telnyx_submission.py |
| Prova/marker estável, retry/unknown/crash, payload/key | test_telnyx_submission.py |
| Sender fake, zero chamadas inelegíveis e sem writer lock | fake_runner_receives_durable_identity; ineligible_runner_never_calls_sender; generic_fake_retryable_response |
| Replacement, prova retroativa, histórico ausente, purge/reuso | test_telnyx_submission.py + test_telnyx_submission_migration.py |
| Migration0020, backup/restore, rollback,3 providers e readiness | test_telnyx_submission_migration.py |
| Privacidade | test_commit_failure_rolls_back_and_redacts_sql_error; pure evidence repr; suíte anterior de logs e webhook |
| Tickets 01–09 e Meta/Twilio | Suíte integral final, incluindo status precoce/contradição, lifecycle, pause/handoff e histórico |

## J. Standards Review independente

PASS no candidato `7c75d92913e19c0e767543fea71cda7ff22fb023`, sem P1/P2
pendentes ou smell acionável confirmado. O revisor repetiu as três reproduções e
verificou guards, continuidade, purge, escopo e as comparações históricas.
Execução independente: **677 passed, 0 skipped, 70,67 s**; purge/reuso de ID:
**1 passed, 0 skipped, 2,10 s**, com IP bloqueado. Outras rodadas independentes:
492 passed/0skip,39,62s e177 passed/0skip,24,41s.

Achados P2 corrigidos: replacement de Delivery Attempt apagava marker; atribuição
retroativa de prova em tentativa terminal; ausência de histórico anterior tratada
como prova vazia. Guards e continuidade agora são exigidos estruturalmente e
reproduções permanecem como regressões. Não houve P1 confirmado.

## K. Spec Review independente

PASS no candidato `7c75d92913e19c0e767543fea71cda7ff22fb023`, sem P1/P2
pendentes, requisito incorreto ou ampliação indevida confirmado. Execução completa
independente final: **1983 passed, 1 skipped, 190,41 s**, com IP bloqueado.
O revisor confirmou as correções de replacement, prova retroativa, continuidade e
purge, e conferiu o relatório sem divergência material. Três regressões específicas
de replacement/prova retroativa também passaram em1,67s.

Revisão abrange spec/ADR, contratos externos, gates, máquina de estados,
SQLite/migrations/backup, privacidade, escopo e preservação Meta/Twilio. Template
offline e fingerprint canônico são limites explícitos, sem alegar garantia externa
ou implementação do sender. O orquestrador ainda precisa auditar a publicação.

## L. Registro central e ressalvas

[Issue 11](https://github.com/zazacknazzo/rj-studio-ai/issues/11) recebe o SHA de publicação,
evidência final e ressalvas abaixo. Nenhum checkbox de risco é encerrado nesta
entrega; CX-31 conserva a aprovação offline anterior.

| IDs | Evidência e saldo; dono/gate |
| --- | --- |
| CX-01 | Novos metadados/provas também exigem retenção/erasure/backup; Ticket13/antes de piloto. |
| CX-05 | High-water e negativos temporais cobertos offline; proveniência/clock/NTP real continuam operação/Tickets12–13. |
| CX-06 | Marker durável e resultados tardios preservados; não há recall autorização→HTTP. Sender/composição11–13. |
| CX-11/CX-33 | Canal positivamente verificado continua obrigatório; nenhum comando de ativação/rebinding. Operação/composição12–13. |
| CX-13 | E.164/canal/Customer conferidos; BSUID outbound negado. Identidade real/migração permanecem gate de composição. |
| CX-15 | UUID estável, conflito e unknown implementados/testados; bytes HTTP/replay real não comprovados. Sender11/aceite13. |
| CX-16 | Janela estrita/consentimento/template classificados offline; prova operacional/conta/opt-out real pendentes.11–13. |
| CX-17 | Integração funcional ainda incompleta: sem sender, rota, ativação ou conta real.11–13. |
| CX-19 | Execuções locais independentes não equivalem a CI ou auditoria do orquestrador.13. |
| CX-21 | Branch isolada, auditoria de segredos e preservação main/Baileys; merge/release dependem de autorização própria. |
| CX-24/CX-29/CX-30 | Raw HTTP/streaming, formatos desconhecidos e orçamento real2 s permanecem abertos.12–13. |
| CX-32 | Conflitos de delivery continuam bloqueadores, sem resolução/reenvio implícito. Operação12–13. |
| CX-34 | Consulta→LLM permanece com possível custo de chamada autorizada; saída cercada. Runtime/operação12–13. |

Novas ressalvas propostas, sem aceite de exceção:

- **CX-35 — BLOQUEADOR de sender: reprodução exata do request e proteção externa.**
  Origem ADR 0018/código7c75d92 e docs oficiais20/11. Dono Ticket 11, coordenação13.
  Gate antes de qualquer HTTP: vincular organização, método/path/query e bytes
  determinísticos à chave, desabilitar/unificar retries SDK, validar respostas e
  persistir evidências/tempos sem payload privado em logs. Fechamento exige código,
  testes de expiração/restart/colisão/timeout e auditoria do orquestrador; unknown
  não se torna reenviável por especificar esse contrato.
- **CX-36 — BLOQUEADOR operacional: obtenção e revogação de consentimento/templates.**
  Origem contratos internos ADR 0018. Donos operação/composição12–13, sob autorização.
  Gate antes de habilitação/piloto: fluxo autenticado com proveniência, escopo,
  frescor, revogação/opt-out e propósito, incluindo aprovação/pausa de template real.
  Fechamento exige prova implementada e testes concorrentes/restart mais aprovação;
  inserir fixtures ou uma referência opaca não verifica consentimento real.
- **CX-37 — REVISAR: destinatário BSUID de saída ainda não implementado.** Origem
  recipient_unproven/ADR 0018. Dono sender11/composição12. Gate antes de prometer
  respostas a números ocultos: contrato oficial de recipient/account/namespace,
  nenhuma inferência de telefone, testes de escopo/callbacks/identity e autorização.
  Até lá, entrada namespaced preservada e saída negada.

Demais riscos do registro mantêm seus donos/gates. Nenhuma limitação se considera
resolvida somente por constar em uma política ou teste offline.

## M. Isolamento e limites

Trabalho apenas na branch10, a partir da SHA exata. Push normal, sem merge/main.
Main confirmado em `af1c9eb862a4180ca6b9e537349e4f8abaa2bb29`; branch09 conserva
`c2cc68c0c714d8f8c642f7759f3799a90b3feae4`. Worktree Baileys preservado por comparação
de HEAD/status e hashes de272 arquivos. Nenhum código Baileys consta no diff.

Nenhum sender Telnyx, HTTP comercial, rota pública, onboarding, credencial real,
ativação de canal, template real, campanha/follow-up, SaaS, CRM ou alteração de
LLM/persona/grounding foi realizado. Documentação e operações GitHub de entrega
foram as únicas comunicações de rede autorizadas nesta tarefa. A validação é
offline; não prova WhatsApp real, latência2 s, sincronização ou prontidão de produção.
Ticket 11 não iniciado e depende de nova auditoria direta/autorização explícita.

## Arquivos alterados

- `docs/ARCHITECTURE.md`
- `docs/architecture/v1-ticket10-validation.md`
- `docs/automation-operations.md`
- `docs/decisions/0018-whatsapp-eligibility-and-submission-identity.md`
- `docs/decisions/README.md`
- `docs/specs/README.md`
- `docs/specs/V1-telnyx-coexistence-ticket-10.md`
- `src/rj_studio_ai/delivery.py`
- `src/rj_studio_ai/migrations/__init__.py`
- `src/rj_studio_ai/migrations/versions/0021_telnyx_submission_policy.py`
- `src/rj_studio_ai/persistence.py`
- `src/rj_studio_ai/telnyx_submission.py`
- `src/rj_studio_ai/whatsapp_policy.py`
- `tests/telnyx_channel_fixture.py`
- `tests/test_agentic_intake_migration.py`
- `tests/test_appointment_intake_migration.py`
- `tests/test_automation_operations.py`
- `tests/test_conversational_intake_migration.py`
- `tests/test_migrations.py`
- `tests/test_openai_metadata_migration.py`
- `tests/test_operational_event_journal.py`
- `tests/test_outbound_pause.py`
- `tests/test_telnyx_delivery_status.py`
- `tests/test_telnyx_lifecycle.py`
- `tests/test_telnyx_messages.py`
- `tests/test_telnyx_submission.py`
- `tests/test_telnyx_submission_migration.py`
- `tests/test_whatsapp_policy.py`
