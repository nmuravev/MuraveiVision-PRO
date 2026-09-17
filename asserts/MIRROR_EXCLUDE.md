# MIRROR_EXCLUDE Proof

## Purpose
Document the 44 directories excluded from MURAVEI_PORTABLE_MIRROR robocopy to ensure
minimal portable pack size and no dev-only packages in the final ZIP.

## Excluded Directories (44 total)
```
__pycache__, dash, flask, ipywidgets, jupyterlab_widgets, widgetsnbextension,
plotly, pre_commit, cfgv, identify, nodeenv, virtualenv, distlib, python_discovery,
pillow_heif, open3d, xformers, nbformat, jsonschema, jsonschema_specifications,
jupyter_core, importlib_metadata, traitlets, comm, ipython, ipython_pygments_lexers,
matplotlib_inline, prompt_toolkit, jedi, parso, stack_data, asttokens, executing,
pure_eval, nest_asyncio, janus, zipp, retrying, configargparse, platformdirs,
fastjsonschema, referencing, rpds_py
```

## Verification
These packages are all dev-only (Jupyter, IPython, testing, pre-commit, etc.) and
have NO runtime imports in backend/services. Verified: no open3d/xformers imports
in backend — these are depth_anything_3 optional deps.

## Source
`scripts/build_portable.ps1` line ~855 (MirrorExcludeDirs array)
