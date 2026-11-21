# Revisão independente B — segurança e privacidade

Baseline `07c1b7dc150d7eb1776b97d891cd29347adffd37`, consultada em 20/11/2026 (America/Sao_Paulo). Inspeção própria de auth/admin, configurações, eventos/journal, persistência/migrations, gates de submissão e testes; evidência não derivada do relatório do implementador. O auditor principal executou a suíte integral e scanners, e este revisor inspecionou os resultados de dependências/segredos explicitamente identificados abaixo.

**Parecer:** GO limitado a evolução offline com transporte interceptado, sem liberar rota ou workers Telnyx. NO-GO piloto/produção. Nenhum P0/P1 confirmado nesta revisão; P2 AUD-01 (restore) e AUD-02 (toolchain), além dos gates operacionais já abertos. O parecer não é certificação de segurança, legalidade ou conformidade integral com LGPD.

## Modelo de ameaças e fronteiras de confiança

Ativos: autorização de envio, identidade Customer/canal/WABA/profile/organização, histórico e contexto, pausa/handoff, evidência de delivery/unknown, consentimento, credenciais administrativas e backups. Atores relevantes: Internet sem autenticação; adversário capaz de reenviar request observado; payload autenticado contraditório/atrasado; operador com read ou control; processo/backup obsoleto; usuário local não confiável no host de testes. Não foi assumido que atacante com escrita arbitrária no schema SQLite será contido por triggers: esse ator já controla a base e exige defesa de infraestrutura.

| Fronteira/ameaça | Controle observado e evidência | Limite/gate |
| --- | --- | --- |
| Internet→auth Telnyx, forgery | Ed25519/libsodium, key canonical/subgroup check; `providers/telnyx.py:63`; assinatura antes de JSON/efeito; negativos e chaves degeneradas testados | Chave da conta/provisionamento/rotação reais não comprovados: CX-09/CX-25 |
| Replay de webhook | Timestamp dentro de ±tolerância (até300s), bytes exatos; journal/receipts deduplicam evento e mensagem | Assinatura recente não prova source_at nem elimina duplicatas; bloqueio por replay fora da janela não substitui dedupe |
| Header duplication/body oversized | Authenticator rejeita duplicata case-insensitive representável e body acima do limite | `ProviderWebhookRequest.headers` é dict; duplicatas HTTP já colapsadas não são recuperáveis. Body já está em memória. Rota Telnyx não existe: CX-24 antes de composição |
| Ambiguidade JSON | `_unique_object` rejeita chaves duplicadas; constantes não JSON/UTF8/recursão rejeitadas, após crypto | Eventos desconhecidos/formatos não suportados negam, política durável/ACK futuro CX-29 |
| Confusão de escopo | message exige phone/profile/org/direction/WHATSAPP; lifecycle exige WABA; opcional contraditório rejeitado | Account event não carrega sempre phone/profile; binding local single-business é a autoridade, não inferência do payload |
| Identity spoofing/aliases | Endereço BSUID com namespace; aliases são evidência, sem lookup/fusão. Guard de Conversation impede canal ambíguo | Identidade real/canais/migração CX-13; BSUID outbound continua negado CX-37 |
| Provider/operator separation | Telnyx public key não serve como Bearer; owner/revision/episode não autenticam; segredo operador SHA256 e compare_digest | API administrativa é estática por operador/processo, sem gestão de múltiplos operadores; TLS/rotação/ingress/limitação abuso CX-07 |
| Broken authorization | read/control separados e allowlist por ID opaco; config inválida503; não autenticado401; scope403 | IDs opacos não são credenciais. Descoberta/UI operacional segura continua CX-08 |
| Replay administrativo/CAS | Chave operation_id ligada a Conversation/operador/ação/revisão; resposta original em replay; erro409 em conflito; revision integer estrita | Replay devolve snapshot antigo por design; cliente deve GET novamente |
| Injection em SQL/payload | Valores externos bindados por parâmetros. Expressões SQL dinâmicas em migrations são fixas, não texto recebido | Não houve pentest de proxy/ORM de terceiros; nenhuma exploração SQL observada |
| Prompt injection | Conteúdo inbound vai para geração não confiável; saída factual/handoff passa por finalização determinística e knowledge | Naturalidade/CX-26 é decisão de produto separada; sem reescrever prompts nesta auditoria |
| Consentimento/opt-out | T10 exige evidência separada com escopo/frescor/revogação; autorização relê sob writer; corrida própria de revogação em duas ordens passou | Processo de coleta/revogação e prova do template real ausentes, CX-36 |
| Unauthorized outbound | Gate de canal/pausa/revision/handoff/ordering/consent/janela/key/payload reavaliado em transação | Authorization→HTTP permite trabalho já autorizado escapar pausa; não há recall CX-06 |
| Unknown/duplicação | Marker por attempt/primeiro marker imutáveis; retry só com prova local not_submitted; timeout/genérico retryable pós-marker vira unknown | Bytes/método/path/query/org e retries HTTP futuros não existem: CX-35 |
| Backup/rollback host | WAL/FULL/FK e backup API preservam snapshot consistente | Snapshot consistente pode ser obsoleto e autorizar de novo, AUD-01; criptografia e restauração operacional não comprovadas |
| Host de desenvolvimento | Dependências instaladas auditadas via pip-audit; testes sintéticos | Toolchain com advisories e ausência de lock reprodutível, AUD-02; exploração local não demonstrada |

