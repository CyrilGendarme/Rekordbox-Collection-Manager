"""Global dark theme for Your Sets."""
import tkinter as tk
from tkinter import ttk


# ── Palette ────────────────────────────────────────────────────────────────
BG           = "#0e0e12"   # near-black
BG_PANEL     = "#14141a"   # panel background
BG_CARD      = "#1a1a24"   # card / labelframe
BG_INPUT     = "#1e1e2e"   # entry / listbox
BG_HOVER     = "#252535"   # hover
ACCENT       = "#7c6af7"   # purple (primary)
ACCENT_DIM   = "#4a3fa0"   # darker purple
ACCENT2      = "#2eb8b8"   # teal (secondary)
DANGER       = "#e05c6a"   # red
SUCCESS      = "#3ddc97"   # green
WARNING      = "#f0a500"   # amber
FG           = "#e8e8f0"   # main text
FG_DIM       = "#7878a0"   # muted text
FG_BRIGHT    = "#ffffff"
BORDER       = "#2a2a3e"
SEPARATOR    = "#252538"
FONT_MONO    = ("Consolas", 10)
FONT_MONO_SM = ("Consolas", 9)
FONT_UI      = ("Segoe UI", 10)
FONT_UI_SM   = ("Segoe UI", 9)
FONT_BOLD    = ("Segoe UI", 10, "bold")
FONT_TITLE   = ("Consolas", 12, "bold")
FONT_HEAD    = ("Segoe UI", 11, "bold")


