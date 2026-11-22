# Ticket13 — independent Operational Readiness Review

Revisão em22/11/2026, America/Sao_Paulo. **Resultado: nenhum novo P1/P2 confirmado
no candidato inspecionado, limitado a preparação e laboratório OFFLINE.**
Candidato apto a ser submetido à auditoria final do orquestrador; isto não é
autorização operacional. **AUD-01 ABERTO; próximo gate externo, piloto e produção NO-GO.**

## SHA, escopo e independência

- Local HEAD inspecionado e testado:
  `995af20ff7d9e9f592a23c544f09a2407bd1b7f0`.
- Branch: `codex/telnyx-coexistence-13-readiness`; baseline aprovada:
  `f1496be42732b7e57d317444d7ed0020997f0327`.
- O principal informou verificação remotaCP6. Esta revisão conferiu HEAD/status locais,
  não fez fetch/push próprio nem presume autenticação de outra conta.
- Source/tests funcionais permanecem iguais aoCP5
  `988efabe39611821035663dbae24a266b71bfca5`; diffCP5..CP6 contém somente docs.
- Nenhum arquivo no repositório foi editado por este revisor. Probes e evidências próprios
  foram criados fora dele em work/review-operations. Não houve commit/push pelo revisor.
- Nenhuma conta/API Telnyx/Meta, credencial comercial, endpoint público, worker,
  mensagem, LLM, ativação ou piloto foi usado. Não houve alteração Baileys/main.

Inspeção direta: AGENTS e regras de domínio/issues; spec13/ADR0021; offline_recovery.py,
fixture externoSQLite, telnyx_asgi.py, operações administrativas e persistence nas
fronteiras de pause/marker/purge; workflowCI/runner; matriz de gates/retention;
docsCP6 runbooks/pilot/observability e reconciliação do runbook/índices correntes.

## Evidência própria executada

Ambiente observado: Python3.14.7, SQLite3.50.4, pytest9.2.0, macOSarm64.
Fixtures sintéticas, SQLite real e TestClient/ASGI em processo.
Runner sanitiza credenciais/ambiente, cria temporários0700 e instala guardPython.
Esta execução local não é namespace/kernel sandbox nem prova de infraestrutura real.

Comando executado a partir da raiz do repo:
```bash
../venv/bin/python scripts/check_telnyx_offline.py --python ../venv/bin/python --output ../review-operations/final-probes ../review-operations/test_operations_probes.py
```

**Resultado:9passed/0failed/0skipped em15.78s, exit0.**
JUnit registrou9tests/0errors/0failures/0skipped, tempoXML15.795s.
Não extrapolar estes tempos para ACK/SLA ou comparar com Telnyx real.
O recorte se sobrepõe à suíte integral; não somar contagens como cobertura distinta.

| Prova operacional própria | Resultado observado |
| --- | --- |
| Operador autenticado pausa ANTES de humano, sem esperar echo | Pausa efetiva; unauthorized401; estado sem token/endereço |
| Pausa com e sem marker já commitado | Semmarker cancela; marker existente mantém sending e sinaliza in_flight_possible |
| Retry da mesma operação | Retorna receipt original sem segundo efeito |
| Receipt antigo de pausa após resume | Receipt histórico continua paused; GET atual mostra resumed/revision corrente |
| Unknown e retenção | unresolved_delivery visível; purge falha fechado com rollback; unknown/key preservados |
| Unknown depois de2dias | Nenhum claim/retry automático; integridade/FK corretos |
| Seis tentativas de mídia/localização/futuro | Todas422, counterdurável6, sem Message/receipt falso ou payload emcounter/response/metrics |
| Readiness local | Quarentena/generationfalse/egressfalse/operational_channelfalse |
| Papel somenteleitura | Alteração de pausa403 e estado/revision inalterados |
| Retenção vs schema real | As24tabelas migradas constam na matriz |

São dez comportamentos distribuídos em nove casos parametrizados/múltiplos asserts,
não dez execuções independentes.

## Critérios operacionais inspecionados no CP6

1. **Todos16runbooks** trazem responsável, pré-condições, evidência/ações e proibições:
   boot seguro, disconnect, reconnect/sync, assumir humano, pause/resume, unknown,
   conflito, SQLite, webhook indisponível, restore, retries/failover, rotação/perda,
   desativação emergencial, rollback de versão, encerrar piloto e unsupported/humano.
2. Runbook de humano exige pause ANTES de responder e **GET estado/revision atuais após
   POST/replay**, corrigindo o risco de tomar receipt histórico por estado corrente.
   Mostra handoff_active, unresolved_delivery e in_flight_possible.
3. Resume não reconcilia unknown/conflito, não revive fila antiga e não prova consent
   ou janela. Marker anterior à pausa pode estar em voo; não há promessa de recall.
