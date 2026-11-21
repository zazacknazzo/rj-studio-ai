# Revisão independente B — SQLite, concorrência e recovery

Baseline examinada: `07c1b7dc150d7eb1776b97d891cd29347adffd37`. Consulta em 20/11/2026, horário do cliente America/Sao_Paulo. Revisor B inspecionou código, migrations, testes e ADRs diretamente, antes de consultar conclusões dos demais revisores. Nenhum arquivo de produção ou teste versionado foi modificado. Toda execução usou SQLite em arquivos temporários e dados sintéticos.

## Parecer desta revisão

A serialização local de writers, ownership, revisão de pausa, lifecycle, janela e consentimento tem evidência reproduzível. Não foi confirmado P0/P1 nesse conjunto offline. Há um P2 operacional confirmado, **AUD-01**: restaurar um snapshot anterior a um envio ou disconnect faz desaparecer as evidências posteriores e pode autorizar novamente o trabalho. Isso não equivale a duplicação externa observada: não houve HTTP e a chave continua igual, mas o fence local deixou de existir.

Recomendação: **GO apenas para desenvolver e testar sender com transporte mockado**, mantendo o Telnyx fora da configuração runtime; **NO-GO para integração operacional/piloto**. O plano do sender precisa explicitar o gate de restore antes de seu aceite; restaurar e iniciar workers com saída habilitada não é uma recuperação segura. Corrigir/mitigar AUD-01 antes de habilitar qualquer saída, e resolver toolchain AUD-02 antes de rodar CI em host compartilhado. Nenhum risco do issue #11 foi encerrado.

## Execuções próprias

- Oito módulos críticos: **428 passed em 51,16 s**, sem skips/falhas, com bloqueio de conexões IPv4/IPv6 em Python. Uma primeira execução dos mesmos módulos também terminou com código zero; a contagem final e duração citadas são da execução protegida e com resumo explícito.
- Sete cenários adversariais novos, fora do repositório: **7 passed em 2,53 s**. A aprovação significa que as observações esperadas se reproduziram; três desses testes demonstram a deficiência de restore, não sua correção.
- Upgrade vazio por todas as 21 revisões: um head `0021_telnyx_submission_policy`; 22 tabelas, 29 índices, 74 triggers e uma view. `integrity_check=[('ok',)]`; `foreign_key_check=[]`; `migrations_are_current=True`.
- Conexão runtime efetiva: WAL; synchronous=2/FULL; foreign_keys=1; busy_timeout=5000 ms; recursive_triggers=0. O último valor reforça a necessidade de guards de INSERT contra REPLACE, não uma suposição de que triggers DELETE serão executadas durante replacement.

```bash
PYTHONPATH=/tmp/pre11-network-guard:/workspace/rj-studio-ai/src \
PYTHONDONTWRITEBYTECODE=1 /tmp/audit-pre11-venv/bin/python -m pytest \
  -o addopts='' -q --disable-warnings \
  tests/test_telnyx_submission.py tests/test_telnyx_submission_migration.py \
  tests/test_telnyx_lifecycle.py tests/test_telnyx_authentication.py \
  tests/test_automation_operations.py tests/test_sqlite_durability.py \
  tests/test_outbound_pause.py tests/test_generation_pause.py
```

A suíte integral pertence à evidência do auditor principal em [TEST-EVIDENCE.md](TEST-EVIDENCE.md); não foi contada uma segunda vez como execução integral deste revisor. Os caminhos `/tmp` são locais à sessão; a reprodução copiável ao final permite recriá-los em outra conta.

## Cadeia e invariantes de schema

O Alembic tem uma cadeia linear 0001→0021, sem heads concorrentes. `migrations/env.py` solicita DDL transacional por migration; `MigrationManager` usa conexão SQLAlchemy com os mesmos pragmas. A leitura estática dos scripts e os testes de interrupção não substituem teste de falha de energia do volume real.

