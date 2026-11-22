# B3 — implantação e aceite operacional

Estado: NO-GO; uma conta disponível, nenhuma factory B3 promovida. A autorização
humana cobre uma resposta ao participante existente e não fecha o aceite técnico.

## O que está disponível

`infra/waha-authority/src/worker.mjs` implementa os dois papéis. A autoridade usa
binding `AUTHORITY`/classe `Authority`; a testemunha usa `WITNESS`/classe `Witness`.
Ambos usam migration Wrangler `new_sqlite_classes`, tag `v1`, compatibility date
`2026-11-20`, `workers_dev: true` e observability desativada. O canário da conta
principal é descartável como prova operacional: nunca deve virar a testemunha real.
Não apagar sua raiz para repetir um teste.

Na conta existente, `scripts/b3 prepare`, `deploy-authority`, `deploy-canary` e
`canary-check` preparam e verificam implantação fechada. Os arquivos privados ficam
em `.local/b3/cloudflare`, modo0600; nunca versionar ou colar seu conteúdo no chat.
Deploy recusa Worker existente ou recibo anterior, antes de qualquer mutação.
Resultado ambíguo exige inspeção do deployment existente; não repetir automaticamente.
Não executar `scripts/b1 start` deste checkout enquanto a migração não for aprovada.

## Única dependência externa restante para provisionar a testemunha

Uma conta separada sob administrador/credencial/recuperação independentes do Mac,
dos backups e do administrador de restore da autoridade principal. Criar apenas
outro objeto ou token na conta atual não atende. Outra conta controlada pela mesma
credencial de recuperação também não comprova separação. Alternativa: serviço de
terceiro com CAS durável, inventário preservado, respostas autenticadas e custódia
administrativa equivalente; KV eventualmente consistente e R2 com lock removível
pelo mesmo administrador não atendem.

O administrador independente precisa somente de Workers/DO SQLite no Free, acesso
à versão revisada do Worker e ao seguinte pacote de inscrição: hash do source,
SCOPE, ACCOUNT_ID real da autoridade, estado inicial assinado `inspect` de revisão0
e seu digest. O pacote contém hashes e metadados; nenhum texto, contato, chave WAHA
ou segredo de operador da autoridade. Verificar a assinatura e a identidade da
conta por controle de plano autenticado, não por um campo JSON autodeclarado.

Na máquina independente, gerar Ed25519 para `SIGNING_JWK`, `OPERATOR_KEY` próprio e
um `AUTHORITY_KEY` aleatório de pelo menos32bytes. Implantar Witness com vars
`ROLE=witness`, `ACCOUNT_ID` da conta independente e o mesmo `SCOPE`. Enviar `enroll`
com papel operator, expected0 e args `authority_account`, `digest`, `snapshot` do
pacote inicial. O protocolo canônico, HMAC/Ed25519 e desafio está em
`waha_cloudflare_ops.raw_command`; testes executáveis em `test/runtime.mjs`.
Inscrição só é permitida em raiz vazia; nunca substituir uma testemunha inscrita
por outra vazia. Guardar chave privada de assinatura, operador, OAuth/API de deploy
e recuperação exclusivamente sob custódia independente.

Devolver URL `/command`, chave pública, ID real da conta, recibo de deployment/source
e apenas o segredo de chamada `AUTHORITY_KEY`, por canal seguro. A autoridade pode
chamar a testemunha; esse segredo não permite deploy, PITR, reinscrição ou exclusão.
Não transmitir segredos pelo chat, argumentos de shell ou Git. O administrador
principal atualiza somente `WITNESS_URL`, `WITNESS_ACCOUNT_ID`, `WITNESS_PUBLIC_KEY`
e o secret `WITNESS_KEY` da autoridade. Preservar namespace e histórico DO.
Esta atualização e o aceite IAM dependem da configuração externa ainda ausente.

## Aceite antes de promover

Registrar evidência de segregação: contas reais distintas, membros/roles e tokens
mínimos por recurso, ausência de OAuth/API/admin da testemunha no Mac ou seus
backups, recuperação separada e responsável pelo restore. Conta diferente e
assinatura válida são controles necessários; software não prova custódia humana.
O OAuth amplo atualmente presente no Mac não serve como evidência de segregação.
Nenhuma combinação consegue detectar o rollback simultâneo de todas as raízes
administrativas; o procedimento deve excluir essa falha comum.

