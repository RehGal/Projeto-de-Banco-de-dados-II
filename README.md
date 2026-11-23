# minidb 

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

------------------------------------------------------------------------------------------------------------------------------------------------------------


## Módulo 2 — Cache de Páginas (Buffer Pool)

Camada de gerenciamento de memória (*buffer pool*) do **minidb**. O `CachePaginas` atua acima do `Pager` (M1), mantendo páginas de 4096 bytes em *frames* na memória principal para evitar leituras e escritas repetidas em disco, sem usar nenhuma biblioteca externa de banco de dados.

### Visão geral

- **Linguagem:** Python 3
- **Dependências:** nenhuma (apenas biblioteca padrão: `os` e `collections.OrderedDict`)
- **Tamanho do frame:** 4096 bytes (mesmo tamanho da página em disco)
- **Política de substituição:** LRU (*Least Recently Used*)
- **Política de escrita:** *write-back* com bit de sujeira (*dirty*) na expulsão

### Arquitetura do cache

Toda leitura ou escrita de página passa exclusivamente pelo cache, nunca direto pelo arquivo em disco:


```

Arquivo (.db)   [ p0 ][ p1 ][ p2 ][ p3 ] ... [ p19 ]   (4096 bytes cada)
|           |
v           v
Cache (RAM)     [ frame 0 ][ frame 1 ][ frame 2 ]      (bytearray mutável)
p1         p3        livre

Tabela de páginas: { 1: 0, 3: 1 }   (pagina -> frame)

```

#### Política de substituição (LRU)

Quando o cache enche, sai a página **lida/acessada há mais tempo** (que não esteja fixada). Cada novo acerto (*hit*) move a página para o fim da fila:


```

Capacidade: 3 frames | Sequência de acessos: 1, 2, 3, 1, 4

acesso   fila LRU    ação do cache
1      [1]         falta (miss) -> leu do disco
2      [1, 2]      falta (miss) -> leu do disco
3      [1, 2, 3]   falta (miss) -> cache encheu
1      [2, 3, 1]   acerto (hit) -> sem tocar no disco (pág. 1 foi para o fim)
4      [3, 1, 4]   falta (miss) -> expulsou a pág. 2 (menos usada recentemente)

```

### API

| Método / Função | Descrição |
|---|---|
| `CachePaginas(pager, capacidade=16)` | Inicializa o *buffer pool* com `capacidade` *frames* de 4096 bytes. |
| `fixa(n)` | Fixa (*pin*) a página `n` em memória e devolve a referência direta ao `bytearray` do *frame*. |
| `marca_suja(n)` | Marca a página `n` como modificada (*dirty*) em memória. |
| `solta(n, suja=False)` | Libera (*unpin*) a página `n` para que possa ser expulsa futuramente (opcionalmente marcando como suja). |
| `sincroniza()` | Grava no disco todas as páginas sujas em memória e executa `fsync`. |
| `fecha()` | Chama `sincroniza()` e fecha o arquivo do `Pager`. |
| `varre_registros(cache, n_paginas)` | Percorre todos os registros fixando cada página uma única vez e soltando com `try/finally`. |

#### Validações e garantias (falha alta)

- Solicitar uma página inexistente levanta `ValueError`.
- Se o cache estiver cheio e **todas** as páginas estiverem fixadas (`pin_count > 0`), a próxima falta levanta `RuntimeError` em vez de expulsar uma página em uso.
- Chamar `solta(n)` em uma página não carregada ou já solta levanta `ValueError` / `RuntimeError`.
- Páginas marcadas como sujas são gravadas obrigatoriamente no disco via `Pager.escreve_pagina` antes de o *frame* ser reutilizado na expulsão.
- A soma `acertos + faltas` é sempre igual ao número total de chamadas feitas a `fixa`.

### Exemplo de uso

```python
from pager import Pager
from cache import CachePaginas, escreve_registro_em_buffer, le_registro_do_buffer

pager = Pager("teste.db")
pager.aloca()

cache = CachePaginas(pager, capacidade=4)

# Fixa a página 0, altera o slot 0 e garante o solta() no finally
buf = cache.fixa(0)
try:
    escreve_registro_em_buffer(buf, 0, b"12345678")
finally:
    cache.solta(0, suja=True)

cache.fecha()

# Reabre em outro processo e lê de volta
pager = Pager("teste.db")
cache = CachePaginas(pager, capacidade=4)
buf = cache.fixa(0)
try:
    print(le_registro_do_buffer(buf, 0))  # b'12345678'
finally:
    cache.solta(0)
cache.fecha()

```

### Testes

O script de testes (`test_m2.py`) configura caches reduzidos (3 *frames*) para forçar expulsões e valida:

1. **Acerto (*hit*):** ler a mesma página duas vezes realiza apenas 1 leitura física no disco e devolve a mesma referência de memória.
2. **Expulsão LRU:** com 3 *frames*, acessar `1, 2, 3, 1, 4` expulsa a página `2`.
3. **Página suja (*dirty*):** alterar uma página em memória, forçar sua expulsão, encerrar o programa e reabrir o arquivo confirma que o dado foi persistido em disco.
4. **Proteção contra expulsão fixada:** fixar todos os *frames* e pedir uma página ausente levanta `RuntimeError`.
5. **Medição antes e depois:** compara o total de leituras físicas em duas varreduras completas sobre 20 páginas (510 slots/página) sem cache e com cache.

Para executar:

```bash
python test_m2.py

```

Saída esperada:

```
[OK] Teste 1 - Acerto (hit) e referência única
[OK] Teste 2 - Expulsão LRU
[OK] Teste 3 - Página suja gravada na expulsão e validada após reabertura
[OK] Teste 4 - Erro explícito quando todas as páginas estão fixadas
[OK] Teste 5 - Medição Antes/Depois (2 varreduras em 20 páginas): Sem cache = 20400 leituras | Com cache = 20 leituras

Todos os testes do M2 passaram com sucesso!

```

### Medição antes e depois

Em um cenário com **20 páginas** (510 slots de 8 bytes por página) percorridas em **2 varreduras completas**:

* **Sem cache (lendo o disco a cada registro):** `20.400` leituras físicas de disco.
* **Com cache (20 frames + fixação por página):** `20` leituras físicas na primeira varredura (`faltas = 20`) e `0` leituras físicas na segunda varredura (`acertos = 20`), reduzindo o acesso ao disco em mais de **1.000x**.

### Decisão de projeto mais difícil

Garantir o controle de posse e ciclo de vida dos *frames* em memória por meio do par `fixa` e `solta` (*pin/unpin*) combinado com a devolução direta da referência mutável (`bytearray`) do *frame*, em vez de retornar cópias. Como várias operações podem ler ou alterar a mesma página antes que ela desça ao disco, manter um contador de fixação (`pin_count`) por *frame* e integrar a política LRU (`OrderedDict`) exigiu cuidado para nunca expulsar uma página ainda em uso e, ao mesmo tempo, garantir que qualquer página marcada como suja (`dirty`) seja gravada no disco via `Pager` antes de o *frame* ser reutilizado.

### Estrutura do repositório

```
.
├── pager.py
├── cache.py
├── test_m2.py
├── NOTES.md
└── README.md
```
