# RJ Studio AI

V0.1 do atendimento de WhatsApp do RJ Studio:

```text
Twilio Sandbox → adapter Twilio → aplicação → SQLite → resposta automática em TwiML
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

Edite `.env` e preencha `TWILIO_AUTH_TOKEN`.

## Rodar localmente

```bash
rj-studio-maintenance migrate
uvicorn rj_studio_ai.main:app --reload --port 8000
```

`/health` confirma que o processo está vivo. `/ready` confirma configuração,
migrations e escrita no banco:

```bash
curl http://localhost:8000/health
curl http://localhost:8000/ready
```

O startup também aplica migrations pendentes. Imports e criação de `app` não
criam o banco.

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

## Retenção e exclusão

Messages são mantidas por 90 dias por padrão. Nenhuma exclusão ocorre no
startup ou no fluxo de webhooks. O purge é sempre explícito:

```bash
rj-studio-maintenance purge-messages
rj-studio-maintenance delete-conversation \
  --provider twilio \
  --customer-address 'whatsapp:+55...'
```

`MESSAGE_RETENTION_DAYS` altera o prazo usado pelo comando. Os comandos
informam somente contagens; não imprimem endereços nem conteúdo.

## Estrutura

- `application.py`: fluxo canônico de uma Message recebida até a Automatic Reply.
- `providers/base.py`: interface abstrata `WhatsAppProvider`.
- `providers/twilio.py`: parsing, assinatura e TwiML da Twilio.
- `persistence.py`: Conversations, Messages, idempotência e manutenção em SQLite.
- `migrations/`: migrations versionadas com Alembic.
- `main.py`: composição FastAPI, ciclo de vida e endpoints HTTP.

IA, CRM avançado, Trinks, Google Ads e Meta Cloud API permanecem fora desta versão.

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

Agentes começam por `AGENTS.md` e carregam somente os documentos relevantes para a tarefa.
