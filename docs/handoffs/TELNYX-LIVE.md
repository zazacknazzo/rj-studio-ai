# Telnyx live — continuação da fase 1

## Fonte, escopo e baseline

Missão humana de 27/11/2026: conversar com a Lívia pela Telnyx, preservando
OpenAI real, KB, histórico/contexto, grounding, handoff e controles de envio.
Fase 2 somente após múltiplos turnos reais. Participante inicial único, conta
existente preservada e nenhum merge na main.

Esta execução é a única escritora da nova branch `codex/telnyx-live-20261127`.
Worktree isolado; não alterou checkouts, configuração, imagens ou volumes WAHA.
Origin conferido: `https://github.com/zazacknazzo/rj-studio-ai.git`.

Refs obtidas por fetch antes da escolha:

| Branch | SHA conferida |
| --- | --- |
| telnyx-coexistence-13-readiness | `392637c95e8b4143054ae539e71f6f903559c742` |
| telnyx-g0-smoke-staging | `65abbe6ce74a850fd8558b3a0b385a5caf2a18b5` |
| livia-private-operations-20261126 | `00aca1067f0bcd21ba88d969d18b062eec98eae7` |
| waha-open-inbound — baseline escolhida | `966d684a5e689e0b0f96e64d65627d06e6bf5a03` |
| main | `af1c9eb862a4180ca6b9e537349e4f8abaa2bb29` |

G0 é ancestral da baseline (0 commits exclusivos de G0; 20 adicionais na baseline).
Assim as melhorias de pareamento, identidade, preservação do perfil e controles
WAHA já estão presentes; não foi necessário cherry-pick ou merge entre branches.

## Resultado da auditoria inicial

| Área | Implementado e coberto offline | Ainda não comprovado/implementado operacionalmente |
| --- | --- | --- |
| Assinatura e ingresso | Ed25519 sobre bytes brutos, timestamp/escopo, streaming limitado, persistência antes do ACK | Chave e callbacks Telnyx reais no deploy |
| Mensagens e operação | Inbound, echo humano, edit/revoke, deduplicação, pausa/revisão | Formatos reais e operação assistida |
| Lifecycle | Binding WABA/canal/organização/perfil; disconnect/offboard bloqueiam; reconnect exige verificação | Onboarding, elegibilidade, sincronização e ativação reais |
| Envio | UUID estável, request determinístico/HMAC, markers atômicos, gates de janela/consentimento/handoff, unknown sem retry | Transporte e composição Telnyx live seguros |
| Recibos | Correlação antecipada, monotonicidade e conflito | Recebimento/entrega no aparelho e múltiplos turnos |
| Recovery | Laboratório T13 e quarentena estrutural | AUD-01/AR-02 continuam abertos; autoridade/testemunha independentes não comprovadas |
| Inteligência | Pipeline canônico OpenAI, persona, KB, contexto, grounding e handoff presentes na baseline | Conversa Telnyx real e continuidade após troca de provedor |
| Troca de provedor | Seleção/filtros por provider no executor existente | Exclusão global WAHA/Telnyx antes de ligar o segundo runtime |

`Settings.whatsapp_provider` ainda admite apenas Twilio/Meta. `OfflineTelnyxASGI`
é laboratório e mantém generation=false/egress=false/quarantined=true.
O sender Telnyx exige exchange interceptado. Não montar essa composição em um
endpoint comercial nem remover quarentena para obter um teste verde.
A issue #11 foi relida no GitHub: o aceite T13 continua SOMENTE OFFLINE.

## Conta real — bloqueio externo observado

Login autenticado concluído pelo proprietário após MFA. Em Messaging Suite →
WhatsApp Messaging, Business Accounts e Hosted Embedded Signups retornaram:
“This feature is not permitted at this account level.”

As listas exibiam fallback vazio acompanhado do erro. Isso **não prova** ausência
de WABA/números: a consulta foi negada. Account Levels mostrava email verificado,
verificações iniciais e de caso de uso pendentes, além de outros requisitos
pendentes para níveis superiores.

