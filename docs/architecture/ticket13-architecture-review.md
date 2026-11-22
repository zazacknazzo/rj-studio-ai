# Ticket 13 — Architecture / Standards Review independente

Data: 22/11/2026, America/Sao_Paulo. Revisor: architecture_review.
Escopo estritamente OFFLINE; nenhuma edição do repositório, commit ou push pelo revisor.
Somente probes e evidência em diretório separado. Sem credenciais reais ou provider HTTP.

**Parecer:** PASS de revisão no escopo do candidato offline inspecionado, sem novo
P1/P2 pendente confirmado. AUD-01 permanece ABERTO. Próximo gate externo, piloto e
produção continuam NO-GO; esta revisão não substitui a auditoria do orquestrador.

## Identidade do candidato e leitura direta

HEAD conferido: `995af20ff7d9e9f592a23c544f09a2407bd1b7f0`, branch
`codex/telnyx-coexistence-13-readiness`, árvore limpa no início e após os checks.
Baseline T12: `f1496be42732b7e57d317444d7ed0020997f0327`.
Comparei CP5 `988efabe39611821035663dbae24a266b71bfca5` com CP6:
nenhuma mudança em src/tests/scripts/requirements/.github entre essas SHAs.
No diff contra T12, o único fonte novo em src é offline_recovery.py; nenhum arquivo
de bridges/Baileys foi alterado. Busca de consumidores encontra a classe somente em
seu próprio módulo, sem importação/montagem pelo main/config/runtime.

Li AGENTS, specs06–12/ADRs0014–0020 e a auditoria pré11 em
`502bca89e64b45e981ad9c5f2eeb189aad3dd9e6`, depois spec13/ADR0021, recovery,
fixtures/testes, workflow/lock/scripts e os documentos de gates, segurança/consent,
retenção, observabilidade, runbooks e plano de piloto. Relatórios históricos foram
inspecionados; não são contados como execução própria atual.

Hashes SHA256 conferidos no candidato:

| Arquivo | SHA256 |
| --- | --- |
| src/rj_studio_ai/offline_recovery.py | `6d50cfc82a436320c7310185f0f6070347c0e42599876bb7ebef7b76f5166a9c` |
| tests/offline_recovery_fixture.py | `cf9850f15716475e55ca7608602609dd4e4077d94b1a42d2ca37461c863d3eb4` |
| tests/test_offline_recovery.py | `e6dca64cdc4eab7c68ed34ffd822b4c5cdea6e988df46029a5b591127f7807c3` |
| requirements/ci.lock | `38442a4f79b797bcbb1148ec29e004ee49b8196bcd43a6a6f8bddbde5c49e051` |
| .github/workflows/telnyx-offline.yml | `27c3d9d41f0f44221c55b8a0af055304a719ac3e8cf9125c3c564c6f9ce186cd` |
| tests/fixtures/historical/live-record-v8.json | `3d849ff3465d44cf20898aa170e72c08cc99b12e2f1b3266324754818291451e` |

## Conclusões arquiteturais

O laboratório mantém a fronteira correta: constructor exige store quarantinado,
simulation_ready é diagnóstico e operational_egress é sempre false. Não recebe
transport/callback nem cria endpoint/CLI/worker. A liberação simulada não altera
a autorização real do store.

Epoch por begin, revisão CAS por mutação e witness com revisão+digest impedem o
snapshot local de representar frescor. A fake authority ancora a mutação no witness
antes do próprio commit; commit parcial deixa o witness adiante e fecha a linha antiga.
Inventário externo não desaparece por ausência no snapshot, a identidade lógica
independe do ID SQLite, e colisões de chave/bytes são negadas. Unknown e conflict não
viram retryable. Toda entrega pré-recovery continua bloqueada, inclusive após prova
accepted/not_submitted; não há mecanismo de trocar chave para repetir trabalho antigo.

A própria reserva revalida proofs/TTL/completude dentro da mutação CAS, cobrindo a
corrida entre uma consulta readiness e a tentativa seguinte. Roles e aprovação por
ator distinto são ensaiados em SQLite separado; autenticação real, integridade de
respostas e independência/durabilidade das raízes permanecem requisitos externos.

