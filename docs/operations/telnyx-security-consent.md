# Segurança operacional e consentimento — gates T13

22/11/2026. Projeto single-business RJ Studio. Este documento especifica o fluxo futuro;
não cria credenciais reais, rota pública, operador provisionado ou autorização de piloto.
Os testes usam fixtures sintéticas. O serviço atual NÃO tem workflow completo de captura
de consentimento, IAM empresarial ou UI móvel: CX07/08/25/36 continuam bloqueadores.

## Acesso e operações críticas

| Papel proposto | Pode | Não pode | Aprovação/revogação e evidência |
| --- | --- | --- | --- |
| Aplicação | Ingress validado; ler authority e reservar marker sob fence futuro | Grant consent, ativar/rebind, liberar recovery, mudar roles | Identidade de serviço com binding exato; revogação cerca revision |
| Operador de atendimento | Ler Conversation autorizada, pausar, atender, pedir resume futuro | Mudar conta/profile/chave, resolver unknown sem prova | Gestor designa e allowlist limita; acesso pessoal, nunca compartilhado |
| Recoverer | Inventariar/restaurar em quarentena e reconciliar com prova | Aprovar seu próprio release ou modificar prova externa | Acesso temporário por incidente; trilha de cada decisão |
| Approver | Conferir evidência corrente e aprovar ensaio/release futuro | Ser o mesmo recoverer ou reclassificar unknown para retry | Pessoa distinta, revisãoCAS e prazo; revogação imediata |
| Verificador da conta/política | Obter binding/sync/consent/template de fonte confiável | Ser substituído por valor vindo do inbound/LLM | Referências saneadas e validade/escopo verificáveis |
| Segurança/SRE | Revogar, rotacionar, suspender, gerir ingress/segredos | Executar piloto ou conceder exceção de produto | Gestor aprova acesso; audit externo e motivo mínimo |
| Product owner/orquestrador | Autorizar gate delimitado após evidência | Aprovar por silêncio/por um health local | Decisão explícita com limites/critério de parada |

Admin atualT05 usa bearer estático por configuração, allowlist/permissões e operação
idempotente por operation_id+expected_revision. IDs opacos/owner/episode não autenticam.
O laboratório recovery testa roles separados, segredo aleatório sintético, hash no
fixture, CAS, audit append-only e revogação. Não equivale a um IdP/PKI implantado.

| Controle | Preparação/negativo offline | Evidência ainda necessária no deploy |
| --- | --- | --- |
| Autenticação forte | Bearer inválido/revogado/papel errado negados; sem valor em erro | TLS, SSO/MFA quando aplicável, inventário de operadores e expiração |
| Grant/revoke/rotation/loss | Simular remoção/negação; recovery abandona permit em erro | Aprovação nominal, chave nova→binding comprovado, revogar antiga, drill de perda |
| Credential→org/profile/number/WABA | RequestMAC/escopo e testes de mismatch | Responsável comprova associação na conta; não inferir de env/body |
| Configuração | _env_file=None em testes; settings redigem secrets; sem Telnyx no selector | Vault/secret manager, ACL, boot fail-closed, revisão de mudanças, versionamento seguro |
| Logs/APM/audit | Nenhum body/Authorization/telefone/chave em métricas/erros; refs mínimas | Proxy/APM/backups com redaction real e teste de sentinel sintético |
| Replay | Ed25519 raw/timestamp, duplicate headers/receipts, operationCAS e challenge recovery | Clock/NTP/proxy correto; replay capturado autorizado no ambiente |
| TLS/proxy/headers | Testes raw ASGI antes de dict, stream/Content-Length/duplicatas | Certificado válido; trusted proxies explícitos; Host/forwarded headers e access logs testados |
| Abuso/availability | Body/time/capacidade limitados; contention→503 observável | Rate limit por origem autenticada/rota, proteçãoDDoS, alertas e capacidade de disco real |
| Dependências indisponíveis | SQLite/authority/witness/clock/proofs negam permissão | Outage drill de IdP/vault/NTP/proxy/DB, sem bypass por flag |
| Revogação urgente | Epoch/revision e release revogado no fixture; store permanece fechado | Revogar no trust domain antes de reconfigurar cliente; provar propagação/sem cache |

