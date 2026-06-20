from tkinter import ttk


class InfoLabel(ttk.Label):
    """Muted helper text label."""
    def __init__(self, parent, text="", wraplength=0, **kwargs):
        style_kw = dict(style="Dim.TLabel")
        if wraplength:
            style_kw["wraplength"] = wraplength
        super().__init__(parent, text=text, **style_kw, **kwargs)


class HeaderLabel(ttk.Label):
    """Section header label."""
    def __init__(self, parent, text="", size=11, **kwargs):
        from tkinter.font import Font
        super().__init__(parent, text=text, style="Accent.TLabel", **kwargs)

