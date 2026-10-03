"""
Módulo responsável pelo formato de arquivo binário customizado .huff
e pela verificação de integridade usando SHA-256.

Especificação do formato .huff:
-----------------------------------------------------------------------------
Offset | Tamanho  | Descrição
-----------------------------------------------------------------------------
0      | 5 bytes  | Identificador mágico b"HUFF1"
5      | 32 bytes | Hash SHA-256 do arquivo original (verificação de integridade)
37     | 2 bytes  | Tamanho do nome do arquivo original (uint16 big-endian)
39     | N bytes  | Nome do arquivo original codificado em UTF-8
39+N   | 8 bytes  | Tamanho original do arquivo em bytes (uint64 big-endian)
47+N   | 8 bytes  | Quantidade total de bits válidos codificados (uint64 big-endian)
55+N   | 2 bytes  | Quantidade de símbolos na tabela de frequências (0 a 256)
57+N   | K*9 byte | Tabela de frequências: para cada símbolo:
       |          | - 1 byte: valor do símbolo (0 a 255)
       |          | - 8 bytes: frequência (uint64 big-endian)
Final  | Restante | Conteúdo comprimido (payload com bit packing)
-----------------------------------------------------------------------------

Não utiliza pickle, bibliotecas externas nem compressão embutida.
O SHA-256 é utilizado estritamente como soma de verificação de integridade
(checksum) e não para fins de criptografia.
"""

import hashlib
import os
import struct
import time
from dataclasses import dataclass
from typing import Dict, Optional, Tuple

from huffman import (
    build_huffman_tree,
    count_frequencies,
    decode_bytes,
    encode_bytes,
    generate_codes,
)
from node import HuffmanNode

MAGIC_HEADER = b"HUFF1"


@dataclass
class CompressionStats:
    """Informações estatísticas do processo de compressão."""

    source_path: str
    output_path: str
    original_filename: str
    original_size: int
    compressed_size: int
    reduction_percentage: float
    unique_symbols: int
    compression_time: float
    sha256_hash: str
    frequencies: Dict[int, int]
    codes: Dict[int, str]


@dataclass
class DecompressionResult:
    """Resultado do processo de descompactação e verificação de integridade."""

    huff_path: str
    restored_path: str
    original_filename: str
    original_size: int
    decompressed_size: int
    expected_sha256: str
    actual_sha256: str
    integrity_ok: bool
    decompression_time: float


def compute_sha256(data: bytes) -> str:
    """Calcula o hash SHA-256 em formato hexadecimal de uma sequência de bytes."""
    return hashlib.sha256(data).hexdigest()


def compute_file_sha256(file_path: str) -> str:
    """Calcula o SHA-256 de um arquivo em disco lendo em blocos."""
    hasher = hashlib.sha256()
    with open(file_path, "rb") as f:
        while chunk := f.read(65536):
            hasher.update(chunk)
    return hasher.hexdigest()


def serialize_huff_data(
    original_filename: str,
    original_data: bytes,
    frequencies: Dict[int, int],
    valid_bits: int,
    compressed_payload: bytes,
) -> bytes:
    """
    Serializa os dados comprimidos e metadados no formato binário .huff.
    """
    header = bytearray()

    # 1. Magic bytes
    header.extend(MAGIC_HEADER)

    # 2. SHA-256 do arquivo original (32 bytes em formato binário)
    sha256_bytes = hashlib.sha256(original_data).digest()
    header.extend(sha256_bytes)

    # 3. Nome original
    filename_bytes = original_filename.encode("utf-8")
    if len(filename_bytes) > 65535:
        filename_bytes = filename_bytes[:65535]
    header.extend(struct.pack(">H", len(filename_bytes)))
    header.extend(filename_bytes)

    # 4. Tamanho original e quantidade de bits válidos
    original_size = len(original_data)
    header.extend(struct.pack(">QQ", original_size, valid_bits))

    # 5. Tabela de frequências
    num_symbols = len(frequencies)
    header.extend(struct.pack(">H", num_symbols))

    # Ordenar por símbolo para padronização e determinismo no arquivo
    for symbol in sorted(frequencies.keys()):
        freq = frequencies[symbol]
        header.extend(struct.pack(">BQ", symbol, freq))

    # 6. Conteúdo comprimido
    header.extend(compressed_payload)
    return bytes(header)