| Revisão | Mudança e proteção relevante | Evidência/limite |
| --- | --- | --- |
| 0001 | Conversation única por provider+customer; Message por provider+message_id; direção CHECK; FK Conversation CASCADE | Não existe isolamento multiempresa; é escopo single-business |
| 0002 | Link inbound→reply e índice único parcial; backfill por histórico ordenado | Backfill histórico não prova entrega externa |
| 0003 | Processing com lease/owner/attempts e FK CASCADE; guards de estado e reply | DELETE de dados autorizado é diferente de reconciliar unknown |
| 0004 | Métricas mínimas, unicidade por attempt e CHECK de resultado | Métricas não copiam corpo; inspeção de deploy/APM pendente |
| 0005 | Recipient persistido, legado recebe vazio | Legado sem destinatário não deve ser convertido em elegível |
| 0006 | Índice para contexto limitado por Conversation/data/ID | Índice não resolve identidade entre providers |
| 0007 | Outbox uma por reply; FK RESTRICT; attempts por owner/number; transições e imutabilidade | Unknown migra conservadoramente; não vira pending |
| 0008 | Inbox durável de callbacks antecipados, correlação por provider/message | Semântica legada de falha permanece nos adapters existentes |
| 0009 | Handoff persistido e marker de submissão imutável | Janela authorization→HTTP permanece inevitável sem coordenação externa |
| 0010 | Intake limitado por Conversation/episódio e CHECKs de preferências | Cursor escalar sobrevive ao purge; não é prova de entrega |
| 0011 | Rebuild da folha intake, dia/tipo/recovery, até três perguntas | Não reconstrói tabelas ancestrais de evidência |
| 0012 | Intake pode ficar sem pergunta, CHECK ajustado | Alteração de produto histórica; auditoria não mudou comportamento |
| 0013 | Métricas opcionais allowlisted da geração | Sem body bruto de LLM no schema métrico |
| 0014 | Journal escopado e aliases únicos; shape CHECK | Sem retenção definida; aliases não são autorização de associação |
| 0015 | Rebuild da folha processing preserva triggers; pause/revision/effect receipt | Testes de rollback/recovery e concorrência executados |
| 0016 | Cancelamento só antes do marker; resultado tardio preservado | Testes das duas ordens pause/authorization e late results executados |
| 0017 | IDs opacos administrativos, CAS/replay, cutoff de resume | Não autentica por ID/owner token; recebimento antigo não é revivido |
| 0018 | Receipt inbound mantém primeira proveniência depois de purge | FK deliberadamente ausente; retenção operacional ainda pendente |
| 0019 | Status Telnyx escopado, receipt não cascata, acceptance token protege reuso de ID | Contradição delivered/read versus failed conserva conflito; não resolve manualmente |
| 0020 | Binding, effects, view de elegibilidade; reconnect não ativa; bloqueios em geração/envio | Ausência de binding é inelegível; ativação/rebinding operacional não existe |
| 0021 | UUIDv4/fingerprint, primeiro marker, evidence por attempt; consent e clock | Backfill não inventa prova histórica; bytes HTTP futuros ainda não vinculados |

`persistence.py:3208` cria cada conexão e verifica pragmas; `sqlite.py:48` aplica FULL/FK/timeout. Não há transação abrangendo LLM/HTTP. `persistence.py:1120` autoriza sob BEGIN IMMEDIATE; `telnyx_submission.py:51` reavalia os gates dentro desse writer. As instruções dinâmicas de SQL observadas compõem identificadores/expressões fixos, com valores externos passados por parâmetros.

## Integridade, replacement, purge e recovery

