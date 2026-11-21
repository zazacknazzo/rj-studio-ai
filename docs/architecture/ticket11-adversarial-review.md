# Ticket11 — revisão adversarial independente de sender/idempotência

Data: 21/11/2026, America/Sao_Paulo. Revisor independente delegado pelo implementador
conforme pedido expresso do usuário. Leitura direta de `AGENTS.md`, spec11, ADR0019,
`telnyx_request.py`, `providers/telnyx_sender.py`, runner, autorização/finalização,
ledger de status, migration0022 e diff contra `07c1b7dc150d7eb1776b97d891cd29347adffd37`.
Não derivei o parecer do relatório final do implementador. Nenhum arquivo de produção,
teste versionado, credencial ou branch foi alterado por este revisor; apenas este relatório.
O implementador permanece o único escritor Git.

## Parecer e alcance

**PASS para o candidato OFFLINE corrigido, sem P1/P2 novo confirmado pendente nesta
perspectiva. NO-GO operacional/produção.** A revisão confirmou e reproduziu um P2 de
resposta malformada, corrigido pelo implementador e reexecutado aqui. Também foi corrigido
um extremo aritmético de timeout de baixa severidade. Isto não aprova piloto, merge,
Tickets12–13 ou HTTP real. AUD01 permanece aberto e bloqueia composição de saída após
restore obsoleto. Uma MAC no mesmo snapshot não prova frescor.

A primeira execução usou código de produção do CP3 (inalterado no CP4 `2751652`);
a verificação final usou a árvore de correções posterior a esse CP. Integridade dos
arquivos efetivamente inspecionados/executados na verificação final:

| Arquivo | SHA256 |
| --- | --- |
| providers/telnyx_sender.py | `632460d157efb954a1897bea49562a38ee71e688eec73ffe653d48dd25aeb849` |
| telnyx_request.py | `4697d82edb594a57e70dffed862f81470e893750e3d51727b25aafc253b0ddb4` |
| delivery.py | `f947306f6c8adf58acaf7e2d2de0e6d53bae61a803538d8077e8471e0d2c5a2c` |
| persistence.py | `b682f4c95e1e04fb15688e179da5b7e436006e1606131b566b95f17f0e7cdf13` |

A SHA Git final deve ser consultada em origin após publicação; estes hashes não predizem
um commit futuro nem substituem a conferência remota do implementador.

## Evidência própria executada

Ambiente: Python3.12.14, pytest9.2.0, SQLite real, `/tmp/ticket11` privado0700,
`/tmp/ticket11/run` com env-i, sem credenciais/proxy para testes e guard Python bloqueando
sockets IPv4/IPv6 (incluindo filhos que o herdam). O guard não é sandbox de kernel.
Nenhuma chamada Telnyx foi feita; todos os exchanges foram funções locais sintéticas.

| Execução | Resultado real | O que comprovou |
| --- | --- | --- |
| `...run -m pytest /tmp/ticket11/adversarial-review/test_probes.py --basetemp=/tmp/ticket11/tmp/adversarial-review -ra` | **6 failed,8 passed,20.77s**, exit1 | Reprodução própria de sucesso malformado aceito; contenção e negativos HTTP passaram |
| Mesmo arquivo **sem modificar os14probes**, `--basetemp=.../adversarial-review-fixed` | **14 passed,0 skips,15.48s**, exit0 | Correção do P2;8workers concorrentes resultam em1claim/1exchange;409/422/429/500/502/503/504 persistem unknown e não reenviam em novo store após2dias |
| Probe aritmético de timeout antes da correção | Captura `isfinite(read_timeout_seconds)==False` com total finito1e308 | Overflow confirmado sem esperar timeout nem abrir rede |
| `...run -m pytest .../test_timeout_budgets.py --basetemp=.../adversarial-review-timeouts -ra` | **3 passed,0 skips,0.28s** |1e308,5e-324 e3.0: orçamentos derivados positivos/finitos ou negativa local sem exchange |
| Rechecagem independente do mesmo probe de timeout após aviso do implementador, basetemp separado | **3 passed,0 skips,0.35s** | Confirmação explícita final da mesma correção; não somar como novos casos |

Estes recortes não são a suíte integral, nem devem ser somados a ela como cobertura
independente adicional. A suíte integral e scanners do implementador/especialistas
constam nos respectivos relatórios, não são alegados como minha execução.

## Achados e disposições

**ADV11-01, P2, corrigido — resposta2xx malformada promovida a acceptance.**
O parser original verificava a identidade central, mas ignorava campos conhecidos
opcionais presentes. Minhas seis variações independentes usaram `from.status='failed'`,
`from.status=[]`, `from.line_type=[]`, `received_at='invalid'`, `encoding={}` e
`wait_seconds='invalid'` com demais campos válidos. Todas finalizaram ACCEPTED;
a expectativa UNKNOWN falhou seis vezes. Isto viola o contrato de resposta estrita:
status inválido ou estrutura/timestamp/número malformados não devem liberar ordering
como acceptance comprovada. Não observei envio duplicado ou endpoint real.

