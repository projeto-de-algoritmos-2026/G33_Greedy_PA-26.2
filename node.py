"""
Módulo de definição do nó da árvore de Huffman.

Cada nó pode ser:
- Nó folha: possui um símbolo (byte de 0 a 255) e sua respectiva frequência.
- Nó interno: possui a soma das frequências de seus filhos esquerdo e direito,
  sem símbolo associado (symbol = None).
"""

from typing import Optional


class HuffmanNode:
    """
    Representa um nó na árvore de Huffman.

    Atributos:
        symbol: Byte representado (0-255) se for nó folha; None se for nó interno.
        frequency: Quantidade de ocorrências do símbolo ou soma das frequências dos filhos.
        left: Filho esquerdo (caminho com bit 0).
        right: Filho direito (caminho com bit 1).
        order_id: Identificador sequencial para desempate estável na Min-Heap.
    """

    _order_counter: int = 0

    def __init__(
        self,
        symbol: Optional[int],
        frequency: int,
        left: Optional["HuffmanNode"] = None,
        right: Optional["HuffmanNode"] = None,
    ):
        self.symbol: Optional[int] = symbol
        self.frequency: int = frequency
        self.left: Optional["HuffmanNode"] = left
        self.right: Optional["HuffmanNode"] = right

        # Menor símbolo presente na subárvore (para desempate totalmente determinístico)
        if self.symbol is not None:
            self.min_symbol: int = self.symbol
        else:
            left_min = self.left.min_symbol if self.left is not None else 256
            right_min = self.right.min_symbol if self.right is not None else 256
            self.min_symbol = min(left_min, right_min)

        # Contador sequencial para garantir estabilidade
        HuffmanNode._order_counter += 1
        self.order_id: int = HuffmanNode._order_counter

    def is_leaf(self) -> bool:
        """
        Verifica se o nó é uma folha (não possui filhos).
        Nós folha representam bytes individuais do arquivo.
        """
        return self.left is None and self.right is None

    def __lt__(self, other: "HuffmanNode") -> bool:
        """
        Comparação para a Min-Heap:
        1. Menor frequência (critério fundamental do algoritmo ambicioso).
        2. Menor min_symbol (desempate determinístico e invariante).
        3. Menor order_id (desempate secundário garantido).
        """
        if not isinstance(other, HuffmanNode):
            return NotImplemented
        if self.frequency != other.frequency:
            return self.frequency < other.frequency
        if self.min_symbol != other.min_symbol:
            return self.min_symbol < other.min_symbol
        return self.order_id < other.order_id

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, HuffmanNode):
            return False
        return (
            self.frequency == other.frequency
            and self.symbol == other.symbol
            and self.order_id == other.order_id
        )

    def __repr__(self) -> str:
        if self.is_leaf():
            sym_repr = f"0x{self.symbol:02X}"
            if self.symbol is not None and 32 <= self.symbol <= 126:
                sym_repr = f"'{chr(self.symbol)}' ({sym_repr})"
            return f"HuffmanNode(leaf={sym_repr}, freq={self.frequency})"
        return f"HuffmanNode(internal, freq={self.frequency})"