O fluxo Connect with GitHub retornou à Telnyx sem uma tela adicional de concessão
observada. Passou por Verification in Progress e, após atualização da página,
**Pending Review**, com prazo informado **24–48 horas**. Não houve pagamento,
compra de número, alteração de credencial, criação de WABA/signup, conexão Meta,
configuração de webhook ou envio Telnyx. Não prometer que a avaliação aprovada
desbloqueará WhatsApp sem conferir novamente as permissões efetivas.

Não havia chave nem binding Telnyx disponíveis ao diagnóstico no novo checkout.
As configurações privadas operacionais inspecionadas tinham OpenAI configurado;
nenhum valor de segredo foi exibido. Não copiar dados de clientes para este repo.

## WAHA preservado

Inspeção somente leitura do ambiente existente confirmou sessão WORKING,
connected_secondary=true, OpenAI configurado e executores em execução.
O backend retornou 503 com egress=false e
`private_test_paused_or_exhausted`; cinco chamadas reservadas e quatro intenções.
Não se atribuiu recebimento/entrega a esses contadores, nem se renovaram prazo,
limites ou escopo. A audiência existente era all_direct; a missão Telnyx começa
com participante único, sem herdar automaticamente essa audiência.

## Novo diagnóstico executável

`src/rj_studio_ai/telnyx_preflight.py` é um comando backend separado. Não muda
main/factories/geração/persistência nem concede autorização de envio.

```sh
python -m rj_studio_ai.telnyx_preflight --env-file .env.telnyx
python -m rj_studio_ai.telnyx_preflight --env-file .env.telnyx --live
python -m rj_studio_ai.telnyx_preflight --env-file .env.telnyx --live --tech-provider
```

Use venv instalado e `PYTHONPATH=src` se a instalação editável não apontar a este
checkout. Segredos vêm somente do ambiente ou arquivo privado 0600 ignorado pelo
Git; nunca de argumentos de CLI. Sem --live não há HTTP. Com --live são GETs
fixos para business_accounts/phone_numbers e, opcionalmente, foreign_apps.
Sem retries, redirects ou proxies/netrc de ambiente; TLS permanece validado;
resposta limitada a 1MiB e timeouts connect/read de 5/10s.

Saída contém classificações fixas e contagens, não payloads, números, nomes,
tokens ou mensagens de erro remotas. Falta de permissão, rede ou metadados de
paginação jamais vira lista vazia saudável. A comparação é de WABA/número;
perfil fica not_verified porque a listagem oficial não documenta esse campo.
App link observado não comprova que seja o app desejado/aprovado para o produto.
`egress_authorized` é sempre false; exit 0 significa diagnóstico executado,
não conexão pronta nem autorização de envio.

## Validação desta execução

- Antes de editar: 30 testes sender integration/private test passaram em 39,52s.
- Novo diagnóstico: 25 testes passaram em 0,55s sob o runner sem credenciais/rede.
- Ruff check e format (408 arquivos), pip check e diff check passaram antes dos
  documentos finais. O diagnóstico real local classificou credential_missing
  e não fez HTTP à API Telnyx. A inspeção da conta foi pelo portal autenticado.
- Integral própria: **2406 PASS, 0 failures/errors/skips, 328,87s** pelo runner
  saneado. Excluído o arquivo `test_waha_cloudflare_integration.py`, que depende
  do workerd/loopback e roda no job separado do CI. Não são 25+30+2406 testes:
  os lotes focais se sobrepõem à integral.
- Checks finais: Ruff check/format (409 arquivos), compileall, pip check e
  diff check PASS. Gitleaks 8.30.1 Darwin arm64 teve checksum oficial verificado;
  árvore com três falsos positivos históricos triados, nenhum novo; range
  baseline..`6408fed` com zero findings. A primeira triagem recebeu caminhos
  absolutos incompatíveis com o validador; scan repetido na raiz exportada com
  caminhos relativos e a triagem existente passou, sem alterar allowlist.
