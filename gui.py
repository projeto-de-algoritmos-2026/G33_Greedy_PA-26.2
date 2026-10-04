"""
Interface gráfica do HuffPress inspirada no design de Linear, GitHub Desktop, Raycast e Vercel.
Desenvolvida com CustomTkinter e Tkinter puro para canvas de alto desempenho.

Princípios visuais:
- Tipografia com forte hierarquia (Noto Sans / DejaVu Sans e Noto Sans Mono / DejaVu Sans Mono).
- Paleta sóbria e técnica (fundo #F8FAFC, superfícies #FFFFFF, bordas sutis #E2E8F0, acento #4F46E5).
- Abas discretas com linha indicadora ativa sutil (accent).
- Árvore de Huffman com "Ajustar à tela" (Fit to View), zoom (40%-250%), pan e destaque de caminho até a raiz.
- Gráfico de frequências responsivo, colunas perfeitamente alinhadas e clique para seleção.
- Stepper do algoritmo guloso detalhando extração dos dois menores, fusão e nova heap.
- Simulador didático "Experimentar Huffman" com visualização dos bits (original vs huffman).
- Visão geral com explicação de overhead (payload vs cabeçalho) e detalhes técnicos recolhíveis.
"""

import math
import os
import shutil
import subprocess
import sys
import tkinter as tk
import tkinter.font as tkf
from tkinter import filedialog, messagebox, ttk
from typing import Dict, List, Optional, Tuple

import customtkinter as ctk

from file_format import (
    CompressionStats,
    DecompressionResult,
    compress_file,
    compute_file_sha256,
    decompress_file,
)
from huffman import (
    GreedyStep,
    build_huffman_tree,
    count_frequencies,
    format_symbol,
    generate_codes,
    simulate_greedy_steps,
)
from node import HuffmanNode

# Configuração global de aparência do CustomTkinter
ctk.set_appearance_mode("Light")
ctk.set_default_color_theme("blue")


# =============================================================================
# SISTEMA DE DESIGN & CONSTANTES VISUAIS
# =============================================================================

COLOR_BG = "#F8FAFC"            # Slate 50
COLOR_SURFACE = "#FFFFFF"       # Branco puro
COLOR_BORDER = "#E2E8F0"        # Slate 200
COLOR_BORDER_LIGHT = "#F1F5F9"  # Slate 100
COLOR_TEXT_PRIMARY = "#0F172A"  # Slate 900
COLOR_TEXT_SECONDARY = "#64748B"# Slate 500
COLOR_TEXT_MUTED = "#94A3B8"    # Slate 400
COLOR_ACCENT = "#4F46E5"        # Indigo 600
COLOR_ACCENT_BG = "#EEF2FF"     # Indigo 50
COLOR_ACCENT_BORDER = "#C7D2FE" # Indigo 200
COLOR_ACCENT_HOVER = "#4338CA"  # Indigo 700
COLOR_SUCCESS = "#16A34A"       # Emerald 600
COLOR_SUCCESS_BG = "#F0FDF4"    # Emerald 50
COLOR_WARNING = "#D97706"       # Amber 600
COLOR_WARNING_BG = "#FFFBEB"    # Amber 50
COLOR_ERROR = "#DC2626"         # Red 600
COLOR_ERROR_BG = "#FEF2F2"      # Red 50


def resolve_system_fonts() -> Tuple[str, str]:
    """Detecta as melhores fontes disponíveis no Linux/sistema."""
    try:
        available = set(tkf.families())
        sans = "Noto Sans" if "Noto Sans" in available else "DejaVu Sans"
        mono = "Noto Sans Mono" if "Noto Sans Mono" in available else "DejaVu Sans Mono"
        return sans, mono
    except Exception:
        return "DejaVu Sans", "DejaVu Sans Mono"


FONT_FAMILY_SANS, FONT_FAMILY_MONO = resolve_system_fonts()


def open_folder(path: str):
    """Abre a pasta que contém o arquivo no gerenciador de arquivos do sistema operacional."""
    folder = os.path.dirname(os.path.abspath(path))
    try:
        if sys.platform == "win32":
            os.startfile(folder)
        elif sys.platform == "darwin":
            subprocess.run(["open", folder], check=False)
        else:
            subprocess.run(["xdg-open", folder], check=False)
    except Exception:
        pass


def format_size(bytes_count: int) -> str:
    """Formata tamanhos em bytes de forma limpa e técnica."""
    if bytes_count < 1024:
        return f"{bytes_count} B"
    elif bytes_count < 1024 * 1024:
        return f"{bytes_count / 1024:.2f} KB"
    elif bytes_count < 1024 * 1024 * 1024:
        return f"{bytes_count / (1024 * 1024):.2f} MB"
    else:
        return f"{bytes_count / (1024 * 1024 * 1024):.2f} GB"


def calculate_header_breakdown(stats: CompressionStats) -> Tuple[int, int]:
    """
    Calcula com precisão a divisão entre Metadados (.huff header) e Payload Huffman:
    - Header: Magic (5B) + SHA-256 (32B) + Nome len (2B) + Nome UTF-8 +
              Tam original (8B) + Bits válidos (8B) + Num símbolos (2B) +
              Tabela de frequências (num_símbolos * 9B)
    - Payload: tamanho final comprimido - tamanho do cabeçalho
    """
    fn_bytes = len(stats.original_filename.encode("utf-8"))
    num_symbols = len(stats.frequencies)
    header_size = 5 + 32 + 2 + fn_bytes + 8 + 8 + 2 + (num_symbols * 9)
    payload_size = max(0, stats.compressed_size - header_size)
    return header_size, payload_size


def find_leaf_path(node: Optional[HuffmanNode], target_sym: int) -> Optional[List[Tuple[HuffmanNode, str]]]:
    """
    Encontra o caminho na árvore da raiz até a folha com target_sym.
    Retorna lista de (nó, bit) onde bit é a aresta que levou até ele ('0' ou '1', vazio na raiz).
    """
    if node is None:
        return None
    if node.is_leaf():
        if node.symbol == target_sym:
            return [(node, "")]
        return None

    left_path = find_leaf_path(node.left, target_sym)
    if left_path is not None:
        return [(node, "0")] + left_path

    right_path = find_leaf_path(node.right, target_sym)
    if right_path is not None:
        return [(node, "1")] + right_path

    return None


def get_tree_metrics(node: Optional[HuffmanNode]) -> Tuple[int, int]:
    """Calcula quantidade de folhas e profundidade máxima da árvore."""
    if node is None:
        return 0, 0

    def _calc(n: HuffmanNode) -> Tuple[int, int]:
        if n.is_leaf():
            return 1, 0
        l_leaves, l_depth = _calc(n.left) if n.left else (0, 0)
        r_leaves, r_depth = _calc(n.right) if n.right else (0, 0)
        return (l_leaves + r_leaves), 1 + max(l_depth, r_depth)

    return _calc(node)


# =============================================================================
# COMPONENTE: BARRA DE NAVEGAÇÃO MODERNA (TABS COM LINHA ATIVA DISCRETA)
# =============================================================================
class ModernTabBar(ctk.CTkFrame):
    """
    Barra de navegação sóbria e moderna estilo Linear / Raycast:
    Texto forte na aba ativa + linha accent inferior discreta, sem pills grandes.
    """

    def __init__(self, parent, tabs: List[Tuple[str, str]], on_change, **kwargs):
        super().__init__(parent, fg_color="transparent", height=38, **kwargs)
        self.tabs = tabs
        self.on_change = on_change
        self.active_tab_id = tabs[0][0] if tabs else ""
        self.buttons: Dict[str, tk.Label] = {}

        # Linha horizontal sutil na base
        self.canvas_line = tk.Canvas(self, height=2, bg=COLOR_BORDER, highlightthickness=0)
        self.canvas_line.pack(side="bottom", fill="x")

        # Container dos botões
        btns_frame = ctk.CTkFrame(self, fg_color="transparent")
        btns_frame.pack(side="top", fill="x")

        for tab_id, tab_label in self.tabs:
            lbl = tk.Label(
                btns_frame,
                text=tab_label,
                font=(FONT_FAMILY_SANS, 11),
                fg=COLOR_TEXT_SECONDARY,
                bg=COLOR_BG,
                cursor="hand2",
                padx=14,
                pady=6,
            )
            lbl.pack(side="left")
            lbl.bind("<Button-1>", lambda e, tid=tab_id: self.select_tab(tid))
            lbl.bind("<Enter>", lambda e, l=lbl, tid=tab_id: self._on_hover(l, tid, True))
            lbl.bind("<Leave>", lambda e, l=lbl, tid=tab_id: self._on_hover(l, tid, False))
            self.buttons[tab_id] = lbl

        self.bind("<Configure>", lambda e: self._redraw_active_line())

    def _on_hover(self, lbl: tk.Label, tab_id: str, is_hover: bool):
        if tab_id != self.active_tab_id:
            lbl.configure(fg=COLOR_TEXT_PRIMARY if is_hover else COLOR_TEXT_SECONDARY)

    def select_tab(self, tab_id: str, notify: bool = True):
        self.active_tab_id = tab_id
        for tid, lbl in self.buttons.items():
            if tid == tab_id:
                lbl.configure(
                    font=(FONT_FAMILY_SANS, 11, "bold"),
                    fg=COLOR_TEXT_PRIMARY,
                )
            else:
                lbl.configure(
                    font=(FONT_FAMILY_SANS, 11),
                    fg=COLOR_TEXT_SECONDARY,
                )
        self._redraw_active_line()
        if notify and self.on_change:
            self.on_change(tab_id)

    def _redraw_active_line(self):
        self.canvas_line.delete("all")
        active_lbl = self.buttons.get(self.active_tab_id)
        if not active_lbl or not active_lbl.winfo_viewable():
            return

        x1 = active_lbl.winfo_x()
        x2 = x1 + active_lbl.winfo_width()
        # Desenha o traço ativo accent sobre a linha cinza base
        self.canvas_line.create_line(x1 + 6, 1, x2 - 6, 1, fill=COLOR_ACCENT, width=2)


