# G0 — readiness Telnyx e decisões separadas

Data: 22/11/2026, America/Sao_Paulo. Escopo: inspeção de código, testes sintéticos
e documentação pública; **nenhum portal comercial, conta, credencial ou número real
foi acessado**. AUD-01/AR-02 continuam abertos. Nenhum checkbox da issue #11 foi fechado.

VERIFICADO significa evidência efetivamente examinada para o escopo indicado;
NÃO VERIFICADO significa que o fato externo ainda carece de prova;
BLOQUEADO significa requisito obrigatório sem implementação/evidência/liberação
suficiente para o gate. Fixture nunca verifica conta, elegibilidade ou consentimento.

## Checklist verificável

Evidência real futura fica em repositório restrito: somente referência opaca,
data, escopo, validade, responsável e resultado no relatório público. Não publicar
chaves (nem public key da conta), tokens, assinatura, headers, telefones, nomes,
documentos, capturas com PII ou corpos comerciais. Os donos abaixo são papéis
propostos, ainda sem designação nominal. Não executar as verificações comerciais
até autorização própria e auditoria.

| ID / pré-requisito | Estado atual | Evidência examinada / falta | Como aceitar, por quem / gate |
| --- | --- | --- | --- |
| R01 Conta Telnyx verificada | NÃO VERIFICADO | Nenhum acesso à conta | Responsável Telnyx registra comprovação atual de verificação e permissões no registro restrito; ingresso e saída |
| R02 Administração Meta | NÃO VERIFICADO | Sem prova de acesso ao portfolio dono do número | Administrador comprova papel e propriedade no portfolio correto, sem conceder privilégios à aplicação; onboarding/ingresso |
| R03 WABA correta | NÃO VERIFICADO | `synthetic-waba` é fixture | Administrador confirma cadeia organização→portfolio→WABA→número e divergências; ingresso e saída |
| R04 Número elegível para Coexistence | NÃO VERIFICADO | Nenhuma prova de elegibilidade individual, inclusive +55 | Administrador + Telnyx validam número secundário e caminho Coexistence, operadora, app/versão, região e restrições atuais; preservar conta existente; onboarding |
| R05 Estado sync_pending/syncing/active | NÃO VERIFICADO | Lab usa inserção sintética active; reconnect real sintético resulta verification_required local | Operação registra observação atual do número (`is_on_biz_app`, `coexistence_state`, prazo/progresso quando aplicável); só active satisfaz gate de saída, sem equivaler a consentimento |
| R06 Messaging Profile e routing | NÃO VERIFICADO | UUID usado nos testes é fixture | Operação comprova profile ligado ao número/WABA/org corretos; confirma endpoint/failover e ausência de dupla admissão WABA/profile; ingresso e saída |
| R07 Public key de webhook | NÃO VERIFICADO | Chave Ed25519 gerada efêmera, só em memória | Segurança confirma proveniência da chave da conta e rotação, runtime libsodium e relógio/NTP; prova de assinatura válida e negativas no deploy; ingresso |
| R08 TLS/proxy/streaming/logs | BLOQUEADO | ASGI local executado; nenhum deploy/proxy testado | SRE demonstra HTTPS com cadeia válida, preservação de bytes/headers, duplicatas, limites streaming, timeouts, ACL/admin separado, ausência de body/Authorization em logs/APM; ingresso |
| R09 Consentimento e identidade dos participantes | NÃO VERIFICADO | Grant/revoke SQL exclusivamente sintéticos | Operador registra identidade/canal/finalidade/escopo/proveniência/validade e opt-out atuais em fonte confiável; antes de armazenar dados reais definir autorização/base aplicável; saída exige opt-in atual |
| R10 Operador humano designado | NÃO VERIFICADO | Nenhuma pessoa/escala provisionada | Produto nomeia titular e suplente; operador demonstra seleção segura da Conversation, pausa autenticada antes de falar, estado atual, fila/alerts para unsupported/unknown e parada; ingresso assistido e saída |
| R11 Retenção e erasure | BLOQUEADO | Matriz T13 é proposta; não é política operacional aprovada/implantada | Responsável privacidade/produto aprova finalidades/prazos/holds; engenharia demonstra aplicação, tombstones/fences e replay após purge sem perda de evidência; antes de dados reais |
| R12 Backups e restore | BLOQUEADO | SQLite backup API exercitada só com dados sintéticos | SRE prova snapshots consistentes, criptografia/ACL, inventário WAL/logs/cópias, independência das raízes, retenção e restauração quarantinada; RPO/RTO ainda propostas |
| R13 Autoridade externa de recovery | BLOQUEADO | T13 é laboratório; G0 reproduz permissividade do store legado após snapshot antigo | Engenharia/SRE/Segurança demonstram authority/witness independentes, autenticados, monotônicos, CAS, ledger write-ahead completo antes de todo HTTP possível, IAM e falhas/indisponibilidade/rollback; AUD-01/AR-02, obrigatório para saída |
| R14 Egress protegido em restore/rollback | BLOQUEADO | Store da composição offline nega; proteção operacional de host/credencial/worker não existe nesta entrega | SRE demonstra deny externo ao SQLite, boot/restore/deploy/reboot/rollback fechados, revogação e release atual auditada; não reutilizar fila/key nem gerar outra para unknown |
| R15 Composição operacional receive-only | BLOQUEADO | Factory offline real executada sem background workers; runtime principal não monta rota Telnyx | Engenharia prepara release com ingresso separado, sem generator/sender/SDK/credenciais de saída e com deny de egress no destino; auditor verifica todos os caminhos/rotas/CLI antes de conexão |
| R16 Composição operacional de saída | BLOQUEADO | Somente sender com callable interceptado; nenhum HTTP comercial implementado/autorizado | Novo escopo aprovado deve integrar transporte real à autoridade/ledger e gates correntes; nenhum flag de bypass ou troca de fixture por cliente real |
| R17 Aprovação humana e kill switch | BLOQUEADO | Pausa sintética durante geração funciona; gate humano de saída real e kill switch de infraestrutura não implantados | Auditoria + autorização humana delimitada; operador/SRE demonstram revogar novos envios, observar in-flight/unknown e impedir restart/bypass; saída |
| R18 Baseline e harness sintético | VERIFICADO (offline) | Baseline origin T13 exata; G0 auth→SQLite→processing→grounding→autorização→request determinístico→fake→status→histórico | Testes versionados `test_g0_staging_smoke.py`; não verifica nenhum R01–R17 real |
| R19 Negativos de aplicação | VERIFICADO (offline) | Assinatura, janela, consentimento, request integrity, pausa, reconnect, quarantine, duplicata, timeout/unknown/restore exercitados; guard exige interceptação efetiva | Testes G0 + suites T10–T13; negativos de bypass no destino seguem R13–R17 bloqueados |
| R20 Opt-out operacional | BLOQUEADO | Texto “revogo meu consentimento” sozinho não altera `telnyx_consent`; G0 não implementa captura/revoke | Definir fluxo autenticado/atômico e encaminhamento humano imediato; testar revogação antes/depois do marker e persistência externa atual; antes de saída real |