O store genérico legado continua mais permissivo por compatibilidade e ainda pode
reproduzir o achado original fora da composição fechada. O código e ADR dizem isso
explicitamente. Não interpretei o novo laboratório como correção da integração
operacional ausente. Rollback conjunto de todas as raízes e integração futura de cada
writer/transport continuam gates de AUD-01.

Runbooks cobrem pausa antes do atendimento humano, leitura do estado atual após
receipt histórico, unknown/conflict, banco/webhook, restore, rotação, kill e rollback
sem apagar filas/keys nem restaurar autorização antiga. Retenção distingue conteúdo
de tombstones/fences, cobre as24tabelas e backups, e não ativa expurgo novo nem afirma
conformidade LGPD. Consentimento/template/operador móvel/fila humana são lacunas
declaradas, sem presumir que fixtures ou referências opacas provam operação real.
Plano de piloto exige duas autorizações futuras, conta secundária e participantes
consentidos, limites/rollback/parada; não executei qualquer passo comercial.

## Evidência realmente executada por este revisor

Host macOS arm64, CPython3.14.7, SQLite3.50.4, pytest9.2.0; venv separado do repo.
O runner sanitiza credenciais, cria temp/basetemp0700 e aplica guard IP/DNS Python.
Nenhuma conexão de provider foi feita. Isto não é kernel network namespace neste host.

| Execução própria | Resultado |
| --- | --- |
| Baseline: test_telnyx_asgi_egress.py + test_telnyx_request.py sob guard | 47 passed,7.76s |
| Primeiro conjunto de4probes CP2, já depois das correções concorrentes do primary | 4 passed,2.31s |
| Conjunto expandido CP2 | 5 passed/1 failed,3.48s: erro do probe, explicado abaixo |
| Mesmos6probes com expectativa de exceção correta | 6 passed,2.65s |
| Candidato995af20:6probes próprios +9guard +2corridas consent +v8 | **18 passed/0skip,14.95s** |
| Ruff check e format --check | PASS;350arquivos formatados |
| pip check e git diff --check | PASS |
| Comparação de86pins do lock com distribuições instaladas | 0mismatches;87distribuições incluindo app |
| SHA256 + cmp da fixture v8 contra arquivo original recuperado | Hash igual;cmp exit0 |

Na inspeção inicial identifiquei dois candidatos: colisão de submission_key entre
intents no merge e reserva sem rechecagem de TTL no adapter. O primary os corrigiu
antes da minha primeira execução própria. Não afirmo ter reproduzido dinamicamente
a versão antiga. Os probes independentes confirmam os negativos corrigidos.
O alias reserve_simulated_submission atualmente delega a record_possible_submission;
não há mais o desvio de readiness observado na primeira leitura.

A falha do conjunto expandido era minha expectativa de RecoveryClosed numa chamada
DIRETA à fake authority; nesse nível o erro injetado é OSError. O wrapper da sessão
é que redige/converte para RecoveryClosed. Corrigi somente esse probe fora do repo;
a mesma verificação agora confirma que a mutação da autoridade não comita.

O original histórico v8 foi comparado diretamente com
`work/evals/openai-agentic-surface-smoke-2026-10-04-01/phase-A.json` no workspace
anterior. É a mesma sequência de bytes; o teste do candidato carrega schema8 e passa
sem skip. Isso prova compatibilidade de leitura daquele artefato histórico, não
geração/modelo/preço/latência atuais. Nenhum LLM foi chamado.

Inspecionei CI: actions por SHA, permissões read-only, checkout sem credenciais
persistidas, instalação/audit/downloads antes de unshare, checks dentro do namespace,
guard Python complementar, pin de86versões e Gitleaks com checksum/triagem estrita de
três arquivos baseline imutáveis. Não executei o workflow Linux, pip-audit ou Gitleaks
nesta revisão; resultados desses serviços pertencem à evidência do executor responsável.
A resolução é pin de versões, não hash-lock universal de wheels.

Observação documental P3 enviada ao primary: comentário inicial do lock diz
“Linux3.12/3.14 CI verified separately”, mas o YAML seleciona3.12 e a documentação
corretamente condiciona validação ao workflow observado. Na entrega, declarar apenas
versões/SHAs de runs realmente observados; não inferir Python3.14Linux dessa frase.