def deserialize_huff_data(
    data: bytes,
) -> Tuple[str, int, str, Dict[int, int], int, bytes]:
    """
    Decodifica o formato binário .huff.

    Retorna:
        (original_filename, original_size, sha256_hex, frequencies, valid_bits, compressed_payload)
    """
    if len(data) < len(MAGIC_HEADER):
        raise ValueError("Arquivo inválido: tamanho menor que o cabeçalho mínimo.")

    offset = 0

    # 1. Validar Magic Bytes
    magic = data[offset : offset + len(MAGIC_HEADER)]
    offset += len(MAGIC_HEADER)
    if magic != MAGIC_HEADER:
        raise ValueError(
            f"Formato não reconhecido. Cabeçalho esperado {MAGIC_HEADER!r}, obtido {magic!r}."
        )

    # 2. Ler SHA-256 original (32 bytes)
    if len(data) < offset + 32:
        raise ValueError("Arquivo .huff corrompido: cabeçalho SHA-256 truncado.")
    sha256_raw = data[offset : offset + 32]
    offset += 32
    sha256_hex = sha256_raw.hex()

    # 3. Ler nome original
    if len(data) < offset + 2:
        raise ValueError("Arquivo .huff corrompido: tamanho do nome não encontrado.")
    (filename_len,) = struct.unpack(">H", data[offset : offset + 2])
    offset += 2

    if len(data) < offset + filename_len:
        raise ValueError("Arquivo .huff corrompido: nome do arquivo truncado.")
    original_filename = data[offset : offset + filename_len].decode(
        "utf-8", errors="replace"
    )
    offset += filename_len

    # 4. Ler tamanho original e bits válidos
    if len(data) < offset + 16:
        raise ValueError("Arquivo .huff corrompido: metadados de tamanho truncados.")
    original_size, valid_bits = struct.unpack(">QQ", data[offset : offset + 16])
    offset += 16

    # 5. Ler tabela de frequências
    if len(data) < offset + 2:
        raise ValueError("Arquivo .huff corrompido: tamanho da tabela de frequências ausente.")
    (num_symbols,) = struct.unpack(">H", data[offset : offset + 2])
    offset += 2

    frequencies: Dict[int, int] = {}
    for _ in range(num_symbols):
        if len(data) < offset + 9:
            raise ValueError("Arquivo .huff corrompido: entrada da tabela de frequências truncada.")
        symbol, freq = struct.unpack(">BQ", data[offset : offset + 9])
        offset += 9
        frequencies[symbol] = freq

    # 6. Conteúdo comprimido residual
    compressed_payload = data[offset:]

    return (
        original_filename,
        original_size,
        sha256_hex,
        frequencies,
        valid_bits,
        compressed_payload,
    )


def compress_file(
    source_path: str, output_path: Optional[str] = None
) -> CompressionStats:
    """
    Compacta um arquivo usando Huffman manual e salva no formato .huff.
    """
    if not os.path.exists(source_path):
        raise FileNotFoundError(f"Arquivo de origem não encontrado: {source_path}")

    start_time = time.perf_counter()

    with open(source_path, "rb") as f:
        original_data = f.read()

    original_size = len(original_data)
    original_filename = os.path.basename(source_path)
    sha256_hex = compute_sha256(original_data)

    # 1. Contar frequências
    frequencies = count_frequencies(original_data)

    # 2. Construir árvore de Huffman
    root = build_huffman_tree(frequencies)

    # 3. Gerar códigos
    codes = generate_codes(root)

    # 4. Codificar e empacotar bits
    packed_bytes, valid_bits = encode_bytes(original_data, codes)

    # 5. Serializar arquivo .huff
    serialized_huff = serialize_huff_data(
        original_filename=original_filename,
        original_data=original_data,
        frequencies=frequencies,
        valid_bits=valid_bits,
        compressed_payload=packed_bytes,
    )

    if output_path is None:
        output_path = source_path + ".huff"

    with open(output_path, "wb") as f:
        f.write(serialized_huff)

    compressed_size = len(serialized_huff)
    reduction = 0.0
    if original_size > 0:
        reduction = max(0.0, (1.0 - (compressed_size / original_size)) * 100.0)

    elapsed_time = time.perf_counter() - start_time

    return CompressionStats(
        source_path=source_path,
        output_path=output_path,
        original_filename=original_filename,
        original_size=original_size,
        compressed_size=compressed_size,
        reduction_percentage=reduction,
        unique_symbols=len(frequencies),
        compression_time=elapsed_time,
        sha256_hash=sha256_hex,
        frequencies=frequencies,
        codes=codes,
    )


def decompress_file(
    huff_path: str,
    output_path: Optional[str] = None,
    output_dir: Optional[str] = None,
) -> DecompressionResult:
    """
    Descompacta um arquivo .huff, recupera o arquivo original byte a byte
    e verifica a integridade comparando o SHA-256.
    """
    if not os.path.exists(huff_path):
        raise FileNotFoundError(f"Arquivo .huff não encontrado: {huff_path}")

    start_time = time.perf_counter()

    with open(huff_path, "rb") as f:
        huff_bytes = f.read()

    (
        original_filename,
        original_size,
        expected_sha256,
        frequencies,
        valid_bits,
        compressed_payload,
    ) = deserialize_huff_data(huff_bytes)

    # 1. Reconstruir a árvore de Huffman a partir das frequências
    root = build_huffman_tree(frequencies)

    # 2. Descodificar os bytes percorrendo a árvore com os bits do payload
    decompressed_data = decode_bytes(
        packed_data=compressed_payload,
        total_valid_bits=valid_bits,
        original_size=original_size,
        root=root,
    )

    # 3. Verificação de integridade via SHA-256
    actual_sha256 = compute_sha256(decompressed_data)
    integrity_ok = actual_sha256.lower() == expected_sha256.lower()

    if not integrity_ok:
        raise ValueError(
            f"Falha de integridade SHA-256! Esperado: {expected_sha256}, obtido: {actual_sha256}"
        )

    # Determinar caminho de saída
    if output_path is None:
        target_dir = output_dir or os.path.dirname(huff_path) or "."
        output_path = os.path.join(target_dir, original_filename)

    with open(output_path, "wb") as f:
        f.write(decompressed_data)

    elapsed_time = time.perf_counter() - start_time

    return DecompressionResult(
        huff_path=huff_path,
        restored_path=output_path,
        original_filename=original_filename,
        original_size=original_size,
        decompressed_size=len(decompressed_data),
        expected_sha256=expected_sha256,
        actual_sha256=actual_sha256,
        integrity_ok=integrity_ok,
        decompression_time=elapsed_time,
    )