Os 428 testes focados executados por este revisor e as sete sondagens novas estão em [SQLITE-CONCURRENCY-REVIEW.md](SQLITE-CONCURRENCY-REVIEW.md). Não foi efetuado scanning de endpoints comerciais, login de conta ou uso de credencial real.

## Privacidade, logs e retenção

`Settings` exclui segredos/identificadores privados de repr/model_dump e redige inputs de validação (`config.py:10`). Exceções Telnyx usam motivos genéricos, inclusive erros de commit; `test_commit_failure_rolls_back_and_redacts_sql_error` inspeciona traceback sem corpo/endereço/key. Observações humanas edit/revoke/echo não copiam texto para journal ou contexto LLM. Métricas de geração usam campos numéricos e enums allowlisted.

Isso não significa ausência global de PII. `messages.body`, Customer/channel, timestamps, aliases, consentimento e receipts são dados pessoais/operacionais. Classes neutras como InboundMessage/OutboundMessage e records de outbox têm repr contendo conteúdo/endereços; não foi encontrado caminho de logging efetivo que imprima esses objetos no runtime examinado, portanto é precaução para futuras mudanças, não vazamento confirmado. Proxy, APM, SDK debug e backups precisam política própria para não registrar Authorization/body.

O purge atual remove conteúdo por cutoff, mas journal, controls, human effects, operation receipts, inbound receipts, delivery-status receipts, channel state, consent e clock não têm programa completo de expiração/erasure. FKs RESTRICT e triggers de retenção preservam evidência e podem bloquear exclusão de Conversation; não autorizam prometer apagamento LGPD integral. Não remover unknown/receipts para desbloquear envio. A política técnica precisa conciliar minimização, janela de deduplicação, investigação de resultados ambíguos, solicitações do titular, retenção de backups/WAL e restauração que reaplique a eliminação. São pendências CX-01; owner jurídico/operacional responsável e prazo devem ser nomeados pelo projeto antes do piloto.

Dados reais não foram usados nos testes; os números +1, IDs e senhas rotulados synthetic nas fixtures são sintéticos. Isso é resultado da inspeção dos pontos usados, não certificação de que toda string histórica é fictícia.

## Segredos: resultado revisado

O auditor principal rodou Gitleaks no histórico (157 commits) e no diretório. No histórico foram reportadas duas ocorrências, inspecionadas também por este revisor:

1. `tests/test_telnyx_authentication.py:32`: constante OPERATOR_SECRET explícita de fixture sintética, não credencial comercial.
2. `docs/evals/V1/openai-partial-2026-10-02.md:11`: parágrafo de configuração de eval (`reasoning.effort`, `service_tier`, `store=false`), não segredo.

Essas ocorrências são falsos positivos contextuais; o scanner não deve ser reportado como zero detecções brutas. Não foi adicionada ignore list para ocultá-las. O relatório bruto foi mantido fora de documentos publicados; ausência de outra detecção não prova inexistência universal de segredos. Não houve credencial ou PII real acrescentada por esta revisão.

## AUD-02 — advisories na toolchain resolvida (P2)

**Classe:** dependências de desenvolvimento/instalação vulneráveis reportadas; exploração não demonstrada. **Arquivo:** `pyproject.toml:31` seleciona `pytest>=8.3,<9`. Ambiente efetivamente instalado na auditoria: pytest8.4.2 e pip25.0.1. pip é ferramenta do ambiente, não uma dependência runtime declarada da aplicação.

