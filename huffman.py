"""
Módulo principal com a implementação do algoritmo guloso de Huffman.

Fluxo do algoritmo:
1. Contar a frequência de cada byte (0 a 255).
2. Criar um nó folha para cada byte com frequência > 0.
3. Inserir todos os nós na Min-Heap manual.
4. Escolha gulosa em loop:
   - Extrair os dois nós com menor frequência da Min-Heap.
   - Criar um novo nó interno com a soma dessas frequências.
   - Inserir o novo nó de volta na Min-Heap.
5. O nó restante é a raiz da árvore de Huffman.
6. Gerar os códigos binários percorrendo a árvore (esquerda = 0, direita = 1).
7. Codificar e empacotar os bits em bytes.
8. Descodificar percorrendo a árvore a partir dos bits empacotados.
"""

from typing import Dict, Optional, Tuple
from heap import MinHeap
from node import HuffmanNode


def count_frequencies(data: bytes) -> Dict[int, int]:
    """
    Conta a frequência de cada byte nos dados de entrada.
    Complexidade de tempo: O(m), onde m é o tamanho em bytes do arquivo.
    """
    frequencies: Dict[int, int] = {}
    for byte in data:
        frequencies[byte] = frequencies.get(byte, 0) + 1
    return frequencies


def build_huffman_tree(frequencies: Dict[int, int]) -> Optional[HuffmanNode]:
    """
    Constrói a árvore de Huffman utilizando uma Min-Heap manual e a estratégia gulosa.

    Decisão gulosa:
    'Em cada etapa, escolher os dois nós de menor frequência disponíveis.'

    Complexidade:
    - n = quantidade de símbolos distintos (n <= 256 para bytes)
    - Inserção inicial de n nós na Min-Heap: O(n log n)
    - n - 1 iterações gulosas: cada iteração faz 2 extrações e 1 inserção em O(log n)
    - Custo total da árvore: O(n log n)
    """
    if not frequencies:
        return None

    # Caso especial: apenas um símbolo repetido (ex: "AAAAAA")
    # Criamos um nó pai onde o filho esquerdo é a folha única, garantindo código "0".
    if len(frequencies) == 1:
        symbol, freq = next(iter(frequencies.items()))
        leaf = HuffmanNode(symbol=symbol, frequency=freq)
        return HuffmanNode(symbol=None, frequency=freq, left=leaf, right=None)

    # Passo 1: Criar nós folha para cada símbolo e inserir na Min-Heap
    heap = MinHeap()
    # Ordenar símbolos antes da inserção para manter comportamento determinístico
    for symbol in sorted(frequencies.keys()):
        freq = frequencies[symbol]
        leaf = HuffmanNode(symbol=symbol, frequency=freq)
        heap.insert(leaf)

    # Passo 2: Laço guloso - combinar os dois nós com menor frequência
    while heap.size() > 1:
        # DECISÃO GULOSA:
        # Extrair sempre os dois nós com menor frequência disponíveis
        left = heap.extract_min()
        right = heap.extract_min()

        # Criar novo nó interno com a soma das frequências
        merged_freq = left.frequency + right.frequency
        internal_node = HuffmanNode(
            symbol=None,
            frequency=merged_freq,
            left=left,
            right=right,
        )

        # Inserir o novo nó de volta na heap
        heap.insert(internal_node)

    # O último nó restante é a raiz da árvore de Huffman
    return heap.extract_min()


def generate_codes(root: Optional[HuffmanNode]) -> Dict[int, str]:
    """
    Gera o dicionário de códigos de Huffman mapeando cada byte (0-255)
    para sua string de bits correspondente ('0' ou '1').
    Convenção:
    - Esquerda = '0'
    - Direita = '1'
    """
    codes: Dict[int, str] = {}
    if root is None:
        return codes

    # Caso de árvore com apenas 1 folha como filho esquerdo (símbolo único repetido)
    if root.left is not None and root.right is None and root.left.is_leaf():
        codes[root.left.symbol] = "0"
        return codes

    # Caso degenerate de nó único folha
    if root.is_leaf():
        codes[root.symbol] = "0"
        return codes

    def _traverse(node: Optional[HuffmanNode], current_code: str) -> None:
        if node is None:
            return
        if node.is_leaf():
            if node.symbol is not None:
                codes[node.symbol] = current_code
            return

        _traverse(node.left, current_code + "0")
        _traverse(node.right, current_code + "1")

    _traverse(root, "")
    return codes


def encode_bytes(data: bytes, codes: Dict[int, str]) -> Tuple[bytes, int]:
    """
    Codifica a sequência de bytes de entrada utilizando os códigos de Huffman
    e realiza o Bit Packing (empacotamento real de bits em bytes).

    Retorna:
        (packed_bytes, total_valid_bits)
    """
    if not data or not codes:
        return b"", 0

    # Estruturas para bit packing eficiente
    packed = bytearray()
    bit_buffer = 0
    bits_in_buffer = 0
    total_valid_bits = 0

    # Pré-computa inteiros e comprimentos dos códigos para aceleração
    code_lookup: Dict[int, Tuple[int, int]] = {
        sym: (int(code, 2), len(code)) for sym, code in codes.items()
    }

    for byte in data:
        val, length = code_lookup[byte]
        bit_buffer = (bit_buffer << length) | val
        bits_in_buffer += length
        total_valid_bits += length

        # Enquanto houver pelo menos 8 bits no acumulador, descarrega 1 byte
        while bits_in_buffer >= 8:
            bits_in_buffer -= 8
            byte_to_emit = (bit_buffer >> bits_in_buffer) & 0xFF
            packed.append(byte_to_emit)
            bit_buffer &= (1 << bits_in_buffer) - 1

    # Descarrega os bits residuais no último byte (com padding de zeros à direita)
    if bits_in_buffer > 0:
        padding_shift = 8 - bits_in_buffer
        byte_to_emit = (bit_buffer << padding_shift) & 0xFF
        packed.append(byte_to_emit)

    return bytes(packed), total_valid_bits