- Código publicado em `6408fed57aa84c7686d241ce5ae996d1653491c5`, SHA no
  origin conferida; main permanece na SHA acima. [PR #16](https://github.com/zazacknazzo/rj-studio-ai/pull/16)
  em rascunho, base `codex/waha-open-inbound`, sem merge.
- [CI do código](https://github.com/zazacknazzo/rj-studio-ai/actions/runs/46074046586)
  disparada para a SHA exata acima: job cloudflare-fixtures success observado;
  job offline ainda em andamento no momento deste registro. O resultado da
  própria SHA documental posterior deve ser consultado no PR; não inferir CI
  completa deste registro parcial.
- A primeira tentativa de lançar a integral falhou no argparse antes de pytest:
  faltava `--` antes das opções pytest. Corrigida a invocação; log preservado.

## Próxima ação exata

1. Fetch/status/branch e SHA remota; conferir este handoff e reproduzir o lote
   `tests/test_telnyx_preflight.py` pelo runner `scripts/check_telnyx_offline.py`.
2. Após decisão da Telnyx, abrir Account Levels e as páginas WhatsApp novamente.
   Se ainda negadas, resolver habilitação externa; contratação exige proprietário.
3. Provisionar credencial existente no backend por canal privado, conferir chave
   pública/organização e executar diagnóstico --live. Não criar nova chave pelo
   browser sem a aprovação aplicável a nova credencial/acesso.
4. Verificar que a conta do número usa WhatsApp Business App e elegibilidade Meta.
   Usar Add Account → Enable WhatsApp Business App coexistence. **Add Number é
   fluxo padrão**, não Coexistence. Não apagar conta nem desregistrar número.
   Onboarding desvincula companions; coordenar explicitamente o efeito no WAHA
   antes de confirmar a conexão e obter a confirmação do proprietário no telefone.
5. Concluir composição Telnyx operacional com segurança de restauração,
   exclusão entre provedores, allowlist e controles. Validação local não remove
   os gates externos. Revalidar janela/consentimento a cada envio; fora da janela,
   template aprovado quando aplicável, sem fallback inventado.
6. Só declarar fase 1 concluída após inbound assinado, OpenAI real, resposta
   persistida, acceptance, recibo de entrega e múltiplos turnos reais do participante,
   com negativos de replay/self/echo/pausa/unknown e restart. Depois fase 2.

## Fontes oficiais consultadas em 27/11/2026

- [Telnyx quickstart](https://developers.telnyx.com/docs/messaging/whatsapp/quickstart).
- [Telnyx Coexistence](https://developers.telnyx.com/docs/messaging/whatsapp/coexistence):
  caminho correto, sincronização ativa e companions.
- [Telnyx Tech Provider](https://developers.telnyx.com/docs/messaging/whatsapp/embedded-signup/tech-provider):
  app aprovado, vínculo/solution ID e hosted signup com signup_type=coexistence.
- [Listar WABAs](https://developers.telnyx.com/api-reference/whatsapp-business-accounts/list-whatsapp-business-accounts)
  e [números](https://developers.telnyx.com/api-reference/whatsapp-phone-numbers/list-whatsapp-phone-numbers).
- [Account Upgrade](https://developers.telnyx.com/docs/account-setup/account-upgrade).
- [Meta Coexistence](https://developers.facebook.com/documentation/business-messaging/whatsapp/embedded-signup/onboarding-business-app-users):
  requisitos, efeitos nos companions e janela Cloud API separada do app.

Há uma página antiga de suporte Telnyx que orienta apagar conta/não aceita BYON;
ela conflita com o quickstart/guia Coexistence atuais. Não seguir essa orientação
destrutiva para o número existente. A elegibilidade real permanece gate externo.
