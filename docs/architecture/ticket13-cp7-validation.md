# Ticket 13 — CP7 recuperado e validado OFFLINE

22/11/2026, America/Sao_Paulo. Este checkpoint conclui somente a próxima tarefa
do handoff: integrais/CI, quatro revisões, correção de achados e clone limpo.
CP8 (relatório final A–P e atualização da issue11) permanece pendente.
**AUD-01 ABERTO; qualquer gate externo, piloto e produção continuam NO-GO.**

## Recuperação e exclusividade

O usuário confirmou nesta retomada que esta execução é a única escritora da branch.
Isso é coordenação humana, não lock distribuído. Foram lidos AGENTS, regras locais,
handoff13, spec13/ADR0021, arquitetura relevante, validação12, issue11 e seus13comentários.
Nenhuma evidência anterior foi atribuída como execução própria da nova sessão.

`git fetch origin` executado; SHA de FETCH_HEAD e consulta `git ls-remote origin`
confirmaram CP6 `995af20ff7d9e9f592a23c544f09a2407bd1b7f0`, igual ao HEAD local.
Baseline `f1496be42732b7e57d317444d7ed0020997f0327` é ancestral:7àfrente/0atrás;
local/remoto0/0, árvore limpa, sem WIP descartado. O clone tem refspec restrito aT12:
por isso o fetch da branch13 atualiza FETCH_HEAD; não se presumiu um origin/branch13
inexistente. Main somente lida: `af1c9eb862a4180ca6b9e537349e4f8abaa2bb29`.

## Testes desta retomada antes de editar

Venv próprio novo, Python3.14.7/SQLite3.50.4 macOSarm64, pip26.3/pytest9.2.0.
Os86pins foram instalados e comparados com as distribuições:0divergências.
Instalação pública separada dos testes; app instalada sem dependências/isolamento
de build. Runner sanitizado, temporários0700, guard PythonIP/DNS/filhos, sem contas
ou credenciais comerciais. Guard local não equivale a isolamento kernel.

Comando reproduzível, na raiz do repo (`T13_PYTHON` aponta para o venv próprio;
`T13_EVIDENCE` deve ser diretório novo):

```sh
"$T13_PYTHON" scripts/check_telnyx_offline.py --python "$T13_PYTHON" \
  --output "$T13_EVIDENCE" tests/test_telnyx_sender_integration.py \
  tests/test_offline_recovery.py tests/test_offline_network_guard.py \
  tests/test_telnyx_operational_readiness.py
```

**73passed/0failed/0skipped em42,74s**, antes de qualquer edição do repo.
Ruff check/format350arquivos, compileall src/tests/scripts, pip check e diff check
também passaram nesta retomada. Os resultados e hashes estão no
[JSON de evidências](ticket13-cp7-evidence.json).
Pip-audit próprio:87entradas,86auditáveis,0pacotes com advisories reportados;
app local não indexada explicitamente skipped. Gitleaks8.30.1 da árvore candidata:
3achados brutos, todos baseline inalterados; triagem estrita por arquivo/linha/regra/
hash integral passou, sem ignores. Não declarar zero hits na árvore.

## Trabalho anterior recuperado e verificado

| Evidência herdada | Verificação atual / resultado efetivamente observado |
| --- | --- |
| Integral primary | Log eJUnit2262passed/0failure/0error/0skip; pytest418,22s |
| Integral Spec | Receipt exit0, log2262passed522,38s, JUnit sem failures/errors/skips |
| Manifesto Spec |194hashes before/after idênticos, todos iguais aos objetos Git CP5 eCP6 |
| Clone limpo anterior | HEAD995af20 e status limpo conferidos; JUnit72passed/0skip, log56,02s |

O clone anterior e seus dados foram preservados. O ensaio continua sendo clone local,
não autenticação comprovada de outra conta. As integrais não foram repetidas localmente:
CP5→CP6 mudou somente docs, e a única alteração no lock deste CP7 é comentário.
Os conjuntos se sobrepõem; não somar contagens como cobertura distinta.