def decode_bytes(
    packed_data: bytes,
    total_valid_bits: int,
    original_size: int,
    root: Optional[HuffmanNode],
) -> bytes:
    """
    Descompacta os bytes empacotados percorrendo a árvore de Huffman bit a bit
    até atingir a quantidade exata de bytes originais (ou o fim dos bits válidos).
    """
    if original_size == 0 or root is None or total_valid_bits == 0:
        return b""

    # Caso especial: único símbolo repetido
    if root.left is not None and root.right is None and root.left.is_leaf():
        single_sym = root.left.symbol
        if single_sym is not None:
            return bytes([single_sym]) * original_size

    if root.is_leaf() and root.symbol is not None:
        return bytes([root.symbol]) * original_size

    output = bytearray()
    current_node = root
    bits_processed = 0

    # Percorre cada byte do payload e extrai os bits mais significativos primeiro
    for byte in packed_data:
        for bit_index in range(7, -1, -1):
            if bits_processed >= total_valid_bits or len(output) >= original_size:
                break

            bit = (byte >> bit_index) & 1
            bits_processed += 1

            current_node = current_node.right if bit == 1 else current_node.left

            if current_node is None:
                raise ValueError("Inconsistência nos bits durante a decodificação da árvore.")

            if current_node.is_leaf():
                if current_node.symbol is not None:
                    output.append(current_node.symbol)
                current_node = root

                if len(output) >= original_size:
                    break

        if len(output) >= original_size:
            break

    if len(output) != original_size:
        raise ValueError(
            f"Erro de decodificação: esperado {original_size} bytes, obtido {len(output)} bytes."
        )

    return bytes(output)


def format_symbol(symbol: int) -> str:
    """
    Retorna uma representação legível de um byte para exibição didática na tabela.
    Exemplos: 'A', '0x00', '0xFF', '\\n (quebra)', 'espaço'.
    """
    special_names = {
        0x00: "0x00 (NUL)",
        0x07: "0x07 (BEL)",
        0x08: "0x08 (Backspace)",
        0x09: "0x09 (Tab \\t)",
        0x0A: "0x0A (Newline \\n)",
        0x0D: "0x0D (Return \\r)",
        0x20: "' ' (espaço)",
    }
    if symbol in special_names:
        return special_names[symbol]
    if 33 <= symbol <= 126:
        return f"'{chr(symbol)}'"
    return f"0x{symbol:02X}"


class GreedyStep:
    """Representa um passo individual na construção gulosa da árvore de Huffman."""

    def __init__(
        self,
        step_number: int,
        total_steps: int,
        heap_before: list,
        extracted_left: tuple,
        extracted_right: tuple,
        merged_item: tuple,
        heap_after: list,
    ):
        self.step_number = step_number
        self.total_steps = total_steps
        self.heap_before = heap_before
        self.extracted_left = extracted_left
        self.extracted_right = extracted_right
        self.merged_item = merged_item
        self.heap_after = heap_after


def simulate_greedy_steps(frequencies: Dict[int, int]) -> list:
    """
    Simula e grava cada decisão gulosa da construção da árvore de Huffman.
    Retorna uma lista de objetos GreedyStep para reprodução visual passo a passo.
    """
    if not frequencies or len(frequencies) < 2:
        return []

    # Cria itens iniciais: (rótulo_formatado, frequência, nó)
    nodes = []
    for sym in sorted(frequencies.keys()):
        freq = frequencies[sym]
        node = HuffmanNode(symbol=sym, frequency=freq)
        label = format_symbol(sym)
        nodes.append((label, freq, node))

    # Usamos uma lista ordenada simulando a min-heap para visualização didática clara
    nodes.sort(key=lambda item: (item[1], item[2].min_symbol))
    total_steps = len(nodes) - 1
    steps = []

    for step_num in range(1, total_steps + 1):
        heap_before = [(item[0], item[1]) for item in nodes]

        left_item = nodes.pop(0)
        right_item = nodes.pop(0)

        merged_freq = left_item[1] + right_item[1]
        merged_node = HuffmanNode(
            symbol=None,
            frequency=merged_freq,
            left=left_item[2],
            right=right_item[2],
        )
        merged_label = f"({left_item[0]}+{right_item[0]})"
        if len(merged_label) > 18:
            merged_label = f"Nó_{step_num}"

        new_item = (merged_label, merged_freq, merged_node)

        # Inserir mantendo a ordenação da heap
        nodes.append(new_item)
        nodes.sort(key=lambda item: (item[1], item[2].min_symbol))

        heap_after = [(item[0], item[1]) for item in nodes]

        steps.append(
            GreedyStep(
                step_number=step_num,
                total_steps=total_steps,
                heap_before=heap_before,
                extracted_left=(left_item[0], left_item[1]),
                extracted_right=(right_item[0], right_item[1]),
                merged_item=(new_item[0], new_item[1]),
                heap_after=heap_after,
            )
        )

    return steps
