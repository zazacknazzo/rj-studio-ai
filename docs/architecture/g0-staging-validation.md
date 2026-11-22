# Sprint G0 — Lívia E2E sintético e preparação Telnyx

22/11/2026, America/Sao_Paulo. **Staging sintético: executado. Ingresso real:
NO-GO. Saída real: NO-GO. AUD-01/AR-02 ABERTOS. Auditoria externa G0 pendente.**

## Baseline, escopo e isolamento

Repositório: `zazacknazzo/rj-studio-ai`. Baseline T13 exata, fetch/origin
conferidos: `392637c95e8b4143054ae539e71f6f903559c742`.
Branch nova: `codex/telnyx-g0-smoke-staging`; clone separado, escritor único
designado pela instrução G0. Main observada `af1c9eb862a4180ca6b9e537349e4f8abaa2bb29`.
CP0 remoto `9c98f39a686dd82d05c0c22b1a14f31401a7b082`; CP1 remoto
`4f59e2570d4de5278139a4d5e924a009f07c1c8c` efetivamente consultados após push.
SHA final será consultada após commit/push, sem antecipar o próprio hash, e
registrada na entrega/issue #11 junto à CI cuja head_sha corresponda exatamente.

AGENTS/regras locais, relatório final T13, handoff e issue #11/auditoria final
foram lidos. A autorização humana G0 amplia somente o trabalho sintético;
não revoga NO-GO operacional do T13. Nenhum risco da issue #11 foi encerrado.
Sem merge, force push, alteração de Baileys, runtime principal ou inteligência V1.

## O que foi composto

O [harness](../../tests/g0_staging_fixture.py) e os
[cenários](../../tests/test_g0_staging_smoke.py) reutilizam as peças existentes,
sem nova arquitetura de mensageria:

```text
envelope sintético assinado com chave efêmera
  → ASGI real /webhooks/telnyx, TestClient sem listener de rede
  → autenticação Ed25519 e normalização reais
  → SQLite/migrations/receipt/dedupe e ACK após commit reais
  → ProcessingRunner + MessageResponder + ConversationContextBuilder reais
  → LLMDecision programada (FIXTURE, nenhum modelo chamado)
  → grounding/persona/intake/handoff e persistência reais
  → claim + gates de autorização + request/markers/MAC reais
  → TelnyxWhatsAppSender com callable fake fixo
  → acceptance fake → webhooks de status assinados sintéticos
  → ledger e histórico reais atualizados
```

A factory ASGI continua quarantinada, sem worker/sender em background e com
readiness generation/egress/operational_channel falsos. Para exercitar autorização
positiva, o harness cria **outro handle do store genérico legado**, com signer,
para o MESMO banco sintético privado e exchange fake fixo. Isso é a seam de teste
histórica T10/T11, **não integração de recovery/autoridade externa nem release
operacional**. Não há flag, opção de transporte real ou configuração de produção.
AR-02 continua aberto; não copiar esse handle para um deploy.

O CLI aceita somente Python do venv e diretório de evidência novo. Cria um filho
via runner T13 com ambiente allowlisted, HOME temporário 0700, sem `.env`, secrets
ou credenciais herdadas. Guard intercepta IPv4/IPv6/DNS e filhos; o harness verifica
interceptação efetiva. macOS não tem namespace kernel nesta execução; CI Linux usa
`unshare --net`. Nenhuma chamada a LLM/API comercial, listener público ou conta.

## Aplicação executada versus fixtures

| Camada | Natureza / evidência | Limite |
| --- | --- | --- |
| Autenticação, normalização e HTTP | Código real; negativos e bytes assinados pela fixture | Não valida chave/proxy/TLS da conta real |
| Persistência/processamento | SQLite real, migrations reais, claims/markers/receipt/histórico reais | Não valida durabilidade/latência do deploy |
| Geração | LLMDecision validada mas SCRIPTADA; `trusted_reply` não é usado para os diálogos | Nenhuma inferência, token, custo, qualidade ou naturalidade atuais medidos |
| Resposta final | Grounding/persona/appointment intake/handoff reais renderizam a proposta; prosa livre “agendei/R$999” é excluída | Wording parte de catálogo/fatos de teste, não resposta de modelo real |
| Salon Knowledge | YAML aprovado apenas dentro da fixture, marcado `[DADO SINTÉTICO]` | Não publica informações, horário ou preço verdadeiro do salão |
| Canal/consentimento | Inserções SQL explícitas de active/opt-in e revoke | Sem elegibilidade, opt-in ou API de revogação operacionais |
| Outbound | Autorização/request determinístico/Idempotency-Key/MAC/markers reais, antes do fake e fora de transação | Nenhum socket comercial ou credencial de outbound |
| Acceptance/status | Conteúdo do provider fake e envelopes sintéticos assinados; parser/ledger reais | Não há entrega em aparelho nem conta WhatsApp |
| Recovery | Snapshot SQLite antigo real, fonte externa T13 simulada nos focais | AUD-01 reproduzido no legado; não resolvido |

