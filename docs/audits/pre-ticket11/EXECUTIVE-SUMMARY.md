# Parecer executivo — auditoria integral pré-Ticket 11

**GO OFFLINE RESTRITO / NO-GO PILOTO E PRODUÇÃO.** A fundação permite desenvolver e testar o sender com transporte inteiramente mockado, preservando os requisitos corretivos e critérios de aceite descritos neste pacote. O parecer não aprova automaticamente o próximo componente.

Código auditado: `07c1b7dc150d7eb1776b97d891cd29347adffd37`, branch `codex/telnyx-coexistence-10-eligibility`. Inspeções e testes ocorreram em 20/11/2026, America/Sao_Paulo (21/11 UTC). A revisão final e a publicação foram retomadas em 21/11/2026, após novo fetch e confirmação de que a branch de auditoria não recebera alterações de outra conta. A suíte não foi apresentada como reexecutada nessa retomada.

## Evidência decisiva

- Suíte integral própria: **1.983 testes aprovados e um skip**, em 233,83 s, exit 0. Código de produção inalterado, ambiente saneado e conexões IP bloqueadas nos processos Python. Ruff check, format (301 arquivos), compileall, pip check e diff check passaram.
- Três perspectivas independentes leram código, specs e fontes: arquitetura/V1; segurança/reliability/SQLite; specs/contratos oficiais. Executaram recortes de 403/1, 428/0 e 54/0 (aprovados/skips), além de sete sondagens e 53 casos de eval offline. Esses recortes se sobrepõem à suíte integral; não representam cobertura adicional somável.
- As 21 migrations formam uma cadeia linear até 0021. Integridade SQLite e FKs passaram. Autorização por owner/revisão/canal/consentimento/janela e gravação dos markers são transacionais. Callbacks antecipados preservam escopo; sucesso contradito por falha conserva o conflito e bloqueia automação.
- Telnyx permanece fora do runtime. Sender, rota pública, ativação, consentimento operacional e resolução de conflitos não existem como fluxo integrado.
- Foram consultadas diretamente 12 fontes oficiais atuais, com hashes e commits na matriz. O endpoint WhatsApp e Idempotency-Key estão documentados; os bytes HTTP e o escopo externo ainda não estão vinculados à identidade local. Um SDK futuro pode repetir chamadas automaticamente; a baseline não instala o SDK Telnyx.

## Todos os P0 / P1 / P2

**Nenhum P0 ou P1 foi confirmado.** Há três P2, com estados distintos:

| ID | Achado e evidência | Critério bloqueador |
| --- | --- | --- |
| AUD-01 | Restore anterior ao claim, marker ou disconnect pode perder barreiras e autorizar novamente. Três cenários SQLite foram reproduzidos pelo revisor B e pelo auditor principal. Não houve HTTP nem duplicação externa observada | Contrato de recuperação antes do aceite do T11; quarentena e mitigação verificadas antes de saída operacional/piloto |
| AUD-02 | pip 25.0.1 e pytest 8.4.2 têm sete advisories únicos reportados. A faixa pytest<9 exclui a versão corrigida 9.0.3. Alcance local/instalação/CI; exploração não demonstrada | Ambiente isolado e temporário privado antes de uso compartilhado; atualização e validação da toolchain em tarefa própria |
| AUD-03 / DOC-02 | Protocolo entre duas contas ausente no AGENTS/handoff da baseline | Mitigado nesta auditoria por branch exclusiva, escritor Git único e handoff; protocolo permanente antes de outro escritor assumir desenvolvimento |

Os P3 cobrem documentação e planejamento contraditórios, fixture histórica local/CI não comprovado, chamada LLM após pausa durante montagem de contexto, subclasse admitida pelo store genérico confiado e concentração de SQL. Locais, reproduções, correções recomendadas, testes e gates estão em [FINDINGS.md](FINDINGS.md).

## Dez riscos mais importantes

1. **Duplicação após ambiguidade ou restore antigo:** unknown não pode ganhar retry ou chave nova; AUD-01, CX-15/35.
2. **Requisição externa diferente ou retry interno do SDK:** chave/fingerprint ainda não vinculam organização, método, path, query e bytes HTTP; CX-35.
3. **Envio fora da janela ou sem consentimento vigente:** provas locais não validam coleta, opt-out ou template reais; CX-16/36.
4. **Canal reconectado sem sincronização positiva:** reconnect não equivale a active; ativação/rebinding ausentes; CX-11/33.
5. **Intervenção humana tardia e envio já autorizado:** echo best-effort e intervalo autorização→HTTP exigem pausa prévia utilizável; CX-02/06/08.
6. **Webhook incompleto na futura rota:** headers brutos, streaming, chave/clock de deploy e ACK em até 2 s após commit ainda precisam composição; CX-09/24/25/30.
7. **Falsa entrega ou reconciliação insegura:** o ledger protege escopo, mas conflitos/unknown não têm workflow operacional completo; CX-14/31/32.
8. **Identidade, BSUID e formatos não suportados:** aliases não devem fundir clientes nem inferir telefone; rejeição sem destino durável pode esgotar retries; CX-12/13/29/37.
9. **Retenção, backups e privacidade:** journal, receipts, controles e consentimento não têm política integral; logs de proxy/APM e erasure precisam decisão; CX-01/07.
10. **Liberação sem evidência operacional:** toolchain, CI, skip, elegibilidade +55, custos, métricas reais e naturalidade continuam como gates; AUD-02, CX-10/19/20/21/26.

## Baseline e integridade Git

Foi criado um clone novo em `/workspace/rj-studio-ai`. AGENTS e regras de domínio/issues foram lidos antes da inspeção. Fetch confirmou a branch T10 na SHA exata, T09 em `c2cc68c0c714d8f8c642f7759f3799a90b3feae4` e main em `af1c9eb862a4180ca6b9e537349e4f8abaa2bb29`. A branch de auditoria não existia e foi criada sem sobrescrever trabalho. Exclusões aparentes após `clone --no-checkout` desapareceram no primeiro checkout; não eram alterações de outro agente.

Somente `docs/audits/pre-ticket11/` e `docs/handoffs/AUDIT-PRE11.md` foram alterados. Não houve mudança de produção, testes, configuração, knowledge, main, issue #11 ou branch experimental Baileys. Nenhuma branch Baileys apareceu neste clone; worktrees em outras máquinas não foram inspecionados. Checkpoints e retomada estão no [handoff](../../handoffs/AUDIT-PRE11.md). A SHA final exata é confirmada no remoto e informada na entrega; um commit não contém seu próprio hash literal.

Gitleaks produziu duas detecções brutas, triadas como falsos positivos: fixture sintética e prosa. Pip-audit retornou 14 entradas brutas, sete IDs únicos; não passou limpo. O skip depende de uma fixture local não versionada. Esses limites permanecem explícitos em TEST-EVIDENCE. Não houve uso de conta/credencial comercial, requisição real Telnyx/Meta/WhatsApp, ativação ou merge.

## Próxima ação

Solicitar **auditoria final do orquestrador** sobre o pacote publicado, com atenção aos três P2 e aos critérios de aceite do sender. Depois, retomar somente a tarefa offline autorizada em branch própria e com o [plano de correção por dependência](REMEDIATION-PLAN.md). T12–13, operação real, mudanças de inteligência/SaaS e edição da issue #11 dependem de seus escopos e autorizações próprios. Esta auditoria termina na entrega documental.
