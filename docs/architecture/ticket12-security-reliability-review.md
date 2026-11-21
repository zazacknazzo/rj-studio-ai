# Ticket12 — Security / Reliability Review independente

Data: 21/11/2026 (America/Sao_Paulo). Baseline imutável
`246fe79a9bed4b202c49d3b2780320f6d5a0ca9c`. Revisão própria do diff e do WIP
do Ticket12; candidato final de código/testes conferido em
`533052f2d60ee43bd66e82170af1801f4523c76a`. Sem editar fonte/teste ou executar Git mutation. O implementador é
o único escritor Git; este revisor escreveu somente este relatório.

**Parecer OFFLINE:** candidato elegível à auditoria direta após incorporação das
correções abaixo. Nenhum P1/P2 novo confirmado permanece aberto nesta revisão;
isso não é prova universal de ausência. **PRODUÇÃO / QUALQUER EGRESS REAL: NO-GO.**
AUD01 continua aberto: quarentena estrutural offline não implementa autoridade
externa de frescor, reconciliação ou liberação operacional autenticada.

## Leitura direta e fronteiras

Inspecionei AGENTS, spec Ticket12, ADR0020, helpers HTTP/ASGI, autenticação e parser
Telnyx, `receive_telnyx_messages`, writer/commit/deadline do store, assinatura e
binding do request, migration0023 e testes de ingresso, restauração e egress.
Não usei o resultado anterior do implementador como execução minha.

- Headers permanecem uma sequência até a detecção de duplicatas de assinatura,
  timestamp e framing. Contagem/tamanho de headers são limitados; Content-Length
  conflitante com transfer-encoding é rejeitado. A assinatura usa bytes originais.
- O stream é limitado pelos bytes reais e por tempo, inclusive sem comprimento
  declarado ou com comprimento enganoso. JSON/escopo não antecedem a criptografia.
- Eventos/effects e recibos são commitados antes de204; erros/locks/rollback/
  deadline não produzem sucesso. Commit tardio pode persistir e requer replay,
  conservando a distinção entre perda de ACK e perda de evento.
- Desconhecidos/mídia/arrays não ganham ACK vazio. O agregado de rejeições contém
  motivo fixo, contagem saturada e timestamps; nenhum body, ID, hash ou endereço.
  Ele mede observações, inclusive retries, não Messages únicas nem arquivo recuperável.
- Health e seis dimensões de readiness não autorizam canal: egress, geração,
  administração e canal operacional permanecem falsos na composição offline.
- A fábrica e o construtor exigem quarentena fora do arquivo restaurado. Não
  compõem sender/worker/LLM/liberação. O store em quarentena nega mesmo um request
  válido; o modo estrito com signer, exercitado apenas em testes interceptados,
  exige HMAC/request exatos antes dos gates transacionais herdados.
- Config/main/Meta/Twilio não selecionam Telnyx. A compatibilidade interna permissiva
  do store genérico permanece fora da composição fechada; não é licença operacional.

## P2 encontrados, reprodução independente e correção

### SR12-01 — espera por capacidade ignorava deadline — corrigido

O `run_sync(..., limiter=...)` original podia esperar indefinidamente por uma vaga,
ainda antes de iniciar SQL. Reservei todas as oito vagas, iniciei um webhook válido
e aguardei1,65s: a requisição continuou pendente. Só após liberar a capacidade
retornou503. Não havia fsync/SQLite desse request em andamento, portanto a
não-preempção de commit não justificava essa espera sem limite.

Sondagem própria `test_waiting_for_capacity_honors_request_deadline` falhou antes
da correção. O implementador separou admissão e workers, limitou aquisição por
`fail_after(remaining_budget)` e compartilhou a barreira com rejeições/readiness.
A mesma sondagem passou depois:1passed4,31s. No conjunto final de sondagens,
passou novamente. A regressão versionada é
`tests/test_telnyx_asgi_durability.py::test_capacity_wait_is_bounded_without_starting_sql`.
Uma requisição rejeitada por capacidade não iniciou persistência nem ganhou ACK.

### SR12-02 — Task.cancel destacava transação em execução — corrigido

Em uma thread admitida, bloqueei `record_webhook_events` com Events. Cancelei a
task ASGI por `asyncio.Task.cancel()`. A task encerrou e devolveu a vaga de admissão
antes de a thread terminar (`detached=True`, `borrowed_tokens=0`). AnyIO's shield
padrão não cobria essa modalidade de cancelamento. Cancelamentos repetidos poderiam
contornar o limite pretendido de trabalhos em execução; isso contrariava o contrato
de não destacar persistência. Não houve envio externo ou perda de integridade
SQLite demonstrados.

Sondagem própria `test_cancellation_does_not_detach_running_persistence`: antes,
1failed2,77s. O implementador passou a criar/proteger a task do worker, drená-la
sob cancelamento repetido e só então liberar admissão/propagar o cancelamento,
sem emitir ACK. A mesma sondagem passou na correção. Inspecionei também a regressão
versionada de três cancelamentos: a vaga fica ocupada, um commit é concluído e o
replay posterior não duplica a Message. Falha eventual do job é consumida enquanto
o cancelamento permanece autoritativo.

