"""Senhas e tokens de acesso do painel ColdTrack.

- Senha: scrypt (hashlib) com sal aleatório por usuário. O banco guarda só o
  resultado no formato "scrypt$n$r$p$sal$hash" (base64), nunca a senha.
- Token: JWT HS256 assinado com o segredo da app setting JWT_SECRET, válido
  por 8 horas, com o e-mail (sub), o nome e o perfil do usuário.

Não depende do Azure: testado com `python -m unittest`.
"""

import base64
import hashlib
import hmac
import os
import time

import jwt

PERFIS = ("operador", "gestor")
VALIDADE_TOKEN_S = 8 * 3600

# Custo do scrypt: ~16 MB de memória por tentativa, caro para ataque de força bruta.
N, R, P = 2 ** 14, 8, 1


def _b64(dados):
    return base64.b64encode(dados).decode()


def gerar_hash(senha):
    sal = os.urandom(16)
    derivada = hashlib.scrypt(senha.encode(), salt=sal, n=N, r=R, p=P, dklen=32)
    return f"scrypt${N}${R}${P}${_b64(sal)}${_b64(derivada)}"


def conferir_senha(senha, armazenado):
    try:
        _, n, r, p, sal, esperado = armazenado.split("$")
        derivada = hashlib.scrypt(senha.encode(), salt=base64.b64decode(sal),
                                  n=int(n), r=int(r), p=int(p), dklen=32)
    except (ValueError, TypeError, AttributeError):
        return False
    # Comparação em tempo constante: não revela quantos bytes acertaram.
    return hmac.compare_digest(derivada, base64.b64decode(esperado))


def gerar_token(usuario, segredo, agora=None):
    agora = int(time.time() if agora is None else agora)
    carga = {
        "sub": usuario["id"],
        "nome": usuario["nome"],
        "perfil": usuario["perfil"],
        "iat": agora,
        "exp": agora + VALIDADE_TOKEN_S,
    }
    return jwt.encode(carga, segredo, algorithm="HS256")


def ler_token(token, segredo):
    """Devolve os dados do token ou None se inválido, adulterado ou vencido."""
    try:
        carga = jwt.decode(token, segredo, algorithms=["HS256"],
                           options={"require": ["sub", "perfil", "exp"]})
    except jwt.PyJWTError:
        return None
    return carga if carga.get("perfil") in PERFIS else None


def token_do_cabecalho(valor):
    """Extrai o token de 'Authorization: Bearer <token>'."""
    if not valor or not valor.startswith("Bearer "):
        return None
    return valor[len("Bearer "):].strip() or None