Nunca emitir token comercial no repo/issue; nunca imprimir env, cookies, QR ou DB real.
Se segredo vazar: suspender saída, revogar na origem, preservar audit minimizado, trocar
com binding confirmado e abrir incidente; apagar histórico Git não revoga segredo.
Sem rotação real neste ticket. Pausa é preventiva, não recall de HTTP já iniciado.

## Workflow de consentimento proposto e demonstrável

1. Antes do piloto, privacidade/produto definem finalidade de service_response,
   identidade do negócio, canal/número, escopo, avisos e base legal aplicável.
   Consentimento WhatsApp não substitui avaliação LGPD e opt-in não é janela24h.
2. Operador autenticado captura escolha positiva verificável. Registrar referência ao
   comprovante em repositório restrito, versão do aviso, finalidade, canal, Customer
   e período; o journal operacional não recebe print/body privado do comprovante.
   Não presumir consent a partir de conversa ativa, histórico importado, echo ou contato.
3. Verificador independente confirma proveniência e escopo. Um futuro command de grant
   deve usar operation_id, expected_revision, ator, instante confiável e auditoria
   append-only na mesma transação da alteração. Sem essa implementação, apenas fixture.
4. Grant válido exige granted_at≤now<expires_at, sem revoked_at e referência não vazia.
   Prazo proposto de revalidação:90dias para service_response, ou menor conforme escolha,
   escopo e avaliação jurídica; NÃO é regra de validade universal de consentimento.
5. Opt-out por qualquer canal suspende imediatamente contato/automação: operador pausa,
   revoga autorização de consent na origem confiável e registra motivo categórico,
   referência mínima/instante/ator/revision. O pedido não precisa justificar-se.
   Não depender de echo do Business App: não aciona automaticamente processamento opt-out.
6. O futuro command de revoke e authorize_delivery_submission devem serializar em
   BEGIN IMMEDIATE. Se revoke commita primeiro, autorização nega; se marker commita
   primeiro, envio pode estar em voo. Preservar marker/unknown, informar operador,
   impedir nova autorização e não prometer cancelamento externo.
7. Alteração de finalidade/escopo ou consentimento expirado exige nova prova afirmativa;
   revogação histórica não é apagada por upsert. Inbound posterior não reativa consent
   automaticamente. Captura/audit de consent ainda não são workflow de produção.
8. Restauração perde grants/revokes locais; authority atual independente precisa
   revalidar e negar no caso desconhecido. SQLite antigo não reinicia validade.

## Janela e templates

A política Meta vigente consultada22/11 informa opt-in e respeito a opt-out; free-form
só dentro de24h após mensagem do Customer. T10 exige proveniência source confiável,
primeiro recibo durável, clock high-water e comparação estrita <24h. Timestamp de
assinatura/receipt/echo não substitui source. Business App e Cloud API não compartilham
estado da janela. Exatamente24h é fechado, e consent atual não prolonga essa janela.

Template somente com ID/nome/idioma/conteúdo/categoria/finalidade e status de aprovação
vigentes obtidos de fonte autenticada, observados após a última mudança e com prazo
definido. Revalidar pausa/rejeição/revogação do template antes de possível envio.
Um nome conhecido, fixture ou referência opaca não prova aprovação real.
SenderV1 continua free-form, sem fallback/conversão para template; não enviar fora da
janela. Template operacional exige spec/implementação e autorização próprias.

Fontes oficiais:
[Meta Business Messaging Policy](https://whatsappbusiness.com/policy/),
[Telnyx Coexistence](https://developers.telnyx.com/docs/messaging/whatsapp/coexistence),
[Coexistence webhooks](https://developers.telnyx.com/docs/messaging/whatsapp/coexistence/webhooks).