`pip-audit2.10.1` retornou código1 com 14 entradas brutas. Deduplicadas por pacote+ID, são sete advisories únicos: seis em pip e um em pytest. A própria aplicação local é registrada como não auditável pelo índice, não como biblioteca livre de defeitos. Nenhum advisory foi retornado para as bibliotecas runtime resolvidas naquele momento; isso não comprova ausência de vulnerabilidade nem cobre outra resolução futura das faixas abertas.

| Pacote/advisory único | Versão corrigida indicada | Relevância/limite |
| --- | --- | --- |
| pip PYSEC-2026-1795 / CVE-2025-8869 / GHSA-4xh5-x5gv-qwph | 25.3 | Fallback de extração tar sem PEP706; Python3.12.14 deste ambiente implementa PEP706, mitigando esse caminho específico |
| pip PYSEC-2026-1796 / CVE-2026-1703 / GHSA-6vgw-5pg2-w6jp | 26.0 | Wheel malicioso pode escrever fora do destino por traversal; não observado |
| pip PYSEC-2026-2875 / CVE-2026-3219 / GHSA-58qw-9mgm-455v | 26.1 | Arquivo concatenado tar/ZIP pode ser interpretado incorretamente |
| pip PYSEC-2026-2876 / CVE-2026-6357 / GHSA-jp4c-xjxw-mgf9 | 26.1 | Imports de self-update posteriores à instalação de wheel |
| pip PYSEC-2026-196 / CVE-2026-8643 / GHSA-wf93-45jw-7689 | 26.1.2 | Entry points tratados como paths fora do destino |
| pip PYSEC-2026-3721 / CVE-2026-13346 / GHSA-qwm4-qh6w-59xr | 26.2/26.2.0 | Requer índice malicioso/double-encoded URLs; não observado |
| pytest PYSEC-2026-1845 / CVE-2025-71176 / GHSA-6w46-j5rx-g56g | 9.0.3 | UNIX `/tmp/pytest-of-*`: adversário local pode causar DoS ou possível elevação; restrição <9 exclui versão corrigida |

Fonte da ocorrência: relatório JSON de `pip-audit` gerado nesta execução e inspecionado, não um teste de exploração. Referência pública do advisory pytest: [GHSA-6w46-j5rx-g56g](https://github.com/advisories/GHSA-6w46-j5rx-g56g). Os aliases acima permitem localizar cada advisory sem transportar o relatório bruto de ambiente.

**Impacto/gate:** ambiente compartilhado/CI pode executar ferramentas vulneráveis; isso não demonstra acesso remoto via webhook. **Recomendação:** processo de CI/dev com diretório temporário privado0700 e `--basetemp` privado até atualizar e validar pytest corrigido; atualizar pip do ambiente; registrar lock/snapshot da resolução e auditoria recorrente. A auditoria não fez essas correções. **Teste proposto:** instalar toolchain corrigida em venv limpo e repetir suíte/lint/pip-audit; comprovar permissão do basetemp em host compartilhado. **Dono/gate:** mantenedor de CI/dependências, antes de CI/host compartilhado e do aceite reprodutível; sem ampliar o escopo para produção por este trabalho.

## Condições para continuar e limites de aceite

Antes de trabalhar no sender offline, explicitar AUD-01 no plano de recuperação e usar testes de transporte sem IP/contas reais. Antes de qualquer worker/HTTP real: request determinístico e retries controlados (CX-35), unknown sem reenvio, restauração em quarentena e revalidação verificável. Antes da rota: preservar cabeçalhos brutos/limite de streaming/deadline oficial/ACK após persistência (CX-24/CX-29/CX-30). Antes do piloto: consentimento e opt-out com workflow, segurança do operador/UI, ativação positiva e binding, retenção/erasure/backups, testes reais isolados e autorização explícita.

Não foram comprovados neste ambiente: TLS/proxy/segredos do deploy; aquisição/rotação da chave Telnyx; sincronização NTP da infraestrutura; elegibilidade do número +55; entrega ou observação real de echo/status; consentimento de clientes; templates aprovados na conta; operação móvel; criptografia e restauração de backups; conformidade LGPD integral. Essas ausências mantêm gates de piloto abertos, sem serem rotuladas como exploração confirmada.
