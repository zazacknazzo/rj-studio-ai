# CI reproduzível e evidência offline

22/11/2026. .github/workflows/telnyx-offline.yml prepara uma execução Linux sem
segredos comerciais. Instalação de pacotes/advisories/downloads públicos ocorre
ANTES do isolamento de rede; nenhum desses passos usa conta/API Telnyx.

## Resolução e fronteiras

requirements/ci.lock fixa87distribuições observadas, incluindo pip26.3/pytest9.2.0,
audit/build tools. Aplicação local é instalada separadamente com --no-deps e
--no-build-isolation; hatchling/editables também estão fixados.
O lock é de VERSÕES: não é lock universal por plataforma nem pin por hash de wheel.
A resolução efetivamente usada deve ser comparada com resolved.txt/pip-inspect.json.
Python3.14.7/SQLite3.50.4 macOSarm64 foram usados localmente; LinuxPython3.12 só
pode ser chamado validado depois de observar o workflow concluído.

Workflow usa actions checkout/setup-python/upload-artifact fixadas por SHA, permissões
contents:read, checkout sem persistir credenciais e nenhum secrets.* no YAML.
As SHAs foram consultadas nos refs oficiaisv6 em22/11. Gitleaks8.30.1 tem SHA256
do tar oficial Linux fixado e verificado antes de executar; tar Darwinarm64 local também
foi verificado com checksums do release. Binários não são enviados ao repositório.

## Checks reais do pipeline

1. Instalar venv/lock/app sem fixtures privadas; registrar versões/resolução.
2. pip-audit do ambiente resolvido com resultadoJSON e cache próprio. A app local
   rj-studio-ai não está no índice e aparece explicitamente como skipped; não ocultar.
3. Gitleaks da árvore TRACKED materializada por git archive (sem venv/binaries/ruído)
   e do range baselineT12..HEAD. Sem .gitleaksignore, exclusões de regra ou allowcomments.
4. Três achados brutos históricos da árvore têm triagem explícita com arquivo/linha/regra
   e hash INTEGRAL do arquivo inalterado: schemahashpúblicoT11, prosaeval e fixture
   sintética de hash de operador. check_gitleaks_report.py rejeita achado novo/alterado;
   não chamar a árvore de “zero hits”. RangeT13 exige zero hits.
5. sudo unshare --net cria namespaceLinux e devolve execução ao usuário do runner.
   assert_no_external_network.py verifica somente loopback e nenhuma default route
   IPv4/IPv6 ANTES dos checks. Nenhuma conexão é feita por essa verificação.
6. Dentro desse namespace: Ruff check/format, compileall src/tests/scripts, pip check,
   pip inspect, diff check e pytest integral (inclui migrations/concurrency/restore/carga).
7. O runner Python também sanitiza env/credentials, usa tmp/basetemp0700, bloqueia
   IPv4/IPv6 TCP/UDP/sendmsg/send/sendall/bind/listen e DNS; filhos recebem o guard.
   Nove probes novos comprovam a negação em processosPython novos.
   O guard Python isoladamente NÃO é kernel sandbox; não cobre binários nativos.
8. JUnit usa xunit1, compatível com record_property das cargas; dados sintéticos.
   EvidênciasCI são publicadas como artifact por14dias. Proposta de retenção180dias do
   relatório saneado/audit é decisão separada, ainda não implementada no artifact server.

## Skip histórico v8

O arquivo ORIGINAL foi encontrado no workspace anterior em22/11, inspecionado e copiado
byte a byte para tests/fixtures/historical/live-record-v8.json. Proveniência e SHA256
estão no README da fixture;10casos de benchmark, hashes/contadores/contratos sem corpo
de Customer, prompt/response privados ou segredo. Gitleaks original retornou0hits.
O teste histórico agora verifica hash e carrega schema8 de caminho versionado:
não depende de work/ pessoal e não pula por ausência. Não fabricamos novo live record,
não chamamos LLM nem reinterpretamos latência/custo históricos como evidência atual.

## Reprodução por outra conta

Em clone limpo da branch/SHA publicada: ler AGENTS/handoff e confirmar escritor humano
antes de editar. Criar venv próprio, instalar requirements/ci.lock --no-deps, instalar
app --no-deps --no-build-isolation, executar scripts/check_telnyx_offline.py.
Em Linux com permissão de namespace, usar a sequência do workflow; em macOS reportar
somente guardPython, sem alegar kernel isolation. pip check/audit, Ruff/format,
compileall/diff e scanners devem ser realmente reexecutados. Não copiar banco/segredo
de outra conta. Registrar falhas/interrupções e comparar SHAs com origin sem force.

Sucesso do pipeline não concede autorização externa nem encerra AUD01/CX19 sozinho.
RelatórioT13 e issue11 registram runs/SHAs/resultados observados e limites atuais.