# =============================================================================
# COMPONENTE: VISUALIZADOR DE ÁRVORE DE HUFFMAN (FIT TO VIEW, ZOOM, HIGHLIGHT)
# =============================================================================
class ModernTreeCanvas(ctk.CTkFrame):
    """
    Visualizador interativo e responsivo da árvore de Huffman:
    - Ocupa praticamente toda a aba
    - Ajustar à tela (Fit to View) real
    - Zoom (40% a 250%) com scroll ou botões
    - Arraste com pan
    - Destaque sincronizado de caminho da raiz até a folha selecionada
    - Painel inferior compacto flutuante de detalhes do nó
    """

    def __init__(self, parent, on_node_selected=None, **kwargs):
        super().__init__(parent, fg_color="transparent", **kwargs)
        self.on_node_selected = on_node_selected

        self.zoom_level = 1.0
        self.root_node: Optional[HuffmanNode] = None
        self.codes: Dict[int, str] = {}
        self.total_frequency = 1
        self.selected_symbol: Optional[int] = None

        # Posições base (zoom=1.0) e nós indexados por order_id
        self.base_positions: Dict[int, Tuple[float, float]] = {}
        self.node_positions: Dict[int, Tuple[float, float]] = {}
        self.node_objects: Dict[int, HuffmanNode] = {}
        self.active_path_node_ids: set = set()
        self.active_path_edges: set = set()

        # Variáveis de pan
        self._pan_start_x = 0
        self._pan_start_y = 0

        # Barra superior limpa e minimalista
        top_bar = ctk.CTkFrame(self, fg_color="transparent", height=32)
        top_bar.pack(fill="x", padx=6, pady=(0, 6))

        title_container = ctk.CTkFrame(top_bar, fg_color="transparent")
        title_container.pack(side="left")

        ctk.CTkLabel(
            title_container,
            text="Árvore de Huffman",
            font=ctk.CTkFont(family=FONT_FAMILY_SANS, size=14, weight="bold"),
            text_color=COLOR_TEXT_PRIMARY,
        ).pack(side="left")

        self.lbl_tree_stats = ctk.CTkLabel(
            title_container,
            text="",
            font=ctk.CTkFont(family=FONT_FAMILY_SANS, size=11),
            text_color=COLOR_TEXT_SECONDARY,
        )
        self.lbl_tree_stats.pack(side="left", padx=10)

        # Controles alinhados à direita
        ctrls = ctk.CTkFrame(top_bar, fg_color="transparent")
        ctrls.pack(side="right")

        ctk.CTkButton(
            ctrls,
            text="Ajustar à tela",
            width=96,
            height=26,
            fg_color=COLOR_SURFACE,
            hover_color=COLOR_BORDER_LIGHT,
            text_color=COLOR_TEXT_PRIMARY,
            border_width=1,
            border_color=COLOR_BORDER,
            font=ctk.CTkFont(family=FONT_FAMILY_SANS, size=11, weight="bold"),
            corner_radius=6,
            command=self.fit_to_view,
        ).pack(side="right", padx=(6, 0))

        ctk.CTkButton(
            ctrls,
            text="+",
            width=28,
            height=26,
            fg_color=COLOR_SURFACE,
            hover_color=COLOR_BORDER_LIGHT,
            text_color=COLOR_TEXT_PRIMARY,
            border_width=1,
            border_color=COLOR_BORDER,
            font=ctk.CTkFont(family=FONT_FAMILY_SANS, size=13, weight="bold"),
            corner_radius=6,
            command=self.zoom_in,
        ).pack(side="right", padx=2)

        self.lbl_zoom = ctk.CTkLabel(
            ctrls,
            text="100%",
            width=46,
            font=ctk.CTkFont(family=FONT_FAMILY_SANS, size=11),
            text_color=COLOR_TEXT_SECONDARY,
        )
        self.lbl_zoom.pack(side="right")

        ctk.CTkButton(
            ctrls,
            text="−",
            width=28,
            height=26,
            fg_color=COLOR_SURFACE,
            hover_color=COLOR_BORDER_LIGHT,
            text_color=COLOR_TEXT_PRIMARY,
            border_width=1,
            border_color=COLOR_BORDER,
            font=ctk.CTkFont(family=FONT_FAMILY_SANS, size=13, weight="bold"),
            corner_radius=6,
            command=self.zoom_out,
        ).pack(side="right", padx=2)

        # Container do Canvas ocupando praticamente toda a área
        canvas_box = ctk.CTkFrame(
            self,
            fg_color=COLOR_SURFACE,
            corner_radius=8,
            border_width=1,
            border_color=COLOR_BORDER,
        )
        canvas_box.pack(fill="both", expand=True)

        self.canvas = tk.Canvas(
            canvas_box,
            bg=COLOR_SURFACE,
            highlightthickness=0,
            cursor="hand2",
        )
        self.hbar = ttk.Scrollbar(canvas_box, orient=tk.HORIZONTAL, command=self.canvas.xview)
        self.vbar = ttk.Scrollbar(canvas_box, orient=tk.VERTICAL, command=self.canvas.yview)
        self.canvas.configure(xscrollcommand=self.hbar.set, yscrollcommand=self.vbar.set)

        self.hbar.pack(side="bottom", fill="x")
        self.vbar.pack(side="right", fill="y")
        self.canvas.pack(side="left", fill="both", expand=True, padx=2, pady=2)

        # Eventos do canvas (clique, arrasto e zoom com roda)
        self.canvas.bind("<ButtonPress-1>", self._on_canvas_press)
        self.canvas.bind("<B1-Motion>", self._on_canvas_drag)
        self.canvas.bind("<ButtonRelease-1>", self._on_canvas_release)
        self.canvas.bind("<Configure>", self._on_canvas_configure)

        # Scroll do mouse para zoom
        self.canvas.bind("<Button-4>", lambda e: self._on_mouse_zoom(1.15))
        self.canvas.bind("<Button-5>", lambda e: self._on_mouse_zoom(1 / 1.15))
        self.canvas.bind("<MouseWheel>", self._on_mousewheel)

        # Painel inferior flutuante para detalhes e destaque do caminho
        self.bottom_detail_bar = ctk.CTkFrame(
            canvas_box,
            fg_color=COLOR_SURFACE,
            corner_radius=8,
            border_width=1,
            border_color=COLOR_ACCENT_BORDER,
            height=44,
        )
        # Oculto por padrão
        self._is_detail_bar_visible = False

        self.lbl_detail_summary = ctk.CTkLabel(
            self.bottom_detail_bar,
            text="",
            font=ctk.CTkFont(family=FONT_FAMILY_SANS, size=11),
            text_color=COLOR_TEXT_PRIMARY,
        )
        self.lbl_detail_summary.pack(side="left", padx=14)

        self.lbl_detail_breadcrumb = ctk.CTkLabel(
            self.bottom_detail_bar,
            text="",
            font=ctk.CTkFont(family=FONT_FAMILY_MONO, size=10, weight="bold"),
            text_color=COLOR_ACCENT,
        )
        self.lbl_detail_breadcrumb.pack(side="left", padx=10)

        ctk.CTkButton(
            self.bottom_detail_bar,
            text="✕ Limpar seleção",
            width=80,
            height=24,
            fg_color="transparent",
            hover_color=COLOR_BORDER_LIGHT,
            text_color=COLOR_TEXT_SECONDARY,
            font=ctk.CTkFont(family=FONT_FAMILY_SANS, size=10),
            command=self.clear_selection,
        ).pack(side="right", padx=10)

    def _on_mousewheel(self, event):
        if event.delta > 0:
            self._on_mouse_zoom(1.15)
        elif event.delta < 0:
            self._on_mouse_zoom(1 / 1.15)

    def _on_mouse_zoom(self, factor: float):
        new_zoom = max(0.40, min(2.50, self.zoom_level * factor))
        if abs(new_zoom - self.zoom_level) > 0.01:
            self.zoom_level = new_zoom
            self.lbl_zoom.configure(text=f"{int(self.zoom_level * 100)}%")
            self.render()
            self._center_bounding_box()

    def zoom_in(self):
        self._on_mouse_zoom(1.18)

    def zoom_out(self):
        self._on_mouse_zoom(1 / 1.18)

    def set_tree(self, root: Optional[HuffmanNode], codes: Dict[int, str]):
        self.root_node = root
        self.codes = codes
        self.total_frequency = root.frequency if root else 1
        self.selected_symbol = None
        self._compute_base_layout()

        if root:
            leaves, depth = get_tree_metrics(root)
            self.lbl_tree_stats.configure(
                text=f"• {leaves} folhas · profundidade {depth}"
            )
        else:
            self.lbl_tree_stats.configure(text="")

        self.after(60, self.fit_to_view)

    def _compute_base_layout(self):
        """Calcula as coordenadas base da árvore em zoom=1.0 usando posicionamento folha-a-folha."""
        self.base_positions.clear()
        self.node_objects.clear()
        if not self.root_node:
            return

        leaf_x = [0.0]
        base_x: Dict[int, float] = {}
        base_y: Dict[int, float] = {}
        base_leaf_gap = 52.0
        base_level_gap = 62.0

        def _walk(node: HuffmanNode, depth: int):
            if node is None:
                return
            self.node_objects[node.order_id] = node

            if node.is_leaf():
                base_x[node.order_id] = leaf_x[0]
                leaf_x[0] += base_leaf_gap
                base_y[node.order_id] = 40.0 + depth * base_level_gap
                return

            _walk(node.left, depth + 1)
            lx = base_x[node.left.order_id] if node.left else leaf_x[0]

            if node.right:
                _walk(node.right, depth + 1)
                rx = base_x[node.right.order_id]
                base_x[node.order_id] = (lx + rx) / 2.0
            else:
                base_x[node.order_id] = lx

            base_y[node.order_id] = 40.0 + depth * base_level_gap

        _walk(self.root_node, 0)
        self.base_positions = {k: (base_x[k], base_y[k]) for k in base_x}

    def fit_to_view(self):
        """
        Implementa o Ajustar à tela (Fit to View) completo:
        1. Bounding box real de todos os elementos
        2. Viewport real do canvas
        3. Escala necessária para caber em largura e altura (com margem de ~8%)
        4. Centraliza a árvore perfeitamente
        """
        self.canvas.update_idletasks()
        if not self.base_positions:
            return

        view_w = max(100, self.canvas.winfo_width())
        view_h = max(100, self.canvas.winfo_height())

        min_x = min(x for x, y in self.base_positions.values())
        max_x = max(x for x, y in self.base_positions.values())
        min_y = min(y for x, y in self.base_positions.values())
        max_y = max(y for x, y in self.base_positions.values())

        tree_w = max(1.0, max_x - min_x + 60)
        tree_h = max(1.0, max_y - min_y + 60)

        # Margem de aproximadamente 8% de cada lado (viewport útil ~84%)
        avail_w = view_w * 0.84
        avail_h = view_h * 0.84

        scale_w = avail_w / tree_w
        scale_h = avail_h / tree_h
        target_zoom = min(scale_w, scale_h)

        # Limites razoáveis exigidos: 40% a 250%
        target_zoom = max(0.40, min(2.50, target_zoom))
        self.zoom_level = target_zoom
        self.lbl_zoom.configure(text=f"{int(self.zoom_level * 100)}%")

        self.render()
        self.after(30, self._center_bounding_box)

    def _center_bounding_box(self):
        """Centraliza o conteúdo renderizado na tela."""
        self.canvas.update_idletasks()
        view_w = self.canvas.winfo_width()
        view_h = self.canvas.winfo_height()
        if not self.node_positions or view_w <= 1 or view_h <= 1:
            return

        min_x = min(x for x, y in self.node_positions.values())
        max_x = max(x for x, y in self.node_positions.values())
        min_y = min(y for x, y in self.node_positions.values())
        max_y = max(y for x, y in self.node_positions.values())

        cx = (min_x + max_x) / 2
        cy = (min_y + max_y) / 2

        sr = self.canvas.cget("scrollregion")
        if not sr:
            return
        sr_x1, sr_y1, sr_x2, sr_y2 = [float(v) for v in sr.split()]
        total_w = sr_x2 - sr_x1
        total_h = sr_y2 - sr_y1

        if total_w > 0:
            target_left = cx - (view_w / 2)
            fx = (target_left - sr_x1) / total_w
            self.canvas.xview_moveto(max(0.0, min(1.0, fx)))

        if total_h > 0:
            target_top = cy - (view_h / 2)
            fy = (target_top - sr_y1) / total_h
            self.canvas.yview_moveto(max(0.0, min(1.0, fy)))

    def _on_canvas_configure(self, event):
        if self.node_positions:
            self._update_scrollregion()

    def _on_canvas_press(self, event):
        self._pan_start_x = event.x
        self._pan_start_y = event.y
        self.canvas.scan_mark(event.x, event.y)

    def _on_canvas_drag(self, event):
        self.canvas.scan_dragto(event.x, event.y, gain=1)

    def _on_canvas_release(self, event):
        # Se houve pouco deslocamento, trata como clique
        dx = abs(event.x - self._pan_start_x)
        dy = abs(event.y - self._pan_start_y)
        if dx < 4 and dy < 4:
            self._handle_click(event.x, event.y)

    def _handle_click(self, vx: int, vy: int):
        cx = self.canvas.canvasx(vx)
        cy = self.canvas.canvasy(vy)

        clicked_sym: Optional[int] = None
        for order_id, (nx, ny) in self.node_positions.items():
            node = self.node_objects.get(order_id)
            if node and node.is_leaf() and node.symbol is not None:
                w = 46 * self.zoom_level
                h = 36 * self.zoom_level
                if abs(cx - nx) <= w / 2 + 3 and abs(cy - ny) <= h / 2 + 3:
                    clicked_sym = node.symbol
                    break

        if clicked_sym is not None:
            self.select_symbol(clicked_sym, notify=True)
        else:
            self.clear_selection(notify=True)

    def select_symbol(self, symbol: int, notify: bool = False):
        """Seleciona um símbolo e destaca seu caminho até a raiz."""
        self.selected_symbol = symbol
        self._update_path_highlight()
        self.render()

        # Exibir painel flutuante inferior
        if not self._is_detail_bar_visible:
            self.bottom_detail_bar.place(relx=0.02, rely=0.91, relwidth=0.96)
            self._is_detail_bar_visible = True

        sym_str = format_symbol(symbol)
        code = self.codes.get(symbol, "")
        freq = 0
        for node in self.node_objects.values():
            if node.is_leaf() and node.symbol == symbol:
                freq = node.frequency
                break

        pct = (freq / self.total_frequency * 100) if self.total_frequency > 0 else 0
        self.lbl_detail_summary.configure(
            text=f"{sym_str}  ·  {freq:,} ocorrências ({pct:.1f}%)  ·  Código: {code or '—'}  ({len(code)} bits)"
        )

        # Monta breadcrumb de caminho
        path = find_leaf_path(self.root_node, symbol)
        if path:
            crumbs = ["raiz"]
            for _, bit in path[1:]:
                crumbs.append(f"─{bit}→")
            crumbs.append(sym_str)
            self.lbl_detail_breadcrumb.configure(text="  " + " ".join(crumbs))
        else:
            self.lbl_detail_breadcrumb.configure(text="")

        if notify and self.on_node_selected:
            self.on_node_selected(symbol)

    def clear_selection(self, notify: bool = False):
        self.selected_symbol = None
        self.active_path_node_ids.clear()
        self.active_path_edges.clear()
        if self._is_detail_bar_visible:
            self.bottom_detail_bar.place_forget()
            self._is_detail_bar_visible = False
        self.render()
        if notify and self.on_node_selected:
            self.on_node_selected(None)

    def _update_path_highlight(self):
        self.active_path_node_ids.clear()
        self.active_path_edges.clear()
        if self.selected_symbol is None or self.root_node is None:
            return

        path = find_leaf_path(self.root_node, self.selected_symbol)
        if not path:
            return

        for i in range(len(path)):
            node, _ = path[i]
            self.active_path_node_ids.add(node.order_id)
            if i > 0:
                parent, bit = path[i - 1]
                self.active_path_edges.add((parent.order_id, node.order_id))

    def _update_scrollregion(self):
        if not self.node_positions:
            return
        view_w = max(100, self.canvas.winfo_width())
        view_h = max(100, self.canvas.winfo_height())

        min_x = min(x for x, y in self.node_positions.values())
        max_x = max(x for x, y in self.node_positions.values())
        min_y = min(y for x, y in self.node_positions.values())
        max_y = max(y for x, y in self.node_positions.values())

        w_margin = max(80, int(view_w / 2))
        h_margin = max(60, int(view_h / 2))
        node_pad = 40 * self.zoom_level

        sr_x1 = min_x - node_pad - w_margin
        sr_y1 = min_y - node_pad - h_margin
        sr_x2 = max_x + node_pad + w_margin
        sr_y2 = max_y + node_pad + h_margin
        self.canvas.configure(scrollregion=(sr_x1, sr_y1, sr_x2, sr_y2))

    def render(self):
        """Renderiza a árvore aplicando o zoom e destacando o caminho se houver."""
        self.canvas.delete("all")
        self.node_positions.clear()

        if not self.root_node:
            self.canvas.create_text(
                300, 150,
                text="A árvore de Huffman será renderizada aqui após a compactação.",
                font=(FONT_FAMILY_SANS, 11),
                fill=COLOR_TEXT_MUTED,
            )
            return

        # Escala posições base pelo zoom_level atual
        for oid, (bx, by) in self.base_positions.items():
            self.node_positions[oid] = (bx * self.zoom_level, by * self.zoom_level)

        # 1. Desenho das arestas (com bits 0 à esquerda e 1 à direita)
        def _draw_edges(node: HuffmanNode):
            if node is None or node.is_leaf():
                return
            px, py = self.node_positions[node.order_id]

            if node.left:
                cx, cy = self.node_positions[node.left.order_id]
                is_edge_active = (node.order_id, node.left.order_id) in self.active_path_edges
                edge_color = COLOR_ACCENT if is_edge_active else COLOR_BORDER
                edge_width = 2.5 if is_edge_active else 1.2
                self.canvas.create_line(px, py, cx, cy, fill=edge_color, width=edge_width)

                mx, my = (px + cx) / 2 - 8, (py + cy) / 2
                self.canvas.create_text(
                    mx, my, text="0",
                    font=(FONT_FAMILY_MONO, max(7, int(8 * self.zoom_level)), "bold"),
                    fill=COLOR_ACCENT if is_edge_active else COLOR_TEXT_MUTED,
                )
                _draw_edges(node.left)

            if node.right:
                cx, cy = self.node_positions[node.right.order_id]
                is_edge_active = (node.order_id, node.right.order_id) in self.active_path_edges
                edge_color = COLOR_ACCENT if is_edge_active else COLOR_BORDER
                edge_width = 2.5 if is_edge_active else 1.2
                self.canvas.create_line(px, py, cx, cy, fill=edge_color, width=edge_width)

                mx, my = (px + cx) / 2 + 8, (py + cy) / 2
                self.canvas.create_text(
                    mx, my, text="1",
                    font=(FONT_FAMILY_MONO, max(7, int(8 * self.zoom_level)), "bold"),
                    fill=COLOR_ACCENT if is_edge_active else COLOR_TEXT_MUTED,
                )
                _draw_edges(node.right)

        _draw_edges(self.root_node)

        # 2. Desenho dos nós (internos discretos e folhas em pequenos cards)
        def _draw_nodes(node: HuffmanNode):
            if node is None:
                return
            x, y = self.node_positions[node.order_id]
            is_active = node.order_id in self.active_path_node_ids

            if node.is_leaf():
                w = 46 * self.zoom_level
                h = 36 * self.zoom_level
                is_target_leaf = (self.selected_symbol is not None and node.symbol == self.selected_symbol)

                bg_fill = COLOR_ACCENT_BG if is_target_leaf else COLOR_SURFACE
                outline_c = COLOR_ACCENT if (is_target_leaf or is_active) else COLOR_BORDER
                border_w = 2.0 if is_target_leaf else (1.5 if is_active else 1.0)

                self.canvas.create_rectangle(
                    x - w / 2, y - h / 2, x + w / 2, y + h / 2,
                    fill=bg_fill, outline=outline_c, width=border_w,
                )

                sym_str = format_symbol(node.symbol) if node.symbol is not None else ""
                self.canvas.create_text(
                    x, y - 6 * self.zoom_level,
                    text=sym_str,
                    font=(FONT_FAMILY_SANS, max(7, int(9 * self.zoom_level)), "bold"),
                    fill=COLOR_ACCENT if is_target_leaf else COLOR_TEXT_PRIMARY,
                )
                self.canvas.create_text(
                    x, y + 8 * self.zoom_level,
                    text=f"{node.frequency}",
                    font=(FONT_FAMILY_SANS, max(6, int(8 * self.zoom_level))),
                    fill=COLOR_TEXT_SECONDARY,
                )
            else:
                r = 11 * self.zoom_level
                bg_fill = COLOR_ACCENT_BG if is_active else COLOR_BORDER_LIGHT
                outline_c = COLOR_ACCENT if is_active else COLOR_BORDER
                border_w = 1.8 if is_active else 1.0

                self.canvas.create_oval(
                    x - r, y - r, x + r, y + r,
                    fill=bg_fill, outline=outline_c, width=border_w,
                )
                self.canvas.create_text(
                    x, y,
                    text=f"{node.frequency}",
                    font=(FONT_FAMILY_SANS, max(6, int(7 * self.zoom_level))),
                    fill=COLOR_ACCENT if is_active else COLOR_TEXT_SECONDARY,
                )
                _draw_nodes(node.left)
                _draw_nodes(node.right)

        _draw_nodes(self.root_node)
        self._update_scrollregion()


