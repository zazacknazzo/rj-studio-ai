# RJ Studio AI

V0 do atendimento de WhatsApp do RJ Studio:

```text
Twilio Sandbox → webhook FastAPI → SQLite → resposta automática em TwiML
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
uvicorn rj_studio_ai.main:app --reload --port 8000
```

Confirme em `http://localhost:8000/health`.

## Conectar ao Twilio Sandbox

1. Exponha a porta 8000 com um túnel HTTPS, por exemplo `ngrok http 8000`.
2. Copie a URL HTTPS completa para `TWILIO_PUBLIC_WEBHOOK_URL` em `.env`, terminando com `/webhooks/whatsapp`.
3. No Sandbox do WhatsApp da Twilio, configure **When a message comes in** com essa mesma URL e método `POST`.
4. Reinicie o backend depois de editar `.env`.
5. Entre no Sandbox pelo WhatsApp pessoal e envie uma mensagem.

O backend responderá com `AUTOMATIC_REPLY` e salvará a Conversation no arquivo indicado por `DATABASE_PATH`.

Para chamadas manuais locais sem assinatura da Twilio, use `TWILIO_VALIDATE_SIGNATURE=false`. Reative a validação ao conectar o Sandbox.

## Testar

```bash
pytest
ruff check .
```

## Estrutura

- `application.py`: fluxo provider-independent de uma Message recebida até a Automatic Reply.
- `providers/base.py`: interface abstrata `WhatsAppProvider`.
- `providers/twilio.py`: tradução, assinatura e TwiML da Twilio.
- `persistence.py`: Conversations e Messages em SQLite.
- `main.py`: aplicação FastAPI e endpoints HTTP.

IA, CRM avançado, Trinks, Google Ads e Meta Cloud API permanecem fora desta V0.

## Documentação do projeto

- [Produto](docs/PRODUCT.md)
- [Roadmap V0–V7](docs/ROADMAP.md)
- [Arquitetura existente e dívidas da V0](docs/ARCHITECTURE.md)
- [Linguagem do domínio](docs/CONTEXT.md)
- [Decisões arquiteturais](docs/decisions/README.md)
- [Especificações por versão](docs/specs/README.md)
- [Evals](docs/evals/README.md)

Agentes começam por `AGENTS.md` e carregam somente os documentos relevantes para a tarefa.
