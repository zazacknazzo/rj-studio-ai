# Handoff — Telnyx Coexistence Ticket13

- Origin: https://github.com/zazacknazzo/rj-studio-ai.git
- Baseline aprovada: f1496be42732b7e57d317444d7ed0020997f0327.
- Branch autorizada: codex/telnyx-coexistence-13-readiness.
- Escopo: preparação, hardening, CI e testes OFFLINE; proibições na spec13.
- Escritor exclusivo: reconfirmado pelo usuário na retomada de22/11/2026,
  chat01a2015d-cb63-7060-a5cf-49e361bf3739; esta execução é a única escritora
  de Git da branch. Revisores só leitura/probes fora do repo. Nova retomada exige
  exclusividade humana vigente; esta linha não é lock distribuído.
- Última SHA remota verificada antes deste checkpoint: CP6
  995af20ff7d9e9f592a23c544f09a2407bd1b7f0. Consultar origin após publicarCP7.
- Main observado: af1c9eb862a4180ca6b9e537349e4f8abaa2bb29.
- Clone separado preserva todos os worktrees/WIP anteriores, incluindo Baileys.

## Checkpoints

| CP | Concluído / WIP / pendente | Testes executados / falhas | Remoto verificado |
| --- | --- | --- | --- |
| CP0 | Spec/ADR/handoff preparados antes de implementação | baseline sender integration20passed8.87s; Python3.14.7/SQLite3.50.4; guardIP; spec/diff | baseline acima |
| CP1 | Matriz completa CX01–37/AUD01–06/AR01–03; nenhum checkbox alterado | IDs conferidos contra snapshot da issue/auditoria; diff check | CP0 acima |
| CP2 | Lab recovery com authority+witness externos simulados/SQLite, sempre sem egress | 63passed12.01s recovery+ASGI; probes contratos/arquitetura37passed8.26s; Ruff/diff; P2 TTL corrigido | CP1 acima |
| CP3 | Segregação/segurança/consentimento especificados; corrida revoke→authorize realSQLite | 222passed9.40s (race2/policy/admin), Ruff/diff | CP2 acima |
| CP4 | Matriz24tabelas+authority/witness/backups/evidências; sem novo purge | 160passed16.94s retention/replay/migrations/adversarial; diff | CP3 acima |
| CP5 | CI/lock86, guardDNS/children, v8original, carga com falha; CIremota a observar | 13passed5.27s (cargas3/guard9/v8); 106passed10.65s recorte anterior; Ruff346/compile/pipcheck/audit87/0advisories; Gitleaks3baseline | CP4 acima |
| CP6 | Runbooks16, CX29/fila, observabilidade e piloto sóplanejamento; índices/histórico alinhados | Integrais anteriores concluídas2262PASS/0skip; CI988efab e995af20 success, observadas na retomada | CP6 acima |
| CP7 | Recuperação, quatro reviews concluídos, evidência persistida; P3comentário lock corrigido sem alterar pins; clone limpo preservado | Retomada73PASS42.74s antes de editar; Spec13PASS18.66s; Ruff/format/compile/pipcheck/audit/diff; detalhes no relatórioCP7 | CP6 acima; consultar origin após pushCP7 e observar run da novaSHA |
| CP8 | Pendente: relatório final A–P e issue11 | Não iniciado nesta retomada | Não publicado |

## Riscos e evidências

AUD-01 aberto; laboratório não é autoridade operacional. Nenhum risco fechado.
Issue11/c13/T12 lidos. Auditoria pré11 inspecionada pelo objeto Git502bca89;
nenhuma importação/merge da branch de auditoria. Revisores independentes em leitura.
Ambiente próprio ../venv (pip26.3/pytest9.2.0), sem credenciais comerciais.
Limites de rede Python distintos de isolamento kernel; CI externa ainda não comprovada.
Não executar restore/worker/ativação/replay de envios nem trocar submission keys.

## Próxima ação exata

Confirmar pushCP7 com `git ls-remote origin refs/heads/codex/telnyx-coexistence-13-readiness`.
Observar aCI dessaSHA: `gh run list --repo zazacknazzo/rj-studio-ai --branch codex/telnyx-coexistence-13-readiness --limit 3`;
selecionar run cujo headSha coincide com aSHA remota e ler seu resultado/log.
Se verde, próxima tarefa é SOMENTE CP8: relatório final A–P e registro na issue11,
seguido de parada e solicitação de auditoria do orquestrador. CP8 não foi iniciado.
Store continua quarantinado. Fetch/status/handoff antes de nova retomada;
reproduzir focal com venv próprio:
`python scripts/check_telnyx_offline.py --python /isolated/venv/bin/python tests/test_telnyx_sender_integration.py`.
Não sobrescrever WIP e não usar force push. Nova execução precisa exclusividade humana.

CP2: primeiro recorte31passed6.45s. Spec independente reproduziu2falhasTTL (P2 do contrato de laboratório); corrigidos recheck dentroCAS e alias com guard. Colisão key/intent e conflito local corrigidos por inspeção. Revisor confirmou ramos pause/disconnect ainda não exercitavam transições; agora usam echo/lifecycle reais sintéticos. Probes próprios independentes reexecutados; sem ocultar tentativas.

CP5: arquivo v8original recuperado do workspace anterior; hash/provenance em tests/fixtures/historical. Não houve geração nova. SSLstdlib não confiava inicialmente no issuer local ao baixar scanner; repetido com truststore nativo, sem desativarTLS, checksum verificado. Pip-audit87entradas (86auditáveis+appskipped),0pacotescomadvisories; contagem exata conferida noJSON. Kernel isolation CI ainda não executado no momento deste commit.

## Retomada CP7 —22/11/2026

Checkpoint recuperado995af20: fetch/ls-remote/ancestry/status conferidos;
baseline7àfrente/0atrás, local/remoto0/0, árvore limpa. Refspec limitadoT12:
fetch da branch13 usa FETCH_HEAD, sem pressupor remote-tracking ref inexistente.
Todos os workspaces anteriores preservados. Venv próprio da retomada em
`retomar-ticket-13-rj-studio-ai/work/venv`,86pins exatos,Python3.14.7/SQLite3.50.4.
Focal73passed42.74s antes de editar; guardPython, não namespace local.
Integrais herdadas primary2262passed418.22s eSpec2262passed522.38s,0skips,
JUnit/log/receipt inspecionados;194hashes Spec idênticosCP5/CP6. Não reexecutadas
localmente nesta retomada. Clone anterior limpo995af20,72passed56.02s herdados.
CI44981309346(CP5)/44981650933(CP6)success; logCP6 Linux3.12.16,
isolamento kernel confirmado,2262passed224.28s/0skip.
Quatro revisões preservadas em docs/architecture/ticket13-*-review.md;
Spec concluída por adendo independente13probesPASS18.66s. Nenhum novoP1/P2 confirmado.
P3comentário Linux3.14 removido do lock;86pins inalterados. Fonte/testes/CI inalterados.
Falhas: fetchsandboxDNS, repetido com acesso autorizado; instalação app prematura
sem hatchling, repetida offline após terminar pins. Não rotuladas comoPASS.
Detalhes: [validaçãoCP7](../architecture/ticket13-cp7-validation.md) eJSON vinculado.
AUD01 e gates permanecem abertos; issue11 somente lida; nenhuma exceção aceita.