# =============================================================================
# COMPONENTE: GRÁFICO DE FREQUÊNCIAS MODERNO & ALINHADO
# =============================================================================
class FrequencyChartView(ctk.CTkFrame):
    """
    Gráfico de frequências com estrutura perfeitamente alinhada:
    [ Símbolo (fixo) ]  [ Barra flexível ]  [ % alinhado ]  [ Contagem alinhada ]
    Clique para selecionar e ver detalhes.
    """

    def __init__(self, parent, on_select_symbol=None, **kwargs):
        super().__init__(parent, fg_color=COLOR_SURFACE, corner_radius=8, border_width=1, border_color=COLOR_BORDER, **kwargs)
        self.on_select_symbol = on_select_symbol
        self.frequencies: Dict[int, int] = {}
        self.codes: Dict[int, str] = {}
        self.total_bytes = 1
        self.selected_symbol: Optional[int] = None
        self.sorted_items: List[Tuple[int, int]] = []

        # Cabeçalho da aba
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.pack(fill="x", padx=18, pady=(14, 8))

        ctk.CTkLabel(
            header,
            text="Frequência dos símbolos",
            font=ctk.CTkFont(family=FONT_FAMILY_SANS, size=14, weight="bold"),
            text_color=COLOR_TEXT_PRIMARY,
        ).pack(side="left")

        self.lbl_subtitle = ctk.CTkLabel(
            header,
            text="— os 15 símbolos mais frequentes do arquivo",
            font=ctk.CTkFont(family=FONT_FAMILY_SANS, size=11),
            text_color=COLOR_TEXT_SECONDARY,
        )
        self.lbl_subtitle.pack(side="left", padx=8)

        # Canvas flexível de barras
        self.canvas = tk.Canvas(self, bg=COLOR_SURFACE, highlightthickness=0, cursor="hand2")
        self.canvas.pack(fill="both", expand=True, padx=16, pady=(0, 6))

        self.canvas.bind("<Configure>", lambda e: self.render())
        self.canvas.bind("<Button-1>", self._on_canvas_click)

        # Barra inferior de detalhes ao selecionar
        self.detail_strip = ctk.CTkFrame(self, fg_color=COLOR_ACCENT_BG, corner_radius=6, height=36)
        self.lbl_detail = ctk.CTkLabel(
            self.detail_strip,
            text="",
            font=ctk.CTkFont(family=FONT_FAMILY_SANS, size=11),
            text_color=COLOR_TEXT_PRIMARY,
        )
        self.lbl_detail.pack(side="left", padx=12, pady=6)

        self.btn_go_tree = ctk.CTkButton(
            self.detail_strip,
            text="Ver na Árvore →",
            width=100,
            height=24,
            fg_color=COLOR_ACCENT,
            hover_color=COLOR_ACCENT_HOVER,
            text_color="#FFFFFF",
            font=ctk.CTkFont(family=FONT_FAMILY_SANS, size=10, weight="bold"),
            command=self._on_click_go_tree,
        )
        self.btn_go_tree.pack(side="right", padx=10, pady=6)

    def set_data(self, freqs: Dict[int, int], codes: Dict[int, str], total_size: int):
        self.frequencies = freqs
        self.codes = codes
        self.total_bytes = max(1, total_size)
        self.selected_symbol = None
        self.sorted_items = sorted(freqs.items(), key=lambda i: i[1], reverse=True)[:15]
        self.render()

    def select_symbol(self, sym: Optional[int], notify: bool = True):
        self.selected_symbol = sym
        self.render()
        if sym is not None and sym in self.frequencies:
            freq = self.frequencies[sym]
            pct = (freq / self.total_bytes) * 100
            code = self.codes.get(sym, "")
            sym_lbl = format_symbol(sym)
            self.lbl_detail.configure(
                text=f"{sym_lbl} (Byte {sym})  ·  {freq:,} ocorrências  ·  {pct:.1f}% do total  ·  Código: {code or '—'} ({len(code)} bits)"
            )
            self.detail_strip.pack(fill="x", padx=16, pady=(0, 10))
        else:
            self.detail_strip.pack_forget()

        if notify and self.on_select_symbol:
            self.on_select_symbol(sym)

    def _on_click_go_tree(self):
        if self.on_select_symbol and self.selected_symbol is not None:
            self.on_select_symbol(self.selected_symbol, switch_to_tree=True)

    def _on_canvas_click(self, event):
        y = event.y
        row_h = 28
        start_y = 10
        idx = int((y - start_y) // row_h)
        if 0 <= idx < len(self.sorted_items):
            sym, _ = self.sorted_items[idx]
            self.select_symbol(sym, notify=True)
        else:
            self.select_symbol(None, notify=True)

    def render(self):
        self.canvas.delete("all")
        if not self.sorted_items:
            return

        avail_w = max(200, self.canvas.winfo_width())
        max_freq = self.sorted_items[0][1]

        sym_col_w = 110
        pct_col_w = 70
        count_col_w = 75
        bar_start_x = sym_col_w + 10
        bar_max_w = max(60, avail_w - bar_start_x - pct_col_w - count_col_w - 20)

        row_h = 28
        bar_h = 14
        y = 10

        for sym, freq in self.sorted_items:
            pct = (freq / self.total_bytes) * 100
            sym_lbl = format_symbol(sym)
            is_selected = (self.selected_symbol == sym)

            # Fundo suave para a linha selecionada
            if is_selected:
                self.canvas.create_rectangle(
                    4, y - 2, avail_w - 4, y + row_h - 4,
                    fill=COLOR_ACCENT_BG, outline="",
                )

            # 1. Coluna de Símbolo (fixa)
            self.canvas.create_text(
                12, y + row_h / 2 - 2,
                text=sym_lbl,
                anchor="w",
                font=(FONT_FAMILY_SANS, 10, "bold"),
                fill=COLOR_ACCENT if is_selected else COLOR_TEXT_PRIMARY,
            )

            # 2. Pista de fundo sutil da barra
            by = y + (row_h - bar_h) / 2 - 2
            self.canvas.create_rectangle(
                bar_start_x, by, bar_start_x + bar_max_w, by + bar_h,
                fill=COLOR_BORDER_LIGHT, outline="",
            )

            # 2.1 Barra proporcional preenchida
            bw = max(4, int((freq / max_freq) * bar_max_w))
            bar_color = COLOR_ACCENT if not is_selected else COLOR_ACCENT_HOVER
            self.canvas.create_rectangle(
                bar_start_x, by, bar_start_x + bw, by + bar_h,
                fill=bar_color, outline="",
            )

            # 3. Percentual alinhado
            pct_x = bar_start_x + bar_max_w + 14
            self.canvas.create_text(
                pct_x, y + row_h / 2 - 2,
                text=f"{pct:4.1f}%",
                anchor="w",
                font=(FONT_FAMILY_SANS, 10),
                fill=COLOR_TEXT_SECONDARY,
            )

            # 4. Contagem alinhada
            count_x = pct_x + pct_col_w
            self.canvas.create_text(
                count_x, y + row_h / 2 - 2,
                text=f"{freq:,}x",
                anchor="w",
                font=(FONT_FAMILY_MONO, 10, "bold"),
                fill=COLOR_TEXT_PRIMARY if is_selected else COLOR_TEXT_SECONDARY,
            )

            y += row_h


# =============================================================================
# COMPONENTE: TABELA DE CÓDIGOS HUFFMAN
# =============================================================================
class CodesTableView(ctk.CTkFrame):
    """
    Tabela com boa tipografia, espaçamento e fonte monoespaçada para os códigos.
    Clique seleciona e permite ver a folha correspondente na árvore.
    """

    def __init__(self, parent, on_select_symbol=None, **kwargs):
        super().__init__(parent, fg_color=COLOR_SURFACE, corner_radius=8, border_width=1, border_color=COLOR_BORDER, **kwargs)
        self.on_select_symbol = on_select_symbol
        self.selected_symbol: Optional[int] = None
        self.sym_by_item_id: Dict[str, int] = {}

        header = ctk.CTkFrame(self, fg_color="transparent")
        header.pack(fill="x", padx=18, pady=(14, 8))

        ctk.CTkLabel(
            header,
            text="Dicionário de Códigos de Huffman",
            font=ctk.CTkFont(family=FONT_FAMILY_SANS, size=14, weight="bold"),
            text_color=COLOR_TEXT_PRIMARY,
        ).pack(side="left")

        ctk.CTkLabel(
            header,
            text="— códigos de prefixo ótimos gerados pela árvore",
            font=ctk.CTkFont(family=FONT_FAMILY_SANS, size=11),
            text_color=COLOR_TEXT_SECONDARY,
        ).pack(side="left", padx=8)

        tbl_box = ctk.CTkFrame(self, fg_color="transparent")
        tbl_box.pack(fill="both", expand=True, padx=16, pady=(0, 6))

        # Configurar estilo ttk para modernizar o Treeview
        style = ttk.Style()
        style.theme_use("clam")
        style.configure(
            "HuffCodes.Treeview",
            background=COLOR_SURFACE,
            foreground=COLOR_TEXT_PRIMARY,
            fieldbackground=COLOR_SURFACE,
            rowheight=26,
            font=(FONT_FAMILY_SANS, 10),
            borderwidth=0,
        )
        style.configure(
            "HuffCodes.Treeview.Heading",
            background=COLOR_BORDER_LIGHT,
            foreground=COLOR_TEXT_SECONDARY,
            font=(FONT_FAMILY_SANS, 10, "bold"),
            relief="flat",
        )
        style.map(
            "HuffCodes.Treeview",
            background=[("selected", COLOR_ACCENT_BG)],
            foreground=[("selected", COLOR_ACCENT)],
        )

        cols = ("simbolo", "byte", "freq", "pct", "codigo", "bits")
        self.tree = ttk.Treeview(tbl_box, columns=cols, show="headings", style="HuffCodes.Treeview")

        self.tree.heading("simbolo", text="Símbolo")
        self.tree.heading("byte", text="Byte (Dec / Hex)")
        self.tree.heading("freq", text="Frequência")
        self.tree.heading("pct", text="% Arquivo")
        self.tree.heading("codigo", text="Código Huffman")
        self.tree.heading("bits", text="Tamanho (bits)")

        self.tree.column("simbolo", width=130, anchor="w")
        self.tree.column("byte", width=120, anchor="center")
        self.tree.column("freq", width=100, anchor="e")
        self.tree.column("pct", width=80, anchor="center")
        self.tree.column("codigo", width=220, anchor="center")
        self.tree.column("bits", width=90, anchor="center")

        scrollbar = ttk.Scrollbar(tbl_box, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar.set)

        self.tree.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        self.tree.bind("<<TreeviewSelect>>", self._on_tree_select)

        # Barra inferior com ação
        self.action_bar = ctk.CTkFrame(self, fg_color=COLOR_BORDER_LIGHT, corner_radius=6, height=36)
        self.lbl_selected_info = ctk.CTkLabel(
            self.action_bar,
            text="",
            font=ctk.CTkFont(family=FONT_FAMILY_SANS, size=11),
            text_color=COLOR_TEXT_PRIMARY,
        )
        self.lbl_selected_info.pack(side="left", padx=12, pady=6)

        ctk.CTkButton(
            self.action_bar,
            text="Destacar na Árvore →",
            width=120,
            height=24,
            fg_color=COLOR_ACCENT,
            hover_color=COLOR_ACCENT_HOVER,
            text_color="#FFFFFF",
            font=ctk.CTkFont(family=FONT_FAMILY_SANS, size=10, weight="bold"),
            command=self._on_go_tree,
        ).pack(side="right", padx=10, pady=6)

    def set_data(self, freqs: Dict[int, int], codes: Dict[int, str], total_size: int):
        for item in self.tree.get_children():
            self.tree.delete(item)
        self.sym_by_item_id.clear()

        sorted_syms = sorted(freqs.keys(), key=lambda s: freqs[s], reverse=True)
        for sym in sorted_syms:
            freq = freqs[sym]
            pct = (freq / total_size * 100) if total_size > 0 else 0
            code = codes.get(sym, "")
            item_id = self.tree.insert(
                "",
                tk.END,
                values=(
                    format_symbol(sym),
                    f"{sym} (0x{sym:02X})",
                    f"{freq:,}",
                    f"{pct:.1f}%",
                    code,
                    f"{len(code)} bits",
                ),
            )
            self.sym_by_item_id[item_id] = sym

    def _on_tree_select(self, event):
        sel = self.tree.selection()
        if sel:
            item_id = sel[0]
            sym = self.sym_by_item_id.get(item_id)
            if sym is not None:
                self.selected_symbol = sym
                vals = self.tree.item(item_id, "values")
                self.lbl_selected_info.configure(
                    text=f"Símbolo selecionado: {vals[0]}  ·  Código: {vals[4]} ({vals[5]})"
                )
                self.action_bar.pack(fill="x", padx=16, pady=(0, 10))
                if self.on_select_symbol:
                    self.on_select_symbol(sym, switch_to_tree=False)
        else:
            self.action_bar.pack_forget()

    def _on_go_tree(self):
        if self.selected_symbol is not None and self.on_select_symbol:
            self.on_select_symbol(self.selected_symbol, switch_to_tree=True)


# =============================================================================
# COMPONENTE: STEPPER DO ALGORITMO GULOSO (VISUALIZAÇÃO DA MIN-HEAP & FUSÃO)
# =============================================================================
class AlgorithmStepperView(ctk.CTkFrame):
    """
    Visualizador passo a passo do algoritmo de Huffman:
    - Destaca os 2 menores nós extraídos da Min-Heap
    - Ilustra a fusão e o novo nó gerado
    - Exibe a Min-Heap resultante
    """

    def __init__(self, parent, **kwargs):
        super().__init__(parent, fg_color=COLOR_SURFACE, corner_radius=8, border_width=1, border_color=COLOR_BORDER, **kwargs)
        self.greedy_steps: List[GreedyStep] = []
        self.current_step_index = 0

        header = ctk.CTkFrame(self, fg_color="transparent")
        header.pack(fill="x", padx=18, pady=(14, 4))

        ctk.CTkLabel(
            header,
            text="Algoritmo de Huffman: Decisões Gulosas",
            font=ctk.CTkFont(family=FONT_FAMILY_SANS, size=14, weight="bold"),
            text_color=COLOR_TEXT_PRIMARY,
        ).pack(side="left")

        self.lbl_step_counter = ctk.CTkLabel(
            header,
            text="",
            font=ctk.CTkFont(family=FONT_FAMILY_SANS, size=12, weight="bold"),
            text_color=COLOR_ACCENT,
        )
        self.lbl_step_counter.pack(side="right")

        # Explicação teórica sutil
        expl = ctk.CTkFrame(self, fg_color=COLOR_BORDER_LIGHT, corner_radius=6)
        expl.pack(fill="x", padx=16, pady=(0, 10))

        ctk.CTkLabel(
            expl,
            text="Propriedade da escolha ambiciosa: a cada passo, retiramos os dois elementos com menor frequência da Min-Heap,\n"
                 "criamos um nó pai com a soma de suas frequências e o reinserimos na heap.",
            font=ctk.CTkFont(family=FONT_FAMILY_SANS, size=10),
            text_color=COLOR_TEXT_SECONDARY,
            justify="left",
        ).pack(anchor="w", padx=12, pady=6)

        # Canvas onde os nós da heap e a fusão são desenhados
        self.canvas = tk.Canvas(self, bg=COLOR_SURFACE, highlightthickness=0)
        self.canvas.pack(fill="both", expand=True, padx=16, pady=(0, 6))

        # Controles de navegação
        nav_box = ctk.CTkFrame(self, fg_color="transparent")
        nav_box.pack(fill="x", padx=16, pady=(0, 12))

        self.btn_next = ctk.CTkButton(
            nav_box,
            text="Próximo passo →",
            font=ctk.CTkFont(family=FONT_FAMILY_SANS, size=11, weight="bold"),
            fg_color=COLOR_TEXT_PRIMARY,
            hover_color="#1E293B",
            text_color="#FAFAFA",
            width=120,
            height=28,
            command=self.next_step,
        )
        self.btn_next.pack(side="right")

        self.btn_prev = ctk.CTkButton(
            nav_box,
            text="← Anterior",
            font=ctk.CTkFont(family=FONT_FAMILY_SANS, size=11),
            fg_color=COLOR_BORDER_LIGHT,
            hover_color=COLOR_BORDER,
            text_color=COLOR_TEXT_PRIMARY,
            width=90,
            height=28,
            command=self.prev_step,
        )
        self.btn_prev.pack(side="right", padx=6)

    def set_steps(self, steps: List[GreedyStep]):
        self.greedy_steps = steps
        self.current_step_index = 0
        self.render()

    def next_step(self):
        if self.current_step_index < len(self.greedy_steps) - 1:
            self.current_step_index += 1
            self.render()

    def prev_step(self):
        if self.current_step_index > 0:
            self.current_step_index -= 1
            self.render()

    def render(self):
        self.canvas.delete("all")
        if not self.greedy_steps:
            return

        step = self.greedy_steps[self.current_step_index]
        self.lbl_step_counter.configure(
            text=f"Passo {step.step_number} de {step.total_steps}"
        )
        self.btn_prev.configure(state="normal" if self.current_step_index > 0 else "disabled")
        self.btn_next.configure(state="normal" if self.current_step_index < len(self.greedy_steps) - 1 else "disabled")

        # 1. Min-Heap ANTES da extração
        self.canvas.create_text(
            12, 14,
            text="1. Estado da Min-Heap antes da etapa (os dois menores são escolhidos):",
            anchor="w",
            font=(FONT_FAMILY_SANS, 10, "bold"),
            fill=COLOR_TEXT_PRIMARY,
        )

        card_w = 64
        card_h = 44
        gap = 8
        x = 12
        y = 32

        for i, (label, freq) in enumerate(step.heap_before):
            is_extracted = (i < 2)
            bg = COLOR_ACCENT_BG if is_extracted else COLOR_SURFACE
            border_c = COLOR_ACCENT if is_extracted else COLOR_BORDER
            border_w = 2.0 if is_extracted else 1.0

            self.canvas.create_rectangle(
                x, y, x + card_w, y + card_h,
                fill=bg, outline=border_c, width=border_w,
            )
            self.canvas.create_text(
                x + card_w / 2, y + 14,
                text=label,
                font=(FONT_FAMILY_SANS, 8, "bold"),
                fill=COLOR_ACCENT if is_extracted else COLOR_TEXT_PRIMARY,
            )
            self.canvas.create_text(
                x + card_w / 2, y + 31,
                text=f"{freq}",
                font=(FONT_FAMILY_MONO, 9, "bold"),
                fill=COLOR_ACCENT if is_extracted else COLOR_TEXT_SECONDARY,
            )
            if is_extracted:
                badge_text = "1º menor" if i == 0 else "2º menor"
                self.canvas.create_text(
                    x + card_w / 2, y + card_h + 10,
                    text=badge_text,
                    font=(FONT_FAMILY_SANS, 7, "bold"),
                    fill=COLOR_ACCENT,
                )
            x += card_w + gap

        # 2. Esquema visual da fusão
        my = 110
        self.canvas.create_text(
            12, my,
            text="2. Escolha ambiciosa & criação do nó intermediário:",
            anchor="w",
            font=(FONT_FAMILY_SANS, 10, "bold"),
            fill=COLOR_TEXT_PRIMARY,
        )

        l_lbl, l_f = step.extracted_left
        r_lbl, r_f = step.extracted_right
        m_lbl, m_f = step.merged_item

        # Dois nós filhos
        c1_x = 120
        c2_x = 240
        child_y = my + 20
        w_box = 80
        h_box = 32

        self.canvas.create_rectangle(
            c1_x - w_box / 2, child_y, c1_x + w_box / 2, child_y + h_box,
            fill=COLOR_ACCENT_BG, outline=COLOR_ACCENT, width=1.5,
        )
        self.canvas.create_text(
            c1_x, child_y + 16,
            text=f"{l_lbl} : {l_f}",
            font=(FONT_FAMILY_SANS, 9, "bold"),
            fill=COLOR_ACCENT,
        )

        self.canvas.create_rectangle(
            c2_x - w_box / 2, child_y, c2_x + w_box / 2, child_y + h_box,
            fill=COLOR_ACCENT_BG, outline=COLOR_ACCENT, width=1.5,
        )
        self.canvas.create_text(
            c2_x, child_y + 16,
            text=f"{r_lbl} : {r_f}",
            font=(FONT_FAMILY_SANS, 9, "bold"),
            fill=COLOR_ACCENT,
        )

        # Linhas convergindo para a soma
        parent_cx = (c1_x + c2_x) / 2
        sum_y = child_y + h_box + 22

        self.canvas.create_line(c1_x, child_y + h_box, parent_cx - 20, sum_y, fill=COLOR_ACCENT, width=1.5)
        self.canvas.create_line(c2_x, child_y + h_box, parent_cx + 20, sum_y, fill=COLOR_ACCENT, width=1.5)

        self.canvas.create_text(
            parent_cx, sum_y,
            text=f"{l_f} + {r_f} = {m_f}",
            font=(FONT_FAMILY_MONO, 11, "bold"),
            fill=COLOR_TEXT_PRIMARY,
        )

        # Seta para baixo
        self.canvas.create_line(parent_cx, sum_y + 10, parent_cx, sum_y + 26, arrow="last", fill=COLOR_ACCENT, width=1.8)

        # Novo nó resultante
        res_y = sum_y + 30
        self.canvas.create_rectangle(
            parent_cx - 70, res_y, parent_cx + 70, res_y + 30,
            fill="#F0FDF4", outline=COLOR_SUCCESS, width=1.8,
        )
        self.canvas.create_text(
            parent_cx, res_y + 15,
            text=f"Novo Nó: {m_f}",
            font=(FONT_FAMILY_SANS, 10, "bold"),
            fill=COLOR_SUCCESS,
        )

        # 3. Min-Heap resultante
        hy = res_y + 48
        self.canvas.create_text(
            12, hy,
            text=f"3. Min-Heap resultante após inserção ({len(step.heap_after)} nós restantes):",
            anchor="w",
            font=(FONT_FAMILY_SANS, 10, "bold"),
            fill=COLOR_TEXT_PRIMARY,
        )

        hx = 12
        hy_cards = hy + 18
        for label, freq in step.heap_after:
            is_new = (freq == m_f)
            bg = COLOR_SUCCESS_BG if is_new else COLOR_SURFACE
            border_c = COLOR_SUCCESS if is_new else COLOR_BORDER
            border_w = 1.8 if is_new else 1.0

            self.canvas.create_rectangle(
                hx, hy_cards, hx + card_w, hy_cards + card_h,
                fill=bg, outline=border_c, width=border_w,
            )
            self.canvas.create_text(
                hx + card_w / 2, hy_cards + 14,
                text=label,
                font=(FONT_FAMILY_SANS, 8, "bold"),
                fill=COLOR_SUCCESS if is_new else COLOR_TEXT_PRIMARY,
            )
            self.canvas.create_text(
                hx + card_w / 2, hy_cards + 31,
                text=f"{freq}",
                font=(FONT_FAMILY_MONO, 9, "bold"),
                fill=COLOR_SUCCESS if is_new else COLOR_TEXT_SECONDARY,
            )
            if is_new:
                self.canvas.create_text(
                    hx + card_w / 2, hy_cards + card_h + 10,
                    text="novo",
                    font=(FONT_FAMILY_SANS, 7, "bold"),
                    fill=COLOR_SUCCESS,
                )
            hx += card_w + gap


# =============================================================================
# COMPONENTE: SIMULADOR DIDÁTICO ("EXPERIMENTAR HUFFMAN" & BITS)
# =============================================================================
class DidacticSimulatorView(ctk.CTkFrame):
    """
    Simulador didático interativo:
    Permite digitar frases curtas (ex: 'BANANA') e ver:
    - Comparação visual exata dos bits (Original 8-bit vs Huffman)
    - Tabela de frequências e códigos
    - Economia percentual de bits
    """

    def __init__(self, parent, on_open_tree=None, **kwargs):
        super().__init__(parent, fg_color="transparent", **kwargs)
        self.on_open_tree = on_open_tree

        # Card de controle e input
        input_card = ctk.CTkFrame(
            self,
            fg_color=COLOR_SURFACE,
            corner_radius=8,
            border_width=1,
            border_color=COLOR_BORDER,
        )
        input_card.pack(fill="x", pady=(0, 10))

        ctk.CTkLabel(
            input_card,
            text="Experimentar Huffman (Simulador Didático)",
            font=ctk.CTkFont(family=FONT_FAMILY_SANS, size=15, weight="bold"),
            text_color=COLOR_TEXT_PRIMARY,
        ).pack(anchor="w", padx=18, pady=(14, 4))

        ctk.CTkLabel(
            input_card,
            text="Digite um pequeno texto (até 100 caracteres) para visualizar a codificação caractere a caractere:",
            font=ctk.CTkFont(family=FONT_FAMILY_SANS, size=11),
            text_color=COLOR_TEXT_SECONDARY,
        ).pack(anchor="w", padx=18, pady=(0, 10))

        entry_row = ctk.CTkFrame(input_card, fg_color="transparent")
        entry_row.pack(fill="x", padx=18, pady=(0, 14))

        self.txt_input = ctk.CTkEntry(
            entry_row,
            placeholder_text="Ex: BANANA",
            font=ctk.CTkFont(family=FONT_FAMILY_MONO, size=13),
            height=34,
        )
        self.txt_input.insert(0, "BANANA")
        self.txt_input.pack(side="left", fill="x", expand=True, padx=(0, 8))
        self.txt_input.bind("<Return>", lambda e: self.simulate())

        ctk.CTkButton(
            entry_row,
            text="Simular Huffman",
            font=ctk.CTkFont(family=FONT_FAMILY_SANS, size=11, weight="bold"),
            fg_color=COLOR_ACCENT,
            hover_color=COLOR_ACCENT_HOVER,
            text_color="#FFFFFF",
            height=34,
            width=130,
            command=self.simulate,
        ).pack(side="left")

        # Presets rápidos
        presets_row = ctk.CTkFrame(input_card, fg_color="transparent")
        presets_row.pack(fill="x", padx=18, pady=(0, 12))

        ctk.CTkLabel(
            presets_row,
            text="Exemplos rápidos:",
            font=ctk.CTkFont(family=FONT_FAMILY_SANS, size=10, weight="bold"),
            text_color=COLOR_TEXT_MUTED,
        ).pack(side="left", padx=(0, 6))

        for word in ["BANANA", "ABRACADABRA", "HUFFMAN", "ESTRUTURAS DE DADOS"]:
            ctk.CTkButton(
                presets_row,
                text=word,
                height=22,
                font=ctk.CTkFont(family=FONT_FAMILY_SANS, size=9),
                fg_color=COLOR_BORDER_LIGHT,
                hover_color=COLOR_BORDER,
                text_color=COLOR_TEXT_PRIMARY,
                command=lambda w=word: self._set_preset(w),
            ).pack(side="left", padx=3)

        # Card de Resultados da Simulação
        self.results_card = ctk.CTkFrame(
            self,
            fg_color=COLOR_SURFACE,
            corner_radius=8,
            border_width=1,
            border_color=COLOR_BORDER,
        )
        self.results_card.pack(fill="both", expand=True)

        self.canvas_bits = tk.Canvas(self.results_card, bg=COLOR_SURFACE, highlightthickness=0)
        self.canvas_bits.pack(fill="both", expand=True, padx=16, pady=14)

        self.canvas_bits.bind("<Configure>", lambda e: self.render_bits())

        # Dados da última simulação
        self.sim_text = "BANANA"
        self.sim_freqs: Dict[int, int] = {}
        self.sim_codes: Dict[int, str] = {}
        self.sim_orig_bits = 0
        self.sim_huff_bits = 0
        self.simulate()

    def _set_preset(self, text: str):
        self.txt_input.delete(0, "end")
        self.txt_input.insert(0, text)
        self.simulate()

    def simulate(self):
        text = self.txt_input.get().strip()
        if not text:
            return
        if len(text) > 100:
            text = text[:100]

        raw_bytes = text.encode("utf-8")
        freqs = count_frequencies(raw_bytes)
        root = build_huffman_tree(freqs)
        codes = generate_codes(root)

        orig_bits = len(raw_bytes) * 8
        huff_bits = sum(len(codes[b]) for b in raw_bytes)

        self.sim_text = text
        self.sim_freqs = freqs
        self.sim_codes = codes
        self.sim_orig_bits = orig_bits
        self.sim_huff_bits = huff_bits
        self.render_bits()

    def render_bits(self):
        self.canvas_bits.delete("all")
        if not self.sim_text:
            return

        text = self.sim_text
        codes = self.sim_codes

        # 1. Cabeçalho de Comparação de Bits
        savings = (
            ((self.sim_orig_bits - self.sim_huff_bits) / self.sim_orig_bits * 100)
            if self.sim_orig_bits > 0
            else 0
        )
        self.canvas_bits.create_text(
            12, 16,
            text=f"Visualização de Bits: '{text}'",
            anchor="w",
            font=(FONT_FAMILY_SANS, 13, "bold"),
            fill=COLOR_TEXT_PRIMARY,
        )

        badge_txt = f"↓ {savings:.1f}% de bits economizados!" if savings > 0 else f"{savings:.1f}%"
        self.canvas_bits.create_text(
            12, 38,
            text=f"Original: {self.sim_orig_bits} bits  ➔  Huffman: {self.sim_huff_bits} bits  ({badge_txt})",
            anchor="w",
            font=(FONT_FAMILY_SANS, 11, "bold"),
            fill=COLOR_SUCCESS if savings > 0 else COLOR_WARNING,
        )

        # 2. Bloco: Original (ASCII 8-bit por caractere)
        y = 70
        self.canvas_bits.create_text(
            12, y,
            text="Original (8 bits fixos por caractere):",
            anchor="w",
            font=(FONT_FAMILY_SANS, 10, "bold"),
            fill=COLOR_TEXT_SECONDARY,
        )

        y += 18
        char_x = 12
        col_w = 78

        for ch in text:
            b_val = ord(ch) if ord(ch) < 256 else ord(ch.encode("utf-8")[:1])
            ascii_bin = f"{b_val:08b}"

            self.canvas_bits.create_rectangle(
                char_x, y, char_x + col_w, y + 42,
                fill=COLOR_BORDER_LIGHT, outline=COLOR_BORDER,
            )
            self.canvas_bits.create_text(
                char_x + col_w / 2, y + 13,
                text=ch if ch != " " else "SPACE",
                font=(FONT_FAMILY_SANS, 10, "bold"),
                fill=COLOR_TEXT_PRIMARY,
            )
            self.canvas_bits.create_text(
                char_x + col_w / 2, y + 29,
                text=ascii_bin,
                font=(FONT_FAMILY_MONO, 8),
                fill=COLOR_TEXT_SECONDARY,
            )
            char_x += col_w + 6

        # 3. Bloco: Huffman (Códigos de tamanho variável)
        y += 64
        self.canvas_bits.create_text(
            12, y,
            text="Huffman (códigos de prefixo de tamanho variável):",
            anchor="w",
            font=(FONT_FAMILY_SANS, 10, "bold"),
            fill=COLOR_ACCENT,
        )

        y += 18
        char_x = 12
        for ch in text:
            b_val = ord(ch) if ord(ch) < 256 else ord(ch.encode("utf-8")[:1])
            huff_code = codes.get(b_val, "—")

            self.canvas_bits.create_rectangle(
                char_x, y, char_x + col_w, y + 42,
                fill=COLOR_ACCENT_BG, outline=COLOR_ACCENT_BORDER,
            )
            self.canvas_bits.create_text(
                char_x + col_w / 2, y + 13,
                text=ch if ch != " " else "SPACE",
                font=(FONT_FAMILY_SANS, 10, "bold"),
                fill=COLOR_TEXT_PRIMARY,
            )
            self.canvas_bits.create_text(
                char_x + col_w / 2, y + 29,
                text=huff_code,
                font=(FONT_FAMILY_MONO, 9, "bold"),
                fill=COLOR_ACCENT,
            )
            char_x += col_w + 6

        # 4. Tabela de códigos didática
        y += 66
        self.canvas_bits.create_text(
            12, y,
            text="Dicionário de Símbolos Gerado para esta frase:",
            anchor="w",
            font=(FONT_FAMILY_SANS, 10, "bold"),
            fill=COLOR_TEXT_PRIMARY,
        )

        y += 16
        for sym in sorted(self.sim_freqs.keys(), key=lambda s: self.sim_freqs[s], reverse=True):
            freq = self.sim_freqs[sym]
            c = codes.get(sym, "")
            sym_name = format_symbol(sym)
            row_str = f"• Símbolo {sym_name:<10}  |  {freq}x ocorrências  |  Código: {c:<8} ({len(c)} bits vs 8 originais)"
            self.canvas_bits.create_text(
                16, y,
                text=row_str,
                anchor="w",
                font=(FONT_FAMILY_MONO, 9),
                fill=COLOR_TEXT_PRIMARY,
            )
            y += 18


# =============================================================================
# JANELA PRINCIPAL HUFFPRESS (RESPONSIVA, EDITORIAL, HIERARQUIA TIPOGRÁFICA)
# =============================================================================
class HuffPressGUI:
    """Aplicação desktop moderna HuffPress."""

    def __init__(self, root: ctk.CTk):
        self.root = root
        self.root.title("HuffPress")
        self.root.geometry("1180x760")
        self.root.minsize(980, 680)
        self.root.configure(fg_color=COLOR_BG)

        # Estado global
        self.current_file_path: Optional[str] = None
        self.last_stats: Optional[CompressionStats] = None
        self.last_decompression: Optional[DecompressionResult] = None
        self.selected_symbol: Optional[int] = None

        self._build_top_header()
        self._build_main_container()

        # Começa na tela inicial (Hero)
        self.show_hero_state()

    def _build_top_header(self):
        """Header do aplicativo com logotipo e botão Sobre."""
        top_frame = ctk.CTkFrame(self.root, height=44, fg_color="transparent")
        top_frame.pack(fill="x", padx=24, pady=(12, 0))

        logo_box = ctk.CTkFrame(top_frame, fg_color="transparent")
        logo_box.pack(side="left")

        ctk.CTkLabel(
            logo_box,
            text="HuffPress",
            font=ctk.CTkFont(family=FONT_FAMILY_SANS, size=18, weight="bold"),
            text_color=COLOR_TEXT_PRIMARY,
        ).pack(side="left")

        ctk.CTkLabel(
            logo_box,
            text=" · Compressão de Huffman",
            font=ctk.CTkFont(family=FONT_FAMILY_SANS, size=12),
            text_color=COLOR_TEXT_SECONDARY,
        ).pack(side="left", padx=4)

        right_box = ctk.CTkFrame(top_frame, fg_color="transparent")
        right_box.pack(side="right")

        ctk.CTkButton(
            right_box,
            text="Sobre",
            font=ctk.CTkFont(family=FONT_FAMILY_SANS, size=11),
            fg_color="transparent",
            hover_color=COLOR_BORDER_LIGHT,
            text_color=COLOR_TEXT_SECONDARY,
            width=50,
            height=26,
            command=self._on_about,
        ).pack(side="right")

    def _build_main_container(self):
        self.container = ctk.CTkFrame(self.root, fg_color="transparent")
        self.container.pack(fill="both", expand=True, padx=24, pady=(8, 14))

    def _clear_container(self):
        for widget in self.container.winfo_children():
            widget.destroy()

    # =========================================================================
    # ESTADO 1: ENTRADA (HERO & DROPZONE)
    # =========================================================================
    def show_hero_state(self):
        self._clear_container()

        center_wrapper = ctk.CTkFrame(self.container, fg_color="transparent")
        center_wrapper.pack(expand=True)

        ctk.CTkLabel(
            center_wrapper,
            text="Compressão técnica, limpa e elegante.",
            font=ctk.CTkFont(family=FONT_FAMILY_SANS, size=28, weight="bold"),
            text_color=COLOR_TEXT_PRIMARY,
        ).pack(pady=(0, 6))

        ctk.CTkLabel(
            center_wrapper,
            text="Compactação sem perdas orientada pelo algoritmo guloso de Huffman.",
            font=ctk.CTkFont(family=FONT_FAMILY_SANS, size=13),
            text_color=COLOR_TEXT_SECONDARY,
        ).pack(pady=(0, 24))

        drop_card = ctk.CTkFrame(
            center_wrapper,
            width=460,
            height=190,
            fg_color=COLOR_SURFACE,
            corner_radius=10,
            border_width=1,
            border_color=COLOR_BORDER,
        )
        drop_card.pack(pady=(0, 16))
        drop_card.pack_propagate(False)

        inner = ctk.CTkFrame(drop_card, fg_color="transparent")
        inner.pack(expand=True)

        ctk.CTkButton(
            inner,
            text="Selecionar arquivo",
            font=ctk.CTkFont(family=FONT_FAMILY_SANS, size=13, weight="bold"),
            fg_color=COLOR_TEXT_PRIMARY,
            hover_color="#1E293B",
            text_color="#FFFFFF",
            height=38,
            width=180,
            corner_radius=6,
            command=self._on_select_file,
        ).pack(pady=(0, 8))

        ctk.CTkLabel(
            inner,
            text="ou clique para navegar nos arquivos do computador",
            font=ctk.CTkFont(family=FONT_FAMILY_SANS, size=11),
            text_color=COLOR_TEXT_SECONDARY,
        ).pack(pady=(0, 6))

        ctk.CTkLabel(
            inner,
            text="TXT · JSON · CSV · LOG · SQL · QUALQUER FORMATO",
            font=ctk.CTkFont(family=FONT_FAMILY_MONO, size=9, weight="bold"),
            text_color=COLOR_TEXT_MUTED,
        ).pack()

        bottom_links = ctk.CTkFrame(center_wrapper, fg_color="transparent")
        bottom_links.pack(pady=(4, 0))

        ctk.CTkButton(
            bottom_links,
            text="Descompactar arquivo .huff",
            font=ctk.CTkFont(family=FONT_FAMILY_SANS, size=11),
            fg_color="transparent",
            hover_color=COLOR_BORDER_LIGHT,
            text_color=COLOR_TEXT_SECONDARY,
            command=self._on_open_huff,
        ).pack(side="left", padx=8)

        ctk.CTkButton(
            bottom_links,
            text="Experimentar Huffman (Simulador) →",
            font=ctk.CTkFont(family=FONT_FAMILY_SANS, size=11, weight="bold"),
            fg_color="transparent",
            hover_color=COLOR_BORDER_LIGHT,
            text_color=COLOR_ACCENT,
            command=self._on_open_standalone_simulator,
        ).pack(side="left", padx=8)

    def _on_open_standalone_simulator(self):
        self._clear_container()

        top_nav = ctk.CTkFrame(self.container, fg_color="transparent")
        top_nav.pack(fill="x", pady=(0, 8))

        ctk.CTkButton(
            top_nav,
            text="← Voltar ao início",
            font=ctk.CTkFont(family=FONT_FAMILY_SANS, size=11),
            fg_color="transparent",
            hover_color=COLOR_BORDER_LIGHT,
            text_color=COLOR_TEXT_SECONDARY,
            width=110,
            height=26,
            command=self.show_hero_state,
        ).pack(side="left")

        sim = DidacticSimulatorView(self.container)
        sim.pack(fill="both", expand=True)

    # =========================================================================
    # ESTADO 2: ARQUIVO SELECIONADO (PRONTO PARA COMPACTAR)
    # =========================================================================
    def show_ready_state(self, filepath: str):
        self._clear_container()
        self.current_file_path = filepath

        filename = os.path.basename(filepath)
        size = os.path.getsize(filepath)
        ext = os.path.splitext(filename)[1].upper().replace(".", "") or "ARQUIVO"

        try:
            with open(filepath, "rb") as f:
                sample_bytes = f.read(250000)
            freqs = count_frequencies(sample_bytes)
            num_symbols = len(freqs)
            top_sym, top_count = (
                max(freqs.items(), key=lambda i: i[1]) if freqs else (None, 0)
            )
            top_pct = (top_count / len(sample_bytes)) * 100 if sample_bytes else 0
            top_sym_label = format_symbol(top_sym) if top_sym is not None else "—"
        except Exception:
            num_symbols = 0
            top_sym_label = "—"
            top_pct = 0.0

        nav_frame = ctk.CTkFrame(self.container, fg_color="transparent")
        nav_frame.pack(fill="x", pady=(0, 16))

        ctk.CTkButton(
            nav_frame,
            text="← Trocar arquivo",
            font=ctk.CTkFont(family=FONT_FAMILY_SANS, size=11),
            fg_color="transparent",
            hover_color=COLOR_BORDER_LIGHT,
            text_color=COLOR_TEXT_SECONDARY,
            width=100,
            command=self.show_hero_state,
        ).pack(side="left")

        center_card = ctk.CTkFrame(
            self.container,
            fg_color=COLOR_SURFACE,
            corner_radius=10,
            border_width=1,
            border_color=COLOR_BORDER,
        )
        center_card.pack(fill="both", expand=True, padx=40, pady=10)

        inner = ctk.CTkFrame(center_card, fg_color="transparent")
        inner.pack(fill="both", expand=True, padx=30, pady=24)

        ctk.CTkLabel(
            inner,
            text=filename,
            font=ctk.CTkFont(family=FONT_FAMILY_SANS, size=24, weight="bold"),
            text_color=COLOR_TEXT_PRIMARY,
            anchor="w",
        ).pack(fill="x", pady=(0, 2))

        ctk.CTkLabel(
            inner,
            text=f"{ext} · {format_size(size)} · {size:,} bytes",
            font=ctk.CTkFont(family=FONT_FAMILY_SANS, size=13),
            text_color=COLOR_TEXT_SECONDARY,
            anchor="w",
        ).pack(fill="x", pady=(0, 16))

        ctk.CTkFrame(inner, height=1, fg_color=COLOR_BORDER).pack(fill="x", pady=(0, 18))

        stats_f = ctk.CTkFrame(inner, fg_color="transparent")
        stats_f.pack(fill="x", pady=(0, 24))

        ctk.CTkLabel(
            stats_f,
            text=f"• {num_symbols} símbolos distintos identificados na análise de frequências",
            font=ctk.CTkFont(family=FONT_FAMILY_SANS, size=12),
            text_color=COLOR_TEXT_PRIMARY,
            anchor="w",
        ).pack(fill="x", pady=2)

        ctk.CTkLabel(
            stats_f,
            text=f"• Símbolo mais frequente: {top_sym_label} ({top_pct:.1f}% do arquivo)",
            font=ctk.CTkFont(family=FONT_FAMILY_SANS, size=12),
            text_color=COLOR_TEXT_SECONDARY,
            anchor="w",
        ).pack(fill="x", pady=2)

        ctk.CTkLabel(
            stats_f,
            text="• Compressão sem perdas (lossless) com verificação SHA-256 e formato .huff autocontido",
            font=ctk.CTkFont(family=FONT_FAMILY_SANS, size=12),
            text_color=COLOR_TEXT_SECONDARY,
            anchor="w",
        ).pack(fill="x", pady=2)

        btn_box = ctk.CTkFrame(inner, fg_color="transparent")
        btn_box.pack(pady=12)

        self.btn_compress = ctk.CTkButton(
            btn_box,
            text="Compactar com Huffman",
            font=ctk.CTkFont(family=FONT_FAMILY_SANS, size=13, weight="bold"),
            fg_color=COLOR_TEXT_PRIMARY,
            hover_color="#1E293B",
            text_color="#FFFFFF",
            height=40,
            width=220,
            corner_radius=6,
            command=self._execute_compression,
        )
        self.btn_compress.pack()

        self.lbl_compressing = ctk.CTkLabel(
            inner,
            text="",
            font=ctk.CTkFont(family=FONT_FAMILY_SANS, size=11),
            text_color=COLOR_TEXT_SECONDARY,
        )
        self.lbl_compressing.pack(pady=4)

    def _execute_compression(self):
        if not self.current_file_path:
            return

        self.btn_compress.configure(text="Compactando...", state="disabled")
        self.lbl_compressing.configure(text="Construindo Min-Heap e gerando códigos de Huffman...")
        self.root.update_idletasks()

        try:
            stats = compress_file(self.current_file_path)
            self.last_stats = stats
            self.show_result_state(stats)
        except Exception as e:
            self.btn_compress.configure(text="Compactar com Huffman", state="normal")
            self.lbl_compressing.configure(text="")
            messagebox.showerror("Erro na compactação", f"Ocorreu um erro ao compactar:\n{e}")

    # =========================================================================
    # ESTADO 3: RESULTADO EDITORIAL (CABEÇALHO DE ALTO IMPACTO + ABAS)
    # =========================================================================
    def show_result_state(self, stats: CompressionStats):
        self._clear_container()

        header_size, payload_size = calculate_header_breakdown(stats)
        is_smaller = stats.compressed_size <= stats.original_size
        pct_diff = abs(stats.reduction_percentage)

        # 1. CABEÇALHO DO RESULTADO (Menos altura, alto impacto)
        head_card = ctk.CTkFrame(
            self.container,
            fg_color=COLOR_SURFACE,
            corner_radius=8,
            border_width=1,
            border_color=COLOR_BORDER,
        )
        head_card.pack(fill="x", pady=(0, 8))

        inner_head = ctk.CTkFrame(head_card, fg_color="transparent")
        inner_head.pack(fill="x", padx=16, pady=12)

        # Linha 1: Nome do arquivo e status badge
        row1 = ctk.CTkFrame(inner_head, fg_color="transparent")
        row1.pack(fill="x", pady=(0, 4))

        left_r1 = ctk.CTkFrame(row1, fg_color="transparent")
        left_r1.pack(side="left")

        ctk.CTkButton(
            left_r1,
            text="← Novo arquivo",
            font=ctk.CTkFont(family=FONT_FAMILY_SANS, size=11),
            fg_color="transparent",
            hover_color=COLOR_BORDER_LIGHT,
            text_color=COLOR_TEXT_SECONDARY,
            width=88,
            height=22,
            command=self.show_hero_state,
        ).pack(side="left", padx=(0, 8))

        ctk.CTkLabel(
            left_r1,
            text=stats.original_filename,
            font=ctk.CTkFont(family=FONT_FAMILY_SANS, size=18, weight="bold"),
            text_color=COLOR_TEXT_PRIMARY,
        ).pack(side="left")

        status_txt = "✓ Compactado" if is_smaller else "✓ Codificado (.huff com overhead)"
        status_color = COLOR_SUCCESS if is_smaller else COLOR_WARNING
        ctk.CTkLabel(
            row1,
            text=status_txt,
            font=ctk.CTkFont(family=FONT_FAMILY_SANS, size=12, weight="bold"),
            text_color=status_color,
        ).pack(side="right")

        # Linha 2: Valores principais (30-34px bold) e badge percentual
        row2 = ctk.CTkFrame(inner_head, fg_color="transparent")
        row2.pack(fill="x", pady=(2, 4))

        val_box = ctk.CTkFrame(row2, fg_color="transparent")
        val_box.pack(side="left")

        ctk.CTkLabel(
            val_box,
            text=format_size(stats.original_size),
            font=ctk.CTkFont(family=FONT_FAMILY_SANS, size=30, weight="bold"),
            text_color=COLOR_TEXT_PRIMARY,
        ).pack(side="left")

        ctk.CTkLabel(
            val_box,
            text="  ➔  ",
            font=ctk.CTkFont(family=FONT_FAMILY_SANS, size=20),
            text_color=COLOR_TEXT_MUTED,
        ).pack(side="left")

        ctk.CTkLabel(
            val_box,
            text=format_size(stats.compressed_size),
            font=ctk.CTkFont(family=FONT_FAMILY_SANS, size=30, weight="bold"),
            text_color=COLOR_TEXT_PRIMARY,
        ).pack(side="left")

        badge_str = f"↓ {pct_diff:.1f}% menor" if is_smaller else f"↑ {pct_diff:.1f}% maior"
        badge_bg = COLOR_SUCCESS_BG if is_smaller else COLOR_WARNING_BG
        badge_fg = COLOR_SUCCESS if is_smaller else COLOR_WARNING

        pct_pill = ctk.CTkFrame(val_box, fg_color=badge_bg, corner_radius=6)
        pct_pill.pack(side="left", padx=12)

        ctk.CTkLabel(
            pct_pill,
            text=badge_str,
            font=ctk.CTkFont(family=FONT_FAMILY_SANS, size=12, weight="bold"),
            text_color=badge_fg,
        ).pack(padx=8, pady=2)

        # Botões de ação alinhados à direita na linha 2
        act_box = ctk.CTkFrame(row2, fg_color="transparent")
        act_box.pack(side="right")

        ctk.CTkButton(
            act_box,
            text="Abrir pasta",
            font=ctk.CTkFont(family=FONT_FAMILY_SANS, size=11),
            fg_color=COLOR_SURFACE,
            hover_color=COLOR_BORDER_LIGHT,
            text_color=COLOR_TEXT_PRIMARY,
            border_width=1,
            border_color=COLOR_BORDER,
            height=28,
            width=76,
            corner_radius=6,
            command=lambda: open_folder(stats.output_path),
        ).pack(side="left", padx=4)

        ctk.CTkButton(
            act_box,
            text="Salvar .huff",
            font=ctk.CTkFont(family=FONT_FAMILY_SANS, size=11, weight="bold"),
            fg_color=COLOR_TEXT_PRIMARY,
            hover_color="#1E293B",
            text_color="#FFFFFF",
            height=28,
            width=86,
            corner_radius=6,
            command=self._on_save_huff_copy,
        ).pack(side="left", padx=4)

        # Se o arquivo aumentou: explicação visual contextual
        if not is_smaller:
            warn_banner = ctk.CTkFrame(inner_head, fg_color=COLOR_WARNING_BG, corner_radius=6)
            warn_banner.pack(fill="x", pady=(4, 6))

            ctk.CTkLabel(
                warn_banner,
                text="ℹ O arquivo é muito pequeno e os metadados do formato (.huff: cabeçalho + tabela de frequências) superaram o ganho obtido pela codificação.",
                font=ctk.CTkFont(family=FONT_FAMILY_SANS, size=11),
                text_color=COLOR_WARNING,
                justify="left",
            ).pack(anchor="w", padx=10, pady=4)

        # Linha 3: Barra de Comparação Visual Proporcional
        comp_canvas = tk.Canvas(inner_head, height=8, bg=COLOR_SURFACE, highlightthickness=0)
        comp_canvas.pack(fill="x", pady=(2, 6))

        def _draw_comp_bar(avail_w: int):
            comp_canvas.delete("all")
            max_val = max(stats.original_size, stats.compressed_size, 1)
            bar_y = 2
            bar_h = 4

            # Barra cinza representando o original (100% de referência)
            orig_w = max(4, int((stats.original_size / max_val) * (avail_w - 20)))
            comp_canvas.create_rectangle(
                0, bar_y, orig_w, bar_y + bar_h,
                fill=COLOR_BORDER, outline="",
            )

            # Barra da codificação (Payload em accent, overhead em amber/slate)
            if stats.compressed_size > 0:
                payload_w = int((payload_size / max_val) * (avail_w - 20))
                header_w = int((header_size / max_val) * (avail_w - 20))
                comp_canvas.create_rectangle(
                    0, bar_y, payload_w, bar_y + bar_h,
                    fill=COLOR_ACCENT, outline="",
                )
                comp_canvas.create_rectangle(
                    payload_w, bar_y, payload_w + header_w, bar_y + bar_h,
                    fill=COLOR_WARNING if not is_smaller else COLOR_TEXT_MUTED, outline="",
                )

        comp_canvas.bind("<Configure>", lambda e: _draw_comp_bar(e.width))
        _draw_comp_bar(800)

        # Linha 4: Metadados técnicos sutis
        row4 = ctk.CTkFrame(inner_head, fg_color="transparent")
        row4.pack(fill="x")

        ctk.CTkLabel(
            row4,
            text=f"{stats.unique_symbols} símbolos · {stats.compression_time:.4f} s · SHA-256 verificado",
            font=ctk.CTkFont(family=FONT_FAMILY_SANS, size=11),
            text_color=COLOR_TEXT_SECONDARY,
        ).pack(side="left")

        # 2. BARRA DE NAVEGAÇÃO DISCRETA (TABS)
        tabs_defs = [
            ("summary", "Visão geral"),
            ("frequencies", "Frequências"),
            ("tree", "Árvore"),
            ("codes", "Códigos"),
            ("algorithm", "Algoritmo"),
            ("simulator", "Simulador"),
        ]

        self.tab_views_container = ctk.CTkFrame(self.container, fg_color="transparent")

        self.tab_bar = ModernTabBar(
            self.container,
            tabs=tabs_defs,
            on_change=self._switch_result_tab,
        )
        self.tab_bar.pack(fill="x", pady=(2, 6))
        self.tab_views_container.pack(fill="both", expand=True)

        self.tab_frames: Dict[str, ctk.CTkFrame] = {}

        # Construir todas as abas
        self._build_tab_summary(stats, header_size, payload_size)
        self._build_tab_frequencies(stats)
        self._build_tab_tree(stats)
        self._build_tab_codes(stats)
        self._build_tab_algorithm(stats)
        self._build_tab_simulator(stats)

        # Seleciona Visão geral por padrão
        self.tab_bar.select_tab("summary", notify=True)

    def _switch_result_tab(self, tab_id: str):
        for tid, frame in self.tab_frames.items():
            if tid == tab_id:
                frame.pack(fill="both", expand=True)
            else:
                frame.pack_forget()

        # Ao trocar para a árvore, ajustar à tela e destacar símbolo se houver
        if tab_id == "tree" and "tree" in self.tab_frames:
            tree_widget = self.tab_tree_widget
            if tree_widget:
                tree_widget.after(50, tree_widget.fit_to_view)
                if self.selected_symbol is not None:
                    tree_widget.select_symbol(self.selected_symbol, notify=False)

    # -------------------------------------------------------------------------
    # ABA 1: VISÃO GERAL (RESPOSTAS RÁPIDAS + OVERHEAD + DETALHES RECOLHÍVEIS)
    # -------------------------------------------------------------------------
    def _build_tab_summary(self, stats: CompressionStats, header_size: int, payload_size: int):
        frame = ctk.CTkFrame(self.tab_views_container, fg_color="transparent")
        self.tab_frames["summary"] = frame

        # Grid de 2 colunas
        cols_box = ctk.CTkFrame(frame, fg_color="transparent")
        cols_box.pack(fill="both", expand=True)

        # Coluna 1: Respostas rápidas e métricas principais
        col1 = ctk.CTkFrame(
            cols_box,
            fg_color=COLOR_SURFACE,
            corner_radius=8,
            border_width=1,
            border_color=COLOR_BORDER,
        )
        col1.pack(side="left", fill="both", expand=True, padx=(0, 6))

        ctk.CTkLabel(
            col1,
            text="RESUMO DA COMPRESSÃO",
            font=ctk.CTkFont(family=FONT_FAMILY_SANS, size=10, weight="bold"),
            text_color=COLOR_TEXT_MUTED,
        ).pack(anchor="w", padx=18, pady=(16, 10))

        c1_items = [
            ("Tamanho Original", f"{stats.original_size:,} B ({format_size(stats.original_size)})"),
            ("Tamanho Comprimido", f"{stats.compressed_size:,} B ({format_size(stats.compressed_size)})"),
            ("Resultado", f"{stats.reduction_percentage:.2f}% de redução" if stats.compressed_size <= stats.original_size else f"{abs(stats.reduction_percentage):.2f}% de acréscimo"),
            ("Símbolos únicos", f"{stats.unique_symbols} bytes distintos (de 256)"),
            ("Tempo de execução", f"{stats.compression_time:.4f} s"),
        ]

        for label, val in c1_items:
            row = ctk.CTkFrame(col1, fg_color="transparent")
            row.pack(fill="x", padx=18, pady=4)
            ctk.CTkLabel(
                row,
                text=label,
                width=160,
                font=ctk.CTkFont(family=FONT_FAMILY_SANS, size=11, weight="bold"),
                text_color=COLOR_TEXT_SECONDARY,
                anchor="w",
            ).pack(side="left")
            ctk.CTkLabel(
                row,
                text=val,
                font=ctk.CTkFont(family=FONT_FAMILY_SANS, size=11),
                text_color=COLOR_TEXT_PRIMARY,
                anchor="w",
            ).pack(side="left")

        # Coluna 2: Decomposição do Overhead (.huff breakdown)
        col2 = ctk.CTkFrame(
            cols_box,
            fg_color=COLOR_SURFACE,
            corner_radius=8,
            border_width=1,
            border_color=COLOR_BORDER,
        )
        col2.pack(side="right", fill="both", expand=True, padx=(6, 0))

        ctk.CTkLabel(
            col2,
            text="ANÁLISE DE OVERHEAD & ESTRUTURA",
            font=ctk.CTkFont(family=FONT_FAMILY_SANS, size=10, weight="bold"),
            text_color=COLOR_TEXT_MUTED,
        ).pack(anchor="w", padx=18, pady=(16, 10))

        c2_items = [
            ("Payload codificado", f"{payload_size:,} B", COLOR_ACCENT),
            ("Cabeçalho / metadados", f"{header_size:,} B", COLOR_WARNING if stats.compressed_size > stats.original_size else COLOR_TEXT_SECONDARY),
            ("─────────────────", "───────", COLOR_BORDER),
            ("Arquivo .huff final", f"{stats.compressed_size:,} B", COLOR_TEXT_PRIMARY),
        ]

        for label, val, color in c2_items:
            row = ctk.CTkFrame(col2, fg_color="transparent")
            row.pack(fill="x", padx=18, pady=3)
            ctk.CTkLabel(
                row,
                text=label,
                width=180,
                font=ctk.CTkFont(family=FONT_FAMILY_SANS, size=11, weight="bold"),
                text_color=color if color != COLOR_BORDER else COLOR_TEXT_MUTED,
                anchor="w",
            ).pack(side="left")
            ctk.CTkLabel(
                row,
                text=val,
                font=ctk.CTkFont(family=FONT_FAMILY_MONO, size=11, weight="bold"),
                text_color=color if color != COLOR_BORDER else COLOR_TEXT_MUTED,
                anchor="w",
            ).pack(side="left")

        ctk.CTkLabel(
            col2,
            text="* O cabeçalho inclui magic HUFF1, SHA-256 (32B), nome do arquivo,\n  tamanhos e a tabela serializada com as frequências para descompressão.",
            font=ctk.CTkFont(family=FONT_FAMILY_SANS, size=9),
            text_color=COLOR_TEXT_MUTED,
            justify="left",
        ).pack(anchor="w", padx=18, pady=(12, 0))

        # 3. SEÇÃO RECOLHÍVEL: DETALHES TÉCNICOS (Fechada por padrão)
        tech_wrapper = ctk.CTkFrame(
            frame,
            fg_color=COLOR_SURFACE,
            corner_radius=8,
            border_width=1,
            border_color=COLOR_BORDER,
        )
        tech_wrapper.pack(fill="x", pady=(10, 0))

        tech_header = ctk.CTkFrame(tech_wrapper, fg_color="transparent")
        tech_header.pack(fill="x", padx=18, pady=10)

        self.lbl_tech_toggle = ctk.CTkLabel(
            tech_header,
            text="▶  Detalhes técnicos e integridade",
            font=ctk.CTkFont(family=FONT_FAMILY_SANS, size=12, weight="bold"),
            text_color=COLOR_TEXT_PRIMARY,
            cursor="hand2",
        )
        self.lbl_tech_toggle.pack(side="left")

        # Conteúdo que expande/recolhe
        self.tech_content_frame = ctk.CTkFrame(tech_wrapper, fg_color="transparent")
        self.is_tech_expanded = False

        self.lbl_tech_toggle.bind("<Button-1>", lambda e: self._toggle_technical_details())

        # Linhas técnicas
        t_items = [
            ("SHA-256 do arquivo original:", stats.sha256_hash),
            ("Caminho do arquivo original:", stats.source_path),
            ("Caminho do arquivo comprimido:", stats.output_path),
            ("Formato do arquivo binário:", "HUFF1 (autocontido, sem dependências externas)"),
        ]

        for lbl, val in t_items:
            r = ctk.CTkFrame(self.tech_content_frame, fg_color="transparent")
            r.pack(fill="x", padx=18, pady=2)
            ctk.CTkLabel(
                r,
                text=lbl,
                width=220,
                font=ctk.CTkFont(family=FONT_FAMILY_SANS, size=10, weight="bold"),
                text_color=COLOR_TEXT_SECONDARY,
                anchor="w",
            ).pack(side="left")
            ctk.CTkLabel(
                r,
                text=val,
                font=ctk.CTkFont(family=FONT_FAMILY_MONO, size=10),
                text_color=COLOR_TEXT_PRIMARY,
                anchor="w",
            ).pack(side="left")

    def _toggle_technical_details(self):
        if self.is_tech_expanded:
            self.tech_content_frame.pack_forget()
            self.lbl_tech_toggle.configure(text="▶  Detalhes técnicos e integridade")
            self.is_tech_expanded = False
        else:
            self.tech_content_frame.pack(fill="x", pady=(0, 12))
            self.lbl_tech_toggle.configure(text="▼  Detalhes técnicos e integridade")
            self.is_tech_expanded = True

    # -------------------------------------------------------------------------
    # ABA 2: FREQUÊNCIAS
    # -------------------------------------------------------------------------
    def _build_tab_frequencies(self, stats: CompressionStats):
        frame = ctk.CTkFrame(self.tab_views_container, fg_color="transparent")
        self.tab_frames["frequencies"] = frame

        self.freq_chart = FrequencyChartView(
            frame,
            on_select_symbol=self._on_symbol_selected_from_view,
        )
        self.freq_chart.pack(fill="both", expand=True)
        self.freq_chart.set_data(stats.frequencies, stats.codes, stats.original_size)

    # -------------------------------------------------------------------------
    # ABA 3: ÁRVORE
    # -------------------------------------------------------------------------
    def _build_tab_tree(self, stats: CompressionStats):
        frame = ctk.CTkFrame(self.tab_views_container, fg_color="transparent")
        self.tab_frames["tree"] = frame

        self.tab_tree_widget = ModernTreeCanvas(
            frame,
            on_node_selected=self._on_node_selected_from_tree,
        )
        self.tab_tree_widget.pack(fill="both", expand=True)

        root_node = build_huffman_tree(stats.frequencies)
        self.tab_tree_widget.set_tree(root_node, stats.codes)

    # -------------------------------------------------------------------------
    # ABA 4: CÓDIGOS
    # -------------------------------------------------------------------------
    def _build_tab_codes(self, stats: CompressionStats):
        frame = ctk.CTkFrame(self.tab_views_container, fg_color="transparent")
        self.tab_frames["codes"] = frame

        self.codes_view = CodesTableView(
            frame,
            on_select_symbol=self._on_symbol_selected_from_view,
        )
        self.codes_view.pack(fill="both", expand=True)
        self.codes_view.set_data(stats.frequencies, stats.codes, stats.original_size)

    # -------------------------------------------------------------------------
    # ABA 5: ALGORITMO
    # -------------------------------------------------------------------------
    def _build_tab_algorithm(self, stats: CompressionStats):
        frame = ctk.CTkFrame(self.tab_views_container, fg_color="transparent")
        self.tab_frames["algorithm"] = frame

        self.stepper_view = AlgorithmStepperView(frame)
        self.stepper_view.pack(fill="both", expand=True)

        top_freq = dict(sorted(stats.frequencies.items(), key=lambda i: i[1], reverse=True)[:10])
        steps = simulate_greedy_steps(top_freq)
        self.stepper_view.set_steps(steps)

    # -------------------------------------------------------------------------
    # ABA 6: SIMULADOR
    # -------------------------------------------------------------------------
    def _build_tab_simulator(self, stats: CompressionStats):
        frame = ctk.CTkFrame(self.tab_views_container, fg_color="transparent")
        self.tab_frames["simulator"] = frame

        sim = DidacticSimulatorView(frame)
        sim.pack(fill="both", expand=True)

    # -------------------------------------------------------------------------
    # SINCRONIZAÇÃO DE SELEÇÃO ENTRE COMPONENTES
    # -------------------------------------------------------------------------
    def _on_symbol_selected_from_view(self, symbol: Optional[int], switch_to_tree: bool = False):
        self.selected_symbol = symbol
        if hasattr(self, "tab_tree_widget") and self.tab_tree_widget:
            if symbol is not None:
                self.tab_tree_widget.select_symbol(symbol, notify=False)
            else:
                self.tab_tree_widget.clear_selection(notify=False)

        if switch_to_tree:
            self.tab_bar.select_tab("tree", notify=True)

    def _on_node_selected_from_tree(self, symbol: Optional[int]):
        self.selected_symbol = symbol
        if hasattr(self, "freq_chart") and self.freq_chart:
            self.freq_chart.select_symbol(symbol, notify=False)

    # =========================================================================
    # ESTADO 4: ARQUIVO DESCOMPACTADO (VALIDAÇÃO DE INTEGRIDADE)
    # =========================================================================
    def show_decompressed_state(self, result: DecompressionResult):
        self._clear_container()

        top_nav = ctk.CTkFrame(self.container, fg_color="transparent")
        top_nav.pack(fill="x", pady=(0, 16))

        ctk.CTkButton(
            top_nav,
            text="← Início",
            font=ctk.CTkFont(family=FONT_FAMILY_SANS, size=11),
            fg_color="transparent",
            hover_color=COLOR_BORDER_LIGHT,
            text_color=COLOR_TEXT_SECONDARY,
            width=80,
            command=self.show_hero_state,
        ).pack(side="left")

        card = ctk.CTkFrame(
            self.container,
            fg_color=COLOR_SURFACE,
            corner_radius=10,
            border_width=1,
            border_color=COLOR_BORDER,
        )
        card.pack(fill="both", expand=True, padx=40, pady=10)

        inner = ctk.CTkFrame(card, fg_color="transparent")
        inner.pack(fill="both", expand=True, padx=30, pady=24)

        ctk.CTkLabel(
            inner,
            text="✓ Arquivo restaurado com sucesso",
            font=ctk.CTkFont(family=FONT_FAMILY_SANS, size=12, weight="bold"),
            text_color=COLOR_SUCCESS,
            anchor="w",
        ).pack(fill="x", pady=(0, 4))

        ctk.CTkLabel(
            inner,
            text=result.original_filename,
            font=ctk.CTkFont(family=FONT_FAMILY_SANS, size=24, weight="bold"),
            text_color=COLOR_TEXT_PRIMARY,
            anchor="w",
        ).pack(fill="x", pady=(0, 2))

        ctk.CTkLabel(
            inner,
            text=f"Tamanho recuperado: {format_size(result.decompressed_size)} ({result.decompressed_size:,} bytes) · Tempo: {result.decompression_time:.4f} s",
            font=ctk.CTkFont(family=FONT_FAMILY_SANS, size=13),
            text_color=COLOR_TEXT_SECONDARY,
            anchor="w",
        ).pack(fill="x", pady=(0, 16))

        ctk.CTkFrame(inner, height=1, fg_color=COLOR_BORDER).pack(fill="x", pady=(0, 18))

        integ = ctk.CTkFrame(inner, fg_color=COLOR_SUCCESS_BG, corner_radius=8)
        integ.pack(fill="x", pady=(0, 20))

        ctk.CTkLabel(
            integ,
            text="INTEGRIDADE VERIFICADA VIA SHA-256",
            font=ctk.CTkFont(family=FONT_FAMILY_SANS, size=10, weight="bold"),
            text_color=COLOR_SUCCESS,
        ).pack(anchor="w", padx=16, pady=(12, 2))

        ctk.CTkLabel(
            integ,
            text=f"Hash original verificado: {result.actual_sha256}",
            font=ctk.CTkFont(family=FONT_FAMILY_MONO, size=10),
            text_color=COLOR_TEXT_PRIMARY,
        ).pack(anchor="w", padx=16, pady=(0, 4))

        ctk.CTkLabel(
            integ,
            text="Os bytes do arquivo restaurado coincidem perfeitamente com o original (100% de correspondência byte a byte).",
            font=ctk.CTkFont(family=FONT_FAMILY_SANS, size=11),
            text_color=COLOR_SUCCESS,
        ).pack(anchor="w", padx=16, pady=(0, 12))

        btns = ctk.CTkFrame(inner, fg_color="transparent")
        btns.pack(fill="x")

        ctk.CTkButton(
            btns,
            text="Abrir pasta",
            font=ctk.CTkFont(family=FONT_FAMILY_SANS, size=12, weight="bold"),
            fg_color=COLOR_TEXT_PRIMARY,
            hover_color="#1E293B",
            text_color="#FFFFFF",
            height=34,
            width=130,
            corner_radius=6,
            command=lambda: open_folder(result.restored_path),
        ).pack(side="left", padx=(0, 8))

        ctk.CTkButton(
            btns,
            text="Descompactar outro arquivo",
            font=ctk.CTkFont(family=FONT_FAMILY_SANS, size=12),
            fg_color=COLOR_SURFACE,
            hover_color=COLOR_BORDER_LIGHT,
            text_color=COLOR_TEXT_PRIMARY,
            border_width=1,
            border_color=COLOR_BORDER,
            height=34,
            width=180,
            corner_radius=6,
            command=self._on_open_huff,
        ).pack(side="left")

    # =========================================================================
    # HANDLERS GERAIS
    # =========================================================================
    def _on_select_file(self):
        filepath = filedialog.askopenfilename(
            title="Selecionar arquivo para compactar",
            filetypes=[
                ("Todos os arquivos", "*.*"),
                ("Arquivos de texto", "*.txt;*.csv;*.json;*.log;*.sql;*.md"),
            ],
        )
        if not filepath:
            return
        self.show_ready_state(filepath)

    def _on_open_huff(self):
        filepath = filedialog.askopenfilename(
            title="Selecionar arquivo .huff para descompactar",
            filetypes=[
                ("Arquivos HuffPress (*.huff)", "*.huff"),
                ("Todos os arquivos", "*.*"),
            ],
        )
        if not filepath:
            return

        try:
            result = decompress_file(filepath)
            self.last_decompression = result
            self.show_decompressed_state(result)
        except Exception as e:
            messagebox.showerror("Erro na descompactação", f"Falha ao descompactar:\n{e}")

    def _on_save_huff_copy(self):
        if not self.last_stats:
            return
        default_name = os.path.basename(self.last_stats.output_path)
        dest = filedialog.asksaveasfilename(
            initialfile=default_name,
            title="Salvar cópia do arquivo .huff",
            filetypes=[("Arquivos HuffPress (*.huff)", "*.huff")],
        )
        if dest:
            shutil.copyfile(self.last_stats.output_path, dest)

    def _on_about(self):
        messagebox.showinfo(
            "Sobre o HuffPress",
            "HuffPress 2.0\n\n"
            "Aplicação Desktop para Codificação e Análise de Huffman (Algoritmo Guloso).\n\n"
            "Desenvolvido para a disciplina de Projeto de Algoritmos (PA) — UnB.\n\n"
            "• Min-Heap manual em lista/vetor (sem uso de heapq)\n"
            "• Árvore de Huffman e Bit Packing manual\n"
            "• Integridade estrita garantida por SHA-256 (checksum)\n"
            "• Formato binário .huff totalmente autocontido",
        )


def launch_gui():
    """Inicializa a interface gráfica do HuffPress com CustomTkinter."""
    root = ctk.CTk()
    app = HuffPressGUI(root)
    root.mainloop()