4. Restore/rollback preservam DB/ledger/fences, começam quarantinados e requerem epoch,
   inventário externo completo/provas atuais/aprovador distinto. Não restaurar trust
   roots juntas nem usarbackup antigo para reexecutar envios.
5. CX29 tem procedimentos por formato, alertas e fila mínima proposta. O agregado422
   não permite identificar/reconstruir Customer/conteúdo; ausência de identificação
   segura/fila/operador é explicitamente gate antes do piloto. Não há2xx para ocultar.
6. Plano de piloto é **planejamento apenas**, em duas autorizações separadas:
   infraestrutura/antirollback primeiro e piloto delimitado depois, com escopo nominal,
   conta/número secundário/participantes consentidos/operadores/limites e parada.
7. Elegibilidade individual+55/Coexistence/sync/assinatura real/consent real/IAM/TLS/
   observação de provider não são inferidos dos fixtures/documentação geral.
   Templates operacionais e BSUIDoutbound não foram habilitados.
8. Limites propostos5voluntários/20respostas/60min/US$5 são identificados como proposta,
   não tarifa verificada, autorização de gasto ou prova de escala. Amostra é smoke,
   insuficiente paraSLA. Produção exige decisão própria posterior.
9. Observabilidade inclui ACKpóscommit, p50/p95/p99,204/422/503,dedupe, assinatura,
   quarentena, lifecycle,unknown,conflict,unsupported,SQLite,backlog e humano.
   Indicadores/alertas não implantados são marcados como requisitos.
10. Carga sintética e budget local estão separados de proxy/TLS/rede/fsync/clock real;
    targets históricosCX20 permanecem sem redefinição ou alegação deSLA.
11. Matriz AUD06 foi reconciliada com recuperação byte a byte do originalv8.
    A revisão não chama compatibilidade de parse de geração/modelo real validado.
12. Retenção de artifacts atual14dias e proposta de relatórios/audit180dias estão
    separadas. Nenhum novo prazo/expurgo automático ou conformidadeLGPD foi declarado.

## Achados e correções durante a revisão

**Nenhum novo P1/P2 pendente confirmado nesta revisão.** Bloqueadores conhecidos não
foram reclassificados para conseguir um parecer favorável.

Pendências documentais comunicadas na revisão inicial foram corrigidas antesCP6:
matrizAUD06 desatualizada após recuperaçãov8; distinção retençãoCI14dias versus
proposta180dias; necessidade deGET atual após receipt de pausa repetida.
A questão de receipt é comportamento contratual existente, não novo bypass.

Tentativas próprias preservadas:
- Primeira rodada8casos:5passed/3failed em2.63s. Dois failures eram atributo incorreto
  do meu probe (record expõe first_submission_at, não submission_started_at); terceiro
  esperava purgeunknown retornar0, mas o contrato existente é PersistenceUnavailable
  porFK com rollback seguro, já coberto por teste de retenção anterior.
- Corrigi somente o probe externo, não código:8passed4.34s.
- Acrescentei prova de receipt histórico:9passed7.43s noWIP.
- Reexecução própriaCP6 atual:9passed15.78s, acima.

## Gates que permanecem abertos

AUD01 depende de authority/witness/ledger/autenticação/backup não restauráveis juntos
e integração de TODOS os caminhos de submissão no ambiente de destino. Lab não concede
egress e source genérico legado não foi tornado operacionalmente seguro por este ensaio.
Rollback conjunto de todas as raízes requer uma raiz não revertida; não é resolvido por
schema/HMAC/contador local. Não propor encerramento operacional por esta revisão.

Também continuam exigindo evidência: UI/caminho privado móvel e operadores designados
CX07/08; fila e resolução segura de unsupported/retries/failoverCX29; consent/template
atuaisCX16/36; conta/número/Coexistence/binding/syncCX10/11/33; key/runtime/NTP/TLS/proxy
CX09/24/25; retenção/erasure/backups reaisCX01; aceite conversacionalCX26; CI/release
e E2E/custoCX19/20/21. Outros riscos da matriz conservam seus gates.
Papéis e thresholds propostos ainda precisam responsáveis nominais/ratificação.
Não conceder exceção, encerrar checkbox ou iniciar gate externo por silêncio.

## Integridade das evidências inspecionadas