## Quatro revisões independentes

Relatórios anteriores tiveram seu conteúdo preservado; uma linha em branco extra
no fim do relatório Architecture foi removida após diff check. Hashes originais e
publicados constam noJSON.
Frases sobre CI ainda não executada descrevem o momento original da revisão.

| Perspectiva | Evidência e conclusão |
| --- | --- |
| [Architecture/Standards](ticket13-architecture-review.md) |18focados finais, checks próprios, PASS offline, sem novoP1/P2 confirmado |
| [Spec/External Contract original](ticket13-spec-review.md) + [conclusão desta retomada](ticket13-spec-closure-review.md) | Integral herdada verificada;13probes próprios reexecutados18,66s/0skip; PASS offline |
| [Security/Reliability](ticket13-security-reliability-review.md) |24focados finais, scans próprios e triagem; PASS offline |
| [Operational Readiness](ticket13-operations-review.md) |9probes próprios15,78s, operabilidade/retention/unsupported; sem novoP1/P2 confirmado |

A conclusão Spec resolve a indicação antiga “integral em andamento” por evidência
concluída, preservando o relatório anterior. Revisores são agentes distintos, mas
compartilham host; não se alega infraestrutura/conta independente.

P3 herdado corrigido neste CP7: comentário do lock dizia Linux3.12/3.14 verificado;
workflow seleciona somente3.12. Comentário agora aponta a esta evidência observada,
sem alterar pins. Nenhuma mudança funcional em src/tests/scripts/.github.

## CI remota observada nesta retomada

- [CP5 run44981309346](https://github.com/zazacknazzo/rj-studio-ai/actions/runs/44981309346):
  completed/success naSHA988efabe39611821035663dbae24a266b71bfca5.
- [CP6 run44981650933](https://github.com/zazacknazzo/rj-studio-ai/actions/runs/44981650933):
  completed/success naSHA995af20ff7d9e9f592a23c544f09a2407bd1b7f0.
  Log baixado e inspecionado: LinuxPython3.12.16, namespace sem interfaces externas
  nem rota defaultIPv4/IPv6, Ruff/format/compile/pip check/diff, pytest
  **2262passed/0skip em224,28s**. Audit e scans são etapas anteriores ao namespace.

Aviso `sudo: unable to resolve host` dentro do namespace aparece no log; isolamento
foi confirmado e o job terminou success. Nenhuma validação Linux3.14 é alegada.
O novo push deCP7 dispara outro run; consultar a SHA publicada no GitHub e observar
seu resultado antes de iniciarCP8. Não prever aSHA do próprio commit neste documento.

## Falhas e limitações preservadas

Primeiro fetch no sandbox falhou porDNS; repetição com acesso autorizado concluiu.
Uma tentativa de instalar a app antes de terminar a instalação dos pins falhou com
`Cannot import hatchling.build`; após concluir os pins, repetição offline passou.
Warning do cachepip read-only não foi erro de dependência. Nenhuma dessas tentativas
foi rotulada PASS. Diff check staged apontou a linha em branco extra no relatório
Architecture; removida antes do commit. Relatórios herdados conservam falhas anteriores
e suas correções.

O store permanece quarantinado e o laboratório apenas diagnostica simulation_ready;
não concede operational_egress. AUD01, CX01–37 e AUD/AR conservam seus gates abertos
(CX31 mantém somente o aceite offline histórico). Nenhum risco encerrado ou exceção
aceita. Autoridade/witness/ledger/IAM/consentimento/conta/rede real seguem sem prova
operacional. Não houve TelnyxHTTP real, ativação, egress, piloto, merge/main, Baileys
ou mudança de inteligênciaV1. A issue11 foi somente lida nesta tarefaCP7.

## Próxima ação exata

Após o push normal, conferir aSHA com `git ls-remote origin
refs/heads/codex/telnyx-coexistence-13-readiness` e observar aCI dessaSHA.
Se verde, próximo trabalho é **somente CP8: relatório A–P e registro na issue11**,
preservando todos os gates e solicitando auditoria final do orquestrador.
