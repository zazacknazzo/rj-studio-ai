# Telnyx live — missão de 27/11/2026

Autorização: missão humana TELNYX LIVE + WHATSAPP CONNECTION EXPERIENCE.
Fase 1 precede a interface da fase 2. Baseline escolhida após fetch:
`codex/waha-open-inbound`, `966d684`, descendente do G0 `65abbe6` e das melhorias
WAHA `00aca10`. Branch exclusiva desta execução: `codex/telnyx-live-20261127`.
Não modificar a operação WAHA existente nem main.

## Primeiro recorte: diagnóstico real sem alterações remotas

- Comando explícito `python -m rj_studio_ai.telnyx_preflight --live` consulta
  somente GETs documentados da API Telnyx. Sem `--live`, verifica configuração
  local e não abre conexão. Credencial por ambiente/arquivo privado do backend.
- Exibir classificações fixas, contagens e comparação com a identidade configurada;
  nunca chaves, números, nomes, URLs de onboarding, respostas ou erros remotos.
- Distinguir falta de credencial, autenticação, permissão, rede, resposta inválida,
  paginação incompleta, WABA ausente e sincronização pendente. Erros nunca
  equivalem a lista vazia ou conexão saudável.
- Conferir WABA, número e coexistência ativa. O perfil fica explicitamente
  não verificado: a listagem de números não documenta esse vínculo.
  Opcionalmente consultar
  o vínculo Tech Provider com `--tech-provider`; não presumir sua existência.
- HTTPS fixo em api.telnyx.com, sem redirecionamentos/retries/proxy ambiente,
  limites de resposta e timeout. Não criar WABA/signup, alterar webhooks ou enviar.
- O diagnóstico nunca concede autorização de envio. Preservar a quarentena T12,
  a inteligência canônica e os gates AUD-01/AR-02 existentes.

## Critérios posteriores, ainda pendentes

Habilitação da conta e elegibilidade Meta; Coexistence sem apagar conta existente;
credenciais/configuração backend; composição operacional segura com exclusão
entre provedores; participante único; janela de 24h/templates; OpenAI/KB/contexto/
grounding/handoff; webhooks/entrega reais; múltiplos turnos e negativos de replay,
eco, pausa, resultado desconhecido e reinício. Somente então iniciar fase 2.

O portal autenticado negou WABA e Hosted Embedded Signups pelo nível da conta.
Após o fluxo GitHub disponível, a avaliação ficou Pending Review (24–48h).
Esse estado não comprova aprovação futura nem qual nível desbloqueará WhatsApp.
