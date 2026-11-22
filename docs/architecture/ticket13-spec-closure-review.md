# Ticket 13 — conclusão independente da revisão Spec/External Contract (CP7)

22/11/2026, America/Sao_Paulo. Revisor desta retomada: `/root/close_spec_review`.
Baseline T12: `f1496be42732b7e57d317444d7ed0020997f0327`.
Candidato funcional/CI CP5: `988efabe39611821035663dbae24a266b71bfca5`.
Candidato documental CP6: `995af20ff7d9e9f592a23c544f09a2407bd1b7f0`.

**PASS para concluir a revisão Spec no escopo OFFLINE inspecionado, sem novo P1/P2
confirmado pendente.** Este adendo resolve a indicação desatualizada “INTEGRAL EM
ANDAMENTO” do relatório anterior por inspeção dos resultados concluídos e reprodução
focal própria. Não substitui a auditoria final do orquestrador. AUD-01 permanece
ABERTO; próximo gate externo, piloto e produção continuam NO-GO.

## Escopo e independência

O revisor manteve o repositório somente em leitura, sem commit/push e sem editar o
relatório anterior. Documentos/probes/logs desta revisão ficam em diretório separado.
Leitura direta: AGENTS, spec13/ADR0021, relatório Spec anterior, receipt/manifest/log/
JUnit da integral anterior, matriz de gates e as fronteiras relevantes de
`offline_recovery.py`, além dos dois arquivos de probes reproduzidos.
Compartilhamento do host/venv anterior não comprova host ou conta independentes.
Nenhuma API Telnyx, credencial comercial, conta, ativação, egress, LLM, piloto,
main ou Baileys foi usado/alterado pelo revisor.

## Evidência herdada, verificada nesta retomada

A integral foi executada pelo revisor anterior `/root/contract_review`, não por este
revisor. `full-final-receipt.json` registra exit0, SHA inicial CP5, SHA final CP6,
Python3.14.7/SQLite3.50.4 e duração do wrapper524,579s.
O log termina em **2262 passed em522,38s**. O JUnit contém2262tests,
0failures/0errors/0skipped, tempo522,192s. Diferenças de duração são do pytest,
JUnit e wrapper e não são agregadas ou tratadas como execuções distintas.

Conferi os194 hashes SHA256 em `files_before` e `files_after`:
ambos são idênticos e cada um coincide com os objetos Git dos candidatos CP5 eCP6.
O manifesto inicial também foi comparado com o receipt. Portanto, a mudança de HEAD
durante a integral não alterou os arquivos src/tests/scripts/requirements/.github
inventariados. Isto verifica a cadeia documental recuperada; não reexecuta a integral.

| Artefato herdado | SHA256 observado nesta retomada |
| --- | --- |
| full-final-receipt.json | `f2887be099a714826f3f93bbdef2d7628f530218f141e5d82fc3bd7dd9fb9f35` |
| full-final-manifest.json | `fc108c2ff23e8f4b11c3e64b6f486544a4f9f88d2829a30534071028072fd280` |
| full-final.log | `df737188daf530170a2b758b4b22eb2cd92379ae015ebdef33491f8ddb8290d8` |
| full-final/pytest.xml | `4348f0d05abc58d206e83c3b78d607a1328ef22ad4df30758d7e69fc37b2cc05` |

## Execução própria focal desta retomada

Na raiz do clone anterior, com o venv já existente e runner sanitizado:

```sh
../venv/bin/python scripts/check_telnyx_offline.py --python ../venv/bin/python \
  --output /Users/isaacbahnzz/Documents/Codex/2026-11-22/retomar-ticket-13-rj-studio-ai/work/spec-closure/probes \
  ../review-contract/test_recovery_contract_probes.py \
  ../review-contract/test_contract_probes.py
```

**13 passed em18,66s, exit0; JUnit13tests/0errors/0failures/0skipped.**
Python3.14.7/pytest9.2.0 no macOS. O runner cria ambiente/temporários privados,
sanitiza variáveis e instala guard Python IP/DNS herdado por filhos.
Não é isolamento kernel Linux. Não houve novo download de contrato externo nesta
revisão; conclusões sobre documentação pública permanecem evidência atribuída ao
relatório anterior. A CI remota observada pelo primary é evidência separada.

Foram reexecutados os dois negativos que reproduziram o P2 de TTL (prazo expirado e
expiração entre diagnóstico e reserva CAS), além dos11probes de contrato anteriores:
unsupported repetido preserva422/agregado sem conteúdo, echo não vira consentimento
ou janela, ambiguidade do provedor não autoriza retry, exatamente24h nega e nome
proposto de template não prova aprovação. Os recortes se sobrepõem à integral;
não somar como cobertura única.

| Artefato próprio | SHA256 |
| --- | --- |
| probes.log | `bf18bb2afbb8f603bcae062b0a9ae1dbc0eb5ee2845a28d6ff9335cc1b7d9d15` |
| probes/pytest.xml | `e16c9038cbd57551a717e6ce3d2381475c3388e34f3f7aea63d31093fab687d6` |

## Pendências e limite da conclusão

A spec exige laboratório sem capacidade de envio: a inspeção mantém constructor
quarantinado, nenhuma montagem operacional, e `operational_egress=False` em todos os
retornos. Reserve e alias passam pelo mesmo caminho; a rechecagem CAS/TTL da fake
continua coberta pelos negativos próprios. Inventário externo, autenticação real,
witness independente, completude do write-ahead e raízes não revertíveis permanecem
contratos/gates externos. O store genérico legado permissivo não virou caminho
operacional autorizado. Nenhum risco/checkbox da issue11 foi encerrado.

P3 documental herdado: cabeçalho do lock CP5/CP6 menciona Linux3.12/3.14, enquanto o
workflow seleciona somente3.12. Primary anunciou correção do comentário, preservando
pins. O PASS não certifica Linux3.14; a publicação deve retirar essa alegação e apontar
somente versões/SHAs dos runs observados. Esta observação não altera comportamento e
não justifica repetir a integral funcional quando só o comentário for corrigido.

A revisão anterior e este adendo juntos completam a perspectiva Spec doCP7. Não
realizei nova integral nem repeti toda a auditoria já concluída. CP8/relatório A–P/
issue11 pertencem à próxima tarefa, sob o limite definido pelo usuário.
