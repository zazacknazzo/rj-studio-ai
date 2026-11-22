# B3 — validação e estado operacional

Data:22/11/2026. Baseline B2 `7cda2fffa623fa93b630827d7d650f4234ffd320`.
Branch `codex/b3-livia-cloudflare-egress`. **AUD-01/AR-02 ABERTOS; envio NO-GO.**

## Arquitetura preservada

WAHA permanece um provider do núcleo canônico: ProcessingRunner, MessageResponder,
OpenAI real, Knowledge, grounding, persona, contexto/memória, handoff e outbox.
A factory explícita acrescenta a autoridade ao store estrito e ao executor existente;
não usa o store permissivo nem cria outra inteligência. Não antecipa infraestrutura
multi-tenant da V7. A tentativa temporária B4 foi cancelada pelo usuário antes de
qualquer implementação, deployment ou ativação; não é alternativa autorizada.

## Evidência executada

| Verificação | Resultado observado |
| --- | --- |
| workerd/DO SQLite real, protocolo adversarial |15 PASS, zero skips, source e852746 |
| Python completo, IP sockets bloqueados, fixtures WAHA/OpenAI declarados |2372 PASS, zero skips,160.59s, e852746 |
| Novo ajuste da CLI Wrangler, foco próprio |5 PASS,1.52s; source final inclui1 teste adicional |
| Ruff check/format, diff check, pip check, compileall |PASS |
| npm audit, dependências completas |0 vulnerabilidades |
| Canary DO na Cloudflare real |inscrição/advance persistidos; revisão1 relida em outra chamada; CAS antigo negado |
| Autoridade na Cloudflare real |assinatura/desafio verificados; comando sem autenticação403; mesma conta negada; revisão0, pausada/killed,0 intenções |
| Runtime em uso |B2 preservado; WAHA WORKING/identidade correta; schema23;1 pending,0 tentativas/markers; nenhum runtime.json B3 |

Os testes Python/workerd não são conversas reais. A transação Cloudflare não é
submissão WAHA nem evidência de administração independente. Nenhuma inferência
OpenAI paga foi repetida no B3. B2 já comprovou1 ingresso e1 inferência reais com
Knowledge precos-progressiva; não comprovou entrega ou memória multirrodada real.
CI do snapshot final será observado após push; consultar a execução do SHA remoto,
sem atribuir CI de B2 ou do source anterior a esta versão.

## Auditoria e correções

Standards encontrou4 problemas no primeiro candidato: expiração perdida após
consume, recuperação witness-ahead incompleta, lease curto e repetição de deploy
antes de detectar recibo prévio. Todos corrigidos e rechecados pelo revisor em61e774e.
Spec confirmou correções de expiração e seleção exata do grant. Ambas as perspectivas
então identificaram associação indevida de uma mensagem antiga/manual idêntica.

A correção e852746 exige ID retornado causalmente pela resposta HTTP desta tentativa,
já ancorado accepted na autoridade, antes de qualquer reconciliação local. GET
repete identidade/texto/ACK/timestamp e IDhash. Operator reconcile não promove
UNKNOWN. Timeout sem receipt conserva UNKNOWN, inclusive se houver mensagem manual
idêntica na mesma janela. Positivo simula crash local após acceptance externa;
negativos demonstram recusa de mensagem antiga/ID sem vínculo/ACK e conteúdo inválidos.

Spec rechecando e852746 confirmou resolução e nenhum novo P1/P2 no delta. A execução
final do revisor Standards foi interrompida pelo limite da ferramenta antes de emitir
seu novo laudo; não contar isso como aprovação. O root verificou a alteração e seus
testes. Revalidação independente final de Standards e aceite operacional seguem
pendentes, juntamente com a infraestrutura independente.

A migração0024 foi exercitada em bancos de fixture; o banco real não foi alterado.
Prova imutável permite somente acceptance WAHA comprovada, sem reabrir pending/retry;
triggers independentes de identidade e guards de outros providers permanecem ativos.

## Deployment real e erro corrigido

O primeiro deploy da autoridade concluiu remotamente, mas WRANGLER_LOG=info suprimiu
o output que continha a URL. Recibo exit0/source digest foi preservado. Antes de
qualquer nova mutação, API autenticada confirmou deployment existente, vars/source,
workers.dev e chave de assinatura. Endpoint foi recuperado dos metadados reais;
a autoridade não foi redeployada. Ajuste usa log e desliga debug logs em disco;
consulta deployments JSON real confirmou1 deployment. Canary foi implantado uma vez.
Logs recentes do Wrangler foram checados contra os segredos desta missão:0 matches.
Recibos/keys/IDs/URLs privados continuam fora do Git e dos relatórios públicos.

## Dependência e próximo passo

O requisito original exige raiz administrativa não revertida. Uma conta Cloudflare,
controlada pelo mesmo domínio administrativo, não demonstra esse requisito;
consistência/transações DO não impedem PITR do próprio objeto. A definição está nos
ADRs0021/0022 e no runbook WAHA B1; B3 não inventa uma exigência de outro chatbot.

[Runbook operacional B3](../runbooks/B3-CLOUDFLARE.md) contém o pacote e custódia
necessários: testemunha sob conta/admin/recuperação independentes, ou serviço de
terceiro equivalente com CAS/assinatura/inventário. Nenhuma credencial de deploy,
PITR, assinatura ou operador dessa testemunha pode estar neste Mac/backups.
Configurar, auditar IAM/custódia e validar as duas raízes reais antes de promover a
factory. Não executar release-first, migrar banco real ou substituir backend B2
apenas porque os testes locais/canário passaram.