| Tema | Resultado observado | Limite residual |
| --- | --- | --- |
| REPLACE de outbox/attempt pelo ID ou unicidade | Guards 0021 negam; testes `test_replace_cannot_erase_telnyx_attempt_evidence`, `test_identity_and_body_sql_guards` passam | Não protege contra ator com autorização para remover schema/triggers |
| REPLACE de inbound pela unique key, ID omitido | Reprodução própria negada por FK runtime; transação e autorização original permanecem válidas | FK deve continuar ativa em toda ferramenta operacional |
| Tentativa terminal com prova retroativa | `test_historical_terminal_attempt_cannot_gain_retroactive_submission_proof` passa | Não inventar `not_submitted` em reconciliação manual |
| Histórico de attempts ausente | `test_missing_historical_attempt_fails_closed_after_migration` passa | Restore anterior à criação do histórico não é detectado: AUD-01 |
| Upgrade 0020→0021 e interrupção | Backfill, rollback, backups antes/depois e preservação de colunas anteriores executados em `test_telnyx_submission_migration.py` | Testes sintéticos de SQLite não provam backup físico/operador/criptografia |
| Purge terminal | `test_terminal_purge_cascades_attempts_and_reused_id_gets_new_submission_key` passa | Evidência de attempts pode ser removida com outbox terminal; receipt de status conserva token anterior |
| Unknown/failed/conflito | Purge automático não reconcilia nem reenfileira; FKs/seleção bloqueiam remoção insegura das dependências | Pode bloquear expurgo de um lote inteiro; runbook/retentividade CX-01 precisa decisão |
| Restart após marker/lease | Sending vencido torna-se unknown; nenhuma volta automática a pending | Resposta tardia após lease não vira prova local de acceptance; investigação necessária |
| Restore de snapshot contendo bloqueio | `test_restored_backup_retains_block_and_replay` passa | Só comprova estado presente no backup; snapshot mais antigo perde o bloqueio |
| Durabilidade | FULL+WAL+commit antes do ACK; rollback próprio reverte marker e clock | Sem simulação de perda de energia/corrupção de disco; storage persistente é obrigação de deploy |

## Matriz das corridas e falhas distribuídas

Em cada linha, a ordem inversa também importa: serialização local define quem ganhou o writer, mas não cancela efeito externo já autorizado. As referências abaixo são testes executados no conjunto de 428, salvo os de status/ingress e suíte geral que estão identificados como evidência do auditor principal.

