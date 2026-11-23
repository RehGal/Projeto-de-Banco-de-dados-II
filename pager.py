import os

TAM_PAGINA = 4096
TAM_CABECALHO = 16
TAM_REGISTRO = 8
SLOTS_POR_PAGINA = (TAM_PAGINA - TAM_CABECALHO) // TAM_REGISTRO


def deslocamento(pagina, slot):
    return pagina * TAM_PAGINA + TAM_CABECALHO + slot * TAM_REGISTRO


class Pager:
    def __init__(self, caminho):
        novo = not os.path.exists(caminho)
        self.f = open(caminho, "w+b" if novo else "r+b")

        self.f.seek(0, os.SEEK_END)
        tamanho = self.f.tell()
        if tamanho % TAM_PAGINA != 0:
            self.f.close()
            raise ValueError(f"Arquivo corrompido: tamanho {tamanho} não é múltiplo de {TAM_PAGINA}")

        self.n_paginas = tamanho // TAM_PAGINA
        self.leituras = 0
        self.escritas = 0

    def _valida(self, n):
        if n < 0 or n >= self.n_paginas:
            raise ValueError(f"Erro: Página {n} não existe. Total de páginas: {self.n_paginas}")

    def le_pagina(self, n):
        self._valida(n)
        self.f.seek(n * TAM_PAGINA)
        buf = self.f.read(TAM_PAGINA)

        if len(buf) != TAM_PAGINA:
            raise IOError(f"Página {n} truncada: {len(buf)} bytes lidos")

        self.leituras += 1
        return bytearray(buf)

    def escreve_pagina(self, n, buf):
        self._valida(n)

        if len(buf) != TAM_PAGINA:
            raise ValueError(f"Erro: buffer com {len(buf)} bytes, deveria ter {TAM_PAGINA}")

        self.f.seek(n * TAM_PAGINA)
        self.f.write(buf)
        self.escritas += 1

    def aloca(self):
        n = self.n_paginas
        self.f.seek(n * TAM_PAGINA)
        self.f.write(bytes(TAM_PAGINA))
        self.n_paginas += 1
        return n

    def sync(self):
        self.f.flush()
        os.fsync(self.f.fileno())

    def close(self):
        self.sync()
        self.f.close()
