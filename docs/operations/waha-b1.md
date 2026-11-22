# Lívia / WAHA B1 — operação privada local

**Estado: inferência OpenAI real comprovada; conversa WhatsApp bidirecional NÃO
comprovada. Egress NO-GO por AUD-01/AR-02.** O inicializador não contém opção de
liberação de envio. `resume` habilita somente inferência após verificar o número
conectado. Não promete resposta no aparelho enquanto esse gate permanecer aberto.

Escopo aprovado: número secundário, até dois participantes autorizados, mensagens
individuais de texto iniciadas por eles. Não conectar o número público do salão,
importar histórico, enviar campanhas ou adicionar participantes automaticamente.

## Instalação e configuração privada

No clone da branch `codex/b1-livia-waha-live`:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install --no-deps -r requirements/ci.lock
.venv/bin/python -m pip install --no-deps --no-build-isolation -e .
scripts/b1 init --secondary +55DDDNUMERO --participant +55DDDNUMEROPESSOAL
nano .env.b1
```

Use E.164 real no lugar dos exemplos. Para dois participantes, repita
`--participant`. O arquivo é criado com modo 0600 e nunca é sobrescrito por `init`.
Se já foi criado, edite-o; não gere novos segredos para apagar limites anteriores.
Configure `OPENAI_API_KEY` privadamente. São fixados `LLM_PROVIDER=openai`, modelo
`gpt-6.1-sol`, esforço `low`, teto de saída 1024 e factory canônica
`generator_from_settings`. Não há seleção de FixedReplyGenerator neste fluxo.

Docker e Compose são necessários. Neste Mac foi usado Colima existente:
`colima start --cpu 2 --memory 3 --disk 20`. O launcher encontra o socket Colima
sem alterar o contexto Docker padrão. A imagem WAHA é ARM64 / WEBJS / Chromium,
versão 2026.10.1 com digest fixado no Compose. A imagem Python usa tag 3.12.16-slim;
essa tag não é apresentada como um digest imutável. Dependências seguem o lock
existente do projeto, sem novos pacotes.

```sh
scripts/b1 waha        # somente o canal, mesmo antes de configurar o secundário
scripts/b1 backend     # backend; exige o secundário e os participantes configurados
scripts/b1 start       # os dois serviços
scripts/b1 pair        # prepara sessão e abre o dashboard local
scripts/b1 status      # diagnóstico sem números, credenciais ou QR
```

## Pareamento manual

Abra [dashboard local](http://127.0.0.1:3000/dashboard). Usuário `admin`; senha no
campo `WAHA_DASHBOARD_PASSWORD` de `.env.b1`. Se solicitar conexão à API, use o
valor de `WAHA_API_KEY` do mesmo arquivo. Copie só o conteúdo entre as aspas.
No telefone secundário: WhatsApp → Aparelhos conectados → Conectar aparelho;
escaneie o QR da sessão `default`. QR e tokens não devem ser copiados para chat,
evidência, capturas compartilhadas ou Git.

`scripts/b1 status` só confirma o secundário quando a sessão está WORKING e a
identidade confere. Antes de retomar inferência, o backend consulta apenas os
números expressamente autorizados via API `contacts/check-exists`; aliases LID e
PN brasileiros só são aceitos depois dessa verificação. Não remover/inserir o
nono dígito por heurística. Não há consulta geral de contatos ou mensagens antigas.
Aliases são identidades do canal, não outra memória de Conversation.

```sh
scripts/b1 resume     # inferência, após binding; egress continua bloqueado
scripts/b1 pause      # kill switch persistente e controles de pausa do core
scripts/b1 stop       # pausa e para containers, preserva dados privados
scripts/b1 disconnect # pausa e despareia a sessão secundária
scripts/b1 errors    # diagnósticos agregados; não imprime logs brutos
```

Após parear e retomar, envie uma pergunta do participante autorizado ao secundário.
O webhook autentica HMAC, persiste SQLite e retorna 204 sem esperar o modelo.
ProcessingRunner processa fora do HTTP. A AI Reply fica como draft/outbox pending:
**nesta entrega não há envio automático**, pois AUD-01/AR-02 não foram fechados.
O core impede avançar a próxima inferência da mesma Conversation enquanto a
resposta anterior não tiver resultado autorizado. Não marcar drafts como enviados
para demonstrar memória ou destravar o teste.

## Knowledge e diagnóstico real de OpenAI

`knowledge/rj_studio.yaml` permanece intacto, com 22 fatos aprovados. Contexto,
persona, grounding, políticas comerciais, intake e handoff são os existentes.
O opt-in `use_history_for_knowledge=True` faz a seleção considerar o histórico
canônico para perguntas como “E quanto fica?”. Meta/Twilio/Telnyx mantêm o default.

```sh
scripts/b1 live-check
```

Esse comando usa entradas sintéticas declaradas, OpenAI real e Knowledge real,
com SQLite isolado e privado em `.local/b1/live-check/`. Não instancia WAHA API ou
sender, não cria acceptance fake, não envia mensagens e não comprova WhatsApp.
Registra latência, tokens, drafts e handoffs. Ausência de chave termina com
instrução objetiva; falha não é contabilizada como inferência bem-sucedida.
Conversação multi-turno completa fica bloqueada por draft não entregue; o relatório
registra essa limitação em vez de fabricar status de delivery.

Limites conservadores por journal: 20 chamadas (inclui tentativas), 500.000 tokens
reservados e US$1 estimado pelas taxas versionadas aprovadas pelo projeto em
02/10/2026. Reserva fsync antes da chamada; não há crédito de volta do excedente.
Usage desconhecido/crash mantém bloqueio. As taxas versionadas não são confirmação
de fatura/preço atual. Métricas do runtime preservam custo nulo sem tabela atual.

## Estado persistente e recuperação

`.local/b1/backend` contém SQLite; `control` contém cadeia MAC write-ahead;
`witness` contém o head separado; `sessions` contém autenticação WAHA. Diretórios
privados, ignorados no Git e excluídos do build Docker. Não copiar ao relatório.
Não apagar journal/witness para corrigir erros ou renovar orçamento.

O store WAHA verifica digest lógico do SQLite, grava prepare antes de commit e
checkpoint depois. Adulteração, restore unilateral, witness ausente, commit parcial,
perda de reserva e writer concorrente falham fechados. Boot sempre pausa. Revogação
é durável antes de processamento; comandos textuais reconhecidos incluem `pare`,
`parar`, `stop`, `sair`, `cancelar mensagens` e `não me envie mensagens`. `resume`
não concede consentimento novamente nem libera handoff. Unknown do WAHA nunca
ganha retry automático; os testes usam transporte fake explicitamente identificado.

**Essas raízes continuam sob o mesmo administrador/host.** Rollback conjunto depois
de reiniciar não é demonstravelmente detectável. O mecanismo local não é uma
autoridade monotônica independente nem solução para todos os ataques de writer
local direto. A quarentena de egress é estrutural no store; não delega a autorização
ao store legado nem compõe Outbound Executor. Incluir uma flag não resolve o gate.

Para liberar envio faltam: autoridade antirollback autenticada e administrada
independentemente; epoch/CAS/challenge frescos; inventário independente de intenções,
request exato/destino e submissões potenciais antes de todo HTTP; reconciliação de
unknown e restore com papéis separados; evidência atual de consentimento, pausa,
handoff, binding e budget; auditoria desse caminho operacional e exercício de
desligamento/recuperação. Só então substituir a negação estrutural por autorização
concreta, integrar o sender ao executor e executar o teste privado ponta a ponta.

WAHA imprime credenciais configuradas mesmo com log level `error` na versão
observada. Por isso o Compose usa logging driver `none` no WAHA; o container
anterior com logs foi substituído. Backend tem logs limitados sem access log.
Erros do canal são consultados pela API autenticada. Nenhum segredo/QR foi publicado.

## Contratos consultados

Implementação conferida com documentação oficial de
[configuração](https://waha.devlike.pro/docs/how-to/config/),
[HMAC e eventos](https://waha.devlike.pro/docs/how-to/events/),
[sessões](https://waha.devlike.pro/docs/how-to/sessions/),
[envio de texto](https://waha.devlike.pro/docs/how-to/send-messages/) e
[LIDs/telefones brasileiros](https://waha.devlike.pro/docs/how-to/contacts/).
Versão e digest conferidos no registry do fornecedor; API local autenticada
confirmou 2026.10.1/CORE/WEBJS/Chromium. HMAC usa o corpo bruto e SHA512.
