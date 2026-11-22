# B1 — evidência de integração WAHA privada

22/11/2026, America/Sao_Paulo. **Objetivo bidirecional NÃO concluído. Egress
NO-GO: AUD-01/AR-02. Inferência OpenAI real observada.**

Baseline G0 `65abbe6ce74a850fd8558b3a0b385a5caf2a18b5`, origin e status conferidos.
Branch autorizada `codex/b1-livia-waha-live`; implementação publicada e SHA remota
consultada: `564935d5349adfffb5f5ca69bce9f2d0c1d19f96`.
Main preservada em `af1c9eb862a4180ca6b9e537349e4f8abaa2bb29`.
Nenhum merge/force push ou alteração de source de main, Telnyx, Meta, Twilio ou
Knowledge. A única opção de contexto nova tem default false nos providers atuais.

## Executado com modelo real

[Evidência sanitizada](b1-openai-evidence.json). O diagnóstico completo fez
9 chamadas OpenAI reais e válidas pelo generator runtime existente. O provider de
entrada era explicitamente diagnóstico sintético; não foi WAHA. Não houve fake
acceptance ou envio. Duas execuções preliminares fizeram uma chamada válida cada
e falharam depois na leitura do registro achatado de métricas (`AttributeError`),
corrigida antes do diagnóstico completo. Total observado: **11 chamadas reais
bem-sucedidas**, não 11 conversas WhatsApp. Dados originais estão em SQLite privado.

| Medida do diagnóstico completo | Observado |
| --- | --- |
| Modelo/esforço | gpt-6.1-sol / low |
| Entrada/saída | 28.528 / 1.266 tokens |
| Cache read/write | 12.482 / 16.019 tokens |
| Raciocínio contado | 79 tokens; nenhum texto de raciocínio retido |
| Latência p50 / máxima | 5.101 / 7.959 ms |
| Estimativa pelas taxas versionadas de 02/10/2026 | US$0,0540097 |
| Reserva conservadora consumida | US$0,491005 / 168.753 tokens |
| Chamada OpenAI com fixture/fixed neste diagnóstico | zero |
| WhatsApp recebido / enviado | zero / zero |

Não é confirmação de preço/fatura atual, custo de WhatsApp ou SLA de conversa.

| Cenário solicitado | Resultado observado |
| --- | --- |
| Saudação | Modelo real; apresentação da Lívia finalizada pelo core |
| Progressiva genérica | Modelo real; fallback seguro por insuficiência de fato de serviço aceito no grounding |
| Preço | Tabela aprovada de progressiva; médio R$200,00; nenhum preço inventado |
| Localização | Endereço aprovado na Av. Dr. Zuquim, 1854, Santana |
| Sem informação aprovada | Marca do produto não confirmada; esclarecimento proposto |
| Interesse em agendamento | Perguntou manhã/tarde no sábado; não prometeu disponibilidade/reserva |
| Atendimento humano | Confirmação e handoff durável no core |
| Desconto | Não concedeu 50%; perguntou orçamento |
| Memória multi-turno | Histórico canônico e fato contextual presentes; continuação real bloqueada pela resposta anterior pending não entregue |
| Reinicialização | SQLite/journal/budget/handoffs retidos; boot pausado; nenhuma continuação WhatsApp comprovada |

O Knowledge real tem 22 fatos aprovados, principalmente preços, dados institucionais,
horário, endereço e canal. Não foram criadas avaliações, informações técnicas,
políticas de agendamento ou fatos de serviço sem aprovação para melhorar os resultados.
Grounding/persona podem renderizar fatos e confirmações determinísticos após decisão
real; isso preserva o contrato, não é uma execução de FixedReplyGenerator.

## Testes com fixtures, separados da inteligência real

Toolchain próprio com 86 pins existentes, CPython3.14.7/macOS ARM64; Python guard
de rede com ambiente sanitizado. Não é isolamento kernel no Mac.

