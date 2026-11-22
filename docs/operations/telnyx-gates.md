# Matriz de gates — Ticket13

22/11/2026. Inventário da issue11 (todos CX01–37), auditoria integral pré11
502bca89e64b45e981ad9c5f2eeb189aad3dd9e6 (AUD01–06/AR01–03), specs/ADRs06–12,
relatórios10/11/12 e parecer7069497120. Baseline f1496be. Nenhum risco novo foi
fechado nesta matriz. CX31 conserva a resolução OFFLINE previamente aprovada.
“Implementação” distingue código existente, laboratório, proposta e ausência real.
Dono é PAPEL proposto: nomes/designação e aprovação são gates futuros.
Arquivos de teste abaixo estão em tests/; evidência anterior é inspecionada, não
recontada como execuçãoT13. Resultados atuais ficam no relatório A–P.

| Gate | Requisito | Implementação | Evidência | Lacuna | Dono | Teste de aceite | Bloqueia piloto? |
| --- | --- | --- | --- | --- | --- | --- | --- |
| CX-01 | Retenção/expurgo sem perder dedupe/fences | Purge limitado existente; políticaT13 | T07/10/11; testes de maintenance e receipts | Tombstones/erasure/backup reais pendentes | Privacidade+DBA | Replay após purge/restart/restore sem gerar/envio repetido | Sim |
| CX-02 | Pausa autenticada antes de atendimento humano; echo best-effort | API de operaçãoT05; runbookT13 | test_automation_operations.py; test_generation_pause.py | Operador/celular/acesso real não ensaiados | Operações | Operador seleciona Conversation, pausa, confirma e responde sem echo | Sim |
| CX-03 | Echo inédito atrasado reaplica pausa conservadora | Journal/efeitosT07 | test_telnyx_messages.py | Atrasos/subscriptions reais e treinamento | Operações | Duplicata conhecida não repausa; echo distinto antigo repausa e alerta | Revisar |
| CX-04 | Proveniência source para resume futuro | T07 body.timestamp e cutoff | test_telnyx_messages.py; test_automation_operations.py | TelnyxE2E; Meta/Twilio sem proveniência continua limitação | Integração | Novo inbound após resume gera; antigo/sem prova é suprimido | Sim |
| CX-05 | Clock/skew/cutoff sem reabrir janela | Clock high-waterT10; NTP só plano | test_whatsapp_policy.py; test_telnyx_submission.py | NTP e tempos remotos no deploy | SRE | Skew/clock correction negativos + monitoramento real | Revisar |
| CX-06 | Preservar in-flight/unknown; nenhuma promessa de recall | Marker transacionalT11 | test_telnyx_sender_integration.py; test_outbound_pause.py | Janela autorização→HTTP real irrecolhível | Engenharia+Operações | Pausa após marker mostra in_flight e não dispara segunda entrega | Sim |
| CX-07 | Admin autenticado, TLS e acesso restrito | Bearer/rolesT05; planoT13 | test_automation_operations.py | Ingress/TLS/proxy/rotação/abuso reais | Segurança+SRE | Unauthorized/revogado negado; Authorization/body ausentes de logs | Sim |
| CX-08 | Workflow utilizável de selecionar/pausar/retomar Conversation | IDs opacos/API; runbookT13 | T05 e simulações SQLite | Sem UI/descoberta móvel integrada | Operações+Produto | Ensaio humano aprovado com handoff/unresolved/in_flight visíveis | Sim |
| CX-09 | Assinatura raw Ed25519/timestamp/replay antes de efeito | T06+T12 | test_telnyx_authentication.py; test_telnyx_asgi.py | Chave/captura real e proxy | Segurança+Integração | Assinatura real autorizada e negativos sem persistência | Sim |
| CX-10 | Elegibilidade +55 e Coexistence sem perder Business App | Fontes públicas; checklist futuro | SpecT06 e planoT13 | Conta/número reais não verificados | Responsável da conta | Telnyx confirma número secundário elegível e rollback | Sim |
| CX-11 | Lifecycle bloqueia; reconnect não é active | T09+ASGIT12 | test_telnyx_lifecycle.py | Prova positiva real de binding/sync/eligibilidade | Integração+SRE | Disconnect cancela; restart não reabre; sync pendente bloqueia | Sim |
| CX-12 | Uma admissão por inbound entre subscriptions | Namespace/receiptsT07 | test_telnyx_messages.py | Inscrições reais WABA/profile | Integração | Duplicata de vias reais não gera reply dupla | Revisar |
| CX-13 | Canal/identidade inequívocos; sem fusão de aliases | T07 scoped identities | test_telnyx_messages.py; test_telnyx_delivery_status.py | Migração/BSUID e vários canais não implantados | Arquitetura | Dois canais/customer opacos não contaminam Conversation | Revisar |
| CX-14 | Edit/revoke/status observam sem gerar e sem falso delivered | T07/08 ledger scoped | test_telnyx_delivery_status.py | Payloads/statuses reais | Integração | Callbacks cedo/fora de ordem/contraditórios mantêm conflito | Revisar |
| CX-15 | Chave estável; unknown não retry; idempotência limitada | T10/11 request+markers | test_telnyx_sender_adversarial.py; test_telnyx_submission.py | Sem exactly-once externo ou reconciliação real | Engenharia+Operações | Timeout/409/422/expiry/restore nunca nova chave ou resend cego | Sim |
| CX-16 | Consentimento separado; free-form24h/template aprovado | PolíticaT10; workflowT13 | test_whatsapp_policy.py; test_telnyx_submission.py | Consentimento/template reais não provados | Operações+Privacidade | Negar sem prova, revogado e exatamente24h; template conhecido não basta | Sim |
| CX-17 | Integração funcional real | Componentes e composição offlineT06–12 | test_telnyx_asgi*.py; sender integration | Runtime/conta/transporte reais proibidos | Integração | E2E só após autorização explícita e gates anteriores | Sim |
| CX-18 | Custos e contratos atuais | Plano de medição; sem simular preços comerciais | Fontes oficiais de pricing a rever no gate | Uso/tarifa/câmbio e custo real não medidos | Produto+Financeiro | Orçamento/custo unitário aprovados e monitorados | Revisar |
| CX-19 | CI/execução independente reproduzível | PipelineT13 e resolução proposta | RelatórioT13 registrará execuções reais | CI final e skip histórico exigem evidência própria | CI+Orquestrador | Clone limpo, checks, quatro revisões e skip explicitado | Sim |
| CX-20 | Piloto autorizado e métricas WhatsApp reais | PlanejamentoT13 apenas | Carga ASGI sintética; não éE2E | p95E2E≤8s/custo≤US$10 por1000 replies sem prova | Produto+Operações | Autorização, consentidos, métricas completas e decisão formal | Sim |
| CX-21 | Branch/segredos/release/main preservados | Checkpoints normais; scannerT13 | git diff/Gitleaks/remote SHA | Merge/release não autorizados; review final pendente | Release+Segurança | Scan triado, diff limitado, rollback aprovado sem merge automático | Sim |
| CX-22 | Separar health/ingress/admin/generation/egress/channel | ReadinessT12 | test_telnyx_asgi_observability.py | Readiness operacional aindafalse | SRE | Ingress pode estar saudável com saída bloqueada | Revisar |
| CX-23 | SaaS/Tech Provider somente gate futuro | Nenhuma expansãoT13 | AGENTS/ADR existentes | Projeto single-business; capacidade BSP não comprovada | Produto+Arquitetura | Spec/isolamento próprios antes de outro negócio | Não; futuro |
| CX-24 | Raw headers/stream/commit antes ACK | ASGI/HTTP boundedT12 | test_telnyx_http.py; test_telnyx_asgi_durability.py | Proxy/TLS/headers de rede reais | SRE+Integração | Duplicatas/chunked/lock/commit failure sem ACK indevido no deploy | Sim |
| CX-25 | Proveniência chave/libsodium/NTP no deploy | Validação sintéticaT06; checklistT13 | test_telnyx_authentication.py | Chave real/wheel/rotação/clock não testados | Segurança+SRE | Aquisição confiável, runtime inventariado, skew monitorado | Sim |
| CX-26 | Aceite conversacional/naturalidade próprio | ForaT13; inteligência congelada | Issue12 e avaliações anteriores, não reexecutadasT13 | Revisão produto/avaliação humana pendente | Produto+Orquestrador | Spec/ADR e evidência humana no ticket próprio | Sim |
| CX-27 | Isolamento antes de SaaS externo | ForaT13; sem tenants novos | Issue13; AGENTS | V2.5/V7 requer decisão de produto | Produto+Arquitetura | Isolamento ponta a ponta em escopo próprio | Não; bloqueia SaaS |
| CX-28 | Qualidade/custo de router multimodelo | ForaT13; modelo estático | Issue13/evals futuros | Router não implementado/autorizado | Produto+IA | A/B e efeitos únicos antes de habilitar router | Não; bloqueia router |
| CX-29 | Unsupported sem descarte/2xx falso/tempestade silenciosa | 422+agregado durávelT12; runbookT13 | test_telnyx_asgi_observability.py; probes independentes | Fila humana/retry/failover/conteúdo seguro reais | Operações+Integração | Mídia/localização/futuro/batch422; falha counter503; alertas+esgotamento | Sim |
| CX-30 | ACK dentro do contrato conservador2s | Work1.35s,total1.5sT12 | test_telnyx_asgi_load.py; durability | Help5s conflita; rede/TLS/fsync reais não provados | SRE | ACK204 após commit e <2s no proxy real; reportar503/backpressure | Sim |
| CX-31 | Status precoce preserva escopo/terminalidade | RESOLVIDO SOMENTE OFFLINE por orquestradorT08 | v1-ticket08-validation.md; delivery_status testes | Aceite real continuaCX14; preservar estado da issue | Integração | Regressões scoped/early/conflict permanecem verdes | Offline resolvido |
| CX-32 | Resolução de status conflitante sem duplicar/apagar | Bloqueio durávelT08; runbookT13 | test_telnyx_delivery_status.py | Não há resolver operacional autorizado | Operações+Segurança | Evidência externa+decisão auditada; sem limpar flag/retry tácito | Sim |
| CX-33 | Ativação/rebinding autenticados e epoch atual | BloqueioT09; recovery labT13 | test_telnyx_lifecycle.py; testes recoveryT13 | Ativação/rebinding real não implementados | Responsável conta+SRE | Binding/sync positivos, auth e restart/concorrência reais | Sim |
| CX-34 | Custo residual LLM após gate prévio | Fronteira rechecadora existente | test_generation_pause.py | Cancelamento/custo real requer aceite; sem alterarLLM | Produto+Operações | Resposta não persiste após bloqueio; custo residual comunicado | Revisar |
| CX-35 | Request exato/escopo/MAC e retry externo controlado | Sender injetadoT11; store strictT12 | test_telnyx_request.py; sender integration | Credential→org/profile/number real + transporte futuro | Segurança+Integração | Mesma key/bytes; SDK sem retries; falta request negada | Sim |
| CX-36 | Aquisição/revogação consent e aprovação atual de template | ContratoT10; workflowT13 | test_telnyx_submission.py; race tests | Workflow/identidade/provas reais não implantados | Privacidade+Operações | Proveniência/finalidade/prazo, opt-out concorrente e template real | Sim |
| CX-37 | BSUID outbound não implementado | E.164 only deliberadoT10/11 | test_telnyx_messages.py; test_telnyx_submission.py | Não prometer replies a números ocultos | Integração | Negar sem telefone provado; spec própria para BSUID | Revisar |
| AUD-01 | Restore não concede autorização; antirollback independente | Laboratório de contratoT13; quarentenaT12 | Testes recoveryT13 (CP2); auditoria pré11 | Autoridade/witness/ledger completos e integração no deploy reais | Recovery+SRE+Segurança | Epoch/revisão/proofs/revogações/crash/restore reais antes de fechar | Sim, qualquer egress |
| AUD-02 | Toolchain corrigida usada e auditada | Venv próprio pip26.3/pytest9.2.0 | Manifesto/pip-auditT13 (CP5) | Consulta advisories/CI final deve ser registrada | CI+Segurança | pip check/audit e integral de resolução reproduzida | Sim, gateCI |
| AUD-03 | Handoff/checkpoints/escritor exclusivo e retomada | Norma e confirmação humana22/11 | TICKET-13.md; clone rehearsalCP7 | Não é lock distribuído/autenticação de segunda conta | Engenharia+Responsável projeto | Fetch/status/SHA/teste focal em clone limpo; sem force | Sim na troca de conta |
| AUD-04 | Docs correntes distinguem histórico e autorização atual | Índices/runbook atualizadosT13 | Diff documentalT13 | Não reescrever evidência histórica | Engenharia | Links válidos e nenhum trecho corrente autoriza operação | Revisar |
| AUD-05 | Ratificação SaaS/roadmap em escopo próprio | ForaT13; sem alterar direção | Issue13 e AGENTS | Decisão produto V2.5/V7 pendente | Produto | Decisão ratificada antes de planejar/comercializar SaaS | Não; fora escopo |
| AUD-06 | Fixture histórica/CI portátil | Skip preservado; compat sintética distintaCP5 | test_commercial_steering.py | Artefato original não versionado não foi recuperado | CI+Produto | Não fabricar história; CI registra skip e teste sintético próprio | Sim, aceite reproduzível |
| AR-01 | Custo residual LLM após pausa | MesmoCX34; sem mudançasLLM | Auditoria pré11 architecture | Aceite operacional futuro | Produto | MesmoCX34 | Revisar |
| AR-02 | Seam interna genérica mais permissiva | Compatibilidade mantida; lab nunca libera store | Auditoria pré11; ASGI egress testes | Produção requer composition segura própria | Arquitetura | Nenhum runtime Telnyx usa seam genérica | Sim antes de egress |
| AR-03 | Invariantes SQL concentradas | Sem refactor especulativo | Migrations/persistence testes existentes | Matriz e revisão a cada alteração | Engenharia | Regressões e integridade/FKs em toda migration | Revisar |

## Ordem de decisão

1. Desenvolvimento OFFLINE: baseline/exclusividade/ambiente/escopo preservados,
   spec antes de código, testes e auditoria do orquestrador.
2. Próximo gate externo: NO-GO sem nova autorização explícita e zero bloqueadores
   aplicáveis abertos ou exceção formal do product owner, com mitigação/prazo/dono.
3. Piloto e produção: NO-GO. Plano, CI e simulation_ready não autorizam execução.
4. AUD01 só pode ser proposto para encerramento no ambiente correspondente depois
   de testar autoridade/witness/ledger/integração reais, inclusive falhas e rollback.

