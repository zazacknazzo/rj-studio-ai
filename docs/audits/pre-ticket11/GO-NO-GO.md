# Dois pareceres independentes de liberação

Baseline de código: `07c1b7dc150d7eb1776b97d891cd29347adffd37`, branch aprovada T10 `codex/telnyx-coexistence-10-eligibility`. Auditoria em `codex/audit-pre11-telnyx-v1`; somente documentos. Não houve implementação do sender, correção automática ou operação comercial.

## 1. Continuação do Ticket 11 OFFLINE: GO RESTRITO COM GATES

A fundação inspecionada suporta desenvolver e testar serialização/response handling com transporte completamente interceptado: identidade por entrega, consentimento e janela separados, writer authorization, markers, callback scoped e unknown não reenviável têm evidências concretas. Suíte integral independente: 1.983 passed/1 skip; três revisões distintas com leitura direta e reproduções próprias. Esses resultados sustentam evolução offline, não garantia de exactly-once externo.

**Esse GO não é aprovação automática do sender ou eliminação de P2.** Condições antes de retomar o trabalho dependente:

- Escritor exclusivo, nova branch T11, fetch/status/SHA/handoff; protocolo desta auditoria resolve a continuidade da própria tarefa, enquanto AUD-03 permanente continua pendente.
- Ambiente de testes isolado, sem credenciais/contas reais e com temp privado 0700/`--basetemp` quando houver host compartilhado; tratar atualização da toolchain AUD-02 com evidência própria. Não expor ferramentas vulneráveis a outro usuário local sem mitigação.
- Incluir AUD-01 no contrato/plano de recuperação **antes do aceite do Ticket 11**: snapshot antigo não é autorização operacional; saída após restore deve depender de quarentena/reconciliação/revalidação verificáveis. Não implementar mecanismo dos T12/13 incidentalmente.

Critérios bloqueadores do **aceite do sender offline**:

1. Request exato especificado e vinculado à identidade: organização, método, path, query e bytes do body estáveis. Fingerprint canônico atual não comprova isso (CX-35).
2. Sem retries automáticos do SDK/transporte fora da política local; uma chamada por autorização. 409/10036, 422/10027, 429/5xx, timeout/malformed/resposta perdida não ganham replay cego.
3. Acceptance validada a partir da resposta correta, com ID/escopo; status, echo e ACK não inventam acceptance/delivery.
4. Mesmos gates de owner/lease/pausa/revision/handoff/ordering/lifecycle/consentimento/janela no runner real; assessment anterior não autoriza. Unknown/expiry/restore não geram chave nova para contornar evidência.
5. SQLite e concorrência reais com transporte interceptado: crash/restart, callback antes/depois da acceptance, duplicata/contradição e pausa/disconnect/revogação após marker. Qualquer novo P1/P2 no componente dependente exige correção/revisão antes de seu aceite.

AUD-01 é P2 operacional porque Telnyx permanece desabilitada e a auditoria não observou envio externo. **Se “continuar T11” for ampliado para iniciar worker, HTTP, ativação ou restore com saída, o parecer muda para NO-GO até mitigação.** AUD-02 é toolchain/CI e AUD-03 é coordenação; não exigem mudar inteligência ou algoritmo de autorização para escrever testes mockados. O [plano](REMEDIATION-PLAN.md) propõe as correções por dependência, sem executá-las nesta auditoria.

## 2. Piloto / produção: NO-GO

Não há sender, rota pública, ativação/rebinding verificados, aquisição operacional de consentimento/templates ou integração Telnyx real nesta baseline. A lista de bloqueadores continua aberta, especialmente:

| Gate | Evidência necessária para reconsiderar |
| --- | --- |
| Restore/unknown/request externo — AUD-01, CX-15/35 | Mitigação antirollback/quarentena testada; request determinístico e retry controlado; reconciliação sem duplicação |
| Janela/consentimento/template — CX-16/36 | Processo autenticado de coleta/revogação/opt-out e prova vigente de modalidade e janela até submissão |
| Canal/identidade/onboarding — CX-10/11/13/33/37 | Número secundário elegível, binding/sync positivos, destinatário/callback corretos e política clara de BSUID |
| Ingress HTTP — CX-09/24/25/29/30 | Chave/clock implantados, headers brutos, limite de streaming, tratamento durável de não suportados e ACK ≤ 2 s após commit |
| Operação humana — CX-02/06/07/08/32 | Pausa prévia utilizável, in_flight visível, TLS/rotação/allowlist e resolução auditada de conflitos/unknown |
| Privacidade/retention — CX-01 | Política e execução de erasure/replay/backups/WAL com preservação proporcional de evidência e owner responsável |
| Release/produto — AUD-02/04/06, CX-19/20/21/26 | Ambiente/CI reprodutíveis, skip histórico tratado, docs correntes, secret review e aceite conversacional separado |
| Aceite real — CX-10/18/20 | Autorização específica, participantes consentidos, orçamento, rollback e métricas reais: p95 E2E ≤ 8 s e custo ≤ US$ 10/1.000 replies completas ou decisão formal revisada |

Nenhuma exceção foi aceita, nenhum risco foi encerrado e nenhuma checkbox foi alterada. A existência de documentação oficial, testes sintéticos ou health local não substitui essas evidências. Não foi declarada conformidade jurídica integral com LGPD.

## Decisão solicitada ao orquestrador

Revisar os três P2 e a separação de gates acima, confirmar o escopo de GO exclusivamente offline e os critérios de aceite do T11. Autorizações anteriores de implementação offline persistem, mas **esta auditoria não inicia implementação nem libera Tickets 12–13, piloto, produção ou merge**. A próxima ação desta tarefa é auditoria final do orquestrador sobre o pacote documental publicado.
