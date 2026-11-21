# Testes e evidências independentes

Consulta/execução: 20/11/2026 America/Sao_Paulo; host UTC21/11. Código testado: **07c1b7dc150d7eb1776b97d891cd29347adffd37**. HEAD da auditoria na execução integral: `3d93bd18c963894490dd192aa22cc1cc9ec9241b`, cujo delta era somente dois documentos. Produção, testes, fixtures, knowledge e configurações não foram alterados. Ambiente novo em `/tmp/audit-pre11-venv`, CPython3.12.14, SQLite3.53.1, Linuxx86_64. Instalação: `python3 -m venv /tmp/audit-pre11-venv` e `python -m pip install -e '.[dev]' pip-audit`; sem `.env` comercial.

## Resultado principal

**1983 passed, 1 skipped em233,83s**, exit0. Tempo externo medido235,608s; JUnit1984casos, failures0/errors0/skipped1. Timestamp JUnit de início20/11/2026 23:31:52−03. Reproduz a contagem histórica1983/1; a duração difere, sem alegação de benchmark equivalente. O p95E2E do piloto não foi medido.

```bash
# Executado em subprocesso Python com ambiente reduzido a PATH/LANG/LC_ALL/TMPDIR/HOME
# e as variáveis abaixo; não foram transportadas credenciais do ambiente pai.
PYTHONPATH=/tmp/pre11-network-guard:/workspace/rj-studio-ai/src \
PYTHONDONTWRITEBYTECODE=1 PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 \
/tmp/audit-pre11-venv/bin/python -m pytest -ra --durations=15 \
  --junitxml=/tmp/audit-pre11-pytest.xml
```

A suite utiliza SQLite real, payloads assinados sintéticos, fakes/mocks dos providers e TestClient ASGI. O guard abaixo bloqueou IPv4/IPv6 na API de sockets Python e foi herdado por subprocessos Python com esse ambiente. Não é isolamento por kernel nem afirmação sobre executáveis nativos arbitrários. Não foram feitas chamadas comerciais, utilizadas credenciais reais ou ativados canais. Consultas públicas de documentação/advisories e operações Git ocorreram separadamente da suíte.

## Checks e limites

| Comando / verificação | Resultado real | Limite |
| --- | --- | --- |
| `python -m pytest -ra --durations=15 --junitxml=...` |1983pass/1skip,233,83s,exit0 | Não prova entrega real ou todos os interleavings |
| `ruff check .` |PASS | Ruff0.17.6 |
| `ruff format --check .` |PASS,301arquivos | Contagem real desta resolução, sem usar298do relatório anterior |
| `python -m compileall -q src tests` |PASS | Sintaxe/import bytecode, não teste funcional |
| `python -m pip check` |PASS, nenhuma dependência quebrada | Não é auditoria de vulnerabilidade |
| `git diff --check` |PASS nos checkpoints | Escopo documental conferido separadamente |
| `pip-audit --cache-dir /tmp/audit-pre11-advisory-cache --format json --output /tmp/audit-pre11-pip-audit.json` |exit1:14entradas brutas em2pacotes;7advisories únicos | pip/pytest de desenvolvimento; app local pulada pelo índice; AUD-02 |
| Gitleaks8.30.1 `git --redact --log-opts=07c1b7d... .` |157commits,2detecções brutas | Fixture sintética e prosa, falsos positivos triados; não usar “zero detecções” |
| Gitleaks8.30.1 `dir --redact .` |2detecções brutas na árvore inicial | Mesmos contextos; rechecagem final documental registrada no handoff |
| GitHub combined_status / workflow_runs da SHA |statuses=[] e workflow_runs=[] | Ferramenta workflow consulta runs associados a PR; vazio não inventa prova universal de ausência de toda execuçãoCI |
| Scanner de destinos relativos Markdown baseline |136md,zero destinos inexistentes | Não valida todos os anchors/URLs; revisãoC |

Primeira tentativa de pip-audit falhou antes de consultar advisories porque cache padrão `/home/agent/.cache/pip-audit` era somente leitura. Segunda execução usou cache em `/tmp` e completou. Não houve supressão de advisory ou ignore de Gitleaks. Pip-audit2.10.1 reportou seis IDs únicos de pip25.0.1 e um de pytest8.4.2; detalhes, alcance e versões corrigidas em [SECURITY-PRIVACY-REVIEW.md](SECURITY-PRIVACY-REVIEW.md). Nenhum advisory foi retornado para as bibliotecas runtime instaladas; faixas abertas podem resolver versões diferentes no futuro.

## Execuções independentes adicionais

