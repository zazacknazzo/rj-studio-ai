# Handoff — Telnyx Coexistence Ticket13

- Origin: https://github.com/zazacknazzo/rj-studio-ai.git
- Baseline aprovada: f1496be42732b7e57d317444d7ed0020997f0327.
- Branch autorizada: codex/telnyx-coexistence-13-readiness.
- Escopo: preparação, hardening, CI e testes OFFLINE; proibições na spec13.
- Escritor exclusivo: confirmado pelo usuário neste chat em22/11/2026;
  esta execução é a única escritora de Git da branch. Revisores só leitura/probes fora do repo.
- Última SHA remota verificada: CP5 988efabe39611821035663dbae24a266b71bfca5.
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
| CP6 | Runbooks16, CX29/fila, observabilidade e piloto sóplanejamento; índices/histórico alinhados | difflinks; suitesintegrais/CI988efab emexecução, NÃO chamarPASS ainda | CP5 acima |
| CP7–8 | Pendentes | Não executados | Não publicados |

## Riscos e evidências

AUD-01 aberto; laboratório não é autoridade operacional. Nenhum risco fechado.
Issue11/c13/T12 lidos. Auditoria pré11 inspecionada pelo objeto Git502bca89;
nenhuma importação/merge da branch de auditoria. Revisores independentes em leitura.
Ambiente próprio ../venv (pip26.3/pytest9.2.0), sem credenciais comerciais.
Limites de rede Python distintos de isolamento kernel; CI externa ainda não comprovada.
Não executar restore/worker/ativação/replay de envios nem trocar submission keys.

## Próxima ação exata

CP7: terminar integrais/CI/quatroreviews e cloneclean; corrigir achados; store continua quarantinado.
Fetch/status/handoff antes de retomar; publicar somente checks realmente executados.
Reproduzir com venv próprio:
`python scripts/check_telnyx_offline.py --python /isolated/venv/bin/python tests/test_telnyx_sender_integration.py`.
Não sobrescrever WIP e não usar force push. Conta nova precisa exclusividade humana.

CP2: primeiro recorte31passed6.45s. Spec independente reproduziu2falhasTTL (P2 do contrato de laboratório); corrigidos recheck dentroCAS e alias com guard. Colisão key/intent e conflito local corrigidos por inspeção. Revisor confirmou ramos pause/disconnect ainda não exercitavam transições; agora usam echo/lifecycle reais sintéticos. Probes próprios independentes reexecutados; sem ocultar tentativas.

CP5: arquivo v8original recuperado do workspace anterior; hash/provenance em tests/fixtures/historical. Não houve geração nova. SSLstdlib não confiava inicialmente no issuer local ao baixar scanner; repetido com truststore nativo, sem desativarTLS, checksum verificado. Pip-audit87entradas (86auditáveis+appskipped),0pacotescomadvisories; contagem exata conferida noJSON. Kernel isolation CI ainda não executado no momento deste commit.
