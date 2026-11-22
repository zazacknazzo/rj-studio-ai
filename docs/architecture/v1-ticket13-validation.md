# Ticket 13 — validação final A–P, somente OFFLINE

22/11/2026, America/Sao_Paulo. **Entrega técnica: AGUARDANDO AUDITORIA FINAL DO
ORQUESTRADOR. AUD-01 ABERTO. Próximo gate operacional, PILOTO e PRODUÇÃO: NO-GO.**

Este CP8 consolida evidências existentes e a verificação documental da retomada.
Sua autorização limita-se a este relatório, handoff e registro na issue #11.
O escopo de T13 e as proibições estão na [spec13](../specs/V1-telnyx-coexistence-ticket-13.md)
e no [parecer T12](https://github.com/zazacknazzo/rj-studio-ai/issues/11#issuecomment-7069497120).
Nenhuma aprovação do orquestrador para T13 é declarada por esta entrega.

## A. Resumo executivo e parecer técnico

O candidato reúne um laboratório de recovery com autoridade/witness simulados,
quarentena offline, matriz de riscos, propostas de segurança/consentimento/retenção,
CI reproduzível, runbooks e plano de piloto não executado. As quatro perspectivas
independentes concluíram sem novo P1/P2 confirmado pendente **no escopo offline
inspecionado**, com limitações e falhas preservadas. Fontes: [CP7](ticket13-cp7-validation.md),
[evidências CP7](ticket13-cp7-evidence.json), [ADR0021](../decisions/0021-offline-recovery-authority-and-release-gates.md)
e revisões na seção N.

O [CI final do CP7, run44983569296](https://github.com/zazacknazzo/rj-studio-ai/actions/runs/44983569296),
foi conferido nesta retomada: SHA `58e2210f79a230facc40bee4902b92f6e50902d5`,
`completed/success`, **2262 PASS, 0 SKIP**, pytest 328,29 s. O
[job137089131601](https://github.com/zazacknazzo/rj-studio-ai/actions/runs/44983569296/job/137089131601)
registra o isolamento kernel Linux e os checks. A seção J distingue esse run da CI
que será disparada pelo commit documental CP8.

Parecer do implementador: favorável ao aceite técnico **somente OFFLINE**, submetido
à auditoria final. O laboratório não implementa a infraestrutura de frescor nem a
integração comercial real. Quarentena demonstrada não encerra AUD-01; health,
CI success e `simulation_ready` não concedem egress. As três decisões estão
separadas em P, conforme a [ordem de gates](../operations/telnyx-gates.md).

## B. Baseline, branch e SHA

| Referência | Valor conferido / significado |
| --- | --- |
| Repositório/origin | `https://github.com/zazacknazzo/rj-studio-ai.git` |
| Baseline aprovada T12 | `f1496be42732b7e57d317444d7ed0020997f0327` |
| Branch autorizada | `codex/telnyx-coexistence-13-readiness` |
| SHA de entrada CP8, local e origin | `58e2210f79a230facc40bee4902b92f6e50902d5` |
| Relação na entrada | Baseline ancestral; 9 commits à frente, 0 atrás; local/origin 0/0; working tree limpa |
| Main observada | `af1c9eb862a4180ca6b9e537349e4f8abaa2bb29`, somente leitura |
| Escrita | Usuário reconfirmou exclusividade desta execução CP8 em 22/11/2026; clone separado, nenhum WIP anterior sobrescrito |

Verificações próprias: clone da branch, `git fetch origin` com refs explícitas de
main/branch13, origin, branch, HEAD, remote-tracking refs, status, ancestry e diff.
Registro de continuidade: [handoff13](../handoffs/TICKET-13.md). Base remota
verificável: [commit T12](https://github.com/zazacknazzo/rj-studio-ai/commit/f1496be42732b7e57d317444d7ed0020997f0327),
[entrada CP8](https://github.com/zazacknazzo/rj-studio-ai/commit/58e2210f79a230facc40bee4902b92f6e50902d5)
e [main observada](https://github.com/zazacknazzo/rj-studio-ai/commit/af1c9eb862a4180ca6b9e537349e4f8abaa2bb29).
Exclusividade é coordenação humana, não lock distribuído, conforme [AGENTS](../../AGENTS.md).

A SHA final é obtida de origin **depois** do commit/push normal que versionar este
relatório; não se prevê o próprio hash. O vínculo imutável relatório→SHA→CI da
publicação CP8 fica no cabeçalho de entrega T13 e no comentário da
[issue #11](https://github.com/zazacknazzo/rj-studio-ai/issues/11).
Uma CI de SHA anterior não será apresentada como execução da SHA documental final.

## C. Inventário do diff e isolamento

O [diff T12→entrada CP8](https://github.com/zazacknazzo/rj-studio-ai/compare/f1496be42732b7e57d317444d7ed0020997f0327...58e2210f79a230facc40bee4902b92f6e50902d5)
contém **36 arquivos**, 5191 inserções e 13 remoções: docs21, tests8, scripts4,
src1, workflow1 e lock1. Inventário por finalidade:

| Grupo | Arquivos no diff anterior ao CP8 |
| --- | --- |
| Contrato, continuidade e índices | `docs/specs/V1-telnyx-coexistence-ticket-13.md`, `docs/specs/README.md`, `docs/decisions/0021-offline-recovery-authority-and-release-gates.md`, `docs/decisions/README.md`, `docs/handoffs/TICKET-13.md`, `docs/automation-operations.md` |
| Preparação operacional | `docs/operations/telnyx-gates.md`, `telnyx-recovery.md`, `telnyx-security-consent.md`, `telnyx-retention-backups.md`, `telnyx-ci.md`, `telnyx-observability.md`, `telnyx-runbooks.md`, `telnyx-pilot-plan.md` no mesmo diretório |
| Evidências/revisões | `docs/architecture/ticket13-cp7-validation.md`, `ticket13-cp7-evidence.json`, `ticket13-architecture-review.md`, `ticket13-spec-review.md`, `ticket13-spec-closure-review.md`, `ticket13-security-reliability-review.md`, `ticket13-operations-review.md` no mesmo diretório |
| Laboratório | `src/rj_studio_ai/offline_recovery.py`, `tests/offline_recovery_fixture.py`, `tests/test_offline_recovery.py` |
| Segurança de execução/CI | `.github/workflows/telnyx-offline.yml`, `requirements/ci.lock`, `scripts/assert_no_external_network.py`, `scripts/check_gitleaks_report.py`, `scripts/check_telnyx_offline.py`, `scripts/ci_offline.sh`, `tests/test_offline_network_guard.py` |
| Demais testes e histórico | `tests/test_telnyx_operational_readiness.py`, `tests/test_telnyx_asgi_load.py`, `tests/test_commercial_steering.py`, `tests/fixtures/historical/README.md`, `tests/fixtures/historical/live-record-v8.json` |

CP8 acrescenta este relatório e atualiza o handoff já existente: **somente dois
arquivos documentais** em relação a `58e2210f`; inventário acumulado de 37 arquivos.
Nenhum source, teste, workflow ou pin é alterado pelo CP8. Entre CP6 `995af20` e
`58e2210f`, o diff também se limita a evidências/handoff e comentário do lock, sem
mudança dos 86 pins ou arquivos funcionais. Fontes: [diff CP6→CP7](https://github.com/zazacknazzo/rj-studio-ai/compare/995af20ff7d9e9f592a23c544f09a2407bd1b7f0...58e2210f79a230facc40bee4902b92f6e50902d5)
e [CP7](ticket13-cp7-validation.md).

O único source novo de T13 é o laboratório; não há importação/montagem dele no
runtime principal. `main.py`, seleção de provider/configuração, Baileys e código de
inteligência V1 não integram o diff T13. A mudança de `test_commercial_steering.py`
apenas torna a fixture histórica versionada/hash-verificada, sem executar geração.
Referências: [Architecture](ticket13-architecture-review.md),
[main](../../src/rj_studio_ai/main.py), [config](../../src/rj_studio_ai/config.py),
[teste v8](../../tests/test_commercial_steering.py#L423) e seção J.

## D. Matriz de gates operacionais

A [matriz completa](../operations/telnyx-gates.md) mantém requisito, implementação,
evidência, lacuna, papel responsável e aceite para **CX-01–37, AUD-01–06 e AR-01–03**.
A tabela abaixo consolida a decisão atual; nomes de responsáveis e thresholds
propostos ainda precisam ratificação. Nenhum risco ou checkbox é encerrado no CP8.

| Gates | Evidência disponível e lacuna restante | Dono proposto / decisão |
| --- | --- | --- |
| AUD-01; AR-02 | [Recovery](../operations/telnyx-recovery.md), [testes](../../tests/test_offline_recovery.py) e [quarentena ASGI](../../tests/test_telnyx_asgi_egress.py): simulação e negação offline; faltam raízes, ledger completo e composição reais | Recovery/SRE/Segurança; ABERTO, bloqueia qualquer egress |
| CX-01 | [Matriz de 24 tabelas](../operations/telnyx-retention-backups.md): propostas e testes de integridade/replay; erasure e backups reais pendentes | Privacidade/DBA; bloqueia piloto |
| CX-02, CX-03, CX-04, CX-05, CX-08 | [Runbooks](../operations/telnyx-runbooks.md), [operações](../../tests/test_automation_operations.py), [mensagens](../../tests/test_telnyx_messages.py): pausa/resume/echo sintéticos; faltam workflow humano móvel, proveniência/clock reais | Operações/Integração/SRE; gates aplicáveis abertos |
| CX-06, CX-15, CX-32, CX-35 | [Sender integration](../../tests/test_telnyx_sender_integration.py), [adversarial](../../tests/test_telnyx_sender_adversarial.py), [status](../../tests/test_telnyx_delivery_status.py): binding/key/unknown/conflito; faltam transporte/reconciliação reais, permanece janela marker→HTTP | Engenharia/Operações/Segurança; bloqueia piloto |
| CX-07, CX-09, CX-24, CX-25 | [Segurança](../operations/telnyx-security-consent.md), [auth](../../tests/test_telnyx_authentication.py), [HTTP](../../tests/test_telnyx_http.py), [durabilidade](../../tests/test_telnyx_asgi_durability.py): negativos offline; faltam IAM/TLS/proxy/chave/libsodium/NTP no deploy | Segurança/SRE; bloqueia piloto |
| CX-10, CX-11, CX-33 | [Plano](../operations/telnyx-pilot-plan.md), [lifecycle](../../tests/test_telnyx_lifecycle.py): conta/número +55, Coexistence, sync e binding atuais não verificados | Responsável da conta/Integração; bloqueia piloto |
| CX-12, CX-13, CX-14, CX-37 | [Mensagens](../../tests/test_telnyx_messages.py), [status](../../tests/test_telnyx_delivery_status.py), [submission](../../tests/test_telnyx_submission.py): dedupe/escopo sintéticos; contratos reais e migração pendentes; outbound somente E.164 | Integração/Arquitetura; revisar, sem promessa de BSUID |
| CX-16, CX-36 | [Consentimento](../operations/telnyx-security-consent.md), [corridas](../../tests/test_telnyx_operational_readiness.py), [política](../../tests/test_whatsapp_policy.py): regra temporal/ordem transacional; captura/audit/provas reais e templates operacionais ausentes | Privacidade/Operações; bloqueia piloto |
| CX-17, CX-22 | [ASGI](../../src/rj_studio_ai/telnyx_asgi.py), [readiness](../../tests/test_telnyx_asgi_observability.py): composição isolada; integração comercial real ausente e saída false | Integração/SRE; nenhum health libera operação |
| CX-18, CX-20 | [Observabilidade](../operations/telnyx-observability.md), [plano](../operations/telnyx-pilot-plan.md): cargas locais, sem custo/latência E2E ou tarifas atuais verificados | Produto/Financeiro/Operações; piloto não executado |
| CX-19, CX-21; AUD-02, AUD-03, AUD-06 | [CI](../operations/telnyx-ci.md), [CP7](ticket13-cp7-validation.md), seções J/N: CI/revisões/fixture/focal demonstrados no escopo descrito; auditoria final/release permanecem | CI/Release/Orquestrador; evidência acrescentada, sem fechamento |
| CX-29, CX-30 | [Runbooks](../operations/telnyx-runbooks.md), [carga](../../tests/test_telnyx_asgi_load.py): 422 durável e 503/replay; fila, alertas, retries/failover e ACK de rede reais não demonstrados | Operações/Integração/SRE; bloqueia piloto |
| CX-31 | Estado histórico: resolução SOMENTE OFFLINE previamente aprovada no [parecer T08, seção G da issue #11](https://github.com/zazacknazzo/rj-studio-ai/issues/11); aceite real permanece CX-14 | Preservar histórico da issue, sem novo fechamento |
| CX-26 | [Issue #12](https://github.com/zazacknazzo/rj-studio-ai/issues/12) e matriz: aceite conversacional próprio pendente; inteligência congelada em T13 | Produto/Orquestrador; bloqueia piloto, fora da implementação CP8 |
| CX-23, CX-27, CX-28; AUD-05 | [Matriz](../operations/telnyx-gates.md), [AGENTS](../../AGENTS.md), [issue #13](https://github.com/zazacknazzo/rj-studio-ai/issues/13): SaaS/isolamento/router exigem decisões e escopo próprios | Produto/Arquitetura; futuros, sem expansão T13 |
| CX-34; AR-01 | [Generation pause](../../tests/test_generation_pause.py): custo residual após gate/pausa continua ressalva; nenhum LLM alterado | Produto/Operações; revisar e comunicar limite |
| AUD-04; AR-03 | [Índices/spec](../specs/README.md), [runbook atual](../automation-operations.md), migrations/testes referidos na matriz: história preservada; SQL concentrado requer revisão continuada | Engenharia; revisar, sem refactor CP8 |

As classificações e checkboxes originais pertencem à [issue #11](https://github.com/zazacknazzo/rj-studio-ai/issues/11).
Evidência adicional de CI ou laboratório não muda sua classificação automaticamente.

## E. AUD-01: recovery, autoridade, witness e limitações

O [ADR0021](../decisions/0021-offline-recovery-authority-and-release-gates.md)
parte do problema original: restore do SQLite pode perder simultaneamente markers,
acceptance, pausa, lifecycle e revogação de consentimento. HMAC, schema válido,
contador e tabela no mesmo snapshot não provam frescor. O store genérico legado
continua permissivo fora da composição fechada; o laboratório não o corrigiu como
integração operacional. Evidência explícita: [teste do restore anterior ao claim](../../tests/test_telnyx_asgi_egress.py#L35)
e [Architecture](ticket13-architecture-review.md).

| Camada | O que foi efetivamente demonstrado | O que não foi demonstrado |
| --- | --- | --- |
| Quarentena offline | [Constructor](../../src/rj_studio_ai/offline_recovery.py#L195) exige store quarantinado; [release](../../tests/test_offline_recovery.py#L87) não habilita autorização local; readiness retorna `operational_egress=False` em sucesso/falha | Quarentena de um deploy/worker/transporte comercial |
| Autoridade/witness/ledger simulados | [SQLiteAuthority/SQLiteWitness](../../tests/offline_recovery_fixture.py) em arquivos separados: epoch, revisão CAS, digest, papéis, provas, audit e witness antes do commit da authority | Serviços externos autenticados, linearizabilidade/durabilidade físicas, IAM e backups administrativamente independentes |
| Recovery/reconciliação | [Testes de snapshot/restore](../../tests/test_offline_recovery.py) antes de claim/marker/pausa/disconnect/revoke e após acceptance; inventário externo órfão conservado; old work bloqueado | Completude do inventário de todos os caminhos de submissão reais ou reconciliação com provedor |
| Integração de envio real | Nenhuma: [laboratório](../../src/rj_studio_ai/offline_recovery.py) não recebe transporte/callback; [sender T11](v1-ticket11-validation.md) usa exchange injetado | HTTP comercial, credenciais, conta, ativação, egress, piloto ou produção |

O protocolo ensaiado vincula resource, boot/session nonce e fingerprint consistente
do snapshot; `begin` eleva epoch/revision e invalida releases anteriores. Leituras
de authority/witness não usam permit em cache. Cada mutação é cercada por
revision+digest; rollback dentro da mesma epoch, mesma revisão contraditória,
indisponibilidade e commit parcial witness→authority fecham a sessão. Fonte:
[código](../../src/rj_studio_ai/offline_recovery.py),
[fixture](../../tests/offline_recovery_fixture.py) e
[testes de rollback/crash](../../tests/test_offline_recovery.py#L258).

O inventário write-ahead conserva identidade lógica, submission key e request
digest, inclusive itens ausentes do snapshot. Unknown/conflict não recebem outra
key nem retry automático após 24 h; mesmo prova `accepted`/`not_submitted` mantém
trabalho pré-recovery bloqueado. Reserva revalida proofs/TTL/inventário na mutação
CAS. Aprovação exige pessoa distinta do recoverer e provas scoped atuais de
binding/sync/consentimento/janela. Fontes: [contrato de recovery](../operations/telnyx-recovery.md),
[testes de old work](../../tests/test_offline_recovery.py#L220),
[Spec e TTL](ticket13-spec-review.md), [conclusão Spec](ticket13-spec-closure-review.md).

**AUD-01 permanece ABERTO e bloqueador de qualquer egress real.** Ainda são
obrigatórias evidências externas de authority linearizável, witness independente,
raízes/restore/IAM separados, resposta autenticada com desafio/escopo, cobertura de
todo I/O pelo ledger antes de HTTP, proofs reais atuais, release autenticado e
fault injection na composição de destino. `AuthorityReply` é dataclass, não
autenticação de rede; refs opacas de fixture não provam fato operacional. Rollback
simultâneo de todas as raízes não pode ser detectado apenas por essas raízes
restauradas. Nenhuma dessas lacunas fecha por simulação ou CI. Fonte:
[lista de aceite externo](../operations/telnyx-recovery.md) e
[Security/Reliability](ticket13-security-reliability-review.md).

## F. Segurança e permissões operacionais

O [documento de segurança](../operations/telnyx-security-consent.md) separa aplicação,
operador, recoverer, approver, verificador, Segurança/SRE e product owner/orquestrador.
Papéis são propostas; não há operadores empresariais provisionados. Admin T05 usa
bearer estático, permissões/allowlist e `operation_id`/`expected_revision`;
IDs opacos, owner/episode/revision não autenticam. Negativos constam em
[test_automation_operations.py](../../tests/test_automation_operations.py).

O laboratório verifica papéis separados, revogação, aprovação por ator distinto,
CAS e audit sem tokens; isso não é IdP/PKI implantado. Faltam TLS/ingress restrito,
gestão/rotação/expiração de credenciais, aquisição confiável de public key,
credential→org/profile/número/WABA, libsodium/NTP, proxy/APM com redação efetiva,
rate limits e drills de perda/outage. Fontes: [recovery tests](../../tests/test_offline_recovery.py#L171),
[auth Telnyx](../../tests/test_telnyx_authentication.py) e
[segurança/gates de deploy](../operations/telnyx-security-consent.md).

Nenhuma credencial comercial, PII, banco real, sessão, QR ou log sensível integra a
entrega. Os scanners e sua triagem estão em J; isso não constitui certificação de
ausência absoluta de segredo. Nenhuma chamada Telnyx real, ativação ou rotação foi
executada, conforme o [escopo/handoff](../handoffs/TICKET-13.md).

## G. Consentimento, revogação e política WhatsApp

O [workflow proposto](../operations/telnyx-security-consent.md) exige finalidade,
escopo, identidade/canal, referência restrita da prova, versão do aviso,
proveniência e validade. Conversa ativa, echo, histórico importado ou sync não
concedem consentimento. Opt-in e janela são gates distintos; fixture/ref opaca
não verifica consentimento real. Captura/grant/revoke auditados ainda não compõem
um workflow operacional. A proposta de revalidação em 90 dias requer decisão de
privacidade/produto/jurídico, sem validade legal universal declarada.

A política implementada T10 exige source confiável, primeiro recibo durável,
clock high-water, consentimento atual e janela estrita **menor que 24 h**;
exatamente 24 h nega. Echo, assinatura, receipt, status, edit/revoke e reconnect
não abrem janela. Template exige aprovação atual verificada; V1 não envia template
nem converte free-form fora da janela. Outbound permanece somente E.164.
Evidências: [política](../../src/rj_studio_ai/whatsapp_policy.py),
[testes](../../tests/test_whatsapp_policy.py), [submission](../../tests/test_telnyx_submission.py)
e [13 probes Spec](ticket13-spec-closure-review.md).

As duas ordens revoke→authorize e marker→revoke foram exercitadas com SQLite real
e fatos sintéticos: revogação commitada primeiro nega; marker primeiro preserva a
possibilidade de envio em voo, sem recall. O teste atualiza consent diretamente
sob `BEGIN IMMEDIATE`; não cria API de captura/revogação de produção.
Fonte: [test_telnyx_operational_readiness.py](../../tests/test_telnyx_operational_readiness.py).

Contratos públicos foram examinados pelo revisor Spec em 22/11/2026; a atribuição
e os links oficiais estão no [relatório original](ticket13-spec-review.md).
CP8 inspecionou esse registro, sem alegar nova validação de conta/política comercial.
Evidência individual atual e aprovação operacional continuam gates CX-16/CX-36.

## H. Eventos não suportados, alertas e retries

Eventos autenticados não suportados, mídia/localização/futuro e lote inválido
continuam **422 com observação agregada durável**, sem criar inbound ou sucesso
vazio; falha ao persistir o agregado retorna **503**. O agregado tem razões finitas,
contagem/primeiro/último instante, sem payload privado ou identificação de Customer.
Conta observações, não Messages únicas; não permite reconstruir conteúdo nem
identificar sozinho um caso humano. Evidências: [ASGI](../../src/rj_studio_ai/telnyx_asgi.py),
[observabilidade tests](../../tests/test_telnyx_asgi_observability.py) e
[probes operacionais](ticket13-operations-review.md).

O [runbook CX-29](../operations/telnyx-runbooks.md) exige fila restrita, fonte
autorizada para identificar o caso, operador designado, pausa antes do humano,
alerts de 422/503 e tratamento de retries/failover esgotados. Esses componentes
operacionais **não estão implantados**. Se não houver identificação segura e
tratamento humano, o piloto não inicia. Não responder 2xx para esconder rejeição,
baixar mídia automaticamente, inventar conteúdo ou fabricar novo ID para retry.

Replays de ingresso repetem o envelope sob dedupe/commit antes do ACK; isso é
distinto de retentar outbound ambíguo. Unknown/409/422/timeout no sender não
autorizam reenvio cego nem nova submission key. Fontes: [runbooks](../operations/telnyx-runbooks.md),
[sender adversarial](../../tests/test_telnyx_sender_adversarial.py) e
[Spec/External Contract](ticket13-spec-review.md).

## I. Retenção, LGPD e backups

A [matriz de retenção](../operations/telnyx-retention-backups.md) inventaria as
**24 tabelas** migradas até 0023, authority/witness/audit simulados, backups/WAL/SHM/
freepages e evidências CI. Cada linha distingue finalidade/dados, proposta de prazo,
holds, minimização, dedupe/reuso de identificadores, restore e aceite. O revisor
Operational conferiu a matriz contra schema SQLite sintético real:
[evidência](ticket13-operations-review.md).

Prazos de conteúdo de 90 dias, intakes de 30 dias, audit de 180 dias e backups de
até 30 dias são **propostas**, sujeitas a necessidade/base legal/decisão apropriada.
Unknown, conflito, fences e identidades críticas não podem ser apagados por mera
idade. Sem expurgo automático não significa retenção eterna autorizada. O purge
existente de conteúdo/terminais não implementa toda a política nem secure erase;
delivery attempts podem sair em cascade, enquanto receipts/journal/request identity
retidos preservam parte da proteção. Fonte: [matriz e procedimento](../operations/telnyx-retention-backups.md).

Hash/MAC não são promessa de anonimização. Erasure precisa inventariar logs/APM,
cópias, WAL/freepages, backups e holds; tombstones/anti-reuso/rotação e expiração
exigem desenho/testes/aprovação próprios. Não houve novo purge, expurgo real,
cryptoerasure nem declaração de conformidade integral LGPD. Evidências de replay/
purge/migrations: [messages](../../tests/test_telnyx_messages.py),
[submission](../../tests/test_telnyx_submission.py),
[sender adversarial](../../tests/test_telnyx_sender_adversarial.py),
[migrations](../../tests/test_migrations.py) e
[submission migration](../../tests/test_telnyx_submission_migration.py).

Backup proposto usa snapshot consistente/SQLite backup API, manifest/schema/hash,
criptografia e ACL; não cópia de banco vivo ignorando WAL. RPO 15 min/RTO 60 min
são propostas não comprovadas no destino. Restore/rollback começa sem egress,
com inventário/reconciliação/provas atuais e raízes externas independentes.
Backups antigos não renovam consentimento nem autorizam trabalho perdido.
Fontes: [backup/restore](../operations/telnyx-retention-backups.md) e [recovery](../operations/telnyx-recovery.md).
CX-01 e AUD-01 seguem abertos.

## J. CI, dependências, Gitleaks e toolchain

| Run | SHA específica | Resultado observado e atribuição |
| --- | --- | --- |
| [44981309346, CP5](https://github.com/zazacknazzo/rj-studio-ai/actions/runs/44981309346) | `988efabe39611821035663dbae24a266b71bfca5` | Success recuperado no CP7; [registro](ticket13-cp7-evidence.json) |
| [44981650933, CP6](https://github.com/zazacknazzo/rj-studio-ai/actions/runs/44981650933) | `995af20ff7d9e9f592a23c544f09a2407bd1b7f0` | Success, 2262 PASS/0 SKIP, 224,28 s, log inspecionado na retomada CP7 |
| [44983247843, primeiro CP7](https://github.com/zazacknazzo/rj-studio-ai/actions/runs/44983247843) | `c06b1a90cca1a2658b75c23a237aa626228c5ca4` | **Failure**, Ruff format nos blocos Python Architecture/Operations; pytest não iniciou; falha preservada |
| [44983569296, CP7 corretivo](https://github.com/zazacknazzo/rj-studio-ai/actions/runs/44983569296) | `58e2210f79a230facc40bee4902b92f6e50902d5` | **Completed/success; 2262 PASS, 0 SKIP, 328,29 s**; metadados e log do job137089131601 inspecionados no CP8 |

A correção [58e2210f](https://github.com/zazacknazzo/rj-studio-ai/commit/58e2210f79a230facc40bee4902b92f6e50902d5)
formatou apenas blocos Python dos relatórios; ASTs foram comparadas iguais a
`c06b1a9`. O check anterior à importação não cobria esses arquivos; depois da
importação Ruff check/format de 356 arquivos e diff check passaram. A falha não é
apagada nem reclassificada. Fontes: [CP7](ticket13-cp7-validation.md) e
[JSON](ticket13-cp7-evidence.json).

O [workflow](../../.github/workflows/telnyx-offline.yml) fixa actions por SHA,
`contents:read`, checkout sem persistir credenciais, 86 distribuições no
[lock](../../requirements/ci.lock), Gitleaks 8.30.1 com checksum e artifacts de
14 dias. Pacotes/advisories/downloads públicos ocorrem antes de `unshare --net`;
Ruff/format/compileall/pip check/diff/pytest ficam no namespace, cuja
[asserção](../../scripts/assert_no_external_network.py) verifica somente loopback
e nenhuma default route IPv4/IPv6. O log do run44983569296 confirma essa fronteira.
Não houve conexão com conta/API Telnyx para instalar/auditar ferramentas públicas.

O guard Python complementar sanitiza ambiente, usa temporários 0700, nega APIs
IPv4/IPv6/DNS e é herdado por filhos; [nove testes](../../tests/test_offline_network_guard.py)
exercitam processos novos. Guard Python macOS não equivale a isolamento kernel nem
cobre binários nativos. Fontes: [runner](../../scripts/check_telnyx_offline.py),
[ci_offline.sh](../../scripts/ci_offline.sh) e [documentação CI](../operations/telnyx-ci.md).

Ambiente observado localmente no CP8: Python **3.14.7**, SQLite **3.50.4**, pip
**26.3**, pytest **9.2.0**, Ruff **0.17.6**, venv próprio e **86 pins/0 divergências**.
O CI remoto observado usa Linux Python **3.12.16**; não se alega Linux 3.14.
O P3 do comentário Linux3.14 foi corrigido no CP7 sem mudar pins. O lock fixa
versões, não hashes universais de wheels/plataformas. Referências:
[CP7/ambiente](ticket13-cp7-validation.md), [lock](../../requirements/ci.lock) e
log do [CI corretivo](https://github.com/zazacknazzo/rj-studio-ai/actions/runs/44983569296).

Pip-audit do CP7: **87 entradas, 86 auditáveis, zero pacotes com advisories
reportados**, app local não indexada explicitamente skipped. Esse skip de audit
não é skip de pytest. O CI corretivo também registra `No known vulnerabilities
found`; é consulta pontual, não garantia futura. CP8 não atribui a si a consulta
local anterior. Fonte: [JSON CP7](ticket13-cp7-evidence.json) e run acima.

**Gitleaks: 3 findings históricos brutos na árvore, triados como falsos positivos;
não zero achados na árvore.** Contextos: digest público de schema no relatório T11,
prosa de eval e hash sintético de operador em fixture. A
[triagem versionada](../../scripts/check_gitleaks_report.py) compara path/linha/regra
e hash do arquivo integral, sem novos ignores; achado novo/alterado falha. Range T13
exige zero hits, separado da árvore. O [Security review](ticket13-security-reliability-review.md)
executou scan próprio e preserva exit1 bruto/exit0 da triagem; o log44983569296
também confirma exatamente 3 históricos. Nada disso declara que a árvore teve zero
detecções ou encerra CX-21.

A fixture v8 original recuperada tem **46.181 bytes**, SHA256
`3d849ff3465d44cf20898aa170e72c08cc99b12e2f1b3266324754818291451e`, schema8,
10 casos sintéticos e criação histórica em 04/10/2026. [Proveniência](../../tests/fixtures/historical/README.md),
[teste hash/parse](../../tests/test_commercial_steering.py#L423) e comparações diretas
dos revisores [Spec](ticket13-spec-review.md)/[Architecture](ticket13-architecture-review.md)
confirmam cópia byte a byte, não geração nova. Isso remove a dependência pessoal
do arquivo e o skip histórico de pytest. Demonstra leitura compatível daquele
registro; não revalida modelo, naturalidade humana, geração, preços, latência atual
ou E2E WhatsApp. CP8 também conferiu tamanho/hash, sem chamar LLM.

Para a publicação CP8, o push normal deverá disparar outro run pelo workflow da
branch. A [entrega T13 na issue #11](https://github.com/zazacknazzo/rj-studio-ai/issues/11)
registrará **a SHA final efetivamente consultada e o resultado do run com
`head_sha` exatamente igual**, após sua conclusão. Este arquivo não antecipa
resultado de CI pós-commit. Se houver falha, preservá-la e corrigir somente o
necessário documental, por novo commit normal; nunca atribuir o success de
`58e2210f` a outra SHA.

## K. Performance e observabilidade

As amostras abaixo são as do CP5, documentadas em
[observabilidade](../operations/telnyx-observability.md) e exercitadas pelo
[teste de carga](../../tests/test_telnyx_asgi_load.py): ASGI em processo, assinatura
sintética, macOS/Python3.14.7/SQLite3.50.4, WAL/full e concorrência 8.

| Amostra CP5 | Resultados | p50 / p95 / p99, segundos |
| --- | --- | --- |
| 128 envelopes únicos | 128×204, uma admissão por Message | 0,00551 / 0,06675 / 0,19335 |
| 128 envelopes duplicados | 128×204, dedupe lógico | 0,01688 / 0,07273 / 0,11029 |
| 32 envelopes com lock SQLite | 32×503 e zero Messages; depois, mesmos envelopes→32×204/32 admissões, zero outbound | 0,58143 / 0,59694 / 0,59734 |

O teste permite backpressure 503 sob contenção, repete exatamente os envelopes
após drain e rejeita late success. Os percentis são amostras locais, não SLA;
integrais/CI podem ter outros números e não se seleciona somente a melhor amostra.
Budget de aplicação 1,35 s de trabalho/1,5 s total e alvo externo conservador 2 s
não provam proxy/TLS/rede/fsync real. O revisor registrou divergência documental
2 s/5 s e conservou o gate de 2 s, sem afrouxamento implícito. Fontes:
[ASGI](../../src/rj_studio_ai/telnyx_asgi.py), [Spec review](ticket13-spec-review.md)
e [durabilidade](../../tests/test_telnyx_asgi_durability.py).

Há métricas finitas locais de status/buckets/rejeição durável. Exporters/alertas
operacionais, backlog, operador, autoridade externa e observação do provider são
requisitos propostos, não serviços implantados. A matriz cobre p50/p95/p99,
204/422/503, dedupe, assinatura, quarantine, lifecycle, unknown/conflict,
unsupported, SQLite e intervenção, sem PII/IDs arbitrários em labels. Targets
históricos CX-20/#6 permanecem **p95 E2E ≤8 s** e **custo LLM ≤US$10/1000 replies
completas**, ainda sem prova real. Acceptance, delivered e read são medidas
distintas. Fonte: [matriz de observabilidade](../operations/telnyx-observability.md).

## L. Runbooks, rollback e incidentes

Os [16 runbooks](../operations/telnyx-runbooks.md) cobrem boot seguro, disconnect,
reconnect/sync, assumir humano, pausa/resume, unknown, conflito, SQLite, webhook,
restore, retries/failover, rotação/perda, desativação emergencial, rollback de
versão, encerramento de piloto futuro e unsupported/humano. Trazem papel dono,
pré-condições, ações/evidência e proibições; não são autorização de execução.
O [Operational review](ticket13-operations-review.md) inspecionou os 16 e executou
nove probes próprios, incluindo receipt histórico versus estado atual.

Pausa antecede atendimento humano e é seguida de GET do estado/revision atuais;
receipt idempotente antigo não prova estado corrente. Resume não reconcilia
unknown/conflict, não restaura fila antiga e não prova consent/janela. Marker
anterior à pausa pode estar em voo; não há recall prometido. Evidências:
[operações administrativas](../../tests/test_automation_operations.py),
[probes de operações](ticket13-operations-review.md) e
[corrida após marker](../../tests/test_telnyx_sender_integration.py#L235).

Incidente futuro exige suspender saídas/revogar autoridade, preservar in-flight/
unknown/audit e obter evidência antes de reconciliar. Rollback de código preserva
DB/ledger/fences compatíveis; não restaura banco antigo para repetir trabalho,
não apaga filas/keys e não assume downgrade operacional de schema0023. Restore
depende de autorização própria e quarentena/recovery. Fontes: [runbooks](../operations/telnyx-runbooks.md),
[retention/backups](../operations/telnyx-retention-backups.md), [recovery](../operations/telnyx-recovery.md).
CP8 não executou nenhum desses procedimentos em infraestrutura real.

## M. Plano de piloto sem execução

O [plano](../operations/telnyx-pilot-plan.md) exige duas autorizações futuras:
primeiro auditoria T13 e validação de infraestrutura/antirollback/IAM/ingress;
depois piloto delimitado após resolver os bloqueadores aplicáveis ou obter
exceção formal específica, com dono/mitigação/prazo. **Nenhuma exceção é aceita
nesta entrega.** Produção exige decisão posterior própria.

Conta/número secundário +55/Coexistence/sync, credencial vinculada, consentimento
de cada participante, operadores/fila/alerts, versão/SHA, medição/custo,
rollback e parada precisam evidência nominal em registro restrito. Não se presume
elegibilidade individual por documentação pública. A proposta de até cinco
voluntários, 20 respostas, 60 minutos e US$5 é limite de smoke sujeito à aprovação,
não autorização financeira nem prova de escala. Fonte: [checklist e limites](../operations/telnyx-pilot-plan.md).

Gatilhos propostos de parada incluem duplicação/escopo indevido, consent ausente,
unknown/conflict, perda de operador/fence/auth/clock/DB, binding/lifecycle alterado,
risco de PII, unsupported sem tratamento, ACK fora do contrato e limites atingidos.
Nenhuma conta foi acessada, número conectado, credencial comercial criada,
mensagem enviada, worker ativado ou piloto iniciado. O plano permanece **NÃO
EXECUTAR**, conforme [spec](../specs/V1-telnyx-coexistence-ticket-13.md) e autorização CP8.

## N. Testes e quatro revisões independentes

As contagens abaixo pertencem a execuções distintas **que se sobrepõem**.
Não são somadas como cobertura única, e execução de revisor não é atribuída ao
implementador ou ao orquestrador. Logs/JUnit/hashes recuperados estão no
[JSON CP7](ticket13-cp7-evidence.json), [validação CP7](ticket13-cp7-validation.md)
e [conclusão Spec](ticket13-spec-closure-review.md).

| Execução / responsável | Resultado | Natureza da evidência |
| --- | --- | --- |
| Integral primary anterior | 2262 PASS/0 SKIP, 418,22 s | Herdada; log/JUnit inspecionados no CP7, não reexecutada pelo CP8 |
| Integral revisor Spec anterior | 2262 PASS/0 SKIP, 522,38 s | Herdada; receipt/log/JUnit e 194 hashes before/after iguais, correspondentes a CP5/CP6 |
| Clone limpo anterior | 72 PASS/0 SKIP, 56,02 s | Ensaio local herdado em995af20; não autenticação de segunda conta |
| Retomada primary CP7 antes de editar | **73 PASS/0 SKIP, 42,74 s** | Execução própria daquela retomada, não do CP8 |
| Revisor Spec na retomada CP7 | **13 probes PASS/0 SKIP, 18,66 s** | Execução independente do revisor; inclui negativos TTL e contrato |
| CI corretivo CP7 | **2262 PASS/0 SKIP, 328,29 s** | GitHub Actions44983569296 naSHA58e2210f; metadados/log conferidos pelo CP8 |
| Retomada CP8 antes de editar | **20 PASS/0 SKIP, 7,15 s** | Execução própria em clone/venv separados: sender integration sob runner sanitizado/guard Python |

Reprodução focal efetivamente executada no CP8, a partir da raiz do clone:

```sh
../venv/bin/python scripts/check_telnyx_offline.py --python ../venv/bin/python \
  --output ../cp8-focal tests/test_telnyx_sender_integration.py
```

JUnit CP8: 20 tests, 0 errors, 0 failures, 0 skipped, 7,153 s; SHA256
`7ae3fb02eeee64e50bc05c0942ba8c8aba774c9874bd11b9fa59c324da02b487`.
O artefato local é evidência temporária, não fixture privada exigida para reproduzir
o comando. A CI da publicação repetirá o teste versionado na SHA que receber;
seu resultado será vinculado na issue após observação, conforme J.

Após a redação, o executor CP8 também executou Ruff check **PASS**, Ruff format
`--check` **PASS/357 arquivos**, compileall de src/tests/scripts **PASS**, pip check
**PASS** e `git diff --check` **PASS**. Conferência documental própria confirmou as
16 seções A–P e todos os destinos de links locais existentes. O
[handoff](../handoffs/TICKET-13.md) registra esses checks; o diff de publicação
fica limitado aos dois arquivos documentais descritos em C.

| Perspectiva independente | Resultado e referência persistida | Limite/atribuição |
| --- | --- | --- |
| Architecture/Standards | [Relatório](ticket13-architecture-review.md): 18 focais finais/0 SKIP, 14,95 s; checks próprios; sem novo P1/P2 confirmado pendente offline | Não executou LinuxCI, pip-audit ou Gitleaks; inspeção não é execução desses serviços |
| Spec/External Contract | [Original](ticket13-spec-review.md) + [adendo de conclusão](ticket13-spec-closure-review.md): integral anterior verificada e 13 probes próprios/0 SKIP, 18,66 s; PASS offline | Original “integral em andamento” preservado; adendo registra conclusão, sem fingir nova integral |
| Security/Reliability | [Relatório](ticket13-security-reliability-review.md): 24 focais finais/0 SKIP, 16,57 s; Gitleaks próprio/triagem e range; PASS offline | 15 probes recovery +9 guard; não reexecutou integral nem consulta audit online |
| Operational Readiness | [Relatório](ticket13-operations-review.md): 9 probes/0 SKIP, 15,78 s; sem novo P1/P2 confirmado pendente offline | Dez comportamentos distribuídos em nove casos, sem operação humana móvel/infra real |

São **quatro perspectivas**, não cinco: a conclusão Spec é adendo da mesma
perspectiva. Revisores são agentes distintos, com host e em parte venv compartilhados;
não há alegação de contas/infraestruturas independentes. CP8 usa os relatórios
existentes e não convoca novas revisões nem atribui a si suas execuções.

Falhas e correções relevantes permanecem verificáveis:

- **P2 TTL/reserva de laboratório:** dois probes Spec falharam antes da correção;
  proofs/TTL/inventário passaram a ser revalidados dentro do CAS e o alias usa o
  mesmo caminho. Os negativos originais passaram sem relaxar asserts. [Spec](ticket13-spec-review.md),
  [closure](ticket13-spec-closure-review.md), [fixture](../../tests/offline_recovery_fixture.py#L365).
- **Cobertura pause/disconnect incorreta:** ramos inicialmente só revogavam consent;
  corrigidos para echo e lifecycle reais no adapter/journal sintético, sem afirmar
  evento de conta comercial. [Spec](ticket13-spec-review.md), [testes](../../tests/test_offline_recovery.py#L125).
- **Architecture:** uma falha de probe esperava RecoveryClosed diretamente da fake
  authority, que propaga OSError; somente probe externo corrigido. Candidatos de
  colisão/TTL foram corrigidos antes de sua primeira execução; esse revisor não
  alega ter reproduzido a versão antiga. [Relatório](ticket13-architecture-review.md).
- **Operations:** primeira rodada 5 PASS/3 FAIL por campo incorreto do probe e
  expectativa de purgeunknown divergente do contrato de FK/rollback; probes
  externos corrigidos, sem mudança de produto. [Relatório](ticket13-operations-review.md).
- **Documentação/toolchain:** comentário Linux3.14, prazo de artifacts e GET após
  receipt histórico foram alinhados; falha CI de formatação e correção preservadas
  em J. CP7 também registra fetchDNS, instalação prematura sem hatchling, normalização
  de EOF e tentativa de download SSL repetida com truststore nativo, sem desativar
  TLS. Nenhuma tentativa falha é rotulada PASS. [CP7](ticket13-cp7-validation.md),
  [handoff](../handoffs/TICKET-13.md), [Operations](ticket13-operations-review.md).

## O. Riscos, checkpoints, handoff e ressalvas

O [handoff13](../handoffs/TICKET-13.md) preserva CP0 spec/ADR; CP1 matriz;
CP2 recovery; CP3 segurança/consentimento; CP4 retention/backups; CP5 CI/fixture/
carga; CP6 runbooks/plano; CP7 quatro revisões/correções/evidências; CP8 este
relatório e entrega na issue. Registra também falhas e a próxima ação exata.
A publicação é commit/push normal somente na branch13, sem force, merge ou main.

A [issue #11](https://github.com/zazacknazzo/rj-studio-ai/issues/11) e seus 13 comentários
existentes foram lidos nesta retomada antes da redação; o último parecer existente
é a autorização offline T12→T13. O cabeçalho T13 será acrescentado com link
versionado/SHA/CI/revisões, preservando histórico e todos os 37 checkboxes
existentes. Nenhum risco será encerrado, nenhuma exceção aceita e nenhuma aprovação
do orquestrador inferida. Evidência de autoridade continua com os autores/execuções
identificados em N.

Bloqueadores residuais para decisão do orquestrador:

- **AUD-01/AR-02:** raízes independentes, ledger completo, proofs atuais,
  autenticação/release e composição de todos os caminhos reais ainda ausentes;
  store legado permissivo não é solução operacional. [Recovery](../operations/telnyx-recovery.md).
- **CX-01:** retenção/erasure/tombstones/backups e restore reais. [Matriz](../operations/telnyx-retention-backups.md).
- **CX-02/04/07/08/09/24/25:** operação humana utilizável, proveniência temporal,
  autenticação/TLS/proxy/chaves/runtime/clock reais. [Segurança](../operations/telnyx-security-consent.md).
- **CX-06/10/11/15/16/17/32/33/35/36:** in-flight/unknown/reconciliação, conta/número,
  binding/sync/Coexistence, consent/janela, ativação e envio comercial ainda sem
  demonstração autorizada. [Matriz](../operations/telnyx-gates.md).
- **CX-19/20/21/26/29/30:** auditoria/release finais, aceite E2E/custo e conversacional,
  fila/alerts/retries/failover e latência externa. CI/revisões acrescentam evidência,
  sem encerrar os gates. [Plano](../operations/telnyx-pilot-plan.md),
  [observabilidade](../operations/telnyx-observability.md), [runbooks](../operations/telnyx-runbooks.md).

Demais itens REVISAR/FUTURO permanecem na matriz completa; outbound BSUID,
Meta/Twilio sem proveniência de resume, migração de identidades, custos residuais,
router/SaaS e roadmap não foram resolvidos ou ampliados pelo CP8. Nenhum trabalho
além do Ticket13 está iniciado por esta entrega. Fonte: [matriz](../operations/telnyx-gates.md)
e [spec](../specs/V1-telnyx-coexistence-ticket-13.md).

Após verificar a SHA publicada, o run correspondente e a atualização da issue,
**encerrar o desenvolvimento e solicitar auditoria final do orquestrador**.
Continuação externa exige decisão explícita futura; não há liberação por silêncio.

## P. Três pareceres separados

| Decisão | Parecer técnico desta entrega | Estado formal / condição |
| --- | --- | --- |
| **Aceite técnico do Ticket 13 OFFLINE** | **FAVORÁVEL à submissão e ao aceite no escopo OFFLINE**, pelas evidências/revisões documentadas | **AGUARDANDO AUDITORIA FINAL DO ORQUESTRADOR**; este relatório não declara sua aprovação |
| **Elegibilidade para próximo gate controlado** | **NO-GO PARA EXECUÇÃO**; material apto à avaliação documental do orquestrador | Nova autorização específica e evidências externas aplicáveis obrigatórias; autoridade/witness/ledger reais e AUD-01 não são substituídos pelo laboratório |
| **Prontidão para PILOTO/PRODUÇÃO** | **NO-GO** | AUD-01 e bloqueadores operacionais continuam abertos; sem conta/credencial/envio real, ativação, piloto, produção ou merge autorizados |

Fundamentação: seções D/E/J/N/O, [ordem de gates](../operations/telnyx-gates.md),
[plano não executável](../operations/telnyx-pilot-plan.md) e
[parecer do orquestrador T12](https://github.com/zazacknazzo/rj-studio-ai/issues/11#issuecomment-7069497120).
**Nenhum health, CI success ou `simulation_ready` concede egress operacional.**
