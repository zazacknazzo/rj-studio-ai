
TICKET 09 — TELNYX COEXISTENCE V1
Lifecycle do WhatsApp Business e bloqueio durável de canal

PAPEL
Você é o engenheiro sênior responsável pelo Ticket 09 da integração Telnyx Coexistence V1 do RJ Studio AI.

O Ticket 08 foi aprovado pelo orquestrador após auditoria estática direta no GitHub.

BASELINE EXATA
Repositório: zazacknazzo/rj-studio-ai
Branch: codex/telnyx-coexistence-08-status
SHA: 2e66cd86bf6842bdb3eeee2c9e5faf3d15f21335

Tickets 01–08 aprovados.
Ticket 09 AUTORIZADO apenas offline.
Tickets 10–13 NÃO AUTORIZADOS.

Leia antes de implementar:
- AGENTS.md e instruções locais
- docs/specs/V1-telnyx-coexistence-ticket-08.md
- docs/decisions/0010–0016
- docs/architecture/v1-ticket08-validation.md
- Issue #11 completo e seus comentários
- Domínio, journal, persistence, pause, sender gates e migrations

DOCUMENTAÇÃO OFICIAL
https://developers.telnyx.com/docs/messaging/whatsapp/coexistence/webhooks
https://developers.telnyx.com/docs/messaging/messages/receiving-webhooks

OBJETIVO

Processar de forma autenticada, durável e segura os eventos whatsapp.account.update e impedir que uma conexão WhatsApp desconectada, removida ou ainda não verificada continue gerando ou enviando respostas automáticas.

Não habilitar a Telnyx no runtime de produção.

1. CONTRATO DO EVENTO

Interpretar exclusivamente o contrato real:

data.event_type = whatsapp.account.update
data.payload.record_type = whatsapp_account
data.payload.waba_id = WABA configurada
data.payload.event = transição de lifecycle

Transições conhecidas:
- ACCOUNT_OFFBOARDED
- ACCOUNT_RECONNECTED
- PARTNER_REMOVED

Não confundir data.id (identidade do evento) com WABA, número comercial, profile ou ID de Message.

Verificar assinatura Ed25519 usando o autenticador do Ticket 06 ANTES do parsing e dos efeitos.

Não aceitar WABA diferente da configurada.

Nunca inferir a identidade do canal a partir de campos ausentes ou IDs de mensagens.

2. POLÍTICA DE LIFECYCLE

ACCOUNT_OFFBOARDED:
- Registrar observação durável.
- Bloquear automação associada à conexão.
- Impedir novas gerações e novos envios.
- Preservar tentativas e evidências existentes.

PARTNER_REMOVED:
- Registrar desconexão durável.
- Bloquear geração e envio.
- Não executar reconexão automática.

ACCOUNT_RECONNECTED:
- Registrar observação durável.
- Manter o canal em verification_required / sync_pending.
- NÃO marcar o canal automaticamente como active.
- NÃO retomar automações.
- NÃO reenviar mensagens anteriores.
- Exigir futura validação operacional e autorização específica.

Evento desconhecido:
- Falhar de modo conservador.
- Definir e documentar política para observação durável ou rejeição.
- Não interpretar evento desconhecido como reconexão válida.
- Não gerar ACK de sucesso sem tratamento durável aprovado.

3. GATE DURÁVEL DO CANAL

Estabelecer uma fonte única de verdade para o bloqueio de canal.

O bloqueio deve sobreviver a:
- Restart.
- Retry do webhook.
- Eventos duplicados.
- Pausa/resume administrativo.
- Handoff release.
- Recuperação de geração.
- Recuperação de delivery.
- Replay de eventos antigos.

Verificar em especial:
- claim_generation
- executor de processamento
- conclusão de geração
- claim_next_delivery
- authorize_delivery_submission
- authorize_legacy_reply, quando aplicável
- operações de recuperação e maintenance

Uma mudança de lifecycle não pode deixar operações já autorizadas voltarem a ser enviáveis.

Preservar a ressalva existente da janela autorização→HTTP: não afirmar que uma submissão já iniciada pode ser recolhida.

Não criar uma condição de canal active com base apenas na ausência de bloqueios.

4. ESCOPO E IDENTIDADE

O webhook de account.update fornece WABA, mas não deve ser presumido como prova da identidade de qualquer Conversation.

Vincular WABA à configuração comercial de forma explícita e validada.

Como a V1 é single-business, evitar criar multitenancy prematuramente.

Separar corretamente:
- Scope da conta/WABA.
- Scope do número comercial.
- Conversation.
- Estado de pausa por Conversation.
- Estado de lifecycle do canal.

O bloqueio de canal e a pausa de conversa devem continuar independentes.

Não permitir que a reativação de uma conversa contorne um canal bloqueado.

5. ORDENAÇÃO E REPLAY

Eventos podem chegar duplicados e fora de ordem.

Definir política conservadora, determinística e persistida.

Requisitos:
- Mesmo event_id + mesma evidência: replay idempotente.
- Mesmo event_id + evidência conflitante: rejeição.
- Evento atrasado: não reativar canal.
- Reconexão sem validação adicional: não ativar.
- Relógio incorreto ou timestamp ambíguo: nunca abrir o canal por inferência.

