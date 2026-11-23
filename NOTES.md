# Notas de Desenvolvimento - minidb

## Módulo 1: Página e Arquivo de Dados
- **Posição exata do registro de teste:** O registro gravado no slot 0 da página 2 começa exatamente no **byte 8208** do arquivo em disco (`2 * 4096 + 16 + 0 * 8 = 8208`), ocupando os bytes 8208 a 8215.
- **Decisão de projeto mais difícil:** Isolar o cálculo de deslocamento em uma única função (`deslocamento(pagina, slot)`) e estruturar a classe `Pager` para validar rigorosamente o tamanho dos buffers (4096 bytes) e a existência das páginas alocadas antes de qualquer leitura ou escrita física com `fsync`, evitando corrupção silenciosa ou leitura parcial de páginas vizinhas.

## Módulo 2: Cache de Páginas (Buffer Pool)
- **Decisão de projeto mais difícil:** A decisão mais crítica foi garantir o controle de posse e ciclo de vida dos *frames* em memória por meio do par `fixa` e `solta` (*pin/unpin*) combinado com a devolução direta da referência mutável (`bytearray`) do *frame*, em vez de retornar cópias. Como várias operações podem ler ou alterar a mesma página antes que ela desça ao disco, manter um contador de fixação (`pin_count`) por *frame* e integrar a política LRU (`OrderedDict`) exigiu cuidado para nunca expulsar uma página ainda em uso e, ao mesmo tempo, garantir que qualquer página marcada como suja (`dirty`) seja gravada no disco via `Pager` antes de o *frame* ser reutilizado.