Reproduzir testes Node/workerd, bridge Python e regressão/CI do SHA final; validar
protocolo e recuperação também nas duas contas reais. Inspecionar ausência de
submissões anteriores e restaurar backups somente em ambiente isolado. Não fazer
PITR destrutivo na raiz operacional para testar. A migração0024 deve ser ensaiada
numa cópia e auditada antes de aplicar ao banco real; prova aceita só estende
UNKNOWN→accepted para WAHA, jamais retry ou retorno a pending.

Com contas/custódia e implantação verificadas, inscrever testemunha inicial,
executar `initialize` com o head/sequence autenticados do journal local e conservar
o inventário. Criar runtime.json0600 com `url`, `scope`, `account`, `witness_account`,
`public_key`, `runtime_key`; nenhum segredo de operador/deploy/signing no backend.
`.local/b3/operator.json` contém `{runtime: <config>, operator_key: <segredo>}` sob
custódia do operador. Somente o runtime é montado readonly em `/authority` pelo
`compose.b3.yaml`. Backup anterior não pode sobrescrever uma configuração nova.

Promover explicitamente com compose.b1.yaml + compose.b3.yaml no mesmo projeto,
sem publicar WAHA/dashboard. Boot cria novo epoch, pausa e remove grants. Validar
identidades JID/LID, consentimento, handoff, budgets e head; `scripts/b1 resume`
libera apenas inferência. Só então `scripts/b3 release-first` autoriza a intenção
pendente única por10minutos, após nova checagem do backend e WAHA. Nunca autorizar
um ID numérico SQLite ou um destinatário fornecido livremente.

Verificar accepted durável e ID do provider; recebimento no aparelho continua uma
verificação separada. Registrar explicitamente o que foi observado. Não liberar
novas intenções ou chamar de conversa multirrodada sem nova autorização/aceite.

## Falhas e recuperação

`kill` revoga a autoridade e pausa o backend. Um POST que já entrou na rede pode
ter sido aceito; kill não desfaz aceitação. Consume grava unknown antes do POST e
nunca recria seu ticket. Expiração é mantida após consume e revalidada imediatamente
antes do transporte. Timeout/500/resposta incompleta/local crash não geram retry.

Falha entre witness/autoridade/local fecha o caminho. `repair-roots` usa somente o
snapshot completo minimizado retido na testemunha, verifica revisão/digest, conserva
unknown/accepted/revogações, incrementa epoch e termina pausado/killed. O journal
registra falhas HMAC sticky e exige reparo posterior; não apagar esse registro.
Um head local incorreto ainda exige backup correto; hashes não recriam Messages.
Restaurar uma testemunha abaixo da autoridade permanece bloqueado.

Para falha local APÓS receipt causal já ancorado como accepted na autoridade, `reconcile-accepted --proof-file <0600>` recebe
apenas intenção e ID WAHA. O ID deve coincidir com o hash do ID retornado ao runtime pela própria tentativa
HTTP e já ancorado na testemunha. Operador observa a mensagem existente via GET,
valida sessão/destinatário/texto/ACK/timestamp contra consumed_at/accepted_at
(tolerância máxima5s para relógios) e anota prova na autoridade. O backend repete a
observação e grava prova imutável antes de finalizar localmente. Nunca aceitar um
hash arbitrário como prova de entrega. Sem observação válida, manter unknown e
pedir atendimento humano. Não existe operação not_submitted que reabra envio. Se o POST expira sem recibo
causal ancorado, mesmo um GET com texto/destinatário/horário iguais NÃO pode
transformar UNKNOWN em accepted: pode ser uma mensagem manual idêntica. WEBJS
2026.10.1 em uso não encaminha request.id pré-gerado em getMessageOptions e
generateNewMessageId herda NotImplementedByEngineError; não presumir idempotência
ou correlação que esse engine não fornece. Preservar UNKNOWN e atendimento humano.
O código compilado do container foi inspecionado somente para leitura; nenhum envio
foi feito para verificar essa limitação.
