"""
Generic tab-feature system used by the GUI app.
Each feature can provide a main tab and an optional config tab.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Iterable, List, Optional

import tkinter as tk
from tkinter import ttk


@dataclass(frozen=True)
class FeatureContext:
    """Shared context passed to every feature at build time."""

    root: tk.Tk
    notebook: ttk.Notebook
    config_notebook: Optional[ttk.Notebook] = None
    controller: Optional[Any] = None


class TabFeature(ABC):
    """Base contract for a pluggable GUI feature."""

    name: str = "feature"

    @abstractmethod
    def build_main_tab(self, context: FeatureContext) -> Optional[ttk.Frame]:
        """Create and register the main tab for this feature."""

    def build_config_tab(self, context: FeatureContext) -> Optional[ttk.Frame]:
        """Create and register an optional configuration tab for this feature."""
        return None

    def _create_widgets(self, context: FeatureContext, parent: ttk.Frame):
        """Optional helper used by features that build widgets in one place."""
        return None

    def _refresh_display(self):
        """Optional callback for features that expose a refresh operation."""
        return None


class ConfigSubtabFeature(TabFeature):
    """Template feature for config views rendered as subtabs."""

    config_tab_title: str = "Configuration"

    def build_config_tab(self, context: FeatureContext) -> Optional[ttk.Frame]:
        """Create a config subtab under the shared Configuration tab."""
        if context.config_notebook is None:
            return None

        config_frame = ttk.Frame(context.config_notebook)
        context.config_notebook.add(config_frame, text=self.config_tab_title)
        self._create_config_widgets(context, config_frame)
        return config_frame

    def _create_config_widgets(self, context: FeatureContext, parent: ttk.Frame) -> None:
        """Populate a config subtab. Override in concrete features."""
        return None


class FeatureRegistry:
    """Simple in-memory registry for feature instances."""

    def __init__(self):
        self._features: List[TabFeature] = []

    def register(self, feature: TabFeature) -> None:
        self._features.append(feature)

    def extend(self, features: Iterable[TabFeature]) -> None:
        self._features.extend(features)

    def all(self) -> List[TabFeature]:
        return list(self._features)


def build_registered_tabs(context: FeatureContext, features: Iterable[TabFeature]) -> None:
    """Build all tabs exposed by features in registration order."""
    feature_list = list(features)

    for feature in feature_list:
        feature.build_main_tab(context)

    configuration_tab = ttk.Frame(context.notebook)
    configuration_tab.columnconfigure(0, weight=1)
    configuration_tab.rowconfigure(0, weight=1)

    config_notebook = ttk.Notebook(configuration_tab)
    config_notebook.grid(row=0, column=0, sticky="nsew")

    config_context = FeatureContext(
        root=context.root,
        notebook=context.notebook,
        config_notebook=config_notebook,
        controller=context.controller,
    )

    has_config_subtabs = False
    for feature in feature_list:
        if feature.build_config_tab(config_context) is not None:
            has_config_subtabs = True

    if has_config_subtabs:
        context.notebook.add(configuration_tab, text="Configuration")
