# Retomada da Lívia no WhatsApp

## Fonte e escopo

- Repositório https://github.com/zazacknazzo/rj-studio-ai.
- Branch de continuação `codex/livia-private-operations-20261126`.
- Último commit de código conferido no remoto `067f78092306d1f44b798d3d603cd23ccb8fca91`.
- Baseline B5 `4778a9b15b101f9e552169cb71adef7361ae6468`.
- O usuário pediu publicação e transferência em 26/11/2026, após autorizar a troca da conta da IA e do único participante. Os números completos estão na configuração privada local.
- Root encerrou suas mutações operacionais. O próximo responsável deve conferir exclusividade humana e divergência antes de escrever.
- Autorizações da missão cobrem correções, testes privados, OpenAI real, commits e push. Merge na main requer autorização específica.
- O usuário aceitou o risco de rollback conjunto somente para o teste privado de hoje. AUD-01 e AR-02 continuam abertos. Atendimento público e disparos permanecem fora do escopo autorizado.

## Estado observado na transferência

Em 26/11 às 13h17–13h18 de Brasília, os dois projetos Compose foram parados após
a pausa autenticada do backend novo. O número antigo deixou de ser a conta da IA.
O novo número da IA exige pareamento. Sua sessão chegou a FAILED, sem identidade
vinculada e sem QR disponível. O diagnóstico observou Chromium em execução e HTTP
200 ao acessar web.whatsapp.com de dentro do contêiner. A causa da falha ainda
precisa ser diagnosticada. A leitura do endpoint QR expirou uma vez, sem envio.

O ambiente anterior conserva uma resposta cancelada, zero tentativas e zero
intenções consumidas. O ambiente novo possui zero mensagens, zero entregas,
zero tentativas e zero gerações. Uma reserva histórica de modelo foi carregada
do ambiente anterior para conservar o consumo cumulativo. O novo journal e
ledger mantêm pausa e envio desabilitado.

O prazo conservado nos dois ambientes é 26/11/2026 às 13h25min27s de Brasília,
epoch em milissegundos `1795710327845`. Os comandos start/resume conservam esse
prazo. Confira a validade e a autorização vigente antes de reativar. Preserve
inventário, revogações, prazo e contadores ao tratar uma janela posterior.

## Checkpoints e evidência

| Etapa | Resultado observado |
| --- | --- |
| Auditoria remota | 13 issues e um PR histórico encontrados, branches atualizadas por fetch. Issue #11 confirma Ticket 13 aprovado offline e AUD-01/AR-02 abertos. |
| Runtime anterior | Colima recuperado, WAHA WORKING sem QR, identidade e participante verificados, HMAC do webhook interno conferido. |
| Núcleo real | Nove gerações OpenAI com o pipeline existente e 22 fatos aprovados. Persona, contexto, grounding, handoff e memória usam os módulos canônicos. |
| Fontes em execução | Onze fontes/KB do contêiner comparadas por SHA-256 com o checkout, onze coincidências. |
| Testes Python | 2367 passaram pelo runner isolado, em 206,74s. |
| Worker e bridge | 15 testes workerd e 20 testes Python de integração passaram. |
| CI do código | Run 45850016542 concluído com success, SHA exato 067f78092306d1f44b798d3d603cd23ccb8fca91. |
| Troca autorizada | Configuração e volumes locais isolados, nova sessão criada, envio mantido bloqueado. Pareamento pendente. |
| Conversa real | Pendente. Nenhum múltiplo turno ou recebimento no aparelho foi comprovado nesta missão. |

A primeira execução direta do pytest teve 22 erros de setup em testes G0, que
exigem o runner `scripts/check_telnyx_offline.py`. A execução posterior pelo runner
passou integralmente. O CI confirmou a suíte isolada e os checks de dependências,
segredos e formatação. O hash acima identifica a validação do código. Consulte
Actions para o resultado de commits documentais posteriores.

