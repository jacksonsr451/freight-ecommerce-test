# Execução de demonstração local

Este repositório não define um deployment de produção. O Compose e os comandos abaixo executam uma
demonstração local; não são uma receita de hospedagem, SLA, hardening ou homologação externa.

## Requisitos e inicialização

Instale Docker Engine/Desktop com Compose v2 e execute na raiz:

```text
python scripts/dev.py setup
python scripts/dev.py compose-check
python scripts/dev.py up
docker compose ps
```

Compose publica frontend, backend e PostgreSQL somente em loopback por padrão. PostgreSQL usa volume
nomeado persistente. Migrations e seed não executam automaticamente:

```text
python scripts/dev.py migrate
python scripts/dev.py seed
```

Frontend local: `http://127.0.0.1:5173`. API: `http://127.0.0.1:8000`. O healthcheck da API comprova
liveness, não conexão ou migrations do banco.

## Encerramento e testes

```text
python scripts/dev.py down
python scripts/dev.py compose-test
```

`down` para o Compose normal e preserva seu volume. `compose-test` usa um projeto/volume temporário e
remove seus recursos no cleanup. `down --volumes` não faz parte do fluxo normal porque remove os dados
persistentes locais.

## Limites

Modo de frete padrão é mock e sintético. Pedido/pagamento são simulados. Configurar `FREIGHT_MODE=real`
não comprova autorização, ambiente correto, oferta, aceitação de despacho, atualização de tracking ou
entrega. Não aponte esta demonstração para tráfego público sem uma revisão e um projeto de implantação
separados. A homologação real segue somente `docs/homologacao.md` e a fonte contratual versionada.
