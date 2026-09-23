# RJ Studio AI

Atendimento de WhatsApp do RJ Studio em migração controlada para entrega
proativa:

```text
legacy:    Twilio webhook → aplicação → SQLite → resposta em TwiML
proactive: Twilio webhook → SQLite ingress → ACK
           SQLite → Processing Executor → AI Reply + outbox → Twilio REST
                                                        ↖ status callbacks
```

O núcleo usa uma interface `WhatsAppProvider`. A integração atual é Twilio; uma futura integração com Meta Cloud API pode entrar como outro provider sem alterar o fluxo de Conversations.

## Preparar o ambiente

Requer Python 3.11 ou mais recente.

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'
cp .env.example .env
```

Edite `.env` e preencha `TWILIO_AUTH_TOKEN`. Para o modo proativo, configure
também Account SID, API key dedicada, callback público e os limites do executor.

## Rodar localmente

```bash
rj-studio-maintenance migrate
uvicorn rj_studio_ai.main:app --reload --port 8000
```

`/health` confirma que o processo está vivo. `/ready` confirma configuração,
migrations, modo de delivery, escrita, durabilidade do SQLite e, em modo
proativo, que os Processing e Outbound Executors estão vivos:

```bash
curl http://localhost:8000/health
curl http://localhost:8000/ready
```

O startup também aplica migrations pendentes. Imports e criação de `app` não
criam o banco.

## Deploy com SQLite

O deploy atual usa um único processo da aplicação e um arquivo SQLite em volume
local persistente. Configure `DATABASE_PATH` para esse volume e mantenha
`APP_PROCESS_COUNT=1`; o mesmo valor deve ser usado no supervisor e no número de
workers do Uvicorn. `:memory:` é rejeitado. A aplicação não tenta inferir se o
filesystem do host é efêmero: confirmar o volume persistente faz parte do deploy.

Todas as conexões usam WAL, `synchronous=FULL`, foreign keys e um busy timeout
uniforme. `SQLITE_BUSY_TIMEOUT_SECONDS` configura tanto o timeout da conexão
quanto `PRAGMA busy_timeout`. Operações limitadas pelo deadline podem reduzir os
dois valores para o tempo restante, sem aumentá-los além do valor configurado.

Antes de disponibilizar a instância, confirme que `/ready` retorna `ready`. Não
altere o journal mode enquanto o processo estiver ativo.

## Conectar ao Twilio Sandbox

1. Exponha a porta 8000 com um túnel HTTPS, por exemplo `ngrok http 8000`.
2. Copie a URL HTTPS completa para `TWILIO_PUBLIC_WEBHOOK_URL` em `.env`, terminando com `/webhooks/twilio`.
3. No Sandbox do WhatsApp da Twilio, configure **When a message comes in** com essa mesma URL e método `POST`.
4. Reinicie o backend depois de editar `.env`.
5. Entre no Sandbox pelo WhatsApp pessoal e envie uma mensagem.

Com `LLM_PROVIDER=fixed`, o backend responderá com `AUTOMATIC_REPLY`. Para usar Claude,
defina `LLM_PROVIDER=anthropic`, forneça `ANTHROPIC_API_KEY` e configure os dois preços
por milhão de tokens. Os preços são deliberadamente configuração: consulte a tabela atual
da Anthropic antes de publicar. O backend salva a Conversation no arquivo indicado por
`DATABASE_PATH`.

`DELIVERY_MODE=legacy` é o default. Para o modo proativo, configure
`DELIVERY_MODE=proactive`, `TWILIO_ACCOUNT_SID`, `TWILIO_API_KEY_SID`,
`TWILIO_API_KEY_SECRET` e `TWILIO_STATUS_CALLBACK_URL`. Configure essa última
URL como callback de status público; o sender também a envia ao criar cada
Message resource. O Auth Token continua separado para validar webhooks.

No modo proativo, o inbound persiste a Message e responde com TwiML vazio após
o commit. O Processing Executor gera a AI Reply fora do webhook. A Outbound
Delivery `pending` é enviada pelo executor
REST exatamente por um caminho customer-visible. HTTP 429 usa retry limitado e
backoff persistido; somente códigos Twilio explicitamente conhecidos como
permanentes encerram a delivery. Timeout, perda de conexão, 5xx, 4xx sem
semântica comprovada e resposta ambígua viram `unknown` sem retry automático.

`/webhooks/whatsapp` continua disponível como alias compatível com a V0.

Para chamadas manuais locais sem assinatura da Twilio, use `TWILIO_VALIDATE_SIGNATURE=false`. Reative a validação ao conectar o Sandbox.

## Testar

```bash
pytest
ruff check .
python -m compileall -q src tests
```

O smoke test real está em
[`docs/runbooks/twilio-sandbox-smoke-test.md`](docs/runbooks/twilio-sandbox-smoke-test.md).
O gate do modo proativo está em
[`docs/runbooks/twilio-proactive-smoke-test.md`](docs/runbooks/twilio-proactive-smoke-test.md).
O gate de early ACK e processamento assíncrono está em
[`docs/runbooks/twilio-async-smoke-test.md`](docs/runbooks/twilio-async-smoke-test.md).

## Retenção e exclusão

Messages são mantidas por 90 dias por padrão. Nenhuma exclusão ocorre no
startup ou no fluxo de webhooks. O purge é sempre explícito:

```bash
rj-studio-maintenance purge-messages
rj-studio-maintenance delete-conversation \
  --provider twilio \
  --customer-address 'whatsapp:+55...'
