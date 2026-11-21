# Ticket 12 — composição ASGI Telnyx, validação estritamente offline

21/11/2026, America/Sao_Paulo. Este documento é evidência para auditoria direta;
não concede aprovação operacional nem autorização do Ticket 13.

## A. Resultado e dois pareceres

Composição HTTP isolada implementada com headers brutos, streaming limitado,
auth→scope→parse→transação durável→ACK, deadline inferior a 2 s, rejeições observáveis,
readiness separado e quarentena fora do arquivo SQLite. Nenhum cliente HTTP Telnyx,
credencial comercial, sender/worker ou rota no runtime de produção foi composto.

**OFFLINE:** candidato elegível à auditoria direta: duas execuções integrais finais
com 2207 PASS / 1 skip histórico e três revisões independentes concluídas. Standards,
Spec e Security/Reliability verificaram as correções. O aceite cabe ao orquestrador,
não ao implementador.
**PRODUÇÃO / QUALQUER EGRESS REAL: NO-GO.** AUD-01 permanece aberto; o controle fechado
neste ticket não implementa recuperação/liberação operacional com autoridade externa.

## B. Branch, baseline e SHA

- Repositório: `zazacknazzo/rj-studio-ai`.
- Baseline aprovada T11: `246fe79a9bed4b202c49d3b2780320f6d5a0ca9c`.
- Única branch publicada: `codex/telnyx-coexistence-12-composition`.
- Candidato final de fonte/testes: `533052f2d60ee43bd66e82170af1801f4523c76a`.
  CP5 anterior: `d7b5d72a2e784ec954bf4f100eac9d4eaba7a1dc`; depois, somente framing 204 e regressão.
- SHA da entrega documental final: consultar origin; informada na entrega/issue11
  após confirmação remota, sem tentar prever o hash do próprio documento.
- Main conferida inalterada: `af1c9eb862a4180ca6b9e537349e4f8abaa2bb29`;
  branch T11 conserva a SHA da baseline. Nenhum merge/force push/rebase/reset.

## C. Diff e preservação de escopo

