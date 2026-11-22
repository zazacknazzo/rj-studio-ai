# Ticket 13 — revisão independente Spec / External Contract

Revisor: subagente independente `/root/contract_review`, 22/11/2026,
America/Sao_Paulo. BaselineT12:f1496be42732b7e57d317444d7ed0020997f0327.
Candidato de código/testes/CI:988efabe39611821035663dbae24a266b71bfca5.
DocumentaçãoCP6 inspecionada:995af20ff7d9e9f592a23c544f09a2407bd1b7f0.
Somente leitura do repositório; meus probes e resultados ficam fora dele.
Compartilho host/venv com o escritor; não alego host ou infraestrutura independente.

## Parecer

INTEGRAL EM ANDAMENTO. A conclusão final depende do resultado efetivamente observado.
Os defeitos encontrados por esta revisão foram corrigidos e seus probes originais
reexecutados. Não há novoP1/P2 confirmado pendente na inspeção atual do escopooffline.
AUD01 continuaABERTO; próximo gate externo, piloto e produção:NO-GO.

## Inspeção e contratos oficiais

Li AGENTS, specs06–13, ADR0014–0021, matriz completa de gates e documentos de recovery,
segurança/consentimento, retenção, CI, observabilidade, runbooks e plano de piloto.
Inspecionei authenticator/parser, políticaWhatsApp, request/sender, ASGI/rawHTTP,
laboratório de recovery, autoridade/witnessSQLite, testes, guard e workflowCI.

Fontes públicas oficiais consultadas nesta execução:

| Fonte | Conclusão aplicável e limite |
| --- | --- |
| [Endpoint WhatsApp](https://developers.telnyx.com/api-reference/whatsapp-messaging/send-a-whatsapp-message) e [idempotência](https://developers.telnyx.com/docs/development/api-fundamentals/idempotency) | UUIDv4 local atende ao subconjunto permitido; replay de sucesso é limitado a até24h, sem garantir frescor/ausência de duplicação após restore. Escopo/bytes são distintos de consentimento e autorização. Unknown nunca ganha retry por esse contrato. |
| [Messaging webhooks](https://developers.telnyx.com/docs/messaging/messages/receiving-webhooks) e [Help WhatsApp](https://support.telnyx.com/en/articles/13986487-how-to-configure-whatsapp-webhooks) | Há divergência documental2s/5s. Implementação conserva orçamento1,5s e gate externo2s, sem afrouxamento tácito; comportamento real do caminho precisa confirmação antes do piloto. Repetição sintética não é observação do provedor. |
| [Coexistence](https://developers.telnyx.com/docs/messaging/whatsapp/coexistence) e [webhooks](https://developers.telnyx.com/docs/messaging/whatsapp/coexistence/webhooks) | Echo é best-effort/outbound, não abre janela nem prova opt-in; reconnect não comprova sync/active. Eventos internos de sincronização não são enviados ao cliente. Não inferir proof atual de webhook ausente ou snapshot. |
| [Política WhatsApp,23/09/2026](https://whatsappbusiness.com/policy/) | Opt-in, opt-out, janela24h, template aprovado e escalonamento humano permanecem gates próprios; documentoT13 não trata fixture/nome de template como aprovação real. |

O URL geral de idempotência falhou na ferramenta web, e o download shell do subagente
foi negado por DNS/rede. Li a cópia pública baixada pelo principal, sem atribuir o
download a mim. SHA256idempotency:
ffb46a8a2039abc459544860a2ebf5d15917b8f4c1b83947291df26cca4c8e0d;
coexistence-webhooks:
6292e8f7f877ba886e0f000958d9ffa50ff1e473742082fa3aaeb4928cb9acd7.
Não houve conta, API comercial, chave real, ativação ou envio por esta revisão.

## Achados próprios e correções verificadas

1. **P2 no contrato simulado, corrigido.** Reserve aceitava evidência expirada;
   havia também corrida entre readiness e a reservaCAS. Dois probes próprios falharam
   comDID NOT RAISE em2,58s. Autoridade passou a revalidar provas/inventário/epoch/TTL
   na mutaçãoCAS; alias delegado pelo mesmo caminho. Os mesmos probes, sem relaxar
   asserts, agora passam. Store sempre continuou quarantinado: não foi bypass de
   egress operacional e não foi reclassificado para obterPASS.
2. **Cobertura rotulada incorretamente, corrigida.** Os ramos pause/disconnect usavam
   somente revogação de consentimento. Agora exercitam echo e PARTNER_REMOVED reais
   no adapter/journal sintético, verificando paused/blocked antes do restore. Li e
   executei os casos corrigidos.
3. **P3 documental, corrigidoCP6.** Prazo de artifact90d numa linha da matriz divergia
   dos14d do workflow. Foi alinhado;180d permanece proposta de política separada.

Relatos locais detalhados:preliminary-review.md,cp2-review.md e
cp2-correction-verification.md. Não somar contagens de execuções sobrepostas.

## Evidência própria executada

| Execução | Resultado observado | Limite |
| --- | --- | --- |
|11probes novos sobre baselineT12 |11passed,2,08s,exit0 | ASGI/SQLite sintéticos; unsupported repetido, echo, idempotência e janela/templates |
|2probes novos de expiraçãoCP2 antes da correção |2failed,2,58s,exit1 | Reprodução do defeito; não contada comoPASS |
|Mesmos2probes+11contratos+42testesrecovery corrigidos |55passed,7,02s,exit0 | Mesmo host/venv, nenhum transporte real |
|Integral independente988efabe |EM ANDAMENTO | Resultado final ainda não certificado |

Comando integral executado pelo revisor:

```sh
../venv/bin/python scripts/check_telnyx_offline.py --python ../venv/bin/python --output ../review-contract/full-final
```

Runner sanitiza ambiente, privateTMP/basetemp0700, guardPythonIP/DNS/filhos.
Python3.14.7/pytest9.2.0/SQLite3.50.4 observados. Não é execuçãoLinux/unshare;
workflowCI deve ser observado separadamente, não inferido destes resultados.
Manifesto próprio emfull-final-manifest.json:194arquivos src/tests/scripts/requirements/
.github, SHA256 e conferência de igualdade com988efabe durante a execução.
JUnit/log e hashes finais serão registrados após conclusão.

## Histórico v8 e gates finais

Comparei o artefatooriginalphase-A.json existente no workspace anterior do projeto
com a fixture versionada:46.181bytes idênticos, schema8/criado2026-10-04,
SHA2563d849ff3465d44cf20898aa170e72c08cc99b12e2f1b3266324754818291451e.
Inspecionei suas chaves/strings e não encontrei corpo deCustomer, telefone, token ou
prompt/resposta privados; prompt é fingerprint. Teste agora carrega original com hash,
sem fabricar história ou executar novoLLM. Isso prova compatibilidade de leitura,
não revalida qualidade/modelo/custo/latência históricos. MatrizAUD06 atualizada conferida.

Laboratório declara somente simulation_ready, operational_egressFalse sempre. Não
compõe transporte, não muda quarentena, não integra writerHTTP e não fornece adapter
real de autoridade. Raízes externas, completude do write-ahead, autenticação real,
provas atuais e integração final exigem ensaio no ambiente correspondente antes de
propor encerramentoAUD01. Rollback de todas as raízes não é detectável só pelo estado
antigo. Esses limites estão explícitos, assim como fila/operador paraCX29 e aceitehumano.
Nenhum teste/revisão autoriza executar o plano de piloto ou fechar riscos da issue11.
