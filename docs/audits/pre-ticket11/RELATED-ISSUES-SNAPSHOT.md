# Issues relacionados — snapshot somente leitura

Consulta: 20/11/2026 (America/Sao_Paulo). Corpos integrais obtidos pelo conector GitHub. Nenhuma issue editada; caixas reproduzidas são estado da fonte.

## #2 — V1 — estado atual, bloqueadores e caminho para o piloto

Fonte: https://github.com/zazacknazzo/rj-studio-ai/issues/2

## Estado verificado em 31/10/2026

**V1 funcional e validada localmente; piloto WhatsApp ainda não aprovado.**

### Entregue e preservado

- [x] V0/V0.1: infraestrutura, persistência, migrations, readiness e retenção explícita.
- [x] V1 Tickets 01–11: geração durável, contexto limitado, structured decision, grounding, Lívia, handoff durável e coleta limitada de interesse em agendamento.
- [x] Messaging M01–M06: contratos, SQLite, outbox, delivery runner, Twilio, processing assíncrono/early ACK e Meta.
- [x] 22 facts humanos aprovados publicados; oito drafts continuam fora do runtime.
- [x] Inteligência considerada **VALIDATED ENOUGH** pelo produto; Agentic Surface **APPROVED/FROZEN**.
- [x] OpenAI Low promovido ao runtime; integração local sintética passou, com outbound falso.
- [ ] Evidência ponta a ponta aprovada no WhatsApp real.
- [ ] Ticket 12 encerrado: continua **in-progress**, com gates operacionais pendentes.

### Git e trabalho local

- Base de integração publicada: `codex/v1-messaging-integration-preflight` @ `7495fb8`.
- Experimento local: `codex/experimental-baileys-bridge` @ `efde945`, ainda sem branch remota.
- Nove arquivos locais contêm correções/testes posteriores à revisão, ainda sem commit. Não confundir o commit com o working tree.
- `main` remoto: `af1c9eb`; a V1 ainda está nas branches de trabalho.
- PR #1 promoveu OpenAI para a branch de integração, não para `main`.
- Esta organização não publica código local nem autoriza merge, conexão de conta ou envio.

### Evidência atual

Em 31/10 foram executados apenas checks focados: **11 testes Python da integração, 15 testes Node e TypeScript passaram**. A suíte completa não foi repetida nesta auditoria. Testes atuais usam socket falso e comunicação local. O smoke real Baileys não foi realizado/aprovado.

O histórico contém um incidente de teste: a reprodução inicial de uma corrida de shutdown abriu um socket sem autenticação e gerou QR temporário; foi encerrado sem conta vinculada/envio. A correção e os testes com dependências falsas estão no working tree e precisam de fechamento.

### Regras para o próximo passo

- Primeiro fechar Baileys offline; depois, com autorização explícita, testar WhatsApp com `fixed`.
- Só depois preparar OpenAI Low na composição experimental.
- Manter prompt, persona, grounding, finalizer e regras comerciais congelados.
- Não reabrir B1/B2 ou rodadas de inteligência; resultados históricos permanecem como foram medidos.
- `unknown` não autoriza retry automático; handoff e ordering continuam obrigatórios.
- Nenhuma conta comercial, cliente real, .env, telefone, QR, sessão ou banco privado deve ser publicado.
- O repositório está **público** no momento da auditoria; confirmar se essa visibilidade segue a intenção do proprietário, sem alterá-la automaticamente.

### Fontes e limites

