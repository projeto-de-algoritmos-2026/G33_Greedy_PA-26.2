"""
Módulo de implementação manual da Min-Heap (Fila de Prioridades de Mínimo).

A Min-Heap é a estrutura fundamental do algoritmo de Huffman:
permite inserir novos nós e extrair os nós com menor frequência
em tempo logarítmico O(log n).

Não utiliza bibliotecas prontas como heapq, conforme requisitos da disciplina.
"""

from typing import Any, List, Optional


class MinHeap:
    """
    Min-Heap binária baseada em lista/vetor dinâmico (índices baseados em 0).

    Invariante da Min-Heap:
    Para qualquer nó no índice i (i > 0):
        parent(i) = (i - 1) // 2
        heap[parent(i)] <= heap[i]

    Filhos de i:
        left(i)  = 2 * i + 1
        right(i) = 2 * i + 2
    """

    def __init__(self, items: Optional[List[Any]] = None):
        self._heap: List[Any] = []
        if items:
            for item in items:
                self.insert(item)

    def is_empty(self) -> bool:
        """Retorna True se a heap não contiver elementos."""
        return len(self._heap) == 0

    def size(self) -> int:
        """Retorna a quantidade de elementos na heap."""
        return len(self._heap)

    def __len__(self) -> int:
        return len(self._heap)

    def peek(self) -> Any:
        """
        Retorna o menor elemento da heap sem removê-lo.
        Lança IndexError se a heap estiver vazia.
        """
        if self.is_empty():
            raise IndexError("A Min-Heap está vazia.")
        return self._heap[0]

    def insert(self, item: Any) -> None:
        """
        Insere um novo elemento na Min-Heap.
        Adiciona o elemento ao final do vetor e aplica subida (_sift_up)
        para restaurar a propriedade da heap em O(log n).
        """
        self._heap.append(item)
        self._sift_up(len(self._heap) - 1)

    def extract_min(self) -> Any:
        """
        Remove e retorna o elemento de menor valor (raiz) da heap.
        Substitui a raiz pelo último elemento e aplica descida (_sift_down)
        para restaurar a propriedade da heap em O(log n).
        Lança IndexError se a heap estiver vazia.
        """
        if self.is_empty():
            raise IndexError("Tentativa de extrair de uma Min-Heap vazia.")

        min_item = self._heap[0]
        last_item = self._heap.pop()

        if self._heap:
            self._heap[0] = last_item
            self._sift_down(0)

        return min_item

    def _sift_up(self, index: int) -> None:
        """
        Move o elemento no índice fornecido para cima até restaurar
        a propriedade da Min-Heap (o pai deve ser <= ao filho).
        """
        current = index
        while current > 0:
            parent = (current - 1) // 2
            if self._heap[current] < self._heap[parent]:
                self._heap[current], self._heap[parent] = (
                    self._heap[parent],
                    self._heap[current],
                )
                current = parent
            else:
                break

    def _sift_down(self, index: int) -> None:
        """
        Move o elemento no índice fornecido para baixo até restaurar
        a propriedade da Min-Heap.
        """
        current = index
        total = len(self._heap)

        while True:
            left = 2 * current + 1
            right = 2 * current + 2
            smallest = current

            if left < total and self._heap[left] < self._heap[smallest]:
                smallest = left

            if right < total and self._heap[right] < self._heap[smallest]:
                smallest = right

            if smallest != current:
                self._heap[current], self._heap[smallest] = (
                    self._heap[smallest],
                    self._heap[current],
                )
                current = smallest
            else:
                break

    def __repr__(self) -> str:
        return f"MinHeap(size={len(self._heap)})"
