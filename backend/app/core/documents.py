"""Normalização e validação de CPF/CNPJ dos cadastros.

Guardamos apenas os dígitos: máscara é assunto de apresentação, e duas grafias
do mesmo documento ("12.345.678/0001-95" e "12345678000195") furariam o índice
único das tabelas de clientes e representantes.
"""

_CPF_LENGTH = 11
_CNPJ_LENGTH = 14
_CNPJ_WEIGHTS = (5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2)


def _check_digit_cpf(digits: str, weight_start: int) -> int:
    total = sum(
        int(digit) * (weight_start - position)
        for position, digit in enumerate(digits)
    )
    remainder = (total * 10) % 11
    return 0 if remainder == 10 else remainder


def _check_digit_cnpj(digits: str) -> int:
    # Os pesos reiniciam em 9 depois do 2: para o segundo dígito o 6 entra na
    # frente da mesma sequência, por isso a fatia pelo fim.
    weights = ((6,) + _CNPJ_WEIGHTS)[-len(digits):]
    remainder = sum(int(d) * w for d, w in zip(digits, weights)) % 11
    return 0 if remainder < 2 else 11 - remainder


def _is_valid_cpf(digits: str) -> bool:
    return (
        _check_digit_cpf(digits[:9], 10) == int(digits[9])
        and _check_digit_cpf(digits[:10], 11) == int(digits[10])
    )


def _is_valid_cnpj(digits: str) -> bool:
    return (
        _check_digit_cnpj(digits[:12]) == int(digits[12])
        and _check_digit_cnpj(digits[:13]) == int(digits[13])
    )


def normalize_cpf_cnpj(value: object) -> str:
    """Devolve o documento só com dígitos ou levanta ValueError.

    Valida o dígito verificador porque o comprimento sozinho aceita qualquer
    tecla repetida — e um CPF errado só aparece na hora de emitir a nota.
    """
    if not isinstance(value, str):
        raise ValueError("CPF/CNPJ deve ser informado como texto.")
    digits = "".join(character for character in value if character.isdigit())
    if not digits:
        raise ValueError("CPF/CNPJ obrigatório.")
    if len(digits) not in (_CPF_LENGTH, _CNPJ_LENGTH):
        raise ValueError(
            f"CPF/CNPJ deve ter {_CPF_LENGTH} ou {_CNPJ_LENGTH} dígitos "
            f"(recebido: {len(digits)})."
        )
    # 111.111.111-11 fecha a conta do dígito verificador; só a checagem de
    # repetição barra esse preenchimento de teclado.
    if digits == digits[0] * len(digits):
        raise ValueError("CPF/CNPJ inválido: dígitos repetidos.")
    valid = _is_valid_cpf(digits) if len(digits) == _CPF_LENGTH else _is_valid_cnpj(digits)
    if not valid:
        raise ValueError("CPF/CNPJ inválido: dígito verificador não confere.")
    return digits


def format_cpf_cnpj(digits: str | None) -> str | None:
    """Máscara para exibição; entrada fora do padrão volta como veio."""
    if not digits:
        return digits
    if len(digits) == _CPF_LENGTH:
        return f"{digits[:3]}.{digits[3:6]}.{digits[6:9]}-{digits[9:]}"
    if len(digits) == _CNPJ_LENGTH:
        return f"{digits[:2]}.{digits[2:5]}.{digits[5:8]}/{digits[8:12]}-{digits[12:]}"
    return digits