[Runtime OpenAI e integração local](https://github.com/zazacknazzo/rj-studio-ai/blob/codex/v1-messaging-integration-preflight/docs/architecture/v1-openai-runtime-promotion.md) · [Preflight messaging](https://github.com/zazacknazzo/rj-studio-ai/blob/codex/v1-messaging-integration-preflight/docs/architecture/v1-messaging-integration-preflight.md) · [Decisão de inteligência](https://github.com/zazacknazzo/rj-studio-ai/blob/codex/v1-messaging-integration-preflight/docs/evals/V1/intake-exhaustion-oracle-2026-10-05.md).

Há documentos históricos defasados: Phase B não é o próximo passo, e a promoção OpenAI já ocorreu. A meta antiga de V6 até 02/10/2026 venceu; nenhum novo prazo foi inventado. Issues de acompanhamento organizam a execução; specs/ADRs continuam sendo os contratos técnicos.

## Plano de execução

| Ordem | Item | Situação | Depende de |
| --- | --- | --- | --- |
| 1 | #3 — fechar Baileys offline | Em andamento; primeira ação | Revisão e checks finais |
| 2 | #4 — smoke real fixed | Bloqueado | #3 + autorização operacional |
| 3 | #5 — preparar OpenAI no experimento | Bloqueado | #4 + aprovação do escopo |
| 4 | #6 — integração real/piloto e Ticket 12 | Bloqueado | #5 + autorização/evidência operacional |
| Paralelo | #7 — documentação vigente | Pronto para iniciar | Decisões já registradas |
| Release | #8 — consolidação Git/PRs | Bloqueado para conclusão | #3, #7 e decisão de #6 |
| Backlog | #9 — canais oficiais | Adiado | Configuração/autorização futura |
| Futuro | #10 — V2–V7 | Planejamento posterior | Resultados do piloto |

**Caminho crítico:** #3 → #4 → #5 → #6. Documentação (#7) pode avançar em paralelo; #8 controla a consolidação revisável sem merge automático.

### Checklist de fechamento

- [ ] #3
- [ ] #4
- [ ] #5
- [ ] #6
- [ ] #7
- [ ] #8

[Milestone V1 — piloto controlado](https://github.com/zazacknazzo/rj-studio-ai/milestone/1) reúne somente o trabalho da V1; #9 e #10 ficam fora dele.

### Como manter este acompanhamento

Atualizar o status/label da issue ao iniciar, bloquear ou concluir; registrar evidência e SHA antes de fechá-la. Resultados de teste local, smoke real e aprovação humana são evidências distintas. Nenhuma issue bloqueada autoriza superar controles de conta/envio ou orçamento. Preservar histórico e critérios de aceite. Atualizar esta visão quando um gate mudar.

## #6 — V1 / Ticket 12: validar integração real e prontidão do piloto

Fonte: https://github.com/zazacknazzo/rj-studio-ai/issues/6

Acompanhamento: #2. **Bloqueado por #5 e aprovação operacional.**

## Objetivo
Fechar os gates operacionais remanescentes do Ticket 12 com um piloto restrito, sem reabrir a inteligência já aprovada.

## Aceite
- [ ] Executar uma população controlada com dados sintéticos/participantes consentidos, orçamento e autorização explícitos.
- [ ] Registrar inbound, geração, reply/outbox, ProviderAcceptance e evidência de entrega separadamente.
- [ ] Demonstrar grounding, handoff/suspensão/liberação, interesse em agendamento e ausência de booking/disponibilidade inventados no canal.
- [ ] Medir E2E real, latência do modelo e componentes; manter o gate vigente p95 E2E ≤8s. Métrica diagnóstica não substitui esse gate.
- [ ] Contabilizar usage/custo de todas as tentativas pagas; usar apenas replies completas no denominador. Gate inicial ≤US$10/1.000 replies.
- [ ] Confirmar operação manual de handoff, inspeção de unknown, reinício e retenção/exclusão explícita.
- [ ] Registrar riscos aceitos e decisão humana de piloto; distinguir experimento Baileys de prontidão dos adapters oficiais.
- [ ] Resolver explicitamente critérios da spec antiga supersedidos/deferidos; não declarar Phase B histórica ou comparação cross-provider aprovadas.
- [ ] Encerrar Ticket 12 somente quando seus critérios vigentes estiverem atendidos ou revisados explicitamente pelo produto.

## Fontes / limites
Ticket local `.scratch/rj-studio-ai-v1/issues/12-v1-eval-and-observability-gate.md`, spec V1, ADRs e `docs/architecture/v1-openai-runtime-promotion.md`.
Sem novas rodadas de inteligência, V2, cliente comercial real, agenda ou merge automático.

## #8 — Git: preparar consolidação revisável da V1 sem merge automático

Fonte: https://github.com/zazacknazzo/rj-studio-ai/issues/8

Acompanhamento: #2. **Preparação de release; não autoriza merge.**

## Contexto
`main` remoto está em `af1c9eb`. A base de integração publicada está em `7495fb8`; a implementação Baileys e correções ainda são locais. O histórico deve ser preservado.

## Aceite
- [ ] Após #3, identificar os SHAs revisados e garantir working tree conhecido/commits coerentes.
- [ ] Confirmar que branch de release contém apenas as linhas de trabalho autorizadas; não ressuscitar Ticket 09 antigo nem commits descartados.
- [ ] Auditar histórico/diff a publicar: sem .env, secrets, sessões, QR, SQLite real, logs/PII ou artefatos locais.
- [ ] Publicar branches aprovadas e abrir PRs com bases explícitas e escopo legível, preferindo separação do experimento.
- [ ] Vincular evidência de testes, docs (#7) e gates operacionais (#6).
- [ ] Definir candidato de release e limitações; não rotular piloto/produção como aprovado sem evidência.
- [ ] Manter merge manual e aguardar decisão explícita antes de integrar main; sem rebase/force push do histórico publicado.

## Dependências
Preparação depende de #3; consolidação de release depende também de #7 e decisão sobre #6.
Revisar com o proprietário a visibilidade atualmente pública antes de publicar material operacional.

## #9 — Canais oficiais: preservar gates pendentes de Twilio e Meta

Fonte: https://github.com/zazacknazzo/rj-studio-ai/issues/9

Acompanhamento: #2. **Backlog operacional; fora da sequência imediata Baileys.**

Twilio e Meta estão implementados/testados offline. Os últimos registros ainda não comprovam smoke real aprovado da V1. Baileys não fecha esses gates.

## Critérios para retomada futura
- [ ] Revalidar privadamente configuração, confiança/validade das credenciais e elegibilidade do canal; presença/formato não provam validade.
- [ ] No Meta, resolver o pré-requisito de App Secret e assinatura do webhook conforme runbook.
- [ ] No Twilio, atender os pré-requisitos do smoke protegido conforme runbook.
- [ ] Validar HTTPS/callback quando aplicável sem desabilitar TLS.
- [ ] Só executar smoke com autorização e evidência sanitizada; preservar unknown sem retry automático.
- [ ] Registrar resultado individual de cada provider sem inferir sucesso a partir do outro.

Não auditar/exibir valores de credenciais nesta issue. Não iniciar configuração, rotação, onboarding ou envio nesta rodada.
Fontes: `docs/architecture/v1-twilio-live-smoke.md`, `docs/runbooks/meta-cloud-api-smoke-test.md`.

## #10 — Roadmap após V1: V2–V6 e V7 SaaS

Fonte: https://github.com/zazacknazzo/rj-studio-ai/issues/10

Acompanhamento: #2. **Direção futura, sem implementação autorizada.**

| Fase | Resultado planejado |
| --- | --- |
| V2 | CRM e memória do cliente |
| V3 | Motor comercial e follow-ups |
| V4 | Agenda real e prevenção de conflitos |
| V5 | Áudio/fotos e escalonamento técnico |
| V6 | Atribuição, conversões e growth |
| V7 | SaaS multiempresa após comprovar o produto |

A meta histórica de V6 até 02/10/2026 venceu. Replanejar após evidência do piloto da V1 (#6); não criar datas artificiais ou implementar infraestrutura multi-tenant antecipadamente.

## Próxima decisão de planejamento
- [ ] Validar resultados e limitações do piloto V1.
- [ ] Definir prioridade, capacidade e nova previsão com o product owner.
- [ ] Especificar/aprovar apenas a próxima versão antes de criar implementation tickets.
- [ ] Manter V0–V6 single-business; integrações por adapters, fatos do salão fora do core e ADRs para decisões duráveis.

Este item não inicia V2 nem cria tickets de implementação dessas versões.

---
**Replanejamento proposto em 11/11/2026:** o product owner quer validar V1–V2 no RJ Studio e começar a comercializar uma fundação SaaS após V2, usando receita recorrente para financiar V3–V7. Esta nova direção é acompanhada em #13 e exige um gate V2.5 de isolamento multiempresa, segurança, onboarding, billing e custos antes do primeiro cliente externo. **Este issue permanece como histórico do roadmap inicial (V7 SaaS); não executar alterações arquiteturais nem lançamento sem spec/autorização.**


## #12 — V1 — Naturalidade e autonomia da Lívia: remover frases fixas do atendimento e permitir redação factual flexível

Fonte: https://github.com/zazacknazzo/rj-studio-ai/issues/12

## Decisão do product owner — 11/11/2026

O product owner rejeitou a abordagem de **catálogo de frases autorizadas como limitador da linguagem** e pediu **maior liberdade de escrita e autonomia conversacional**, com o objetivo explícito de a Lívia soar o mais humana possível.

**Não confundir com autorização para inventar preço, desconto, disponibilidade, horários, serviços, políticas, agendamento confirmado, diagnósticos ou resultados de ações.** Transparência quando questionada sobre ser IA continua mandatória.

## Estado real do código (baseline Telnyx Ticket 06 `5b8f561`)

- Já existe `surface=agentic` com `ConversationalReplyPart(kind="conversation", text=...)`, no qual a IA escolhe wording de saudações, perguntas, acolhimento, CTA e continuação; o antigo `REPLY_PHRASES` continua para `legacy` e fallbacks. **Não afirmar que toda resposta é formada só por catálogo.**
- `llm_decision.reply_text` é descartado na renderização probabilística.
- `grounding.finalize_reply` insere `SalonKnowledgeFact.statement` literalmente para partes `fact`, podendo soar como leitura de tabela; código rejeita assertions protegidas em texto livre.
- `LiviaPersona` tem limite de 800 caracteres, regras de identidade/risco e constraints sobre emojis.
- Histórico de evals/human review já identificou respostas secas, fallback genérico, interrupção comercial e perda de contexto; preservá-lo, sem reescrever scores.

## Objetivo de evolução (proposta de contrato; exige spec antes de implementar)

- [ ] Manter `surface=agentic` como caminho principal e **retirar seleção obrigatória de phrase IDs, frases fixas normais e CTA forçado**. Reduzir fallbacks genéricos que ignoram a pergunta do cliente.
- [ ] Permitir que o modelo **redija a mensagem customer-visible em português natural**, com variação contextual, tom humano, precisão comercial, perguntas apenas quando necessárias, sem robô/call center.
- [ ] Tornar Salon Knowledge uma **fonte estruturada de fatos**, não um catálogo de sentenças que devem aparecer literalmente. Permitir paráfrase fiel e seleção do detalhe relevante (ex.: preço segundo comprimento), mantendo números, qualificadores, condições e políticas corretos.
- [ ] Preservar limites rígidos: nada de inventar fatos do salão, descontos não autorizados, disponibilidade, booking/cancelamento/pagamento executados, diagnósticos, identidade humana falsa, ou contornar Human Handoff.
- [ ] Model output segue **não confiável**: projetar um finalizador com validação de claims críticos, referências, condições comerciais e actions; evitar prometer prova semântica perfeita de texto livre. Considerar mitigação/fallback seguro e testes adversariais.
- [ ] Preservar intake durável de serviço/dia/período (no máximo 3 perguntas por episódio) e regras de recuperação/hand-off, sem tornar a conversa interrogatório.
- [ ] Avaliar em **conversas completas, não apenas respostas isoladas**: naturalidade, adaptação ao cliente, não repetição, esclarecimento útil, venda consultiva, factualidade, proteção de instruções, escalonamento adequado, latência/custo.
- [ ] Fazer um protocolo de revisão humana qualitativa com cenários reais sintéticos; critérios de aceite não devem ser apenas `pytest PASS`.
- [ ] Propor e aprovar spec/ADR com migração dos modos `legacy`/`agentic` e compatibilidade, sem alterar retrospectivamente as evidências históricas.

## Restrições e gate

**Requisito de produto aprovado para planejamento; implementação NÃO iniciada por este issue.** Não modificar silenciosamente inteligência congelada enquanto os Tickets Telnyx 07–13 são implementados. O orquestrador deve criar e revisar um ticket de reabertura restrita da superfície conversacional, com impacto claro e testes/evals, mediante autorização específica.

**Gate:** concluir e validar qualidade conversacional antes do piloto V1 real. Registrar risco de falsa alegação factual em texto livre e estratégia de mitigação. Relação com registro de riscos da Coexistence: #11.

**Referências:** `src/rj_studio_ai/livia_persona.py`, `grounding.py`, `llm_decision.py`, `conversational_surface.py`, `docs/architecture/v1-agentic-surface-phase-1.md`, `docs/evals/V1/agentic-surface-human-review-2026-10-04.md`.


## #13 — Estratégia de produto — SaaS após V2, fundação multiempresa V2.5 e roteamento multimodelo

Fonte: https://github.com/zazacknazzo/rj-studio-ai/issues/13

# Mudança de direção de produto — 11/11/2026

## Decisão proposta pelo product owner
Após testar a V1 e V2 no RJ Studio, **iniciar a comercialização controlada do SaaS** e financiar o desenvolvimento das versões V3–V7 com receita recorrente. A V7 deixa de ser a primeira etapa SaaS e passa a representar maturidade/escala. **Não** interpretar esta decisão como autorização para lançamento, implantação ou alteração de código imediatos; requer aceite técnico, pilotos e aprovações específicas.

Outra diretriz: **não usar GPT-6.1 Sol como modelo padrão de todos os turnos**. Adotar roteamento por complexidade/qualidade/custo entre GPT-6 Luna, GPT-6.1 Terra, Claude Haiku/Sonnet, reservando Sol/Opus (ou sucessores) para tarefas complexas quando evals justificarem.

## Sequência sugerida
- [ ] **V1:** terminar Coexistence Telnyx, gates operacionais e naturalidade/segurança do atendimento (issues #11 e #12), antes de qualquer uso real não autorizado.
- [ ] **V2:** CRM e memória no RJ Studio; medir resultado comercial incremental, churn de oportunidades, custo por conversa, latência, handoff, qualidade do atendimento e confiabilidade.
- [ ] **V2.5 (novo gate obrigatório):** especificar e implementar fundação SaaS antes do **primeiro cliente externo**. Inclui isolamento lógico/físico de tenants, isolamento de dados e credenciais, autorização por usuário/recurso, números/provedores por tenant, rotas/webhooks/filas por tenant, idempotência e controles de concorrência scoped, proteção LGPD, segregação de conhecimento, onboarding, billing, planos, quotas, uso, auditoria, observabilidade, backup/restore e operações.
- [ ] **Lançamento controlado:** 5–10 salões, preços e franquias de consumo testados, suporte/onboarding mensurado, custos reais por tenant, contrato/consentimento e plano de incidentes. Não vender V3–V7 como entregues.
- [ ] **V3–V6:** ampliar funcionalidades com priorização por impacto comercial e margem de contribuição; não depender de financiamento externo como condição de existência.
- [ ] **V7:** maturidade operacional, automação de onboarding, escala e extensibilidade de SaaS.

## Roteamento multimodelo — requisito de arquitetura, não implementação autorizada
- [ ] Introduzir contrato provider-neutral de geração com catálogo de modelos e preços versionados, budgets de entrada/saída, medição de latência/custo por tenant e idempotência.
- [ ] Testar **Luna/Haiku** para classificação, extração e turnos triviais; **Terra/Sonnet** para conversas comerciais e redação de alta qualidade; **Sol/Opus** sob demanda para contexto complexo, raciocínio difícil ou auditorias, sempre baseado em evals reais. Não confundir preço reduzido com igual qualidade comercial.
- [ ] Definir router por tipo de trabalho, contexto, incerteza e risco, preferencialmente sem chamada extra cara apenas para classificar. Verificar se fluxo de classificação separada compensa latência.
- [ ] Não permitir fallback arbitrário que produza dupla resposta, dupla ação, mudança de contrato JSON, bypass de grounding, mão dupla de providers sem controle ou reenvio `unknown`.
- [ ] Preservar Human Handoff, regras de fatos/políticas, autorização de descontos, agendamento, tempo de serviço e elegibilidade do WhatsApp. Qualquer modelo que falhe em emitir decisão validável leva a safe outcome ou escalação; não inventar.
- [ ] Aprovar cenários e métricas: naturalidade em conversa longa, precisão factual, conversão incremental, segurança, consistência de JSON, latência p95, custo por conversa e custo por cliente.
- [ ] Versionar a política de roteamento para permitir rollback/A-B, não alterar o comportamento de conversas em andamento sem delimitação.
- [ ] Confirmar modelos e preços oficiais **na implementação**, pois IDs, tarifas e disponibilidade podem mudar.

## Gates e riscos
1. O core e os dados atuais são **single-business**; não basta acrescentar um campo `tenant_id`. Exigir revisão sistemática de consultas, chaves únicas, acessos, jobs, webhooks, contexto LLM, armazenamento e operações para evitar vazamento entre salões.
2. R$199/R$200 é hipótese de **plano de entrada**, a validar contra mensagens Telnyx/Meta, custos de tokens, impostos, suporte, implantação, churn e CAC. Definir franquia, overage e limites antes de vender; não prometer ilimitado.
3. Provar confiabilidade, segurança, observabilidade e consentimento antes de contratar terceiros; o RJ Studio é piloto inicial, mas apenas uma empresa não valida automaticamente todos os processos.
4. Atualizar `docs/ROADMAP.md` e specs/ADRs em branch autorizada depois de ratificada a estratégia. Não alterar congelamento da inteligência enquanto Tickets 07–13 estiverem em andamento.
5. Vincular riscos no issue #11; #10 representa o roadmap antigo (SaaS só na V7) e deve ser reconciliado, preservando o histórico.

## Evidências para encerramento
Spec/ADR de fundação SaaS aprovada, testes reais de isolamento cross-tenant, rollback/migração/retention, métricas de custo e desempenho por modelo/tenant, aprovação do piloto comercial e evidência de billing e governança. Este issue é um registro de decisão/planejamento, não autorização de release.

