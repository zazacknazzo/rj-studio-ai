# Observabilidade e performance — critérios de aceite propostos

22/11/2026. Ingress local já possui contadores de status, buckets finitos e observação
durável de rejeição. Os demais indicadores abaixo são REQUISITOS de operação, não
exporters/alertas implantados. Sem labels de telefone, Customer, Message/eventID,
Authorization/body, hash de texto ou string arbitrária de erro. Case refs opacas só
em fila restrita; métricas agregadas nunca substituem recibo/audit.

| Indicador | Critério proposto antes do piloto | Coleta/evidência | Responsável/ação |
| --- | --- | --- | --- |
| ACK pós-commit | Toda204 após commit; aplicação <1.5s; caminho real <2s | ASGI monotônico + amostra externa proxy/TLS/rede | SRE; deadline/commit incerto→503, não ACK tardio |
| Latência p50/p95/p99 | Reportar por classe suportada/replay/rejeição/falha; local alvo p95<1.0s,p99<1.35s | Histogram finito, ensaio com carga declarada; semSLA | SRE; perfil/host/concurrency/SQLite registrados |
| 204/422/503 | Separar supported/unsupported/infra; zero2xx indevido | TelnyxIngressMetrics e origem de tráfego controlada | Operações; qualquer422 novo no piloto precisa triagem |
| Dedupe | Uma admissão por logical Message em replay/subscriptions | Receipts/journal+counter proposto de replay, semPII | Integração; duplicata de reply interrompe |
| Assinatura/replay inválidos | Zero efeitos; contador403 finito; investigar pico≥5/min | Logs categóricos/metrics sem headers | Segurança; conferir origem/chave/clock sem bypass |
| Quarentena | Generation/egress/channelfalse e alerta contínuo do estado | ReadinessT12 + fence diagnóstico externo futuro | SRE; nunca desligar alerta liberando canal |
| Lifecycle bloqueado | Zero autorização após disconnect/offboard; reconnect não libera | View eligible_telnyx_channels e audit | Operações+conta; exigir prova atual sync/binding |
| Unknown | Qualquernovo unknown interrompe novas saídas da Conversation e é triado imediatamente | Outbox+ledger independente futuro | Operações+recovery; sem retry/nova key |
| Conflict | Qualquercontradição preservada e encaminhada; não limpar estado | delivery_status_events/status_conflict | Operações; validação externa antes de decisão |
| Unsupported | Repetição422 e counterdurável observáveis; human case aprovado antes piloto | Rejection aggregate atual; fila é gate pendente | Operações; sem falsa recepção204 |
| SQLite | Integrity/FK/schema/WAL/full e writability verificados; falha→503 | Checks atuais + disk/lock/fsync no deploy | DBA; suspender processamento antes de restore |
| Backlog | Contagem por pending/sending/retryable/unknown; idade máxima; proposta alerta>10 ou oldest>60s | Queries mínimas/queue monitor futuro | SRE; limitar admissão e pausar, sem esconder atrasos |
| Intervenção humana | Operador designado disponível em100% da sessão piloto; proposta ACKinterno≤60s | Fila restrita com responsável/age | Operações; ausência de operador interrompe piloto |
| Acesso/revogação | Operação negada auditada; revoke invalida sessão imediatamente | AdminT05/authoritylab; IAM real pendente | Segurança; segredo perdido→suspender/rotacionar |
| Provider retries/failover | Replays idempotentes; sem fila infinita; esgotamento visível | Tráfego sintético + logs saneados do provider no gate real | Integração; caso humano ao esgotar |
| Disponibilidade externa | Falha authority/witness/IdP/proofs não abre autorização | Fault injection lab; drillinfra pendente | SRE; fail-closed sem permit emcache |

Limites são propostas internas de ensaio e devem ser ratificados antes do gate externo.
Não são SLA comercial. O orçamento externo2s é conservado apesar de Help específico
WhatsApp publicar200≤5s; confirmar qual caminho real se aplica sem afrouxar a implementação.

## Carga offline executável

test_telnyx_asgi_load.py:128envelopes únicos e128duplicados, concorrência8, ASGIin-process,
SQLite WAL/full e assinatura sintética. Reporta p50/p95/p99/máximo,204/503 e replays após
drain; exige uma admissão por logical Message e zero late success.
Carga de falha controlada:32envelopes/8concorrentes com BEGIN IMMEDIATE segurado
por outra conexão. Todos503, zero Messages; liberar lock e repetir MESMOS envelopes
produz32x204 e32admissões, zerooutbound. Propriedades JUnit preservam números observados.
Testes de durabilidade cobrem deadline/read/SQL/commit/cancelamento sem ACK falso.

Local CP5: únicos128x204, p50=0.00551s/p95=0.06675s/p99=0.19335s;
duplicados128x204,p50=0.01688s/p95=0.07273s/p99=0.11029s.
Lock32x503, p50=0.58143s/p95=0.59694s/p99=0.59734s; replays32x204.
HostmacOS/Python3.14.7/SQLite3.50.4;13testes incluindo guard e v8 passaram5.27s.
Suítes integrais/CI podem apresentar outros números por contenção/carga do host;
preservar cada amostra e não selecionar só o melhor resultado.

ASGI local exclui internet/proxy/TLS/handshake/servidor real/rede do provider e cliente,
clockNTP e falhas de filesystem reais. Não provaACKnaTelnyx nem throughput comercial.
GateCX20/#6 mantém p95E2E≤8s e custoLLM≤US$10/1000replies completas, sem alterar targets.
Produto precisa ratificar os pontos/relógios de medição E2E e amostra antes do piloto;
acceptance, delivered e read são tempos distintos, reportados separadamente.
