"""Sphinx 設定ファイル。"""

import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

# ビルド時に docs/demo.png を _static/ にコピー（git 管理外）
_demo_src = Path(__file__).parent.parent / "demo.png"
_demo_dst = Path(__file__).parent / "_static" / "demo.png"
_demo_dst.parent.mkdir(exist_ok=True)
if _demo_src.exists():
    shutil.copy2(_demo_src, _demo_dst)

project = "my-agent-core"
author = "my-agent-core contributors"
copyright = "2024, my-agent-core contributors"
release = "0.1.0"

extensions = [
    "sphinx.ext.autodoc",
    "sphinx.ext.viewcode",
    "sphinx_autodoc_typehints",
    "myst_parser",
]

autodoc_typehints = "description"
autodoc_member_order = "bysource"
autodoc_default_options = {
    "members": True,
    "undoc-members": True,
    "show-inheritance": True,
    "special-members": "__init__",
}
typehints_fully_qualified = False
always_document_param_types = False
typehints_document_rtype = False

html_theme = "furo"
html_static_path = ["_static"]
language = "ja"
exclude_patterns = ["_build", "Thumbs.db", ".DS_Store"]