| Arquivo | SHA256 |
| --- | --- |
| src/rj_studio_ai/offline_recovery.py | 6d50cfc82a436320c7310185f0f6070347c0e42599876bb7ebef7b76f5166a9c |
| src/rj_studio_ai/telnyx_asgi.py | 368ff72c8744d30a783694f0ddfe43f97dba75845660b76ed9e125bc7fa85846 |
| tests/offline_recovery_fixture.py | cf9850f15716475e55ca7608602609dd4e4077d94b1a42d2ca37461c863d3eb4 |
| docs/operations/telnyx-runbooks.md | ee694c76dfdd239971a08acc286d23d3a34eac492f904d38b24820e07e691e30 |
| docs/operations/telnyx-pilot-plan.md | 2185c777ea5affaeb47be6e3dc175b575cbbb6108b1287216cb2a18232e8c4f3 |
| docs/operations/telnyx-observability.md | e7b96c470c6b12f30bfe4d7f90de8fff76cec503a625cd19e8dd88b78bfeb5f7 |
| Probes próprios test_operations_probes.py | 31738a5a3940f97d3d4450651316c2d07c0b5438b3a3d818365e1c4143cf7c16 |
| JUnit próprio final-probes/pytest.xml | 224a0960e4a95a22874a064a6a6ba11d79268ee94962579d23da94f415611eb3 |

Hashes identificam material, não comprovam infraestrutura externa nem tornam
arquivos temporários persistentes. Publicar o probe adjacente junto deste relatório
ou usar o apêndice abaixo para reprodução em clone limpo.

## Parecer separado

- **Desenvolvimento/preparação OFFLINE:** revisão concluída sem novoP1/P2 confirmado;
  candidato para auditoria final do orquestrador, mantendo limites/autorização.
- **Próximo gate externo controlado:** NO-GO até nova autorização explícita e evidência
  dos bloqueadores aplicáveis no ambiente correspondente.
- **Piloto/produção:** NO-GO; nenhum teste/documento desta revisão autoriza execução.

## Apêndice — probes próprios completos

Salvar fora do repo e executar com o runner/venv próprio como no comando acima.