| Executor / escopo | Resultado | Evidência durável |
| --- | --- | --- |
| RevisorA:12arquivos de contratos/pausa e V1 |403passed/1skip,exit0; duração não capturada | [ARCHITECTURE-REVIEW.md](ARCHITECTURE-REVIEW.md), comando e probes integrais |
| RevisorA:evals offline reais |53casos/23replies;0/97falhas críticas; record validado | Mesmo relatório; não mede qualidade humana/modelo real |
| RevisorB:8módulos críticos |428passed/0skip,51,16s | [SQLITE-CONCURRENCY-REVIEW.md](SQLITE-CONCURRENCY-REVIEW.md) |
| RevisorB:7sondagens novas |7passed,2,53s | Script integral no relatório;3testes demonstram restore inseguro, não sua correção |
| RevisorC:contratos externos e negativos |54passed/0skip,exit0; duração não medida | [EXTERNAL-CONTRACT-MATRIX.md](EXTERNAL-CONTRACT-MATRIX.md) |
| Auditor principal:mutação focal em memória, janela25h |2failed/2passed/155deselected,0,08s,exit1 esperado | Testes exatos24h detectaram mutante; nenhum arquivo de produção modificado |
| Auditor principal:limite baseline após mutante |4passed/155deselected,0,04s,exit0 | Processo novo sem mutação |
| Auditor principal:temp privado + autorização concorrente |1passed,1,91s,exit0; parent0700 | Mitigação verificável para pytest em host compartilhado; não atualiza pacote |
| Auditor principal:contraprova própria de AUD-01 |3passed/4deselected,2,44s,exit0 | Reexecução dos três cenários de restore: aprovação reproduz falta do fence, sem HTTP |

Os recortes se sobrepõem à suíte integral. Não somar suas contagens como casos distintos, cobertura adicional ou independência de todos os caminhos. As três perspectivas iniciaram inspeção direta de código/spec/fontes sem derivar revisões de um resumo comum do implementador. Depois da coleta própria, resultados foram compartilhados para consolidação; revisãoB identifica explicitamente scanners executados pelo auditor principal.

## Skip histórico e reprodução portátil

`tests/test_commercial_steering.py:423–432`, `test_historical_v8_record_remains_loadable`, procura `work/evals/openai-agentic-surface-smoke-2026-10-04-01/phase-A.json`, ignorado pelo Git. Não existia no clone limpo, logo `pytest.skip` em430 foi efetivamente observado. É uma validação histórica opcional, não evidência de provider pulada. Permanece lacuna antes do aceite reprodutívelCX-19: versionar uma fixturev8 sintética/sanitizada ou teste equivalente autorizado, com provenance e assertiva de compatibilidade. Inventar arquivo para fazer o skip passar não validaria o histórico. Nenhuma fixture foi criada no repositório nesta auditoria.

## Mutação focal realizada (sem alteração de arquivo)

A seleção abaixo mata mutação relevante da janela; não é mutation testing exaustivo nem substitui cenários de concorrência.

```python
from datetime import timedelta
import pytest
import rj_studio_ai.whatsapp_policy as policy
policy.SERVICE_WINDOW = timedelta(hours=25)  # apenas memória do processo de teste
raise SystemExit(pytest.main([
    '-q', '-o', 'addopts=', 'tests/test_whatsapp_policy.py',
    '-k', 'free_form_window_uses_exact_source_boundary'
]))
```

Dois asserts que exigem negativa exatamente24h e24h+1µs falharam com o mutante. Em novo processo sem mutação, os4casos passaram. Não foram executados fuzzing/property-based sistemáticos, mutation testing amplo, pentest de deploy, falha física de energia ou smokeE2E comercial: **NÃO EXECUTADOS** porque não estavam disponíveis/seriam desproporcionais ao escopo documental ou exigiriam operação externa expressamente proibida. A suíte existente e os probes reais cobrem limites/parâmetros/conexões SQLite identificados nos relatórios; não se extrapola para prova formal.

## Reprodução do bloqueio de rede

Salvar como `/tmp/pre11-network-guard/sitecustomize.py` e colocar esse diretório primeiro no PYTHONPATH, inclusive de subprocessos. Em outra conta, revisar o guard e nunca carregar `.env` ou reutilizar bancos reais. Para testes compartilhados, criar um diretório pai0700 com `tempfile.mkdtemp` e passar `--basetemp=<pai>/run`; o ensaio adicional executou `tests/test_telnyx_submission.py::test_concurrent_authorization_is_single_use` assim e passou.