def apply_theme(root: tk.Tk):
    """Apply the dark pirate/geeky theme to the entire app."""
    root.configure(bg=BG)

    style = ttk.Style(root)
    style.theme_use("clam")

    # ── General ──────────────────────────────────────────────────────────
    style.configure(".",
        background=BG,
        foreground=FG,
        fieldbackground=BG_INPUT,
        bordercolor=BORDER,
        darkcolor=BG,
        lightcolor=BG_PANEL,
        troughcolor=BG_PANEL,
        selectbackground=ACCENT_DIM,
        selectforeground=FG_BRIGHT,
        font=FONT_UI,
        relief="flat",
        borderwidth=0,
    )

    # ── Frames ────────────────────────────────────────────────────────────
    style.configure("TFrame", background=BG)
    style.configure("Card.TFrame", background=BG_CARD)
    style.configure("Panel.TFrame", background=BG_PANEL)

    # ── LabelFrame ────────────────────────────────────────────────────────
    style.configure("TLabelframe",
        background=BG_CARD,
        bordercolor=BORDER,
        relief="flat",
        padding=10,
    )
    style.configure("TLabelframe.Label",
        background=BG_CARD,
        foreground=ACCENT,
        font=FONT_MONO_SM,
    )

    # ── Labels ────────────────────────────────────────────────────────────
    style.configure("TLabel", background=BG, foreground=FG, font=FONT_UI)
    style.configure("Dim.TLabel", background=BG, foreground=FG_DIM, font=FONT_UI_SM)
    style.configure("Accent.TLabel", background=BG, foreground=ACCENT, font=FONT_BOLD)
    style.configure("Mono.TLabel", background=BG, foreground=ACCENT2, font=FONT_MONO)
    style.configure("Title.TLabel", background=BG, foreground=FG_BRIGHT, font=FONT_TITLE)
    style.configure("Success.TLabel", background=BG, foreground=SUCCESS, font=FONT_UI)
    style.configure("Warning.TLabel", background=BG, foreground=WARNING, font=FONT_UI)
    style.configure("Danger.TLabel", background=BG, foreground=DANGER, font=FONT_UI)

    # ── Buttons ───────────────────────────────────────────────────────────
    style.configure("TButton",
        background=BG_CARD,
        foreground=FG,
        font=FONT_UI,
        borderwidth=1,
        relief="flat",
        padding=(10, 6),
        bordercolor=BORDER,
    )
    style.map("TButton",
        background=[("active", BG_HOVER), ("pressed", ACCENT_DIM)],
        foreground=[("active", FG_BRIGHT)],
        bordercolor=[("active", ACCENT_DIM)],
    )

    style.configure("Accent.TButton",
        background=ACCENT_DIM,
        foreground=FG_BRIGHT,
        font=FONT_BOLD,
        padding=(12, 7),
        borderwidth=0,
    )
    style.map("Accent.TButton",
        background=[("active", ACCENT), ("pressed", "#3a2d8f")],
        foreground=[("active", FG_BRIGHT)],
    )

    style.configure("Danger.TButton",
        background="#3a1a20",
        foreground=DANGER,
        font=FONT_UI,
        borderwidth=1,
        bordercolor="#5a2530",
        padding=(10, 6),
    )
    style.map("Danger.TButton",
        background=[("active", "#5a2530"), ("pressed", DANGER)],
        foreground=[("active", FG_BRIGHT)],
    )

    style.configure("Success.TButton",
        background="#1a3a2a",
        foreground=SUCCESS,
        font=FONT_BOLD,
        padding=(12, 7),
        borderwidth=1,
        bordercolor="#2a5a40",
    )
    style.map("Success.TButton",
        background=[("active", "#2a5a40"), ("pressed", SUCCESS)],
        foreground=[("active", FG_BRIGHT)],
    )

    # ── Notebook (tabs) ───────────────────────────────────────────────────
    style.configure("TNotebook",
        background=BG,
        borderwidth=0,
        tabmargins=[0, 0, 0, 0],
    )
    style.configure("TNotebook.Tab",
        background=BG_PANEL,
        foreground=FG_DIM,
        font=FONT_MONO_SM,
        padding=(16, 8),
        borderwidth=0,
    )
    style.map("TNotebook.Tab",
        background=[("selected", BG_CARD), ("active", BG_HOVER)],
        foreground=[("selected", ACCENT), ("active", FG)],
    )

    # ── Entry ─────────────────────────────────────────────────────────────
    style.configure("TEntry",
        fieldbackground=BG_INPUT,
        foreground=FG,
        insertcolor=ACCENT,
        bordercolor=BORDER,
        lightcolor=BG_INPUT,
        darkcolor=BG_INPUT,
        padding=(8, 5),
        font=FONT_UI,
    )
    style.map("TEntry",
        bordercolor=[("focus", ACCENT_DIM)],
        fieldbackground=[("focus", "#1e1e30")],
    )

    # ── Combobox ──────────────────────────────────────────────────────────
    style.configure("TCombobox",
        fieldbackground=BG_INPUT,
        background=BG_INPUT,
        foreground=FG,
        arrowcolor=ACCENT,
        bordercolor=BORDER,
        padding=(6, 4),
        font=FONT_UI,
    )
    style.map("TCombobox",
        fieldbackground=[("readonly", BG_INPUT), ("focus", "#1e1e30")],
        bordercolor=[("focus", ACCENT_DIM)],
        arrowcolor=[("active", ACCENT)],
    )
    root.option_add("*TCombobox*Listbox.background", BG_INPUT)
    root.option_add("*TCombobox*Listbox.foreground", FG)
    root.option_add("*TCombobox*Listbox.selectBackground", ACCENT_DIM)
    root.option_add("*TCombobox*Listbox.font", FONT_UI)

    # ── Treeview ──────────────────────────────────────────────────────────
    style.configure("Treeview",
        background=BG_CARD,
        foreground=FG,
        fieldbackground=BG_CARD,
        rowheight=26,
        borderwidth=0,
        font=FONT_UI,
    )
    style.configure("Treeview.Heading",
        background=BG_PANEL,
        foreground=ACCENT,
        font=FONT_MONO_SM,
        relief="flat",
        borderwidth=0,
        padding=(8, 6),
    )
    style.map("Treeview",
        background=[("selected", ACCENT_DIM)],
        foreground=[("selected", FG_BRIGHT)],
    )
    style.map("Treeview.Heading",
        background=[("active", BG_HOVER)],
        foreground=[("active", FG_BRIGHT)],
    )

    # ── Scrollbar ─────────────────────────────────────────────────────────
    style.configure("TScrollbar",
        background=BG_PANEL,
        troughcolor=BG,
        bordercolor=BG,
        arrowcolor=FG_DIM,
        relief="flat",
        width=8,
    )
    style.map("TScrollbar",
        background=[("active", ACCENT_DIM), ("pressed", ACCENT)],
        arrowcolor=[("active", FG_BRIGHT)],
    )

    # ── Scale / Slider ────────────────────────────────────────────────────
    style.configure("TScale",
        background=BG,
        troughcolor=BG_PANEL,
        sliderrelief="flat",
        sliderlength=16,
        borderwidth=0,
    )
    style.map("TScale",
        background=[("active", BG)],
        troughcolor=[("active", BORDER)],
    )

    # ── Checkbutton ───────────────────────────────────────────────────────
    style.configure("TCheckbutton",
        background=BG,
        foreground=FG,
        indicatorcolor=BG_INPUT,
        indicatorrelief="flat",
        font=FONT_UI,
    )
    style.map("TCheckbutton",
        background=[("active", BG)],
        indicatorcolor=[("selected", ACCENT), ("active", ACCENT_DIM)],
        foreground=[("active", FG_BRIGHT)],
    )

    # ── Radiobutton ───────────────────────────────────────────────────────
    style.configure("TRadiobutton",
        background=BG,
        foreground=FG,
        font=FONT_UI,
    )
    style.map("TRadiobutton",
        background=[("active", BG)],
        foreground=[("active", FG_BRIGHT)],
    )

    # ── Separator ─────────────────────────────────────────────────────────
    style.configure("TSeparator", background=SEPARATOR)

    # ── Progressbar ───────────────────────────────────────────────────────
    style.configure("TProgressbar",
        background=ACCENT,
        troughcolor=BG_PANEL,
        borderwidth=0,
        thickness=4,
    )

    # ── Spinbox ───────────────────────────────────────────────────────────
    style.configure("TSpinbox",
        fieldbackground=BG_INPUT,
        foreground=FG,
        background=BG_INPUT,
        arrowcolor=ACCENT,
        bordercolor=BORDER,
        font=FONT_UI,
    )