## Contratos externos consultados em 22/11/2026

A documentação pública de [Coexistence Telnyx](https://developers.telnyx.com/docs/messaging/whatsapp/coexistence)
descreve manter o número no Business App e escolher o fluxo Coexistence; o fluxo
standard é diferente. Seu lifecycle bloqueia saída em sync_pending/syncing até
active. Isso orienta R04/R05, **não confirma o número do salão**. Não desregistrar
ou desconectar o número principal para experimentar.

[Quickstart Telnyx](https://developers.telnyx.com/docs/messaging/whatsapp/quickstart)
identifica conta verificada, Meta/WABA e número verificado como pré-requisitos.
Ler material público não comprova propriedade ou acesso administrativo.

[Webhooks Coexistence](https://developers.telnyx.com/docs/messaging/whatsapp/coexistence/webhooks)
documentam echo pelo Messaging Profile e possível duplicação via WABA messages.
Echo é best-effort; eventos internos de sync não chegam ao webhook do cliente.
Ausência de eventos não comprova canal ativo, sincronização ou consentimento.

[Messaging webhooks](https://developers.telnyx.com/docs/messaging/messages/receiving-webhooks)
descrevem assinatura Ed25519, timestamp e HTTPS. Há divergência de ACK: esse guia
diz 2s/2xx, enquanto o [Help WhatsApp](https://support.telnyx.com/en/articles/13986487-how-to-configure-whatsapp-webhooks)
diz 5s/200. Preservar o gate mais estrito de 2s e confirmar o caminho real/204
com o provedor antes do ingresso. ASGI usa 1,35s trabalho/1,5s total; fsync/proxy
e rede de destino ainda não foram medidos. Não copiar exemplo que reserializa JSON
antes de verificar assinatura nem ACK antes da persistência.

O [contrato send WhatsApp](https://developers.telnyx.com/api-reference/whatsapp-messaging/send-a-whatsapp-message)
separa submissão de progressão de entrega assíncrona. A aplicação exige free-form
em janela estrita menor que 24 h com consentimento atual; template não é fallback
implementado. Políticas/preços/janela devem ser revalidados no gate futuro, sem
alegar revisão jurídica ou custo real neste G0.

## Parecer 1 — ingresso real, sem automação e sem outbound

**NO-GO PARA CONEXÃO AGORA.** Viabilidade técnica demonstrada somente em processo
local: a factory ASGI persiste inbound autenticado e ACK sem invocar LLM/worker/
sender; readiness mantém generation/egress/operational_channel falsos. Isso não
autoriza publicar o endpoint ou configurar webhook na conta.

Para converter este parecer em GO de ingresso, exigir auditoria e autorização
próprias, R01–R04/R06–R12 aplicáveis comprovados, R14/R15 com egress negado fora
do SQLite, tratamento operacional de unsupported/retries (CX-29), ACK/proxy e
minimização demonstrados no destino. R05 active **não é inferido nem exigido como
permissão para receber observações autenticadas**; nunca habilitar automação por
readiness do canal. AUD-01/AR-02 podem permanecer abertos apenas para esse escopo
receive-only se a impossibilidade de saída sobreviver a restore/reboot/rollback
e for aceita explicitamente na auditoria. Isso não concede autorização de saída.

## Parecer 2 — uma única resposta real a participante autorizado

**NO-GO PARA ENVIO.** R13/R14/R16/R17/R20 bloqueados são suficientes para negar,
independentemente do resultado do parecer de ingresso. Identidade/consentimento
atuais, binding/active, operador e aprovação humana também não estão comprovados.
Um limite de uma mensagem não reduz os requisitos nem resolve AUD-01.

Saída exige proteção AUD-01/AR-02 operacionalmente demonstrada em TODOS os caminhos
de submissão, authority/witness/ledger atuais e independentes do snapshot,
identidade+consentimento+janela atuais, canal active validado, request exato
aprovado, kill switch externo testado e negativos de bypass no deploy. Incluir
store legado, CLI/manual recovery, factory principal, restart, restore, rollback,
authority indisponível, provas vencidas, outro destinatário e unknown sem retry.
Nenhum componente do harness é permissão para substituir fake por HTTP real.

Os dois pareceres avaliam gates distintos; foram produzidos pelo implementador,
**não são duas auditorias de autores independentes**. A auditoria externa solicitada
ao final do G0 permanece pendente; nenhum gate foi excepcionalizado.

Referências: [issue #11](https://github.com/zazacknazzo/rj-studio-ai/issues/11),
[gates T13](telnyx-gates.md), [recovery](telnyx-recovery.md),
[segurança/consentimento](telnyx-security-consent.md),
[retenção/backups](telnyx-retention-backups.md), [procedimento futuro](telnyx-g0-first-real-test.md).
