# WAHA — respostas a qualquer contato direto

Pedido aprovado pelo usuário em 27/11/2026. A conta da IA deve responder a qualquer
contato que envie mensagem individual de texto. A seleção de destinatários ocorre
pela mensagem recebida com assinatura válida, identidade da conta conectada e
proveniência persistida da resposta. A mudança amplia o teste com participante
fixo descrito no ADR 0022.

Use WAHA_AUDIENCE=all_direct explicitamente. O valor padrão allowlist conserva o
comportamento anterior. A audiência integra o escopo imutável do journal e o ledger.
Uma configuração com audiência diferente do ledger deve falhar ao inicializar.
Dados, inventário, budgets e revogações anteriores devem ser preservados durante
a preparação do novo escopo. O ledger local conserva o risco de rollback conjunto
documentado no ADR 0023. AUD-01 e AR-02 continuam abertos.

Cada conversa mantém contexto próprio. Grupos, broadcast, status, mensagens da
própria conta, mídia e eventos fora da sessão são ignorados. HMAC, opt-out,
handoff, pausa, prazo, limites globais de consumo, uma tentativa de envio e bloqueio
após resultado desconhecido continuam necessários. Toda resposta exige um inbound
persistido do destinatário. Mensagens proativas continuam fora do fluxo.

A configuração não abre uma janela nem concede aprovação para renovar prazos
expirados. A ativação exige sessão funcional, identidade verificada e prazo válido.
A conclusão operacional requer múltiplos turnos reais e confirmação de entrega.