| Estado inicial/operações | Interleavings e resultado correto | Resultado proibido/proteção | Prova e saldo |
| --- | --- | --- | --- |
| Inbound e echo, mesma Conversation | Echo primeiro suprime; inbound primeiro pode admitir e depois é suprimido | Reply depois da revisão de pausa; journal+efeito+admissão transacionais | `test_mixed_batch_suppresses_same_conversation_in_either_order`; sem garantia de echo pontual |
| Claim versus pause | Claim antes pode adquirir; pause invalida owner/revisão. Pause antes nega claim | Work posterior ao pause persistir reply | `test_pause_vs_claim_race_is_serialized`, duas ordens controladas com conexões distintas |
| LLM em execução versus pause | Pause não espera LLM, conclusão perde fence | Persistir reply/outbox da geração antiga | `test_pause_during_llm_does_not_hold_sqlite_lock_or_persist_reply`; custo já incorrido não recolhido |
| LLM versus disconnect | Bloqueio vence conclusão ou cancela outbox anterior | Reply posterior a canal bloqueado | `test_block_during_llm_has_no_writer_lock_or_reply`; janela consulta→LLM CX-34 permanece |
| Delivery claim versus lifecycle | Claim pode ganhar; lifecycle cancela se não marcado. Bloqueio primeiro impede | Nova autorização em canal inelegível | `test_writer_concurrency_has_atomic_outcomes`, competitor claim/authorize |
| Consent revocation versus authorization | Revogação ganha writer: nega. Autorização ganha: marker persiste, revogação depois não recolhe | Authorization depois de revogação já commitada | Reprodução própria `test_consent_revocation_serializes_with_authorization`, duas conexões/ordens |
| Janela expira depois de assessment | Authorization recalcula relógio e limite estrito <24h | Reusar resultado anterior como autorização | `test_exact_window_boundary`, `test_assessment_rechecks_revocation_before_authorization`; source remoto real CX-05 |
| Authorization versus HTTP futuro/pause | Pause antes nega. Marker antes deixa in_flight possível | Prometer recall/exactly-once externo | `test_pause_after_authorization_before_http_exposes_documented_residual_window`; sender ainda ausente |
| Callback antes de acceptance | Receipt fica durável sem promover entrega; acceptance correlaciona escopo/token atomicamente | Delivered sem prova de acceptance local | `test_early_out_of_order_statuses_merge_with_acceptance_after_pause` e módulos status da suíte principal |
| Callback depois de acceptance | Aplica avanço monotônico ou conflito | Downgrade delivered/read por falha contraditória | `delivery_status_events.py:116`; módulo status executado pelo auditor principal |
| Callback duplicado | Mesmo envelope é no-op; mesmo ID com campos diferentes rejeita batch | Dupla admissão/segunda finalização | Journal/event receipt unique + validação de conteúdo; módulo status principal |
| Callback contraditório | Falha+delivered/read preserva sucesso observado e status_conflict bloqueia futuro | Apagar contradição/reabrir ordering | 0019 trigger e `reconcile_statuses`; reconciliação humana CX-32 pendente |
| Crash antes do commit de authorization | Marker, primeiro marker e clock não aparecem | Marker parcial conceder retry/prova | `test_sqlite_failure_rolls_back_all_submission_evidence`, `test_commit_failure_rolls_back_and_redacts_sql_error`, rollback próprio |
| Crash após commit de ingresso | Replay deduplica por receipt e efeito, ACK perdido não readmite | Segundo processamento do mesmo input | `test_lost_ack_restart_and_replay`; não exige ACK observado pelo provedor |
| Crash após marker antes de HTTP | Conservadoramente unknown após lease, mesmo se nada saiu | Reenviar porque não foi vista resposta | `test_crash_expired_claim_is_unknown` e `test_restart_at_submission_boundaries_never_replays` |
| Resposta HTTP perdida | Unknown preserva key/marker; nenhum retry automático | Tratar timeout como não submissão | `test_unproven_or_possible_submission_never_retries`; HTTP real não testado |
| Lease vence/acceptance chega tarde | Finalização stale negada, sending expira para unknown | Owner antigo sobrescrever estado novo | `test_submission_lease_expiry_and_late_acceptance_remain_conservative` |
| Restart com unknown | Não se torna candidato, inclusive dois dias depois | Key jovem ou expirada autorizar replay | `test_generic_fake_retryable_response_after_marker_remains_unknown` |
| Restore com estado antigo | **Falha local confirmada:** estado aceito/cancelado atual desaparece; snapshot pode autorizar | Reviver trabalho bloqueado sem quarentena externa | AUD-01, três reproduções próprias abaixo; ainda sem mecanismo antirollback externo ao snapshot |

Os testes com barriers que aceitam ambos os resultados provam invariantes dos resultados observados, não exploram matematicamente todos os escalonamentos. As corridas pause/claim e pause/authorization têm testes adicionais forçando as duas ordens de commit. Nada aqui prova coordenação entre processos/volumes; o deploy aprovado é um processo por SQLite.

## AUD-01 — Restore obsoleto pode reviver autorização (P2)

**Classe:** risco operacional confirmado por reprodução local; não envio duplicado externo confirmado. **Arquivos:** `persistence.py:246` (initialize), `persistence.py:921` (claim), `persistence.py:1120` (authorization), `telnyx_submission.py:60` (clock no mesmo snapshot). **Invariante:** restauração não deve conceder permissão de reenviar trabalho que pode ter sido submetido ou cancelar bloqueio posterior sem reconciliação.

**Cenário:** snapshot em pending/sending antes do marker; na linha atual autorizar e gravar accepted, ou receber ACCOUNT_OFFBOARDED; abrir cópia antiga, chamar initialize e validar migrations. A cópia conserva active/consent/janela e perde marker/blocked, permitindo outro authorize. Com backup anterior ao claim, até o novo owner e attempt são criados legitimamente, com a chave antiga.

