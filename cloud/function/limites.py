"""Limites de uso das rotas públicas e do login, compartilhados entre instâncias.

A Function roda em várias instâncias ao mesmo tempo (Flex Consumption): um
contador em memória deixaria cada instância contar sozinha. Por isso os
contadores ficam no Cosmos, no container `limites` (nome em LIMITES_CONTAINER),
com chave de partição /id e TTL ligado: cada contador some sozinho depois que a
janela acaba.

Cada contador é uma janela fixa (por exemplo, o minuto ou o dia corrente). A
soma é atômica no banco (`patch_item` com `incr`), então duas instâncias
contando ao mesmo tempo não perdem chamada. O id do documento é um hash da
chave: e-mail e IP não ficam gravados em texto.

Se o container não existir (ambiente antigo, teste local), o contador cai para
a memória da instância e avisa uma vez no log. Falha passageira do banco também
cai para a memória naquela chamada: o limite fica mais frouxo, mas a rota não
para.

Não depende do Azure para ser testado: o container é trocado por um falso.
"""

import hashlib
import logging
import threading
import time

from azure.cosmos import exceptions

MINUTO = 60
DIA = 24 * 3600
# Folga do TTL depois do fim da janela, para o contador não sumir no meio dela.
FOLGA_TTL_S = 300


# ------------------------------------------------------------ IP de quem chama

def _sem_porta(bruto):
    bruto = bruto.strip()
    if bruto.startswith("["):  # IPv6 com porta: [::1]:5678
        return bruto[1:bruto.find("]")] if "]" in bruto else bruto
    if bruto.count(":") == 1:  # IPv4 com porta: 1.2.3.4:5678
        return bruto.split(":")[0]
    return bruto


def ip_do_cliente(headers):
    """IP de quem chamou a API.

    O Azure põe o IP real em X-Azure-ClientIP. Sem ele, vale o ÚLTIMO item do
    X-Forwarded-For: o front do Azure acrescenta o IP que viu no fim da lista, e
    o que vem antes pode ter sido escrito pelo próprio cliente (falso).
    """
    azure = _sem_porta(headers.get("x-azure-clientip") or "")
    if azure:
        return azure
    saltos = [s for s in (headers.get("x-forwarded-for") or "").split(",") if s.strip()]
    if saltos:
        return _sem_porta(saltos[-1]) or "desconhecido"
    return _sem_porta(headers.get("x-client-ip") or "") or "desconhecido"


# ------------------------------------------------------------ plano B em memória

class JanelaEmMemoria:
    """Contadores de janela fixa na memória da instância (plano B do Cosmos)."""

    def __init__(self):
        self._contas = {}
        self._trava = threading.Lock()

    def contar(self, doc_id, fim, somar, agora):
        with self._trava:
            if len(self._contas) > 5000:
                for chave in [c for c, (_, f) in self._contas.items() if f <= agora]:
                    del self._contas[chave]
            n, _ = self._contas.get(doc_id, (0, fim))
            n += somar
            self._contas[doc_id] = (n, fim)
            return n

    def total(self, doc_id):
        with self._trava:
            return self._contas.get(doc_id, (0, 0))[0]

    def limpar(self):
        with self._trava:
            self._contas.clear()


# ------------------------------------------------------------ contadores no Cosmos

class Limites:
    """Contadores por janela fixa guardados no Cosmos, com plano B em memória.

    `obter_container` é uma função sem argumentos que devolve o ContainerProxy
    do container `limites` (a function_app passa a dela; os testes, um falso).
    """

    def __init__(self, obter_container):
        self._obter = obter_container
        self._container = None
        self._sem_container = False
        self._memoria = JanelaEmMemoria()
        self._trava = threading.Lock()

    def reiniciar(self):
        """Esquece o container e zera a memória (testes e troca de configuração)."""
        with self._trava:
            self._container = None
            self._sem_container = False
        self._memoria.limpar()

    def _banco(self):
        """O container, ou None se ele não existe (aí vale a memória)."""
        if self._sem_container:
            return None
        if self._container is None:
            with self._trava:
                if self._container is None and not self._sem_container:
                    try:
                        c = self._obter()
                        c.read()  # confere uma vez por instância se o container existe
                        self._container = c
                    except exceptions.CosmosResourceNotFoundError:
                        self._sem_container = True
                        logging.warning("limites: container de limites não existe; "
                                        "contando na memória de cada instância")
                        return None
        return self._container

    @staticmethod
    def _janela(chave, janela_s, agora):
        inicio = int(agora // janela_s) * janela_s
        doc_id = hashlib.sha256(chave.encode()).hexdigest()[:40] + f"-{inicio}"
        return doc_id, inicio + janela_s

    def contar(self, chave, janela_s, somar=1, agora=None):
        """Soma `somar` ao contador da janela corrente e devolve o total da janela."""
        agora = time.time() if agora is None else agora
        doc_id, fim = self._janela(chave, janela_s, agora)
        try:
            banco = self._banco()
            if banco is not None:
                return self._somar_no_banco(banco, doc_id, somar, int(fim - agora) + FOLGA_TTL_S)
        except Exception as e:  # banco fora do ar: conta na memória nesta chamada
            logging.warning("limites: falha no banco (%s); contando na memória",
                            type(e).__name__)
        return self._memoria.contar(doc_id, fim, somar, agora)

    def total(self, chave, janela_s, agora=None):
        """Total da janela corrente, sem somar nada."""
        agora = time.time() if agora is None else agora
        doc_id, _ = self._janela(chave, janela_s, agora)
        try:
            banco = self._banco()
            if banco is not None:
                try:
                    return int(banco.read_item(doc_id, partition_key=doc_id).get("n", 0))
                except exceptions.CosmosResourceNotFoundError:
                    return 0
        except Exception as e:
            logging.warning("limites: falha no banco (%s); lendo da memória", type(e).__name__)
        return self._memoria.total(doc_id)

    def permitir(self, chave, maximo, janela_s, agora=None):
        """Conta esta chamada e diz se ela ainda cabe no limite da janela."""
        return self.contar(chave, janela_s, agora=agora) <= maximo

    @staticmethod
    def _somar_no_banco(banco, doc_id, somar, ttl):
        operacao = [{"op": "incr", "path": "/n", "value": somar}]
        try:
            return int(banco.patch_item(doc_id, partition_key=doc_id,
                                        patch_operations=operacao)["n"])
        except exceptions.CosmosResourceNotFoundError:
            pass
        try:
            banco.create_item({"id": doc_id, "n": somar, "ttl": ttl})
            return somar
        except exceptions.CosmosResourceExistsError:
            # Outra instância criou no meio do caminho: soma no dela.
            return int(banco.patch_item(doc_id, partition_key=doc_id,
                                        patch_operations=operacao)["n"])