## Fluxos que passaram e o que demonstram

| Cenário | Resultado observado |
| --- | --- |
| Saudação | `Oi!` renderizado e persistido; request exato→fake accepted→delivered→read |
| Informações do salão | Fato de horário SINTÉTICO selecionado e renderizado sem aceitar prosa livre; fake read |
| Interesse em progressiva | Fato de serviço SINTÉTICO pelo grounding; fake read |
| Pedido de preço | Política de preço SINTÉTICA de avaliação; sem aceitar valor inventado R$999; fake read |
| Agendamento | Preferências declaradas→Appointment Interest Intake→Human Handoff; sem reserva nem consulta de agenda; fake read e próxima Message suprimida |
| Atendimento humano | Confirmação trusted e handoff durável; fake read e automação futura suprimida |
| Conversa de três turnos | Saudação→progressiva→preço, três fake delivered; contextos seguintes contêm somente assistant speech após Provider Acceptance |
| Revogação | Revoke SQL sintético após geração nega autorização, sem marker/request/transporte; não implica interpretar opt-out textual |
| Opt-out textual | Probe confirma que o texto isolado não persiste revogação; trabalho não é processado/enviado nesse probe; lacuna operacional preservada |
| Mensagem repetida | Mesmo envelope não duplica Message, geração, request ou envio, inclusive após restart |
| Pausa durante processamento | Echo humano sintético assinado commita pausa enquanto generator fixture está bloqueado; nenhuma AIReply/outbox/transporte persiste |
| Timeout de LLM | Exceção fixture aciona fallback seguro da aplicação/handoff; fake delivered, sem afirmar geração de modelo |
| Timeout/acceptance ambígua do provider | Uma tentativa fake→unknown; chave preservada, sem retry após restart ou 2 dias; bloqueia processamento seguinte |
| Desconexão/reconexão | Pending é cancelado; reconnect fica verification_required, sem reativar trabalho antigo; inbound novo suprimido |
| Restore obsoleto | Snapshot anterior à submissão não tem consentimento revogado/disconnect atuais; ASGI quarantinada nega; store legado autoriza localmente, sem nova chamada fake: reprodução explícita de AUD-01/AR-02 |
| Negativos adicionais | Sem consentimento, janela vencida, quarentena, request adulterado e assinatura inválida não chegam ao fake; guard ausente/flag forjada rejeitados antes de uso |
| Ingresso isolado | ACK/persistência, zero chamadas de generator/transporte/outbox; nenhuma thread de processamento de background |

Há seis variações do fluxo completo até fake read, uma conversa de três turnos
até fake delivered e cenários de bloqueio/falha. **22 cenários não significam 22
conversas completas entregues**. Acceptance é distinto de delivered/read.
Latências do pytest são tempos de testes locais; não são SLA E2E ou custo de LLM.

## Testes e evidência

Ambiente próprio: Python 3.14.7/SQLite 3.50.4, lock T13 (86 pins), pip 26.3,
pytest 9.2.0/Ruff 0.17.6. Instalação de ferramentas públicas precedeu o guard;
nenhuma dependência foi alterada. Resultados próprios G0, sobrepostos e não somáveis:

| Execução | Resultado |
| --- | --- |
| Baseline sender integration antes de editar |20 PASS/0 SKIP,8.95s |
| Primeira demo |7 FAIL/15 PASS/0 SKIP,5.41s; falhas preservadas abaixo |
| Demo corrigida |22 PASS/0 SKIP,4.29s; JSON 22 cenários |
| Focal G0+sender integration+ASGI egress+offline recovery+operational readiness+network guard |118 PASS/0 SKIP,13.67s |
| Integral local | **2286 PASS/0 SKIP,165.26s**; mesmos source/testes de CP1, sem atribuir execução T13 ao G0 |
| CI CP1 | **2286 PASS/0 SKIP, 269.17 s**, completed/success; [run45030731388](https://github.com/zazacknazzo/rj-studio-ai/actions/runs/45030731388), head_sha exata `4f59e2570d4de5278139a4d5e924a009f07c1c8c`; Linux Python 3.12.16, namespace sem rede |

Ruff/check/format/compileall/pipcheck/diff executados; links locais conferidos.
Gitleaks árvore CP1: **3 achados brutos históricos, triagem versionada PASS**;
não zero achados na árvore. Nenhum novo ignore/allowlist. Range G0 até CP1:
2 commits, zero achados. Checks finais Ruff/format 366/compileall/pipcheck/diff e
links locais PASS. Não houve consulta
pip-audit local nova; no log CP1 a consulta pública da CI informou zero
vulnerabilidades conhecidas, e o scanner confirmou os mesmos 3 achados históricos.
O log confirmou `Kernel network isolation verified: only loopback, no IPv4/IPv6
default routes`; instalação/advisories ocorreram antes desse isolamento.

[Evidência estruturada](g0-staging-evidence.json) registra comandos exatos,
contagens/tempos/hashes JUnit e hashes dos source/testes executados. JUnit da
integral:2286 testes/0 errors/0 failures/0 skips, 165.197 s; SHA256
`03152db378411b2459e2e4bdafb2dfd6deb1e7c94eeb3f333f1ab9ffd6cfe028`.
As contagens se sobrepõem e não devem ser somadas. A CI final será conferida
na SHA publicada; resultado CP1 não será atribuído à SHA documental posterior.

Falhas: Ruff inicial encontrou 3 linhas longas (formatter corrigiu); primeira demo
esperava Olá, mas catálogo real renderiza Oi; construtor exigia submission_key
keyword-only; relógio truncado podia preceder next_attempt_at criado durante
processamento. Corrigidos apenas harness/assert de catálogo/chamada/relógio,
mantendo gates reais e asserts de autorização/histórico/unknown/restore. Não
classificar a primeira execução como PASS. Nenhuma alteração em src foi necessária.

## Demonstração reproduzível

Em clone da branch G0, após instalar o toolchain público; não carregar `.env` ou
qualquer credencial comercial. Diretório de output precisa ser novo a cada run.

```sh
python3 -m venv ../g0-venv
../g0-venv/bin/python -m pip install --no-deps -r requirements/ci.lock
../g0-venv/bin/python -m pip install --no-deps --no-build-isolation -e .
../g0-venv/bin/python scripts/run_g0_staging_smoke.py \
  --python ../g0-venv/bin/python --output ../g0-evidence-new
```

O comando executa 22 cenários com guard, produz `pytest.xml` e `g0-report.json`
com transcrições sintéticas e atribuição de fixtures em cada cenário. Não abre
servidor. Sem o guard efetivo, o harness falha fechado. O runtime principal não
é configurado para Telnyx. Para repetir o focal executado:

```sh
../g0-venv/bin/python scripts/check_telnyx_offline.py \
  --python ../g0-venv/bin/python --output ../g0-focused-new \
  tests/test_g0_staging_smoke.py tests/test_g0_staging_guard.py \
  tests/test_telnyx_sender_integration.py tests/test_telnyx_asgi_egress.py \
  tests/test_offline_recovery.py tests/test_telnyx_operational_readiness.py \
  tests/test_offline_network_guard.py
```

## Readiness, riscos e próximo gate

[Checklist R01–R20 e dois pareceres](../operations/telnyx-g0-readiness.md): ingresso
real **NO-GO** até auditoria e comprovação de deploy receive-only/conta/binding/
chave/TLS/operador/retenção; saída real **NO-GO** também por AUD-01/AR-02, autoridade
externa/ledger/egress de restore e rollback, consentimento atual/captura de opt-out,
active, aprovação e kill switch operacionais ausentes. Não inferir elegibilidade +55.

[Primeiro teste real](../operations/telnyx-g0-first-real-test.md): procedimento
preparado, NÃO EXECUTADO. Os dois pareceres são avaliações separadas de gates
pelo implementador; não são duas auditorias de autores independentes. Solicita-se
auditoria independente antes de qualquer conexão real; ela não foi simulada.

Outros gates T13 preservados: CX-01/02/04/06/07/08/09/10/11/15/16/17/19/20/21/
24/25/26/29/30/32/33/35/36. Sem prova de número/canal, UI/operador, retenção
implantada, antirollback, custo ou conversação de modelo real. Não há nova flag
de bypass, integração comercial, merge ou envio. [Handoff G0](../handoffs/G0.md).