Fonte própria inspecionada: snapshot público `/tmp/ticket11/openapi`, endpoint
`/messages/whatsapp`, `WhatsappResponse` e `RCSToItem`, mais o documento de idempotência.
O enum de `from.status` é received/delivered; line_type tem enum; encoding é string;
received_at é date-time; wait_seconds aceita number|null. A ausência destes opcionais
não é um erro inventado. O erro reproduzido foi aceitar **presença inválida**.

O implementador adicionou validação de campos opcionais conhecidos, timestampRFC3339,
número finito e conflito com modalidades não textuais. Reexecutei **os mesmos14probes
inalterados**:14pass; as seis variações agora permanecem unknown e não aceitam. Achado
encerrado no candidato offline observado, sujeito à auditoria direta do orquestrador.

**ADV11-02, P3, corrigido — orçamento de leitura podia tornar-se infinito.**
`timeout_seconds=1e308` é finito, mas a expressão `timeout*2/3` overflowava. Meu exchange
capturou read infinito; não houve espera nem rede. A implementação passou a subtrair
o orçamento de conexão do total e negar derivados não positivos. Os três probes
independentes acima passaram;1e308 mantém budgets finitos,5e-324 nega localmente e3.0
preserva orçamentos positivos. Nenhum risco novo de retry foi observado.

## Inspeção de invariantes e limites não comprovados

- Request material inclui organização/profile/método/scheme/host/path/query/tipo/
  remetente/destinatário/bytes/chave; HMAC privada evita novo digest público de texto.
  Verificação ocorre antes do marker e novamente antes do exchange. Canonicalização
  fixa e imutabilidade normal do objeto tornam divergência local negativa.
- Writer existente revalida owner/lease/policy/consent/pausa/revisão/handoff/order/
  conflito/canal, vincula MAC e commit dos markers sem I/O. Callback antecipado usa o
  ledger separado; aceitação HTTP não promove sent/delivered/read.
- Não há cliente HTTP/default/SDK/credencial ou seleção runtime nova. `retries=0` e
  `follow_redirects=False` foram observados por inspeção e recortes locais. O protocolo
  da função injetada é **confiável**, não isola código Python arbitrário nem comprova
  que um futuro cliente real honrará essas opções.
- `send_prepared` é uma seam de baixo nível cujo caller precisa ter feito autorização;
  não é endpoint autenticado nem novo mecanismo operacional. A integração aprovada
  do runner respeita esse contrato; não tratar o método isolado como capacidade de
  autorização ou como garantia contra um caller interno arbitrário.
- Os probes próprios de concorrência exercitaram8workers e um banco, não todos os
  escalonamentos possíveis, crash físico de disco ou coordenação entre volumes.
- AUD01 e o controle externo de quarentena/reconciliação permanecem contrato/gate,
  não implementação. CX01 retenção, CX06 autorização→HTTP, CX11/33 ativação e CX36
  consentimento operacional continuam pendentes. Idempotência Telnyx expira e nunca
  autoriza retry de unknown. Não executei restore operacional, provisioning, piloto,
  API de conta, sincronização real ou verificação de controle entre duas contas.

## Reprodução portátil dos probes próprios

Os arquivos temporários não são evidência durável por si. Salvar os blocos abaixo em
um diretório privado0700 e executar com o mesmo guard/env-i/venv corrigido descritos
no relatório de validação, PYTHONPATH incluindo src e tests. Os dados são sintéticos.
O primeiro bloco deve produzir14pass no candidato corrigido; na versão CP3 ele produz
6failed/8pass explicitamente. O segundo deve produzir3pass. Não remover o guard nem
substituir as funções de exchange por cliente HTTP.

