# Registro v8 histórico recuperado

`live-record-v8.json` é cópia byte a byte do artefato original
`work/evals/openai-agentic-surface-smoke-2026-10-04-01/phase-A.json`, recuperado em
22/11/2026 de um workspace anterior, não fabricado/regenerado nesta tarefa.
SHA256: `3d849ff3465d44cf20898aa170e72c08cc99b12e2f1b3266324754818291451e`.
O próprio registro informa criação2026-10-04T17:45:57.312894Z, revisão
8f1b3d8ce33e89908581239e90882da7dae2f95d, schema8 e10casos sintéticos.

Inspecionado: contém contratos/IDs de casos, hashes, contadores/latências, decisões
e observações mínimas de grounding. Não contém corpo de Message, prompt/resposta
privados, endereço de Customer ou credencial; Gitleaks do diretório original retornou
zero detecções. Nenhuma chamada de modelo foi executada para recuperá-lo.

O teste agora usa esse arquivo versionado e verifica seu hash antes do parse.
Isso elimina a dependência do diretório privado e o skip histórico. Valida leitura
compatível do registro antigo, sem revalidar geração/modelo, naturalidade humana,
preços atuais ou E2E WhatsApp; `live_generation` é metadado da execução HISTÓRICA.
