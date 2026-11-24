"""Senhas, tokens e 2FA (TOTP) do painel ColdTrack.

- Senha: scrypt (hashlib) com sal aleatório por usuário. O banco guarda só o
  resultado no formato "scrypt$n$r$p$sal$hash" (base64), nunca a senha.
- Token: JWT HS256 assinado com o segredo da app setting JWT_SECRET, válido
  por 8 horas, com o e-mail (sub), o nome, o perfil, a empresa (emp) e a versão
  da sessão (ver). Trocar a senha sobe a versão e derruba os tokens antigos.
- Login: a partir da 5ª senha errada seguida, a conta entra em espera de 1 min,
  que dobra a cada nova falha (2, 4, 8 min) até o teto de 15 min. Durante a
  espera nem a senha certa entra, e as tentativas não aumentam a espera.
  Falhas com mais de 24 h são esquecidas.
- Chave de dispositivo: 32 bytes aleatórios; o banco guarda só o SHA-256.
- 2FA (TOTP): segredo base32 por usuário, QR Code otpauth://, 10 códigos de
  recuperação (hash scrypt, uso único), anti-replay via contador TOTP.

Não depende do Azure: testado com `python -m unittest`.
"""

import base64
import hashlib
import hmac
import logging
import os
import secrets
import time
from typing import Optional

import jwt
import pyotp

# motorista: só vê o veículo vinculado a ele (GET /motorista) e a própria conta.
PERFIS = ("operador", "gestor", "motorista")
VALIDADE_TOKEN_S = 8 * 3600
MAX_FALHAS = 5
ESPERA_BASE_S = 60
ESPERA_MAX_S = 15 * 60
ESQUECER_FALHAS_S = 24 * 3600

# Custo do scrypt: ~16 MB de memória por tentativa, caro para ataque de força bruta.
N, R, P = 2 ** 14, 8, 1

# 2FA: códigos de recuperação
RECUPERACAO_QTD = 10
RECUPERACAO_TAM = 8  # caracteres alfanuméricos minúsculos
RECUPERACAO_ALFABETO = "abcdefghijklmnopqrstuvwxyz0123456789"

# Desafio 2FA no login: JWT de 5 min
DESAFIO_2FA_VALIDADE_S = 5 * 60


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
        "emp": usuario["empresaId"],
        "ver": usuario.get("sessao", 0),
        "iat": agora,
        "exp": agora + VALIDADE_TOKEN_S,
    }
    return jwt.encode(carga, segredo, algorithm="HS256")


def ler_token(token, segredo):
    """Devolve os dados do token ou None se inválido, adulterado ou vencido."""
    try:
        carga = jwt.decode(token, segredo, algorithms=["HS256"],
                           options={"require": ["sub", "perfil", "emp", "exp"]})
    except jwt.PyJWTError:
        return None
    return carga if carga.get("perfil") in PERFIS else None


def token_do_cabecalho(valor):
    """Extrai o token de 'Authorization: Bearer <token>'."""
    if not valor or not valor.startswith("Bearer "):
        return None
    return valor[len("Bearer "):].strip() or None


# ------------------------------------------------------------ espera do login

def bloqueado_ate(usuario, agora=None):
    """Epoch até quando a conta está em espera, ou 0 se está liberada."""
    agora = time.time() if agora is None else agora
    fim = usuario.get("bloqueadoAte", 0) or 0
    return fim if fim > agora else 0


def espera_para(falhas):
    """Segundos de espera depois de `falhas` senhas erradas seguidas (0 = sem espera)."""
    if falhas < MAX_FALHAS:
        return 0
    return min(ESPERA_BASE_S * 2 ** min(falhas - MAX_FALHAS, 10), ESPERA_MAX_S)


def operacoes_de_falha(usuario, agora=None):
    """Operações de patch do Cosmos que contam uma senha errada.

    Só mexem em `falhas` e `ultimaFalha`: um patch não sobrescreve a senha nem a
    sessão, mesmo que elas tenham mudado depois da leitura. A soma é atômica no
    banco (`incr`), então duas tentativas ao mesmo tempo contam duas.
    """
    agora = time.time() if agora is None else agora
    recente = agora - (usuario.get("ultimaFalha") or 0) < ESQUECER_FALHAS_S
    contar = ({"op": "incr", "path": "/falhas", "value": 1} if recente
              else {"op": "set", "path": "/falhas", "value": 1})
    return [contar, {"op": "set", "path": "/ultimaFalha", "value": int(agora)}]


OPERACOES_DE_SUCESSO = [{"op": "set", "path": "/falhas", "value": 0},
                        {"op": "set", "path": "/bloqueadoAte", "value": 0}]


# ------------------------------------------------------------ logs

def mascarar_email(email):
    """'ana.souza@vale.com' -> 'a***@vale.com': o log mostra o domínio, não a pessoa."""
    if not isinstance(email, str) or not email:
        return "(vazio)"
    nome, arroba, dominio = email.partition("@")
    if not arroba:
        return email[:1] + "***"
    return f"{nome[:1]}***@{dominio}"