```python
"""Independent adversarial probes, synthetic scopes, no HTTP client."""

import json
from dataclasses import replace
from datetime import timedelta
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest
from test_telnyx_authentication import ORG, PROFILE, PHONE
from test_telnyx_authentication import private_key as private_key
from test_telnyx_authentication import settings as settings
from test_telnyx_messages import ingress as ingress
from test_telnyx_messages import TIME, CUSTOMER
from test_telnyx_delivery_status import pending
from rj_studio_ai.providers.telnyx_sender import (
    TelnyxWhatsAppSender,
    TelnyxHttpResponse,
    TelnyxOutcomeUnknown,
)
from rj_studio_ai.telnyx_request import TelnyxRequestSigner
from rj_studio_ai.persistence import SqliteConversationStore, DeliveryState
from rj_studio_ai.delivery import OutboundDeliveryRunner


@pytest.fixture
def signer():
    return TelnyxRequestSigner(
        ORG, PROFILE, "review-integrity", b"independent-review-key-only-123456789"
    )


def payload(request):
    return {
        "data": {
            "record_type": "message",
            "direction": "outbound",
            "id": "review-message-1",
            "type": "WHATSAPP",
            "organization_id": ORG,
            "messaging_profile_id": PROFILE,
            "from": {"phone_number": PHONE},
            "to": [{"phone_number": CUSTOMER, "status": "queued"}],
            "body": {"type": "text", "text": {"body": request.message.body}},
        }
    }


def http(data):
    return TelnyxHttpResponse(200, json.dumps(data).encode())


def runner(store, signer, exchange):
    return OutboundDeliveryRunner(
        store, TelnyxWhatsAppSender(signer, exchange), 3, provider="telnyx"
    )


@pytest.mark.parametrize("field,value", [("status", "failed"), ("status", []), ("line_type", [])])
def test_invalid_known_sender_fields_must_not_accept(ingress, signer, field, value):
    _, store, _ = ingress
    pending(store)

    def exchange(request, **_):
        data = payload(request)
        data["data"]["from"][field] = value
        return http(data)

    result = runner(store, signer, exchange).run_once(now=TIME)
    assert result.state is DeliveryState.UNKNOWN


@pytest.mark.parametrize(
    "field,value", [("received_at", "invalid"), ("encoding", {}), ("wait_seconds", "invalid")]
)
def test_invalid_known_response_fields_must_not_accept(ingress, signer, field, value):
    _, store, _ = ingress
    pending(store)

    def exchange(request, **_):
        data = payload(request)
        data["data"][field] = value
        return http(data)

    result = runner(store, signer, exchange).run_once(now=TIME)
    assert result.state is DeliveryState.UNKNOWN


def test_many_workers_one_exchange_and_no_replay(ingress, signer):
    _, store, path = ingress
    pending(store)
    barrier = Barrier(8)
    calls = []

    def exchange(request, **_):
        calls.append(request)
        return http(payload(request))

    def work(_):
        barrier.wait()
        return runner(SqliteConversationStore(path), signer, exchange).run_once(now=TIME)

    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(work, range(8)))
    assert sum(x is not None for x in results) == 1 and len(calls) == 1

    def unexpected(*_, **__):
        pytest.fail("repeat exchange")

    assert (
        runner(SqliteConversationStore(path), signer, unexpected).run_once(
            now=TIME + timedelta(days=2)
        )
        is None
    )


@pytest.mark.parametrize("status", [409, 422, 429, 500, 502, 503, 504])
def test_error_never_retries_with_fresh_worker(ingress, signer, status):
    _, store, path = ingress
    pending(store)
    calls = []

    def exchange(request, **_):
        calls.append(request)
        return TelnyxHttpResponse(status, b'{"errors":[{"code":"10036"}]}')

    result = runner(store, signer, exchange).run_once(now=TIME)
    assert result.state is DeliveryState.UNKNOWN

    def unexpected(*_, **__):
        pytest.fail("repeat exchange")

    assert (
        runner(SqliteConversationStore(path), signer, unexpected).run_once(
            now=TIME + timedelta(days=2)
        )
        is None
    )
    assert len(calls) == 1
```

```python
"""Independent timeout arithmetic probe; exchange only captures budgets."""

import math
from uuid import uuid4
import pytest
from rj_studio_ai.domain import OutboundMessage
from rj_studio_ai.providers.telnyx_sender import (
    TelnyxWhatsAppSender,
    TelnyxHttpResponse,
    TelnyxOutcomeUnknown,
)
from rj_studio_ai.telnyx_request import TelnyxRequestSigner, InvalidTelnyxRequest


@pytest.mark.parametrize("seconds", [1e308, 5e-324, 3.0])
def test_derived_budgets_are_positive_finite_or_rejected_locally(seconds):
    signer = TelnyxRequestSigner(
        "synthetic-org", "4001781e-626f-4a41-a914-b1b682150f94", "review", b"x" * 32
    )
    message = OutboundMessage(
        "+5511999999999", "+5511888888888", "Synthetic", submission_key=str(uuid4())
    )
    calls = []

    def exchange(request, **policy):
        calls.append(policy)
        return TelnyxHttpResponse(429, b"{}")

    sender = TelnyxWhatsAppSender(signer, exchange)
    try:
        sender.send_prepared(sender.prepare(message), timeout_seconds=seconds)
    except InvalidTelnyxRequest:
        assert calls == []
    except TelnyxOutcomeUnknown:
        assert len(calls) == 1
        assert all(
            math.isfinite(calls[0][name]) and calls[0][name] > 0
            for name in ("connect_timeout_seconds", "read_timeout_seconds")
        )
```
