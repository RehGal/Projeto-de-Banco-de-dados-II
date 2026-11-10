# minidb — Módulo Pager

Camada de armazenamento em disco do **minidb**, um banco de dados didático. O `Pager` gerencia um arquivo dividido em páginas de tamanho fixo (4096 bytes), oferecendo leitura, escrita e alocação de páginas, sem usar nenhuma biblioteca externa de banco de dados.

## Visão geral

- **Linguagem:** Python 3
- **Dependências:** nenhuma (apenas biblioteca padrão: `os`)
- **Tamanho da página:** 4096 bytes
- **Cabeçalho da página:** 16 bytes (reservados; bytes 8–15 guardam espaço para um LSN futuro)
- **Tamanho do registro:** 8 bytes

## Estrutura do arquivo

```
| Página 0 | Página 1 | Página 2 | ... | Página N-1 |
|  4096 B  |  4096 B  |  4096 B  |     |   4096 B   |
```

Cada página:

```
| Cabeçalho (16 B) | Slot 0 (8 B) | Slot 1 (8 B) | ... |
```

O deslocamento de um registro no arquivo é:

```python
deslocamento(pagina, slot) = pagina * 4096 + 16 + slot * 8
```

Exemplo: o slot 0 da página 2 fica em `2 * 4096 + 16 + 0 * 8 = 8208`.

## API

| Método | Descrição |
|---|---|
| `Pager(caminho)` | Abre o arquivo (cria se não existir) e calcula o número de páginas. |
| `le_pagina(n)` | Retorna a página `n` como `bytearray` de 4096 bytes. |
| `escreve_pagina(n, buf)` | Grava `buf` (exatamente 4096 bytes) na página `n`. |
| `aloca()` | Acrescenta uma página zerada ao fim do arquivo e retorna seu número. |
| `sync()` | Faz `flush` + `fsync`, forçando a escrita em disco. |
| `close()` | Chama `sync()` e fecha o arquivo. |

### Validações (falha alta)

- Acessar uma página inexistente levanta `ValueError`.
- Escrever um buffer com tamanho diferente de 4096 bytes levanta `ValueError`.
- Ler uma página truncada levanta `IOError`.

## Exemplo de uso

```python
from pager import Pager, TAM_PAGINA

pager = Pager("teste.db")

for _ in range(4):
    pager.aloca()

pager.escreve_pagina(2, b"A" * TAM_PAGINA)
pager.escreve_pagina(3, b"B" * TAM_PAGINA)
pager.close()

pager = Pager("teste.db")
print(pager.le_pagina(2) == b"A" * TAM_PAGINA)  # True
pager.close()
```

## Testes

O script de teste (bloco `if __name__ == "__main__"`) verifica:

1. **Ida e volta:** a página 2 lida após reabrir o arquivo tem 4096 bytes e conteúdo igual ao gravado.
2. **Vizinha intacta:** o primeiro byte da página 3 continua `B`.
3. **Alinhamento:** o tamanho do arquivo é múltiplo de 4096.

Para executar:

```bash
python pager.py
```

Saída esperada:

```
Tamanho e igualdade da Pág 2 (Ida e volta): 4096 True
Primeiro byte da Pág 3 (Vizinha intacta): b'B'
Tamanho do arquivo é múltiplo de 4096? True
```

## Decisão de projeto mais difícil

Definir como gerenciar a criação do arquivo e a alocação de páginas vazias de forma segura. Optamos por uma classe `Pager` que encapsula o arquivo aberto e valida estritamente todas as entradas de `le_pagina` e `escreve_pagina`. O desafio foi garantir que o programa falhasse alto, com exceções claras, caso o buffer não tivesse exatamente 4096 bytes, em vez de corrigir o tamanho silenciosamente, o que poderia mascarar bugs de corrupção de dados mais adiante.

## Byte do registro de teste

O registro do slot 0 da página 2 foi parar no **byte 8208** do arquivo:

- Início da página 2: `2 * 4096 = 8192`
- Pulo do cabeçalho: `8192 + 16 = 8208`
- Início do slot 0: `8208 + 0 * 8 = 8208`

## Estrutura do repositório

```
.
├── pager.py
├── NOTES.md
└── README.md
```
