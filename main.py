"""
Ponto de entrada principal do projeto HuffPress.

Uso:
- Interface gráfica (padrão):
    python3 main.py

- Modo linha de comando (opcional, para testes rápidos em terminal):
    python3 main.py -c arquivo.txt           # Compacta
    python3 main.py -d arquivo.txt.huff      # Descompacta
"""

import argparse
import sys
from file_format import compress_file, decompress_file
from gui import launch_gui


def main():
    if len(sys.argv) == 1:
        # Sem argumentos de linha de comando: abre a interface gráfica
        launch_gui()
        return

    # Suporte a argumentos CLI opcionais
    parser = argparse.ArgumentParser(
        description="HuffPress - Compactador de arquivos com Huffman (Algoritmo Guloso)"
    )
    group = parser.add_mutually_exclusive_group(required=False)
    group.add_argument(
        "-c", "--compress", metavar="ARQUIVO", help="Compacta o arquivo fornecido em .huff"
    )
    group.add_argument(
        "-d",
        "--decompress",
        metavar="ARQUIVO.huff",
        help="Descompacta o arquivo .huff e verifica integridade",
    )
    parser.add_argument(
        "-o", "--output", metavar="SAIDA", help="Caminho de saída personalizado"
    )

    args = parser.parse_args()

    if args.compress:
        print(f"Compactando {args.compress}...")
        stats = compress_file(args.compress, output_path=args.output)
        print("✓ Compactação concluída com sucesso!")
        print(f"  Arquivo original:   {stats.original_size} bytes")
        print(f"  Arquivo comprimido: {stats.compressed_size} bytes")
        print(f"  Redução:            {stats.reduction_percentage:.2f}%")
        print(f"  Símbolos únicos:    {stats.unique_symbols}")
        print(f"  Tempo:              {stats.compression_time:.4f} s")
        print(f"  SHA-256 original:   {stats.sha256_hash}")
        print(f"  Criado:             {stats.output_path}")

    elif args.decompress:
        print(f"Descompactando {args.decompress}...")
        result = decompress_file(args.decompress, output_path=args.output)
        print("✓ Descompactação concluída com sucesso!")
        print(f"  Restaurado em:      {result.restored_path}")
        print(f"  Tamanho:            {result.decompressed_size} bytes")
        print(f"  Integridade:        {'OK (SHA-256 verificado ✓)' if result.integrity_ok else 'FALHA'}")
        print(f"  Tempo:              {result.decompression_time:.4f} s")
    else:
        launch_gui()


if __name__ == "__main__":
    main()