## Reprodução dos probes próprios

Salvar o bloco abaixo como arquivo de teste fora do repo. Na raiz do candidato:

```bash
/path/to/venv/bin/python scripts/check_telnyx_offline.py \
  --python /path/to/venv/bin/python --output /new/private/evidence \
  /absolute/path/test_architecture_probes.py \
  tests/test_offline_network_guard.py tests/test_telnyx_operational_readiness.py \
  tests/test_commercial_steering.py::test_historical_v8_record_remains_loadable
```

Os imports usam apenas fixtures sintéticas versionadas. As contagens se sobrepõem
às demais revisões/suítes e não devem ser somadas como cobertura distinta.

```python
"""Independent architecture probes; synthetic adapters and actual SQLite only."""

from uuid import uuid4

import pytest
from offline_recovery_fixture import RESOURCE
from test_offline_recovery import lab as lab
from test_offline_recovery import release_lab
from test_telnyx_authentication import private_key as private_key
from test_telnyx_authentication import settings as settings
from test_telnyx_messages import ingress as ingress

from rj_studio_ai.offline_recovery import InventoryItem, RecoveryClosed


def test_import_cannot_assign_one_key_to_two_logical_intents(lab):
    make, authority, _, _, claim, _ = lab
    authority.begin(
        RESOURCE,
        "independent-external-only-import",
        authority.tokens["recoverer"],
        expected_revision=0,
        session_id="external-prior-session",
        snapshot_digest="prior-snapshot",
        inventory=(InventoryItem("external-only-logical-intent", claim.submission_key, None),),
    )
    with pytest.raises(RecoveryClosed):
        make().begin(authority.tokens["recoverer"])


def test_authority_itself_rejects_reserve_after_proof_expiry(lab):
    release_lab(lab)
    _, authority, _, _, _, _ = lab
    current = authority.state()
    authority.now += 60
    with pytest.raises(ValueError):
        authority.reserve(
            RESOURCE,
            "independent-expiry-check",
            authority.tokens["application"],
            expected_revision=current.revision,
            session_id=current.session_id,
            item=InventoryItem("independent-expired-intent", str(uuid4()), "bound-bytes"),
        )


def test_expiry_between_readiness_and_reserve_denies(lab, monkeypatch):
    session = release_lab(lab)
    _, authority, _, _, _, _ = lab
    original_reserve = authority.reserve

    def expiry_before_reserve(*args, **kwargs):
        authority.now += 60
        return original_reserve(*args, **kwargs)

    monkeypatch.setattr(authority, "reserve", expiry_before_reserve)
    with pytest.raises(RecoveryClosed):
        session.record_possible_submission(
            InventoryItem("independent-toctou-intent", str(uuid4()), "bound-bytes")
        )
    assert not session.readiness()["simulation_ready"]


def test_no_transport_or_store_authority_is_granted_by_release(lab):
    session = release_lab(lab)
    _, _, _, _, claim, _ = lab
    assert session.readiness()["operational_egress"] is False
    assert not hasattr(session, "sender")
    assert not session._store.authorize_delivery_submission(
        delivery_id=claim.delivery_id,
        owner_token=claim.owner_token,
    )


def test_reserve_crash_after_witness_latches_all_sessions_closed(lab):
    session = release_lab(lab)
    make, authority, _, _, _, _ = lab
    authority.fail_commit = True
    with pytest.raises(RecoveryClosed):
        session.record_possible_submission(
            InventoryItem("independent-crash-intent", str(uuid4()), "bound-bytes")
        )
    assert not session.readiness()["simulation_ready"]
    with pytest.raises(RecoveryClosed):
        make().begin(authority.tokens["recoverer"])


def test_witness_failure_prevents_authority_mutation_commit(lab):
    session = release_lab(lab)
    _, authority, witness, _, _, _ = lab
    before = authority.state()
    witness.fail_next = True
    with pytest.raises(OSError):
        authority.revoke(
            RESOURCE,
            "independent-witness-failure",
            authority.tokens["security"],
            expected_revision=before.revision,
        )
    assert authority.state() == before
```