```python
import os
import socket

_connect = socket.socket.connect
_connect_ex = socket.socket.connect_ex
_sendto = socket.socket.sendto

def _blocked(sock, *args, **kwargs):
    if sock.family in (socket.AF_INET, socket.AF_INET6):
        raise RuntimeError('AUDIT_PRE11_IP_NETWORK_BLOCKED')
    return _connect(sock, *args, **kwargs)

def _blocked_ex(sock, *args, **kwargs):
    if sock.family in (socket.AF_INET, socket.AF_INET6):
        raise RuntimeError('AUDIT_PRE11_IP_NETWORK_BLOCKED')
    return _connect_ex(sock, *args, **kwargs)

def _blocked_sendto(sock, *args, **kwargs):
    if sock.family in (socket.AF_INET, socket.AF_INET6):
        raise RuntimeError('AUDIT_PRE11_IP_NETWORK_BLOCKED')
    return _sendto(sock, *args, **kwargs)

socket.socket.connect = _blocked
socket.socket.connect_ex = _blocked_ex
socket.socket.sendto = _blocked_sendto
os.environ['AUDIT_PRE11_NETWORK_GUARD'] = 'active'
```

## Manifesto do ambiente resolvido

Este snapshot documenta a resolução observada, incluindo ferramentas de auditoria. Não é lock autorizado nem mudança de dependências da aplicação. O pin pytest<9 está na linha31do pyproject; pip25.0.1 veio do venv. Nenhum pacote foi atualizado para corrigir achados nesta auditoria.

```text
aiohappyeyeballs==2.7.1
aiohttp==3.14.5
aiohttp-retry==2.9.1
aiosignal==1.4.0
alembic==1.20.1
annotated-doc==0.0.7
annotated-types==0.8.0
anthropic==1.17.0
anyio==4.16.0
attrs==26.1.0
boolean.py==5.0
CacheControl==0.15.0
certifi==2026.11.20
cffi==2.1.1
charset-normalizer==3.5.2
click==8.5.1
cryptography==50.0.2
cyclonedx-python-lib==11.12.0
defusedxml==0.7.1
docstring_parser==0.18.0
fastapi==0.165.0
filelock==4.2.12
frozenlist==1.8.0
h11==0.16.0
httpcore==1.0.9
httpcore2==2.16.2
httptools==0.9.0
httpx==0.28.1
httpx2==2.16.2
idna==3.20
iniconfig==2.3.1
jiter==0.19.0
license-expression==30.4.4
Mako==1.4.3
markdown-it-py==4.3.0
MarkupSafe==3.0.4
mdurl==0.1.2
msgpack==1.2.4
multidict==7.2.1
opentelemetry-api==1.45.2
packageurl-python==0.17.6
packaging==26.3
pip-requirements-parser==32.0.1
pip_api==0.0.35
pip_audit==2.10.1
platformdirs==4.14.8
pluggy==1.7.0
propcache==0.5.4
py-serializable==2.2.0
pycparser==3.12
pydantic==2.14.4
pydantic-settings==2.16.3
pydantic_core==2.50.5
Pygments==2.21.0
PyJWT==2.15.1
PyNaCl==1.6.2
pyparsing==3.3.3
pytest==8.4.2
python-dotenv==1.2.4
python-multipart==0.0.34
PyYAML==6.0.4
requests==2.34.2
rich==15.0.0
-e git+https://github.com/zazacknazzo/rj-studio-ai.git@3d93bd18c963894490dd192aa22cc1cc9ec9241b#egg=rj_studio_ai
ruff==0.17.6
sniffio==1.3.1
sortedcontainers==2.4.0
SQLAlchemy==2.1.9
starlette==1.10.0
tomli==2.5.0
tomli_w==1.2.0
truststore==0.10.5
twilio==9.13.0
typing-inspection==0.4.5
typing_extensions==4.16.0
urllib3==2.8.0
uvicorn==0.54.0
uvloop==0.23.0
watchfiles==1.3.0
websockets==17.4
yarl==1.25.1
```

## Integridade dos resultados locais

| Arquivo temporário | SHA256 |
| --- | --- |
|pytest.log (4356bytes)|`9c9edf9b47849c46b8cdd3e637e2d7657aba1be546aa0004306b4ba3c0d7fc74`|
|JUnitXML (302560bytes)|`6933021c610db29fbf25cf004e14ccf7b5f559048bfd4901dd000857119f3026`|
|pipfreeze (1560bytes)|`6376ae6faae3affc3d6c3b7455574b4c8f8e20dfbcbe245aca7754bac9e7172c`|
|pip-auditJSON (12759bytes)|`bcec636498b1fe3a14eb603af4ccef686392e0c99e45c6aa3276c884bfb67f5d`|

Hashes não tornam `/tmp` persistente; comandos, versões, resultados e scripts essenciais estão neste pacote documental para outra conta reproduzir. Não publicamos logs brutos com corpos/credenciais ou bancos. O último SHA remoto verificado e a sequência de checkpoints ficam em [AUDIT-PRE11.md](../../handoffs/AUDIT-PRE11.md).
