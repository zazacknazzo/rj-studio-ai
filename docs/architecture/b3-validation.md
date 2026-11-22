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
CI do source final d13b731: SUCCESS na execução45070001408, com2353 testes Python
isolados em kernel Linux sem rede +20 bridge Python/workerd =2373 PASS,0 skips;
15 testes Node/workerd PASS. Audits de dependências e Gitleaks/source/histórico PASS.
[Execução verificada](https://github.com/zazacknazzo/rj-studio-ai/actions/runs/45070001408).

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

Spec rechecando e852746 confirmou resolução e nenhum novo P1/P2 no delta. Uma
revalidação Standards foi interrompida por limite da ferramenta, sem ser contada
como aprovação. Depois do restabelecimento, Standards rechecando d13b731 confirmou
resolução, reproduziu as recusas de recibo ausente/mensagem antiga e reportou zero
P1/P2 de código pendentes confirmados. Isso não é GO operacional: infraestrutura,
IAM/custódia e exercício real de recuperação seguem pendentes. AWS não foi incluída
nessa revisão de código.

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

## Alternativa solicitada após o checkpoint

O usuário não dispõe de administrador independente e informou não ter conta AWS.
Foi pesquisada candidata com S3 Object Lock COMPLIANCE, escritas condicionais,
endpoint de witness e assinatura com chave fora da Cloudflare/Mac. Não adotada como
substituta auditada: exige tratar versões novas/delete markers, prazo/expiração,
identidade da conta/bucket, CAS, IAM e assinatura. Um modelo experimental fora do
source operacional passou14 negativos/positivos offline; zero chamadas/recursos AWS.
Não é adaptador AWS implementado nem prova do provedor. Ver entrega externa
B3-ALTERNATIVA-AWS.md/zip. Cadastro AWS, custos e retenção irreversível ainda dependem
do usuário e do pacote final revisado. Não modificar B3 para aceitar um ID AWS falso
ou simplesmente ignorar o check da testemunha.