[Comparação completa](https://github.com/zazacknazzo/rj-studio-ai/compare/246fe79a9bed4b202c49d3b2780320f6d5a0ca9c...codex/telnyx-coexistence-12-composition).
Diff final: 29 arquivos, +3389/−6 linhas; 0 atrás da baseline. Inclui relatórios, manifesto,
evidências e runbook; inventário completo no fim deste relatório.

Mudanças funcionais: `telnyx_http.py`, `telnyx_asgi.py`, opção de HMAC/quarentena no
store, contador durável de rejeições e migration0023 com checagem estrutural.
Nenhuma alteração em `main.py`, `config.py`, adapters Meta/Twilio, sender Telnyx,
inteligência/persona/grounding/LLM, conhecimento ou Baileys. Testes históricos mudam
somente expectativa do head0022→0023, conservando revisões interrompidas/integridade.
Não existe worktree Baileys nesta máquina; não se declara inspeção de outra máquina.

## D. Contratos oficiais atuais

Consulta pública em21/11/2026; nenhuma chamada a `api.telnyx.com` ou portal autenticado.
Fontes e detalhes também foram reconsultados pelo revisor Spec.

| Fonte | Contrato empregado / limite |
| --- | --- |
| [Messaging webhooks](https://developers.telnyx.com/docs/messaging/messages/receiving-webhooks.md) | ACK2xx ematé 2 s; Ed25519/Base64 sobre timestamp\|bytes originais,5min de tolerância recomendada; retries/failover limitados e sem ordem garantida |
| [Coexistence](https://developers.telnyx.com/docs/messaging/whatsapp/coexistence/webhooks.md) | Echo outbound/humano best-effort, lifecycle e edit/revoke; WABA messages pode duplicar profile inbound; reconnect inicia sync, não prova active |
| [Idempotência](https://developers.telnyx.com/docs/development/api-fundamentals/idempotency.md) | Organização/método/path/chave, query mesmos parâmetros/valores, body byte-identical; replay2xx por até24h, expiração pode executar novamente |

Hashes dos Markdown realmente consultados:

- Messaging: `1b38355c445e9399c7189b2943bc0191ceaeed5273995ed9d74cdcc924c812ff`.
- Coexistence: `6292e8f7f877ba886e0f000958d9ffa50ff1e473742082fa3aaeb4928cb9acd7`.
- Idempotência: `ffb46a8a2039abc459544860a2ebf5d15917b8f4c1b83947291df26cca4c8e0d`.

Exemplos que sugerem ACK imediato, reserialização JSON ou guardar payload completo
não substituem commit-before-ACK, bytes originais e minimização aprovados neste projeto.
As specs/ADRs06–11, validaçãoT11, handoff, auditoria pré11 em502bca89 e issue11 foram
inspecionados; resultados históricos não foram atribuídos à execução atual.

## E. Arquitetura da composição

```text
ASGI bruto → limites/duplicatas/framing → body limitado em bytes/tempo
→ admissão limitada pelo deadline → verificação Ed25519 → escopo → parser06–09
→ BEGIN IMMEDIATE → binding/proveniência/journal/efeitos/Message/status → commit
→ checagem final do deadline →204 vazio → métricas agregadas

payload autenticado rejeitado → contador mínimo transacional →422 (nunca2xx)
capacidade/SQLite/commit/deadline indisponível →503; replay idempotente
```

A fábrica sintética explícita não possui app global, rota no main, seleção de provider,
sender, LLM, executor de geração/saída ou liberação. O construtor direto rejeita store
sem quarentena. Oito vagas de admissão e oito workers reservados limitam execução;
a espera por admissão expira antes de iniciar SQL. Uma transação iniciada é aguardada,
inclusive sob cancelamentos asyncio/AnyIO repetidos; sua vaga só retorna depois.
Cancelamento não emite ACK; um commit concluído continua deduplicável no replay.

## F. Matriz de eventos / CX29

| Entrada assinada | Tratamento / HTTP | Efeito durável |
| --- | --- | --- |
| message.received textual válido |204 depois do commit | Message/proveniência, processamento elegível ou suprimido pelo lifecycle/pausa |
| message.echo humano, inclusive mídia |204 depois do commit | Journal/pausa sem conteúdo; zero input gerador |
| message.received edit/revoke |204 depois do commit | Observação mínima; nenhuma reescrita histórica/geração |
| sent/finalized/read suportado |204 depois do commit | Ledger scoped, correlação antecipada/tardia, conflito monotônico |
| account.update conhecido |204 depois do commit | Offboard/disconnect bloqueiam; reconnect verification_required, nunca active |
| Mídia inbound, tipo/evento/status/lifecycle futuro, whatsapp.messages, JSON inválido ou escopo inválido |422 depois de observação mínima | Somente agregado payload_rejected; zero Message/effect parcial |
| Array HTTP/batch inventado ou tuple local misto inválido |Não2xx / rejeição local | Nenhum sibling suportado é commitado |
| Assinatura inválida |403 | Nenhum parsing/efeito/contador de payload |

O contador novo contém somente motivo fixo, número saturado de observações e primeiro/
último receipt local; uma linha possível, sem raw body/hash/IDs/endereço. Inclui retries,
não mede Messages únicas e não permite recuperar conteúdo rejeitado. Não foi ampliado
o escopo do operational journal. Falha do contador devolve503 visível nas métricas.
Manter422 pode esgotar retries/failover do provedor; alerts, operador, subscriptions,
tratamento de mídia/futuros e validação real são gates antes do piloto. Não se esconde
essa limitação retornando sucesso. Retenção/erasure/backups continuam CX01.

## G. Segurança ASGI

Headers permanecem sequência até rejeitar duplicatas case-insensitive de assinatura,
timestamp, Content-Type, Content-Length e Transfer-Encoding. Mais de100 headers ou16 KiB
rejeita431; CL+TE e framing ambíguo rejeitam400. Headers desconhecidos não são logados.
Depois disso, apenas headers selecionados chegam ao request canônico.

Body preserva os bytes, inclusive Unicode fragmentado. Limite padrão262144 bytes,
configurável até1 MiB segundo T06; contagem real em streaming independe de CL. CL ausente
é aceito dentro do limite; CL enganoso/oversized/malformado ou divergente é400/413.
JSON media type obrigatório415, disconnect400, leitura lenta408. Ed25519 precede JSON;
autenticação não significa suporte, janela, consentimento ou readiness operacional.

## H. Deadline e carga controlada

1,5 s total,1,35 s trabalho,150 ms reservados para checagem/resposta/overhead; leitura
no máximo500 ms dentro do orçamento. SQLite espera no máximo500 ms ou o restante do
trabalho, o que for menor. Admissão/auth/parser/wait/SQL/commit compartilham orçamento.
Checagens pré/pós-commit e no limite da resposta impedem2xx tardio. Commit após budget
pode ficar durável mas devolve503; replay não duplica. Métricas rodam após send.

Carga in-process ASGI + SQLite WAL/FULL,128 requests,concorrência 8, bodies fragmentados.
Última medição local focada: únicos125x204/3x503; p95=0,13888s,p99=0,52874s,
max=0,53049s; três retries com envelopes idênticos após drenar retornaram204,128Messages
únicas. Duplicatas128x204,p95=0,06941s,p99=0,13383s,max=0,19525s,uma Message. Zero2xx
tardio. Na integral local: únicos p95=0,18745 s/p99=0,43827 s,127x204/1x503→1x204
no replay; duplicados p95=0,08976 s/p99=0,17680 s,128x204. Na integral Spec:
únicos p95=0,18849 s/p99=0,50754 s,128x204; duplicados p95=0,07783 s/
p99=0,15972 s,128x204; zero 2xx tardio em ambos. Dados exatos no JSON final.

Revisor Standards mediu independentemente128x204 únicos(p95=.18849s,p99=.44526s) e
128x204 duplicados(p95=.06386s,p99=.13865s). Amostras não equivalem a garantia de todos
os hosts/cargas. A espera inicial50 ms produziu29/6respostas503 locais; com500 ms ainda
houve uma execução127x204/1x503. Esses resultados foram preservados. O teste agora mede
backpressure e exige recuperação/deduplicação, sem inventar SLA de100%204.

Fsync, preempção do processo e backpressure ASGI/proxy/socket não têm limite físico
comprovado. Nenhum ACK sobre rede Telnyx ou latência comercial foi medido. O aplicativo
protege a elegibilidade do sucesso; não promete hard real-time ou SLA externo2s.

## I. Quarentena e AUD-01

Seis cenários: snapshot antes de claim, antes de marker, antes de disconnect,
snapshot antigo após acceptance, snapshot depois de acceptance e expiração externa.
Reinício da fábrica continua em quarentena e nega autorização, mesmo com request válido;
não existe release endpoint. Teste adicional adquire novo owner no pending restaurado,
mostra assessment legado elegível (reproduz AUD-01) e autorização da composição negada.
Nenhuma nova chave, unknown apagado ou replay de envio foi usado para recuperar.

A barreira é configuração/processo e ausência de workers, fora do SQLite restaurado;
não é epoch externo operacional nem protege código hostil que ignore a composição.
**AUD-01 permanece ABERTO.** Antes de egress real: autoridade independente atual fora de
backups, inventário/reconciliação de possível submissão, sync/binding/canal, consentimento/
janela atuais e liberação autenticada auditada, com testes de perda/rollback dessa
infraestrutura. Essa integração real não foi autorizada nem ativada neste ticket.

## J. Egress fencing / CX35

Store da fábrica nega todo egress Telnyx, independentemente de estado restaurado.
Para exercitar o caminho de envio SOMENTE interceptado fora da fábrica, testes injetam
um TelnyxRequestSigner estável no store. No mesmo writer, request ausente/mutado/HMAC
inválido/organização divergente nega antes de binding/marker. Um sender genérico sem
request preparado não consegue passar. Request válido precisa dos gates herdados:
canal positivo, identidade exata, owner/lease, janela/consentimento, pausa/revision,
handoff e ordering/conflito. Verificação não substitui autorização transacional.

Exchange fake confirma binding persistido antes da única chamada; callbacks HTTP
antecipados/tardios/contraditórios conservam scope/conflito. Revogação, lifecycle, pausa,
owner, lease e janela negam mesmo com request válido. TestsT11 cobrem demais gates.
Compatibilidade default `http_request=None` permanece apenas no store interno histórico;
Meta/Twilio não recebem a política Telnyx. Nenhum worker de saída foi habilitado.
CX06 autorização→HTTP permanece: trabalho já autorizado não tem recall.

## K. Readiness e observabilidade

| Dimensão | Resultado offline |
| --- | --- |
| Ingresso | Configuração local válida; continua recebendo lifecycle com canal bloqueado |
| Persistência | Schema/head, WAL/FULL/FK/busy timeout, arquivo e writer probe; degrada sob lock/dano |
| Administração | False; API administrativa não compõe este app de testes |
| Geração | False; nenhum executor/LLM |
| Saída | False; quarentena e nenhum sender/executor |
| Canal operacional | False; sem conta/sync/liberação reais |

Health200 só prova processo. Ready200 descreve ingresso/persistência offline e contém
mode=offline/quarantined=true; não significa canal apto a enviar. Métricas têm labels
finitos e buckets cumulativos, sem conteúdo/headers/segredos/IDs ou amostras ilimitadas.
Contador SQLite sobrevive restart; métricas do processo reiniciam. Runbook explica
inspeção local/422/503, retries e limitações de recuperação.

## L. Testes completos, checks e reprodução

Execuções integrais no candidato 533052f: **local 2207 passed / 1 skipped / 2 warnings
em 335,51 s, exit 0; Spec independente 2207 passed / 1 skipped / 2 warnings em
344,15 s, exit 0**. Hashes de fonte/testes preservados durante as duas execuções.
Primeiras execuções em d7b5d72 interrompidas para incluir a correção RFC9110: local
1929 passed/1 skip em 327,77 s; Spec 1730 passed/1 skip em 289,75 s. O SIGINT durante
fixtures produziu KeyError de teardown do pytest; são execuções parciais, não PASS integral.
Uma execução Spec anterior também foi interrompida: 176 passed em 32,92 s.
Venv novo privado0700 `/tmp/ticket12/venv`; Python3.12.14,SQLite3.53.1,
pip26.3/pytest9.2.0,Ruff0.17.6,pip-audit2.10.1,Gitleaks8.30.1.
Instalação separada de testes: PyPI explícito, upgradepip>=26 e `-e '.[dev]' pip-audit`.
Nenhuma dependência declarada de runtime foi alterada. [Manifesto observado](ticket12-toolchain.txt)
não é lock. Runner sanitizado reutilizadoT11: temp/basetemp privado, ambiente reduzido,
sem .env/credenciais e guard de sockets IP Python herdado por filhos; não é sandbox de kernel.

```bash
python scripts/check_telnyx_offline.py --python /isolated/venv/bin/python --output /new/private/evidence tests
ruff check .
ruff format --check .
python -m compileall -q src tests scripts
python -m pip check
python -m pip_audit --cache-dir /private/cache --format json --output /private/audit.json
gitleaks dir . --redact
gitleaks git . --redact --log-opts=246fe79a9bed4b202c49d3b2780320f6d5a0ca9c..HEAD
git diff --check
```

Ruff check/format 331 arquivos,compileall,pip check,diff check PASS.
[Pip-audit real](ticket12-pip-audit.json):82entradas,zero pacotes com advisories retornados;
app local explicitamente não indexada/pulada. Primeira tentativa falhou por cache padrão
read-only, corrigida com cache privado. Zero advisory não é prova universal de segurança.
Gitleaks archive oficial8.30.1 conferido por checksum; range CP0–6: 8 commits / 0 hits;
árvore3hits brutos baseline(public schemahashT11,prosaeval,fixtureoperador sintética),
falsos positivos triados sem ignores. Rechecagem documental final consta na evidência.

Skip histórico esperado: fixturev8 não versionada de test_commercial_steering ausente.
Não foi inventado arquivo para ocultá-lo. Dois avisos record_property/xunit2 no teste de
carga preservam propriedades JUnit; não são falhas, tampouco foram silenciados.
[JSON de evidências](ticket12-test-evidence.json) registra contagens/hash dos logs/JUnit,
medições e falhas anteriores. Os recortes se sobrepõem; não somar como cobertura distinta.

## M. Três revisões independentes e correções

| Perspectiva / artefato | Execução própria / conclusão |
| --- | --- |
| [Standards](ticket12-standards-review.md) |96focados PASS; final CP5 38 testes/probes em 24,70 s; framing final 22 testes em 14,12 s; cinco probes próprios incluindo rollback0023. Candidato 533052f confirmado local/remoto |
| [Spec](ticket12-spec-review.md) |Três probes próprios finais PASS em 7,19 s (deadline, construtor e framing); integral própria 2207 PASS / 1 skip / 2 warnings em 344,15 s |
| [Security/Reliability](ticket12-security-reliability-review.md) |91focados PASS; quatro probes de correção PASS,probeAnyIO adicional PASS; final CP5 33 focados em 18,99 s; framing final 22 testes em 17,59 s |

Quatro P2 do candidato foram reproduzidos e corrigidos: métricas depois da checagem
podiam atrasar204; construtor direto aceitava store sem quarentena; espera de capacidade
sem deadline; Task.cancel destacava transação/liberava vaga. Os mesmos probes originais
e regressões passaram após correção. Um P3 adicional de framing HTTP (Content-Length
proibido em 204 por RFC9110 §8.6) foi corrigido, com inspeção e três probes próprios
da Spec, além das execuções focadas finais dos outros revisores. Nenhum novo P1/P2 confirmado pendente nessas
perspectivas; não é prova universal e não encerra AUD-01/CX. Falhas de testes WIP e
execuções interrompidas estão preservadas nos relatórios/handoff/JSON, não descritas comoPASS.

## N. Issue11, checkpoints e continuidade

[Registro central](https://github.com/zazacknazzo/rj-studio-ai/issues/11), aprovaçãoT11
comment7062936123. O comentário de entrega final é publicado após confirmar a SHA remota; consultar o
comentário mais recente com título Ticket12 entregue. Este relatório não altera o corpo
ou os checkboxes do registro. Nenhum
checkbox fechado, risco encerrado ou exceção aceita por esta implementação.

| Riscos | Saldo / gate restante |
| --- | --- |
| CX01 | Sem payload novo no journal; counters finitos. Retenção/erasure/backups ainda antes do piloto |
| CX02/03/04/05 | Echo/pausa/proveniência preservados; operador utilizável, clock/retomada reais pendentes |
| CX06/11/15/16/33/35/36 | Binding/gates/quarentena offline testados; recall não prometido; sync/consentimento/restore/liberação reais pendentes |
| CX17/22/24/29/30 | ASGI sintético/headers/streaming/readiness/deadline/rejeição implementados; provisioning/alertas/unsupported/retries/latência reais pendentes |
| CX19/21/25 | Duas suítes e revisões locais não são CI, release ou prova de chave/libsodium/NTP implantados |
| CX32/37 | Conflito/unknown preservados; sem resolução manual nova ou outbound BSUID |
| AUD-01/02/03 | AUD-01 operacional aberto; toolchain auditada nesta execução; protocolo/retomada ensaiados, exclusividade humana obrigatória |

[Handoff](../handoffs/TICKET-12.md) reconstrói autorização/baseline/estado/falhas/próximo
comando sem conversa anterior. Usuário confirmou exclusividade; primary fez todos os
commits/pushes, revisores só escreveram relatórios separados. Ensaio em novo clone remoto
d7b5d72:AGENTS/handoff/origin/status/SHA/ancestry conferidos,2focados PASS6,35s comguard;
clone conservado limpo. Simula retomada, não autenticação de segunda conta real.

| CP | SHA remota efetivamente confirmada |
| --- | --- |
| CP0 spec/ADR/handoff |52e0c2b5da61c2ec990a5d07fee6542ba76ede27 |
| CP1 headers/streaming |f54ffbd82f57bc0b5b60f4fcc91533fb4f663fc5 |
| CP2 ingress ASGI |16a43b7127a8e666561ecc333e9654cb4b6dbcc9 |
| CP3 durabilidade/deadline |c1bc518e5f56aed28f23b0903e941a602030dcd5 |
| CP4 rejeições/readiness |f55d7f51ef72bcf659de6b0ffe3faec0308e185f |
| CP5 restore/egress/carga/correções |d7b5d72a2e784ec954bf4f100eac9d4eaba7a1dc |
| CP6 correção RFC204 |533052f2d60ee43bd66e82170af1801f4523c76a |
| CP6 validação/revisões |42130f55081d768db7b3dbed9c02fd07275f314a |
| CP7 relatório/entrega |SHA remota conferida e informada na entrega/issue após este commit |

## O. Limites, proibições e próxima decisão

Executado: SQLite/ASGI reais em dados sintéticos, suíte/checks/probes/revisões e operações
Git/publicdocs/advisories. Simulado: todo envio/acceptance/timeout/callback/restore de
conta; channel/consent positivos são fixtures. Não comprovado: conta+55, sync, operador,
consentimento atual real, LGPD integral, infraantirollback, TLS/proxy/NTP/CI, entrega/custo/
latência WhatsApp reais. Não executado: HTTP Telnyx comercial, credencial, ativação,
worker real, merge/main, Baileys, inteligência ou Ticket 13.

Desenvolvimento INTERROMPIDO após a entrega. Solicita-se
**auditoria direta do orquestrador**. Qualquer Ticket 13 ou egress/piloto/produção exige
nova autorização e fechamento verificável dos gates, especialmente AUD-01.

## Inventário completo contra Ticket11

```text
docs/ARCHITECTURE.md
docs/architecture/ticket12-pip-audit.json
docs/architecture/ticket12-security-reliability-review.md
docs/architecture/ticket12-spec-review.md
docs/architecture/ticket12-standards-review.md
docs/architecture/ticket12-test-evidence.json
docs/architecture/ticket12-toolchain.txt
docs/architecture/v1-ticket12-validation.md
docs/automation-operations.md
docs/decisions/0020-offline-telnyx-asgi-composition.md
docs/decisions/README.md
docs/handoffs/TICKET-12.md
docs/specs/README.md
docs/specs/V1-telnyx-coexistence-ticket-12.md
src/rj_studio_ai/migrations/__init__.py
src/rj_studio_ai/migrations/versions/0023_telnyx_ingress_observations.py
src/rj_studio_ai/persistence.py
src/rj_studio_ai/telnyx_asgi.py
src/rj_studio_ai/telnyx_http.py
tests/test_agentic_intake_migration.py
tests/test_migrations.py
tests/test_openai_metadata_migration.py
tests/test_telnyx_asgi.py
tests/test_telnyx_asgi_durability.py
tests/test_telnyx_asgi_egress.py
tests/test_telnyx_asgi_load.py
tests/test_telnyx_asgi_observability.py
tests/test_telnyx_http.py
tests/test_telnyx_messages.py
```