```python
"""Independent operational probes; synthetic identities and real SQLite only."""

import hashlib
import json
import secrets
import sqlite3
from datetime import timedelta
from pathlib import Path
from uuid import uuid4

import pytest
from starlette.testclient import TestClient
from test_telnyx_asgi import app as app
from test_telnyx_asgi import count, post
from test_telnyx_authentication import PRIVATE_TEXT
from test_telnyx_authentication import private_key as private_key
from test_telnyx_authentication import settings as settings
from test_telnyx_messages import TIME
from test_telnyx_messages import ingress as ingress
from test_telnyx_messages import wire
from test_telnyx_submission import authorize, prepare

from rj_studio_ai.config import Settings
from rj_studio_ai.main import create_app
from rj_studio_ai.persistence import DeliveryState, PersistenceUnavailable, SqliteConversationStore

ROOT = Path(__file__).resolve().parents[1] / "repo"


def admin_client(store, *, permissions=("read", "control")):
    token = secrets.token_urlsafe(32)
    settings = Settings(
        _env_file=None,
        operator_secret_sha256=hashlib.sha256(token.encode()).hexdigest(),
        operator_id="independent-ops-review",
        operator_permissions=permissions,
        operator_conversations=("*",),
    )
    return (
        TestClient(create_app(settings, store=store)),
        {"Authorization": "Bearer " + token},
        token,
    )


def opaque_for_claim(store, path, claim):
    with sqlite3.connect(path) as db:
        inbound_id = db.execute(
            "SELECT inbound_message_id FROM outbound_deliveries d "
            "JOIN messages m ON m.id=d.outbound_message_id "
            "JOIN message_processing p ON p.inbound_message_id=m.in_reply_to_message_id "
            "WHERE d.id=?",
            (claim.delivery_id,),
        ).fetchone()[0]
    return store.automation_identifier(inbound_id)


@pytest.mark.parametrize("marker_first", [False, True])
def test_authenticated_manual_pause_without_echo_preserves_inflight_truth(ingress, marker_first):
    store, path, claim = prepare(ingress)
    if marker_first:
        assert authorize(store, claim)
    opaque = opaque_for_claim(store, path, claim)
    client, headers, token = admin_client(store)
    url = f"/admin/conversations/{opaque}/automation"
    assert client.get(url).status_code == 401
    before = client.get(url, headers=headers).json()
    assert before["paused"] is False
    operation = uuid4().hex
    response = client.post(
        url + "/pause",
        headers=headers,
        json={"operation_id": operation, "expected_revision": before["revision"]},
    )
    assert response.status_code == 200
    paused = response.json()
    assert paused["paused"] and paused["in_flight_possible"] is marker_first
    assert token not in response.text and claim.recipient_address not in response.text
    # The same request repeats its receipt, not a second side effect.
    assert (
        client.post(
            url + "/pause",
            headers=headers,
            json={"operation_id": operation, "expected_revision": before["revision"]},
        ).json()
        == paused
    )
    assert not authorize(store, claim)
    delivery = store.get_delivery(claim.delivery_id)
    if marker_first:
        assert delivery.state is DeliveryState.SENDING
        assert delivery.first_submission_at == TIME
    else:
        assert delivery.state is DeliveryState.CANCELLED
        assert delivery.first_submission_at is None


def test_unknown_is_visible_to_operator_and_is_not_expunged_or_retried(ingress):
    store, path, claim = prepare(ingress)
    assert authorize(store, claim)
    assert store.finalize_delivery(
        delivery_id=claim.delivery_id,
        owner_token=claim.owner_token,
        outcome=DeliveryState.UNKNOWN,
        safe_error_code="synthetic_ambiguous",
        now=TIME,
    )
    opaque = opaque_for_claim(store, path, claim)
    client, headers, _ = admin_client(store)
    state = client.get(f"/admin/conversations/{opaque}/automation", headers=headers).json()
    assert state["unresolved_delivery"] is True
    with pytest.raises(PersistenceUnavailable):
        store.purge_messages_older_than(TIME + timedelta(days=1))
    assert store.claim_next_delivery(now=TIME + timedelta(days=2)) is None
    current = store.get_delivery(claim.delivery_id)
    assert current.state is DeliveryState.UNKNOWN
    assert current.submission_key == claim.submission_key
    with sqlite3.connect(path) as db:
        assert db.execute("PRAGMA integrity_check").fetchone() == ("ok",)
        assert db.execute("PRAGMA foreign_key_check").fetchall() == []


@pytest.mark.parametrize("kind", ["image", "location", "unknown-future-kind"])
def test_unsupported_repeated_attempts_stay_visible_without_false_receipts(app, private_key, kind):
    payload = wire(kind)
    payload["data"]["payload"]["body"]["private_sentinel"] = PRIVATE_TEXT
    with TestClient(app) as client:
        for _ in range(6):
            response = post(client, private_key, payload)
            assert response.status_code == 422
            assert PRIVATE_TEXT not in response.text
        ready = client.get("/ready").json()
        assert ready["quarantined"] is True
        assert ready["egress"] is ready["generation"] is ready["operational_channel"] is False
        metrics = client.get("/metrics").json()
        assert metrics["responses"]["422"] == 6
        assert PRIVATE_TEXT not in json.dumps(metrics)
    assert count(app, "messages") == count(app, "inbound_event_receipts") == 0
    with app.store._connect() as db:
        observations = db.execute("SELECT observations FROM telnyx_ingress_rejections").fetchall()
        assert observations == [(6,)]
        stored = repr(db.execute("SELECT * FROM telnyx_ingress_rejections").fetchall())
        assert PRIVATE_TEXT not in stored


def test_read_only_operator_cannot_change_pause_or_revision(ingress):
    store, path, claim = prepare(ingress)
    opaque = opaque_for_claim(store, path, claim)
    client, headers, _ = admin_client(store, permissions=("read",))
    url = f"/admin/conversations/{opaque}/automation"
    before = client.get(url, headers=headers).json()
    response = client.post(
        url + "/pause",
        headers=headers,
        json={"operation_id": uuid4().hex, "expected_revision": before["revision"]},
    )
    assert response.status_code == 403
    assert client.get(url, headers=headers).json() == before


def test_retention_matrix_covers_actual_migrated_application_tables(tmp_path):
    path = tmp_path / "schema.db"
    store = SqliteConversationStore(path, telnyx_egress_quarantined=True)
    store.initialize()
    with sqlite3.connect(path) as db:
        tables = {
            row[0]
            for row in db.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
            )
        }
    document = (ROOT / "docs/operations/telnyx-retention-backups.md").read_text()
    documented = {
        line.split("|")[1].strip() for line in document.splitlines() if line.startswith("| ")
    }
    assert tables <= documented
    assert len(tables) == 24


def test_historical_pause_receipt_is_distinct_from_current_operator_state(ingress):
    store, path, claim = prepare(ingress)
    opaque = opaque_for_claim(store, path, claim)
    client, headers, _ = admin_client(store)
    url = f"/admin/conversations/{opaque}/automation"
    first = {"operation_id": uuid4().hex, "expected_revision": 0}
    pause = client.post(url + "/pause", headers=headers, json=first)
    assert pause.status_code == 200 and pause.json()["paused"] is True
    resume = client.post(
        url + "/resume",
        headers=headers,
        json={"operation_id": uuid4().hex, "expected_revision": pause.json()["revision"]},
    )
    assert resume.status_code == 200 and resume.json()["paused"] is False
    replay = client.post(url + "/pause", headers=headers, json=first)
    assert replay.json() == pause.json()  # historical receipt; no new pause effect
    current = client.get(url, headers=headers).json()
    assert current["paused"] is False
    assert current["revision"] == resume.json()["revision"]
```
