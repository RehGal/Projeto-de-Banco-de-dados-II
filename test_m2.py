import os
from pager import Pager, SLOTS_POR_PAGINA
from cache import (
    CachePaginas,
    escreve_registro_em_buffer,
    le_registro_do_buffer,
    varre_registros,
)


def limpa_arquivo(caminho):
    if os.path.exists(caminho):
        os.remove(caminho)


def teste_1_acerto():
    arquivo = "test_m2_acerto.db"
    limpa_arquivo(arquivo)

    pager = Pager(arquivo)
    pager.aloca()
    cache = CachePaginas(pager, capacidade=3)

    # Primeira leitura: falta (1 leitura de disco)
    buf1 = cache.fixa(0)
    cache.solta(0)

    # Segunda leitura da mesma página: acerto (nenhuma nova leitura de disco)
    buf2 = cache.fixa(0)
    cache.solta(0)

    assert buf1 is buf2, "Deve retornar a mesma referência de buffer, não uma cópia"
    assert pager.leituras == 1, f"Esperava 1 leitura de disco, obteve {pager.leituras}"
    assert cache.acertos == 1 and cache.faltas == 1
    assert cache.acertos + cache.faltas == 2

    cache.fecha()
    limpa_arquivo(arquivo)
    print("[OK] Teste 1 - Acerto (hit) e referência única")


def teste_2_expulsao_lru():
    arquivo = "test_m2_lru.db"
    limpa_arquivo(arquivo)

    pager = Pager(arquivo)
    for _ in range(5):
        pager.aloca()

    # Sequência exata do slide: 3 frames, acessos 1, 2, 3, 1, 4 -> expulsa 2
    cache = CachePaginas(pager, capacidade=3)
    for pag in [1, 2, 3, 1, 4]:
        cache.fixa(pag)
        cache.solta(pag)

    paginas_no_cache = set(cache.tabela_paginas.keys())
    assert paginas_no_cache == {3, 1, 4}, f"LRU falhou: esperado {{3, 1, 4}}, obtido {paginas_no_cache}"
    assert cache.acertos == 1
    assert cache.faltas == 4
    assert cache.acertos + cache.faltas == 5

    cache.fecha()
    limpa_arquivo(arquivo)
    print("[OK] Teste 2 - Expulsão LRU")


def teste_3_pagina_suja_e_persistencia():
    arquivo = "test_m2_suja.db"
    limpa_arquivo(arquivo)

    pager = Pager(arquivo)
    for _ in range(5):
        pager.aloca()

    cache = CachePaginas(pager, capacidade=3)

    # Altera a página 1 em memória e marca como suja
    registro_esperado = b"12345678"
    buf = cache.fixa(1)
    try:
        escreve_registro_em_buffer(buf, 0, registro_esperado)
    finally:
        cache.solta(1, suja=True)

    assert pager.escritas == 0, "Página suja não deve ir ao disco antes da expulsão/sync"

    # Acessa páginas 2, 3 e 4 para encher os 3 frames e expulsar a página 1
    for pag in [2, 3, 4]:
        cache.fixa(pag)
        cache.solta(pag)

    assert 1 not in cache.tabela_paginas, "Página 1 deveria ter sido expulsa"
    assert pager.escritas == 1, "Página suja deveria ter sido gravada no disco na expulsão"

    # Encerra completamente e reabre em nova instância (simulando outro processo)
    cache.fecha()

    pager_novo = Pager(arquivo)
    cache_novo = CachePaginas(pager_novo, capacidade=3)
    buf_lido = cache_novo.fixa(1)
    try:
        registro_lido = le_registro_do_buffer(buf_lido, 0)
    finally:
        cache_novo.solta(1)

    assert registro_lido == registro_esperado, f"Esperava {registro_esperado}, leu {registro_lido}"

    cache_novo.fecha()
    limpa_arquivo(arquivo)
    print("[OK] Teste 3 - Página suja gravada na expulsão e validada após reabertura")


def teste_4_todas_fixadas_levanta_erro():
    arquivo = "test_m2_pinned.db"
    limpa_arquivo(arquivo)

    pager = Pager(arquivo)
    for _ in range(4):
        pager.aloca()

    cache = CachePaginas(pager, capacidade=3)

    # Fixa todas as 3 páginas disponíveis sem chamar solta()
    cache.fixa(0)
    cache.fixa(1)
    cache.fixa(2)

    erro_levantado = False
    try:
        cache.fixa(3)
    except RuntimeError:
        erro_levantado = True

    assert erro_levantado, "Deveria levantar erro quando todas as páginas estão fixadas"

    # Solta as páginas antes de encerrar
    cache.solta(0)
    cache.solta(1)
    cache.solta(2)
    cache.fecha()
    limpa_arquivo(arquivo)
    print("[OK] Teste 4 - Erro explícito quando todas as páginas estão fixadas")


def teste_5_medicao_antes_e_depois():
    arquivo = "test_m2_medicao.db"
    limpa_arquivo(arquivo)

    total_paginas = 20
    pager = Pager(arquivo)
    for _ in range(total_paginas):
        pager.aloca()
    pager.close()

    # ANTES (sem cache: cada registro lê a página direto do disco, como no slide)
    pager_sem_cache = Pager(arquivo)
    for _ in range(2):  # Duas varreduras completas
        for n in range(total_paginas):
            for _ in range(SLOTS_POR_PAGINA):
                pager_sem_cache.le_pagina(n)
    leituras_sem_cache = pager_sem_cache.leituras
    pager_sem_cache.close()

    # DEPOIS (com cache de 20 frames e varredura fixando por página)
    pager_com_cache = Pager(arquivo)
    cache = CachePaginas(pager_com_cache, capacidade=20)
    for _ in range(2):  # Duas varreduras completas
        list(varre_registros(cache, total_paginas))
    leituras_com_cache = pager_com_cache.leituras

    assert leituras_com_cache == 20, f"Esperava apenas 20 leituras físicas, obteve {leituras_com_cache}"
    assert cache.acertos == 20 and cache.faltas == 20
    assert cache.acertos + cache.faltas == 40

    print(
        f"[OK] Teste 5 - Medição Antes/Depois (2 varreduras em 20 páginas): "
        f"Sem cache = {leituras_sem_cache} leituras | Com cache = {leituras_com_cache} leituras"
    )

    cache.fecha()
    limpa_arquivo(arquivo)


if __name__ == "__main__":
    teste_1_acerto()
    teste_2_expulsao_lru()
    teste_3_pagina_suja_e_persistencia()
    teste_4_todas_fixadas_levanta_erro()
    teste_5_medicao_antes_e_depois()
    print("\nTodos os testes do M2 passaram com sucesso!")