No diagnóstico real, perguntar o preço da progressiva produziu a tabela aprovada.
Perguntar se o salão realiza o procedimento acionou handoff `missing_critical_fact`.
A KB contém preços, porém não um fato aprovado da categoria serviço. O intake
proíbe deduzir disponibilidade a partir de preço. Issues #6 e #12 permanecem
relevantes para piloto e naturalidade. Qualquer correção deve respeitar a
aprovação dos fatos e os controles de grounding.

## Mapa local para o agente que usar este Mac

Raiz da missão
`/Users/isaacbahnzz/Documents/Codex/2026-11-26/files-pasted-by-the-user-miss`.

| Local relativo à raiz | Papel |
| --- | --- |
| `work/runtime` | Checkout da branch publicada, configuração anterior por symlinks, projeto Compose rj-livia-b1 parado. |
| `work/livia-atual` | Worktree em detached HEAD 067f780, configuração nova privada, projeto rj-livia-rebound parado. |
| `work/livia-atual/.env.b1` | Novas identidades, chaves locais novas, chave OpenAI existente, COMPOSE_PROJECT_NAME. |
| `work/livia-atual/.local/b1` | Sessões, banco, controles e testemunha novos. |
| `work/livia-atual/.local/livia-test` | Ledger e runtime da janela privada nova. |
| `work/pareamento.py` | Auxiliar temporário local para obter QR privado e removê-lo ao terminar. |
| `outputs/Parear Lívia.html` | Página local de pareamento, depende do auxiliar e de um QR disponível. |
| `outputs/TRANSFERENCIA-PRIVADA.txt` | Identidades completas e ponteiros locais destinados ao proprietário. |
| `work/suite-isolada` | XML e evidência privada do runner. |
| `work/worker-tests.log`, `work/bridge-tests.log` | Resultados locais dos testes Worker e bridge. |
| `work/issues.json`, `work/comments.json` | Snapshot da auditoria GitHub. |

A configuração, sessões, bancos, QR e evidência privada ficam no Mac.
Um clone em outra máquina exige provisionamento e transferência autorizada por
canal privado. O GitHub contém o código, os testes e a documentação de retomada.

## Próxima ação exata

No checkout da branch publicada, faça fetch, verifique status/divergência e leia
AGENTS.md e este handoff. Reproduza o teste focado com

```sh
.venv/bin/python scripts/check_telnyx_offline.py --python .venv/bin/python --output work/repro-operador -- tests/test_waha_private_cli.py tests/test_waha_private_test.py tests/test_waha_b2.py
```

O diretório de output deve ser novo porque o runner preserva evidência existente.

Depois trabalhe com a configuração nova em work/livia-atual. Para inspecionar a
sessão sem ativar respostas, inicie somente o WAHA com a composição privada

```sh
export DOCKER_HOST="unix://$HOME/.colima/default/docker.sock"
docker-compose --env-file .env.b1 -f compose.b1.yaml -f compose.private-test.yaml up -d --no-build waha
```

Leia o estado com a API autenticada, sem imprimir valores da configuração ou
corpos de resposta remotos. Diagnostique FAILED e obtenha um QR válido. O usuário
precisa ler o QR no aparelho da conta da IA. Confirme a identidade exata antes
de retomar. Preserve a sessão anterior e seus registros.

Após pareamento, confira janela e limites, suba o backend e use os comandos de
docs/handoffs/WAHA-PRIVATE-OPERATIONS.md. A ativação revalida os aliases e a
identidade conectada. Valide mensagem real do único cliente, persistência,
OpenAI, KB, resposta, recibo e ACK. Faça múltiplos turnos, confira continuidade e
testes de duplicidade, self, participante indevido, pausa e unknown sem retry.
Registre cada resultado efetivamente observado antes de declarar conclusão.

Para encerrar no checkout operacional, execute `scripts/livia-test stop`.