Não ordenar lifecycle pelo ID textual do evento.

Se for necessário utilizar occurred_at, explicitar as limitações de relógio e demonstrar o comportamento nas regressões.

6. SQLITE E TRANSAÇÕES

Reutilizar o operational_events journal quando compatível.

Inspecionar record_webhook_events e validate_message_scope: o validador de escopo de Message do Ticket 07 não pode ser aplicado diretamente a ChannelAvailabilityChanged.

Adaptar somente o necessário para distinguir validação de Message e lifecycle.

Observação, efeito de bloqueio e eventual cancelamento de trabalho ainda não submetido devem ser atômicos.

Usar BEGIN IMMEDIATE e transações curtas.

Não fazer rede, LLM nem HTTP de saída dentro da transação.

ACK offline só depois do commit.

Erro de SQLite, timeout ou commit:
- Não produzir ACK de sucesso.
- Não perder observação parcialmente.
- Não deixar estado de canal parcialmente atualizado.
- Preservar replay seguro.

Evitar migrations destrutivas.
Validar migração a partir do head 0019 e preservação de dados históricos.

7. LIMITES DE ESCOPO

NÃO implementar neste ticket:
- Janela WhatsApp 24 h.
- Templates.
- Idempotency-Key de envio.
- Sender Telnyx.
- Rota pública Telnyx.
- Raw ASGI headers ou streaming.
- Readiness de produção.
- Onboarding e reconexão real.
- Resolução operacional de conflitos de status.
- Alteração de modelos LLM.
- Mudança da persona/grounding da Lívia.
- CRM ou SaaS multiempresa.
- Alteração da main ou Baileys.

Tickets 10–13 continuam não autorizados.

8. TESTES OBRIGATÓRIOS

Usar payloads sintéticos fiéis à documentação oficial e SQLite real.

Cobrir:
- Assinatura válida e inválida.
- WABA correta e incorreta.
- ACCOUNT_OFFBOARDED.
- PARTNER_REMOVED.
- ACCOUNT_RECONNECTED.
- Evento desconhecido.
- Duplicata idêntica.
- Mesmo ID com transição conflitante.
- Eventos fora de ordem.
- Reconnect após offboard.
- Offboard atrasado após reconnect.
- Restart em cada estado.
- Bloqueio com geração pendente.
- Bloqueio durante LLM.
- Bloqueio antes de autorização de envio.
- Bloqueio com delivery já adquirido.
- Bloqueio durante status callback.
- Pausa/resume não contorna lifecycle.
- Handoff release não contorna lifecycle.
- Falha de statement SQLite.
- Falha de commit.
- Lost ACK e replay.
- Concorrência entre lifecycle e geração.
- Concorrência entre lifecycle e envio.
- Restauração após migration.
- Ausência de PII e credenciais em logs.
- Compatibilidade integral dos Tickets 01–08.
- Preservação de Meta/Twilio e Baileys.

Não relaxar asserts legados para fazer a suíte passar.
Corrigir regressões na causa e criar testes.

9. VALIDAÇÃO INDEPENDENTE

Executar:
- pytest completo
- Ruff check
- Ruff format --check
- compileall
- pip check
- git diff --check
- auditoria de segredos

Executar revisões Standards e Spec independentes.

Corrigir todos os P1/P2 encontrados e repetir os testes pertinentes.

Não declarar conformidade apenas por testes unitários.
Identificar explicitamente limitações de evidência offline.

10. REGISTRO CENTRAL

https://github.com/zazacknazzo/rj-studio-ai/issues/11

Revalidar especialmente:
CX-01 — Retenção
CX-02/CX-03 — Echo e pausa humana
CX-05 — Cronologia
CX-06 — Envio previamente autorizado
CX-10 — Onboarding/Coexistence
CX-11 — Lifecycle ativo
CX-17 — Integração ainda incompleta
CX-19 — CI e validação
CX-21 — Preservação de main/Baileys
CX-24 — HTTP bruto e ACK
CX-29 — Eventos não suportados
CX-30 — Deadline 2 s
CX-32 — Resolução de conflitos

Registrar qualquer risco novo com ID CX-33+, responsável, gate e critério objetivo de fechamento.

Não encerrar riscos sem evidência e aprovação do orquestrador.

11. ENTREGA

Criar branch isolada a partir da SHA exata do Ticket 08.

Publicar por push normal SOMENTE essa branch.

Entregar:
A. Resumo do escopo
B. Branch e SHA final
C. Diff contra Ticket 08
D. Arquivos alterados
E. Matriz de lifecycle
F. Modelo de persistência e de bloqueio
G. Política de duplicatas/ordenação
H. Evidência de concorrência
I. Resultados completos de testes
J. Revisão independente Standards
K. Revisão independente Spec
L. Ressalvas e atualização issue #11
M. Confirmação de que nada externo foi ativado

Preservar main, Baileys, Meta/Twilio e inteligência V1.

NÃO iniciar Ticket 10.

Aguardar auditoria direta e autorização explícita.