def _codigo_missao() -> str:
    """Lê o código de missão do ambiente (placeholder até o professor enviar)."""
    return os.environ.get("MISSAO_CODIGO", "SEM_CODIGO")


def log_2fa_bloqueado(motivo: str, email: str = "") -> None:
    """Registra bloqueio de 2FA no formato esperado pelo Log Analytics."""
    logging.warning("2fa bloqueado [%s] - %s - %s", _codigo_missao(), motivo, mascarar_email(email))


def log_idor_bloqueado(recurso: str, detalhe: str = "") -> None:
    """Registra bloqueio de IDOR no formato esperado pelo Log Analytics."""
    logging.warning("idor bloqueado [%s] - %s%s", _codigo_missao(), recurso, f" - {detalhe}" if detalhe else "")


# ------------------------------------------------------------ chave de dispositivo

def gerar_chave_dispositivo():
    return secrets.token_urlsafe(32)


def hash_chave(chave):
    # A chave já é aleatória e longa: SHA-256 basta (scrypt a cada leitura
    # de 20 s custaria CPU sem ganho de segurança).
    return hashlib.sha256(chave.encode()).hexdigest()


def conferir_chave(chave, armazenado):
    if not isinstance(chave, str) or not chave or not isinstance(armazenado, str):
        return False
    return hmac.compare_digest(hash_chave(chave), armazenado)

# ------------------------------------------------------------ 2FA (TOTP)


def gerar_totp_secret() -> str:
    """Gera um segredo base32 aleatório para TOTP (RFC 6238)."""
    return pyotp.random_base32()


def totp_uri(segredo: str, email: str, emissor: str = "ColdTrack") -> str:
    """Monta a URI otpauth:// para QR Code."""
    return pyotp.totp.TOTP(segredo).provisioning_uri(name=email, issuer_name=emissor)


def verificar_totp(segredo: str, codigo: str, contador_usado: int, janela: int = 1) -> tuple[bool, int]:
    """Verifica um código TOTP de 6 dígitos com proteção anti-replay.

    Args:
        segredo: segredo base32 do usuário
        codigo: código de 6 dígitos informado
        contador_usado: último contador (time-step) aceito para este usuário
        janela: tolerância de passos adjacentes (padrão 1 = ±30s)

    Returns:
        (valido, novo_contador): True se código válido e não repetido; novo contador a gravar
    """
    if not isinstance(codigo, str) or not codigo.isdigit() or len(codigo) != 6:
        return False, contador_usado

    totp = pyotp.TOTP(segredo)
    agora = int(time.time())
    contador_atual = totp.timecode(agora)

    # Verifica na janela permitida
    for delta in range(-janela, janela + 1):
        contador_teste = contador_atual + delta
        if totp.at(contador_teste) == codigo:
            # Anti-replay: contador deve ser maior que o último usado
            if contador_teste <= contador_usado:
                return False, contador_usado
            return True, contador_teste

    return False, contador_usado


def gerar_recovery_codes(qtd: int = RECUPERACAO_QTD, tam: int = RECUPERACAO_TAM) -> list[str]:
    """Gera códigos de recuperação aleatórios (alfanuméricos minúsculos)."""
    return [
        "".join(secrets.choice(RECUPERACAO_ALFABETO) for _ in range(tam))
        for _ in range(qtd)
    ]


def hash_recovery_codes(codigos: list[str]) -> list[str]:
    """Hash scrypt de cada código de recuperação (normaliza para minúsculas)."""
    return [gerar_hash(c.lower()) for c in codigos]


def verificar_recovery_code(codigo: str, hashes: list[str]) -> tuple[bool, list[str]]:
    """Verifica um código de recuperação e o invalida (remove do array).

    Returns:
        (valido, hashes_restantes): True se código encontrado e removido
    """
    if not isinstance(codigo, str):
        return False, hashes
    codigo = codigo.lower().strip()
    for i, h in enumerate(hashes):
        if conferir_senha(codigo, h):
            # Remove o hash usado (uso único)
            restantes = hashes[:i] + hashes[i + 1 :]
            return True, restantes
    return False, hashes


def gerar_desafio_2fa(usuario: dict, segredo_jwt: str, agora: Optional[int] = None) -> str:
    """Gera JWT curto (5 min) como desafio do 2º passo do login."""
    agora = int(time.time() if agora is None else agora)
    carga = {
        "sub": usuario["id"],
        "2fa": True,
        "emp": usuario["empresaId"],
        "iat": agora,
        "exp": agora + DESAFIO_2FA_VALIDADE_S,
    }
    return jwt.encode(carga, segredo_jwt, algorithm="HS256")


def ler_desafio_2fa(token: str, segredo_jwt: str) -> Optional[str]:
    """Lê o desafio 2FA e devolve o e-mail (sub) se válido."""
    try:
        carga = jwt.decode(
            token,
            segredo_jwt,
            algorithms=["HS256"],
            options={"require": ["sub", "2fa", "exp"]},
        )
    except jwt.PyJWTError:
        return None
    if not carga.get("2fa"):
        return None
    return carga.get("sub")