### Correções compartilhadas, verificadas por sondagens próprias

Standards/Spec reportaram instrumentação entre a última checagem e o início do ACK,
e construtor direto que aceitava store sem quarentena. Inspecionei as correções:
métricas executam após send; construtor exige `_telnyx_egress_quarantined is True`.
Minhas sondagens confirmaram204 no instante monotônico0 antes de instrumentação
que avança para2s, e rejeição do construtor com store genérico. Não atribuo a mim
a descoberta original desses dois itens.

## Execuções próprias e falhas preservadas

Todos os comandos utilizaram o runner sanitizado/IP guard de Ticket11 com venv
`/tmp/ticket12/venv/bin/python`, diretório de evidência novo e privado0700.
Nenhum socket IP, conta/credencial/API comercial, ativação, worker real ou merge.
O guard Python não é sandbox de kernel para executáveis arbitrários.

| Execução própria | Resultado observado |
| --- | --- |
| Foco inicial: rawHTTP, ASGI, durabilidade, observabilidade, egress e adversarial T11 |87passed/1failed18,92s; único erro era teste WIP usando `request.body` em vez de `content`, corrigido pelo implementador |
| Duas sondagens iniciais |2failed4,35s; capacidade é defeito confirmado; assert de métricas ficou incompatível com a correção concorrente pós-send e foi corrigido no próprio probe |
| Quatro sondagens próprias: raw duplicate/joined signature, JSON com chave duplicada autenticado, construtor e instante do ACK |4passed3,15s |
| Mesmo probe original de capacidade após correção |1passed4,31s |
| Foco após correções iniciais |91passed20,65s |
| Probe próprio de cancelamento antes da correção |1failed2,77s |
| Mesmos probes originais de capacidade e cancelamento + construtor + instante do ACK, após correção |4passed4,44s |
| Probe adicional de cancelamento por AnyIO CancelScope, mantendo drenagem até o fim do worker |1passed3,58s |
| Execução focada independente no candidato d7b5d72: durabilidade ASGI e egress |33passed18,99s; HEAD conferida antes/depois |
| Última execução independente no candidato533052f: ASGI/ACK e durabilidade, incluindo framing204 |22passed17,59s; HEAD conferida antes/depois |

Não trato a primeira falha de assert de instrumentação como reprodução de vulnerabilidade
na árvore corrigida: o timestamp no início da resposta é a observação relevante,
não o clock depois da instrumentação. Não apago os2failed originais do histórico.
A última alteração, inspecionada diretamente entre os candidatos, remove
Content-Length de204 conforme RFC9110§8.6 e adiciona assert de body vazio/header ausente.
Ela não modifica persistência, gates ou cancelamento; o foco final acima a reexecutou.
Não executei a suíte integral nesta perspectiva; as execuções integrais de outros
revisores/implementador têm suas próprias atribuições no relatório principal.

Comando de foco reproduzível:

```bash
python scripts/check_telnyx_offline.py --python /tmp/ticket12/venv/bin/python \
  --output /tmp/ticket12-security-new \
  tests/test_telnyx_http.py tests/test_telnyx_asgi.py \
  tests/test_telnyx_asgi_durability.py tests/test_telnyx_asgi_observability.py \
  tests/test_telnyx_asgi_egress.py tests/test_telnyx_sender_adversarial.py
```

Logs próprios, não versionados: `/tmp/ticket12/security-focused.log`,
`security-focused-second.log`, `security-probes-initial.log`,
`security-probes-corrected.log`, `security-capacity-fixed.log`,
`security-cancellation.log`, `security-deadline-cancel-fixed.log`,
`security-anyio-cancel.log`, `security-final-candidate.log`, `security-204-framing.log`.
Os nomes pertencem ao diretório `/tmp/ticket12/`; não pressupor que sobrevivam
à troca de máquina. As regressões versionadas e o comando acima permitem retomada.

## Limites e gates remanescentes

- AUD01 não fechado. Restores antigos podem apagar markers, acceptance, consentimento
  e lifecycle no store genérico; schema/HMAC não provam frescor. A composição offline
  continua fechada por construção. Saída real exige fonte independente atual,
  inventário/reconciliação, evidência de canal/consentimento/janela e liberação
  autenticada auditável; não há API de release neste ticket.
- Desconhecidos recebem rejeição visível, sem payload recuperável no journal.
  Alerts/workflow, política de suporte, subscriptions, esgotamento de retries/failover
  e retenção/erasure permanecem gates antes do piloto. Nenhum risco foi encerrado.
- Deadline limita admissão e protege o sucesso; fsync, shutdown/processo e backpressure
  do servidor não são preemptíveis como um SLA hard real-time. Probes não validam
  latência Telnyx real, chave/clock do deployment ou entrega de mensagens.
- Python/network guard, SQLite sintético e transporte interceptado não demonstram
  infraestrutura, LGPD integral, CI, operador móvel, elegibilidade+55 ou autorização
  comercial. CX01/06/11/15/16/19/24/25/29/30/32/33/35/36/37 mantêm seus gates.

Desenvolvimento deve terminar na entrega offline e voltar à auditoria direta do
orquestrador. Nenhuma conclusão desta revisão autoriza Ticket13 ou produção.