**Impacto:** possível reenvio/atendimento após bloqueio quando futuros workers forem ligados sobre backup antigo; o replay externo com a mesma chave pode deduplicar, mas retenção/bytes/escopo não são garantias locais suficientes. **Recomendação:** restaurar sempre em quarentena sem workers de saída; revalidar binding/consent e reconciliar todo trabalho potencialmente divergente; especificar mecanismo de epoch/fence que não dependa apenas do arquivo restaurado, ou procedimento operacional verificável equivalente. Não gerar chave nova para contornar unknown.

**Regressão proposta:** snapshots antes de claim, antes de marker e antes de disconnect/pausa; após restore, nenhum sender chamado até verificação/reconciliação autenticada. Incluir snapshot após accepted e antes de callback. **Dono/gate proposto:** engenharia de recovery/composição + operação, Tickets 11 (contrato do sender), 12–13 (habilitação); antes do aceite da integração com saída e antes de piloto. Relacionado a CX-15/CX-33/CX-35, sem encerrar ou duplicar automaticamente o registro central.

## Reprodução durável dos sete cenários independentes

Salvar o bloco Python abaixo como `/tmp/audit_pre11_security_adversarial.py`. Ele reutiliza apenas fixtures sintéticas existentes na baseline; não modifica testes versionados. Os três testes de restore aprovam quando o comportamento inseguro é observado, tornando explícito o achado. O guard pode ser recriado com um `sitecustomize.py` no primeiro diretório do PYTHONPATH que rejeite `socket.connect`, `connect_ex` e `sendto` para AF_INET/AF_INET6. Não usar credenciais ou contas reais.

```bash
PYTHONPATH=/tmp/pre11-network-guard:/workspace/rj-studio-ai/src:/workspace/rj-studio-ai/tests \
PYTHONDONTWRITEBYTECODE=1 /tmp/audit-pre11-venv/bin/python -m pytest \
  /tmp/audit_pre11_security_adversarial.py -q --disable-warnings
```

<!-- O script integral é anexado abaixo a partir do arquivo realmente executado. -->

