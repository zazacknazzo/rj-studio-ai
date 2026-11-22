# Sprint G0 — smoke da Lívia em staging sintético

Status: approved

Escopo autorizado pelo usuário em 22/11/2026; implementação restrita a
testes sintéticos e documentação. Não é autorização de conexão real.

Baseline exata: `392637c95e8b4143054ae539e71f6f903559c742`, branch T13.
Branch exclusiva desta execução: `codex/telnyx-g0-smoke-staging`.

## Contrato e aceite

Compor os componentes existentes: ASGI offline e autenticação Ed25519, adapter,
SQLite/migrations, ProcessingRunner/MessageResponder, contexto e grounding,
autorização/request determinístico, TelnyxWhatsAppSender com exchange fake,
acceptance/status autenticado sintético e histórico. Não alterar arquitetura de
mensageria, lógica de produção, seleção de provider, Baileys ou modelo.

Fixtures de decisões LLM serão marcadas como fixtures; respostas finais passam
pela política/renderização real. Chaves criptográficas efêmeras e identidades
sintéticas apenas em memória/banco temporário; não publicar material de chave.
O ASGI permanece quarantinado. Somente um worker de teste privado usa o store
genérico legado com signer e exchange fake fixos; isso não é release operacional
nem solução de AUD-01. Não adicionar opção de bypass ou transporte real.

Cobrir saudação/informações, progressiva, preço, interesse em agendamento sem
reservar vaga, Human Handoff, consentimento revogado, duplicata, pausa durante
geração, timeout/ambiguidade, desconexão/reconexão e restore obsoleto.
Demonstrar negativos: auth inválida, sem consentimento/canal ativo, pausa,
janela vencida, request adulterado, quarentena e unknown sem retry.

Demo reproduzível deve criar ambiente filho sem credenciais/.env e com guard
de rede Python herdado. CI repete sob namespace Linux sem rede. Nenhum acesso
comercial ou chamada a LLM/Telnyx. Relatório deve separar aplicação executada,
fixtures e fatos operacionais não comprovados; sem alegar SLA/custo reais.

## Gates documentais

Checklist verificável com VERIFICADO / NÃO VERIFICADO / BLOQUEADO, evidência,
dono e teste de aceite. Duas decisões separadas: ingresso real sem automação/
outbound e uma resposta real. Para saída exigir AUD-01/AR-02 operacionalmente
mitigados, identidade e consentimento atuais, canal ativo, aprovação humana,
kill switch e negativos de bypass. Qualquer falta mantém NO-GO.

Não executar o procedimento real. Solicitar auditoria antes de conexão real.
Issue #11 continua aberta, sem encerrar riscos. Sem merge/force push/main.
Commit/push normal e handoff em cada checkpoint; nunca antecipar o próprio SHA.
