"""
Generic tab-feature system used by the GUI app.
Each feature can provide a main tab and an optional config tab.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Iterable, List, Optional

import tkinter as tk
from tkinter import ttk


@dataclass(frozen=True)
class FeatureContext:
    """Shared context passed to every feature at build time."""

    root: tk.Tk
    notebook: ttk.Notebook


class TabFeature(ABC):
    """Base contract for a pluggable GUI feature."""

    name: str = "feature"

    @abstractmethod
    def build_main_tab(self, context: FeatureContext) -> Optional[ttk.Frame]:
        """Create and register the main tab for this feature."""

    def build_config_tab(self, context: FeatureContext) -> Optional[ttk.Frame]:
        """Create and register an optional configuration tab for this feature."""
        return None

    def _create_widgets(self, parent: ttk.Frame):
        """Optional helper used by features that build widgets in one place."""
        return None

    def _refresh_display(self):
        """Optional callback for features that expose a refresh operation."""
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
    for feature in features:
        feature.build_main_tab(context)
        feature.build_config_tab(context)