| Execução | Resultado |
| --- | --- |
| Sender Telnyx + contexto | 41 PASS/0 SKIP, 166,238s |
| Primeira suíte B1 | 27 PASS, 26,05s |
| Focal expandido core/WAHA/OpenAI/contexto/handoff/G0/Telnyx | 182 PASS, 251,32s |
| Primeiro teste adicional de timeout | 28 PASS/1 FAIL, 86,97s; expectativa corrigida para bloqueio por custo desconhecido, sem afrouxar runtime |
| Integral local, coletada antes dos dois testes LID | 2.315 PASS/0 SKIP, 549,30s |
| WAHA+contexto após LID | 52 PASS/0 SKIP, 13,04s |
| WAHA atual antes de publicar | 31 PASS/0 SKIP, 11,25s |

Contagens sobrepostas, não somar. JUnit hashes e fingerprints dos source estão na
evidência sanitizada. Os 31 testes atuais exercitam autenticação, escopo/allowlist,
echo/grupos/broadcast/mídia, identidade de sessão, dedupe, ACK antes de modelo,
SQLite e journal, restore obsoleto, consentimento revogado, boot, limites, custo
desconhecido, commit parcial, witness ausente, timeout OpenAI/WAHA, acceptance
ambígua sem retry, handoff e contexto após restart. Transporte WAHA é fake nesses
testes e não autoriza egress real.

```sh
../venv/bin/python scripts/check_telnyx_offline.py --python ../venv/bin/python \
  --output ../b1-publish-focused tests/test_waha_b1.py
```

Ruff check/format376 arquivos, compileall, pip check e diff check PASS. Scanner da
árvore: **3 achados brutos históricos**, triagem existente PASS; range B1 de dois
commits: **zero achados**. O exemplo vazio inicialmente gerava falsos positivos
por captura multilinha; campos gerados foram retirados do exemplo, sem nova
allowlist ou regra de exclusão. Nenhum valor de configuração privada foi encontrado
no conteúdo staged; `.env.b1`, sessão, SQLite e journal estão fora do Git/build.

## Runtime local e CI

Docker/Compose reais; Colima iniciado; WAHA ARM64 2026.10.1 pelo digest fixado.
API autenticada confirmou CORE/WEBJS/Chromium. API sem chave=401; dashboard sem
login=401. Portas publicadas apenas em `127.0.0.1:3000` e `127.0.0.1:8001`.
Backend real iniciado, OpenAI configurada, 22 fatos carregados, worker vivo,
pausado. Sessão observada **SCAN_QR_CODE**, conta ainda não verificada.

WAHA reteve credenciais no log mesmo com log level error; o container foi
substituído com driver `none` e sua configuração efetiva foi verificada. Backend
sem access log; scan de suas saídas não encontrou valores de credenciais. Nada
disso comprova pareamento ou entrega em aparelho.

CI de implementação: [run45042284479](https://github.com/zazacknazzo/rj-studio-ai/actions/runs/45042284479),
head SHA exata acima; instalação, audit e secret scan passaram; suíte de checks
estava em execução ao escrever este checkpoint. A execução da publicação documental
deve ser consultada pela SHA final. Não atribuir success de outra SHA à final.

## Parecer do implementador

Configuração e inferência privada: funcionais nos limites observados. QR manual:
preparado, não confirmado. Recebimento real WhatsApp: não observado. Egress de teste:
**NO-GO**. Conversa bidirecional: **não entregue**.

As pastas de journal/witness detectam restores unilaterais, mas são administradas
pelo mesmo host. Faltam autoridade monotônica autenticada independente, epoch/CAS/
challenge frescos, ledger externo write-ahead por intenção/request/destino antes
de todo HTTP, reconciliação e liberação de recovery por papéis distintos, e auditoria
operacional. Nenhuma auditoria independente B1 foi simulada. O store nega egress
em código, sem flag de escape ou composição com o legado permissivo. O sender não
está ligado ao executor. [Runbook e próximos controles](../operations/waha-b1.md).
