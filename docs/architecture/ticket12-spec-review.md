# Ticket12 — revisão independente de Spec

Revisor: agente Spec separado do implementador; leitura própria e comandos próprios.
Baseline: `246fe79a9bed4b202c49d3b2780320f6d5a0ca9c`.
Revisão iniciada em HEAD `f55d7f51ef72bcf659de6b0ffe3faec0308e185f` mais WIP de CP5.
Candidato CP5 de código/testes: `d7b5d72a2e784ec954bf4f100eac9d4eaba7a1dc`.
Candidato final corrigido: `533052f2d60ee43bd66e82170af1801f4523c76a`.
**Parecer final: candidato elegível OFFLINE para auditoria direta; PRODUÇÃO NO-GO.**

## Escopo inspecionado

AGENTS, specT12/ADR0020, contratos T06–11, ADR0016/17 e diff contra baseline.
Leitura direta de `telnyx_http.py`, `telnyx_asgi.py`, `webhook_ingress.py`, auth/parser,
request signing, alterações de store/migrações e testes novos. Nenhuma alteração de
fonte/teste ou operação Git feita pelo revisor; somente este relatório é escrito.

## Contratos oficiais consultados pelo próprio revisor

Consultas HTTPS públicas em2026-11-21; nenhuma API de conta/comercial foi chamada.

| Fonte Markdown | SHA256 observado / regra confirmada |
| --- | --- |
| https://developers.telnyx.com/docs/messaging/messages/receiving-webhooks.md | `1b38355c445e9399c7189b2943bc0191ceaeed5273995ed9d74cdcc924c812ff`;2s para2xx, até3tentativas/URL |
| https://developers.telnyx.com/docs/messaging/whatsapp/coexistence/webhooks.md | `6292e8f7f877ba886e0f000958d9ffa50ff1e473742082fa3aaeb4928cb9acd7`; WABA messages é via duplicada;echo best-effort;lifecycle não prova sync |
| https://developers.telnyx.com/docs/development/api-fundamentals/idempotency.md | `ffb46a8a2039abc459544860a2ebf5d15917b8f4c1b83947291df26cca4c8e0d`; replay de sucesso por até24h,sem autoridade de retry unknown |

A recomendação genérica de ACK imediato e conservação de payload não substitui
commit antes do ACK/minimização exigidos pelo projeto. Non2xx para contratos não
suportados é política local conservadora, não garantia de retenção/entrega Telnyx.

## Achados reproduzidos e correções

### SPEC12-01 — P2 corrigido: métricas podiam causar ACK após deadline

No candidato inicial, `metrics.record` executava após a última checagem do deadline e
antes de `http.response.start`. Sondagem própria avançou relógio monotônico0→2s dentro
dessa etapa: resposta204 mesmo após o orçamento1.5s. Uma espera no lock de métricas era
uma fonte concreta de atraso nesse intervalo. O implementador moveu métricas para
`finally` depois da emissão da resposta.

Verificação própria passou observando o relógio precisamente em `http.response.start`:
204 em0.0s, depois métrica avançou a2.0s. O teste de fechamento verifica emissão, não
confunde tempo final do harness com o instante do ACK. Sem alegar preempção de fsync ou
backpressure do servidor, limites que continuam documentados.

### SPEC12-02 — P2 corrigido: construtor aceitava store sem quarentena

Fábrica inicial criava store quarantinado, mas construtor público `OfflineTelnyxASGI`
aceitava store comum. Sondagem própria obteve readiness.quarantined=true e autorização
bem-sucedida via `app.store.authorize_delivery_submission` sem http_request. Nenhum
transporte foi invocado. O implementador passou a recusar construtor com store sem
quarentena. Teste próprio confirmou ValueError no mesmo cenário.

Esses dois P2 foram confirmados por2probes originalmente falhando (2.83s), seguidos de
2probes de fechamento passando (2.65s). Os scripts/logs de execução próprios ficaram em
`/tmp/ticket12/spec-probes*`; a especificação das reproduções acima independe do chat.

Regressões portáteis versionadas para reproduzir os dois contratos após clone:

- `tests/test_telnyx_asgi_durability.py::test_metrics_cannot_delay_success_past_deadline`.
- `tests/test_telnyx_asgi_egress.py::test_direct_composition_cannot_accept_unquarantined_store`.

Os probes independentes observaram os mesmos limites por callbacks próprios; não se
apresenta a simples execução dos testes do implementador como sondagem autoral.

### SPEC12-03 — P3 corrigido: Content-Length proibido em204

Inspeção própria identificou que `_respond` incluía Content-Length:0 em todo status,
inclusive204. [RFC9110§8.6](https://www.rfc-editor.org/rfc/rfc9110.html#section-8.6),
consultada diretamente pelo revisor, proíbe Content-Length em204. Clientes ASGI usados
toleraram zero; não foi reproduzida rejeição Telnyx nem exploração. P3 no escopo offline.
O implementador decidiu corrigir o framing antes da entrega e pediu interrupção das
suítes integrais para executar o candidato corrigido por inteiro. Verificação final
da correção: delta de2arquivos inspecionado diretamente em533052f; o caminho204
agora omite Content-Length e preserva corpo vazio. Sondagem própria observa headers
em `http.response.start` do ACK real sintético, sem inferir pelo tempo final do harness.

## Matriz de aderência inspecionada

| Contrato | Implementação/evidência | Limite |
| --- | --- | --- |
| Headers/raw bytes | Duplicatas case-insensitive rejeitadas antes do map;stream limitado por bytes reais;length/smuggling negados | ASGIserver/proxy/TLS reais não exercitados |
| Auth→parse→scope | Autenticador verifica timestamp|bytes antes de JSON;parser existente mantém identidades | Chave/clock reais não provisionados |
| SQLite→ACK | Journal/receipts/effects no mesmo writer;checagem antes/depois de commit;204 somente após retorno durável | fsync/backpressure não preemptíveis |
| Deadline |1.35s trabalho/1.5s total;readbody0.5s;SQLite limitado pelo restante | Carga mede host sintético, não SLA comercial |
| Não suportados |422 após contador durável;falha do contador503;sem sucesso vazio;arraywire rejeitado;tuplelocal atômico | Sem arquivo de recuperação de mídia/payload;alertas/fluxo humano permanecem gates |
| Lifecycle | Bloqueio não impede ingresso;reconnect não ativa;echo mídia ainda pausa | Visibilidade best-effort,sem recall após marker |
| Readiness |6dimensões;admin/generation/egress/channel false;health process-only | Não prova credencial,canal,sync nem operador real |
| Egress | Factory exige quarentena fora doSQLite;store estrito pode verificar requestHMAC;sem worker/release | Default store interno histórico permanece compatível;não é API operacional |
| Restore | Snapshots antigos não alteram flag de composição;sem liberação nem nova chave | AUD01 OPEN: frescor externo/reconciliação/release autenticado reais não implementados |

## Execuções próprias e limitações de evidência

Comando portátil usado em todas as suítes: `python scripts/check_telnyx_offline.py
--python /tmp/ticket12/venv/bin/python --output <novo-diretório-privado> <seleção>`.
O runner saneia ambiente e bloqueia sockets IP Python inclusive filhos; não é sandbox
por kernel contra executáveis arbitrários. SQLite real em arquivos sintéticos; nenhuma
credencial comercial, conta, envio, ativação ou tráfego Telnyx real.

- Foco inicial das6suítes novas:69passed/3failed/2warnings,14.98s. Uma falha era typo no
  teste de alteração de body (campo errado);duas eram respostas503 da carga sob
  contenção/timeoutSQLite50ms. Falhas preservadas, não tratadas como suite verde.
-2probes próprios inicialmente2failed2.83s;fechamento2passed2.65s, descritos acima.
- Integral anterior interrompida por pedido do implementador para incluir correção de
  admission/capacidade encontrada pela revisão Security:176passed32.92s, SIGINT.
  É parcial, não aprovação integral. Resultado em `/tmp/ticket12/spec-full.log`.
-2probes próprios reexecutados no candidato finald7b5d72:2passed6.66s, enquanto a
  suíte integral também executava. Checagem temporal observa o instante de emissão.
- Integral própria emd7b5d72 interrompida por pedido do implementador para incluir
  SPEC12-03: JUnit registra1731testes,0falhas,0erros,1skip,289.754s (1730passed+1skip
  parcial). SIGINT durante setup disparou KeyError no teardown tmp_path e impediu resumo
  textual normal; contagem vem do XML, não de inferência dos pontos. Não é integral verde.
- **Integral própria final em533052f:2207passed/1skip/2warnings,344.15s,exit0**.
  Comando: `python scripts/check_telnyx_offline.py --python /tmp/ticket12/venv/bin/python
  --output /tmp/ticket12/spec-complete tests`. Log em `/tmp/ticket12/spec-complete.log`,
  XML em `/tmp/ticket12/spec-complete/pytest.xml`.
- Skip histórico: `tests/test_commercial_steering.py:430`, evidência v8 local não
  versionada. Não é skip de teste novo/provider e não foi fabricada fixture para escondê-lo.
-2warnings: record_property/JUnitxunit2 nos2cenários de carga; propriedades foram
  efetivamente escritas/lidas noXML. Não houve warning de falha criptográfica/persistência.
-3probes próprios de fechamento no candidato533052f: **3passed7.19s**, exit0.
  Exercitam emissão antes do deadline, recusa do construtor sem quarentena e headers
  do ACK204 conforme RFC9110. XML em `/tmp/ticket12/spec-complete-probes/pytest.xml`.

HEAD permaneceu533052f e o diff de fontes/testes permaneceu vazio após a integral.
Hashes SHA256 dos fontes usados foram conferidos antes e após a execução:

- `telnyx_asgi.py`: `368ff72c8744d30a783694f0ddfe43f97dba75845660b76ed9e125bc7fa85846`.
- `telnyx_http.py`: `d8913037b8adddadc06e08afd37bbe9e95315531f2c808ed873235b9c5a9e3e2`.
- `persistence.py`: `a57121e4379b87b9e4d954f61316eb2919a38f0a818e40f32551f28081f0b2ce`.

## Carga controlada própria

Resultadosextraídos doXML da integral própria;128requests por cenário,8concorrentes,
ASGI em processo + SQLite WAL/FULL. Nenhum HTTPcomercial/LLM foi chamado.

| Cenário | Respostas iniciais | p95 / p99 / max | Retry / late2xx |
| --- | --- | --- | --- |
|128eventos distintos |128x204 |188.49 /507.54 /515.85ms |0retry,0late2xx |
|128replays do mesmo evento |128x204 |77.83 /159.72 /463.61ms |0retry,0late2xx |

Esses percentis incluem somente o caminho sintético neste host. A versão final do teste
registra503quando há contenção e exige recuperação com o mesmo envelope após a carga;
não inventa uma garantia de que toda carga receberá204. Na execução própria final não
houve503. Os resultados iniciais com50ms e contenção permanecem registrados acima.

Hashes da evidência própria final:

- Log: `85a940bb33938d0c4bbb970f495643d1bf18c6d36cf42db35ee069e2ed80c26f`.
- JUnit integral: `bfd7e4440965acd73bbd070a05d353998d786ff08079f9fb82965014ae5d6948`.
- JUnit dos3probes: `e01d104c9c033109ae65944ef71fd1386f952ffd929cc05846c7d2efca9cc75b`.

## Parecer final

**OFFLINE:** candidato533052f elegível para auditoria direta do orquestrador. Integral
própria verde e3probes próprios de fechamento sustentam o contrato corrigido; os2P2 e1P3
novos identificados por esta revisão têm correção e evidência de verificação. Nenhum
P1/P2 novo confirmado permanece pendente nesta revisão do código offline; isso não é
prova de ausência universal de defeitos e não encerra o P2 operacional AUD01.

**OPERACIONAL/PRODUÇÃO: NO-GO.** AUD01 e os demais gates reais continuam abertos.
Quarentena estrutural não prova frescor externo nem oferece release autenticado.
Não foram executados onboarding, credenciais reais, envio, ativação, workeroperacional,
restore com saída ou teste Telnyx real. CI não foi comprovada por esta execução local.
Nenhum risco/checkbox fechado nem exceção aceita por esta revisão. Próxima decisão é a
auditoria direta do orquestrador, sem autoridade para iniciarTicket13 ou liberar produção.