rj-studio-maintenance reconcile-legacy-delivery \
  --delivery-id 123 \
  --resolution accepted_legacy
rj-studio-maintenance list-blocked-deliveries
```

`MESSAGE_RETENTION_DAYS` altera o prazo usado pelo comando. Deliveries pendentes
ou ambíguas protegem seu vínculo contra purge; deliveries terminais elegíveis
podem ser removidas com as Messages expiradas na mesma transação. Os comandos informam
somente metadados operacionais mínimos, sem endereços ou conteúdo.

## Estrutura

- `application.py`: fluxo canônico de uma Message recebida até a Automatic Reply.
- `providers/base.py`: interface abstrata `WhatsAppProvider`.
- `providers/twilio.py`: parsing, assinatura, TwiML e sender REST da Twilio.
- `persistence.py`: Conversations, Messages, outbox, claims e manutenção em SQLite.
- `delivery.py`: runner determinístico e executor outbound baseado no SQLite.
- `processing.py`: runner determinístico e executor de AI baseado no SQLite.
- `migrations/`: migrations versionadas com Alembic.
- `main.py`: composição FastAPI, ciclo de vida e endpoints HTTP.

CRM avançado, Trinks, Google Ads e Meta Cloud API permanecem fora desta migração.

## Smoke test Anthropic manual

O smoke do Claude é opt-in, não roda no CI e só deve ser executado com credencial local.
Os passos e o registro redigido do resultado ficam em
[`docs/runbooks/anthropic-smoke-test.md`](docs/runbooks/anthropic-smoke-test.md).

## Documentação do projeto

- [Produto](docs/PRODUCT.md)
- [Roadmap V0–V7](docs/ROADMAP.md)
- [Arquitetura existente e dívidas da V0](docs/ARCHITECTURE.md)
- [Linguagem do domínio](docs/CONTEXT.md)
- [Decisões arquiteturais](docs/decisions/README.md)
- [Especificações por versão](docs/specs/README.md)
- [Evals](docs/evals/README.md)
- [Salon Knowledge](docs/salon-knowledge.md)
- [Conversation Context](docs/conversation-context.md) · [Structured decision](docs/structured-decision.md)

Agentes começam por `AGENTS.md` e carregam somente os documentos relevantes para a tarefa.
