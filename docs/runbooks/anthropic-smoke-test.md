# Smoke test Anthropic manual

Este teste é opt-in. Ele pode gerar custo e nunca faz parte da suíte automática.

1. Copie `.env.example` para `.env`; mantenha o arquivo fora do Git.
2. Defina `LLM_PROVIDER=anthropic`, `ANTHROPIC_API_KEY`, os dois preços atuais por
   milhão de tokens e `TWILIO_VALIDATE_SIGNATURE=false` para a chamada local.
3. Execute `rj-studio-maintenance migrate` e inicie o servidor.
4. Envie uma única requisição sintética para `/webhooks/twilio` com um `MessageSid`
   novo. Não use telefone, nome ou conteúdo real de Customer.
5. Confirme HTTP 200, uma AI Reply curta, uma linha em `generation_metrics` com
   provider/model/tokens/latência/custo, e nenhuma chave, endereço ou corpo na métrica.
6. Registre abaixo data/hora, commit, modelo, payload sintético, resultado e contagens;
   não registre a chave, telefone, IDs do provider ou resposta completa.

## Execution record

Ainda não executado nesta branch.
