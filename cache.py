from collections import OrderedDict
from pager import TAM_PAGINA, TAM_CABECALHO, TAM_REGISTRO, SLOTS_POR_PAGINA


class CachePaginas:
    def __init__(self, pager, capacidade=16):
        if capacidade <= 0:
            raise ValueError("A capacidade do cache deve ser maior que zero.")

        self.pager = pager
        self.capacidade = capacidade

        # Frames pré-alocados de 4096 bytes (buffers mutáveis)
        self.frames = [bytearray(TAM_PAGINA) for _ in range(capacidade)]
        self.livres = list(range(capacidade))

        # Tabela de páginas: numero_pagina -> indice_frame
        self.tabela_paginas = {}
        self.frame_para_pagina = {}

        # Metadados por frame
        self.pin_count = [0] * capacidade
        self.suja = [False] * capacidade

        # Fila LRU: início = lida há mais tempo (próxima a sair), fim = mais recente
        self.lru = OrderedDict()

        # Contadores de métricas
        self.acertos = 0
        self.faltas = 0

    def _escolhe_vitima(self):
        for pagina in list(self.lru.keys()):
            frame_id = self.tabela_paginas[pagina]
            if self.pin_count[frame_id] == 0:
                if self.suja[frame_id]:
                    self.pager.escreve_pagina(pagina, self.frames[frame_id])
                    self.suja[frame_id] = False

                del self.tabela_paginas[pagina]
                del self.frame_para_pagina[frame_id]
                del self.lru[pagina]
                return frame_id

        raise RuntimeError("Cache cheio e todas as páginas estão fixadas (pinned).")

    def fixa(self, n):
        self.pager._valida(n)

        if n in self.tabela_paginas:
            self.acertos += 1
            frame_id = self.tabela_paginas[n]
            self.pin_count[frame_id] += 1
            self.lru.move_to_end(n)
            return self.frames[frame_id]

        self.faltas += 1
        if self.livres:
            frame_id = self.livres.pop(0)
        else:
            frame_id = self._escolhe_vitima()

        dados = self.pager.le_pagina(n)
        self.frames[frame_id][:] = dados

        self.tabela_paginas[n] = frame_id
        self.frame_para_pagina[frame_id] = n
        self.pin_count[frame_id] = 1
        self.suja[frame_id] = False
        self.lru[n] = None

        return self.frames[frame_id]

    def marca_suja(self, n):
        if n not in self.tabela_paginas:
            raise ValueError(f"Página {n} não está carregada no cache.")
        frame_id = self.tabela_paginas[n]
        self.suja[frame_id] = True

    def solta(self, n, suja=False):
        if n not in self.tabela_paginas:
            raise ValueError(f"Página {n} não está carregada no cache.")

        frame_id = self.tabela_paginas[n]
        if suja:
            self.suja[frame_id] = True

        if self.pin_count[frame_id] <= 0:
            raise RuntimeError(f"Página {n} já está solta (pin_count == 0).")

        self.pin_count[frame_id] -= 1

    def sincroniza(self):
        for pagina, frame_id in self.tabela_paginas.items():
            if self.suja[frame_id]:
                self.pager.escreve_pagina(pagina, self.frames[frame_id])
                self.suja[frame_id] = False
        self.pager.sync()

    def fecha(self):
        self.sincroniza()
        self.pager.close()


def escreve_registro_em_buffer(buf, slot, dados_8_bytes):
    if len(dados_8_bytes) != TAM_REGISTRO:
        raise ValueError(f"Registro deve ter exatamente {TAM_REGISTRO} bytes.")
    inicio = TAM_CABECALHO + slot * TAM_REGISTRO
    buf[inicio : inicio + TAM_REGISTRO] = dados_8_bytes


def le_registro_do_buffer(buf, slot):
    inicio = TAM_CABECALHO + slot * TAM_REGISTRO
    return bytes(buf[inicio : inicio + TAM_REGISTRO])


def varre_registros(cache, n_paginas, slots_por_pagina=SLOTS_POR_PAGINA):
    for n in range(n_paginas):
        buf = cache.fixa(n)
        try:
            for slot in range(slots_por_pagina):
                yield le_registro_do_buffer(buf, slot)
        finally:
            cache.solta(n)