```python
"""Independent audit probes, synthetic data, no external requests."""
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Event

import pytest
from test_telnyx_authentication import private_key as private_key
from test_telnyx_authentication import settings as settings
from test_telnyx_messages import ingress as ingress
from test_telnyx_messages import TIME, receive, wire
from test_telnyx_lifecycle import account
from test_telnyx_submission import authorize, prepare
from rj_studio_ai.persistence import DeliveryState, SqliteConversationStore


def snapshot(source, target):
    with sqlite3.connect(source) as original, sqlite3.connect(target) as backup:
        original.backup(backup)


def test_old_restore_can_reauthorize_already_accepted_work(ingress, tmp_path):
    store, path, claim = prepare(ingress)
    before = tmp_path / "before-authorization.db"
    snapshot(path, before)
    assert authorize(store, claim)
    assert store.finalize_delivery(
        delivery_id=claim.delivery_id, owner_token=claim.owner_token,
        outcome=DeliveryState.ACCEPTED, provider_message_id="synthetic-already-accepted",
        now=TIME,
    )
    restored = SqliteConversationStore(before)
    restored.initialize()
    assert restored.migrations_are_current()
    assert restored.get_delivery(claim.delivery_id).state is DeliveryState.SENDING
    assert restored.get_delivery(claim.delivery_id).first_submission_at is None
    assert authorize(restored, claim, now=TIME + timedelta(seconds=1))


def test_old_restore_loses_disconnect_and_can_authorize(ingress, private_key, tmp_path):
    store, path, claim = prepare(ingress)
    before = tmp_path / "before-disconnect.db"
    snapshot(path, before)
    receive(ingress, private_key, account())
    assert not authorize(store, claim)
    assert store.get_delivery(claim.delivery_id).state is DeliveryState.CANCELLED
    restored = SqliteConversationStore(before)
    restored.initialize()
    assert restored.migrations_are_current()
    assert authorize(restored, claim, now=TIME + timedelta(seconds=1))


def test_restore_before_claim_revives_pending_after_acceptance(ingress, tmp_path):
    from test_telnyx_delivery_status import pending
    _, store, path = ingress
    pending(store)
    before = tmp_path / "before-claim.db"
    snapshot(path, before)
    claim = store.claim_next_delivery(now=TIME)
    assert authorize(store, claim)
    assert store.finalize_delivery(
        delivery_id=claim.delivery_id, owner_token=claim.owner_token,
        outcome=DeliveryState.ACCEPTED, provider_message_id="synthetic-already-accepted",
        now=TIME,
    )
    restored = SqliteConversationStore(before)
    restored.initialize()
    new_claim = restored.claim_next_delivery(now=TIME + timedelta(seconds=1))
    assert new_claim is not None
    assert new_claim.owner_token != claim.owner_token
    assert new_claim.submission_key == claim.submission_key
    assert authorize(restored, new_claim, now=TIME + timedelta(seconds=1))


def test_replace_by_inbound_unique_key_fails_with_runtime_fk(ingress):
    store, path, claim = prepare(ingress)
    with store._connect() as connection:
        assert connection.execute("PRAGMA foreign_keys").fetchone() == (1,)
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute("""
                INSERT OR REPLACE INTO messages(conversation_id,provider,provider_message_id,
                    direction,body,recipient_address,created_at)
                SELECT conversation_id,provider,provider_message_id,direction,'changed',
                    recipient_address,created_at FROM messages WHERE direction='inbound'
            """)
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []
    assert authorize(store, claim)


@pytest.mark.parametrize("revoke_first", [True, False])
def test_consent_revocation_serializes_with_authorization(ingress, revoke_first):
    store, path, claim = prepare(ingress)
    ready, release = Event(), Event()

    def revoke():
        with store._connect() as connection:
            if revoke_first:
                connection.execute("BEGIN IMMEDIATE")
                connection.execute("UPDATE telnyx_consent SET revoked_at=?", (TIME.isoformat(),))
                ready.set()
                assert release.wait(5)
            else:
                assert ready.wait(5)
                connection.execute("BEGIN IMMEDIATE")
                connection.execute("UPDATE telnyx_consent SET revoked_at=?", (TIME.isoformat(),))

    def authorize_peer():
        other = SqliteConversationStore(path)
        if revoke_first:
            assert ready.wait(5)
        result = authorize(other, claim)
        if not revoke_first:
            ready.set()
        return result

    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(revoke)
        second = pool.submit(authorize_peer)
        if revoke_first:
            assert ready.wait(5)
            release.set()
        first.result(10)
        allowed = second.result(10)
    assert allowed is (not revoke_first)
    assert store.get_delivery(claim.delivery_id).first_submission_at == (None if revoke_first else TIME)
    assert not authorize(store, claim)


def test_rollback_removes_markers_and_clock_without_losing_claim(ingress):
    store, path, claim = prepare(ingress)
    with store._connect() as connection:
        connection.execute("BEGIN IMMEDIATE")
        connection.execute("INSERT INTO telnyx_policy_clock VALUES(1,?)", (TIME.isoformat(),))
        connection.execute("UPDATE outbound_deliveries SET submission_started_at=?,first_submission_at=?",
                           (TIME.isoformat(), TIME.isoformat()))
        connection.rollback()
    assert store.get_delivery(claim.delivery_id).first_submission_at is None
    with store._connect() as connection:
        assert connection.execute("SELECT COUNT(*) FROM telnyx_policy_clock").fetchone() == (0,)
        assert connection.execute("PRAGMA integrity_check").fetchone() == ("ok",)
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []
    assert authorize(store, claim)
```
