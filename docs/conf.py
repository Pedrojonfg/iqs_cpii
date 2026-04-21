from __future__ import annotations

import os
import sys

# Make `src/` importable so autodoc can import `iqs.*`
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src")))

project = "iqs"
author = "iqs contributors"

extensions = [
    "sphinx.ext.autodoc",
    "sphinx.ext.napoleon",
    "sphinx.ext.autosummary",
    "sphinx.ext.viewcode",
]

templates_path = ["_templates"]
exclude_patterns: list[str] = ["_build", "Thumbs.db", ".DS_Store"]

autosummary_generate = True
autodoc_typehints = "description"
autodoc_member_order = "bysource"

# Allow building docs without installing runtime deps.
# In the real project environment, you should install deps normally;
# this is only to keep doc builds robust.
autodoc_mock_imports = [
    "ib_insync",
    "numpy",
    "pandas",
    "scipy",
    "yfinance",
    "groq",
    "dotenv",
]

html_theme = "alabaster"

