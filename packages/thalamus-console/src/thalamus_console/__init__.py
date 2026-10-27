"""The console: drive the pinned tmux roster from a phone or a browser. A thalamus
plugin, with rooms and the tmux window layout it is built on.

tmux is the control plane: `windows.py` owns the roster's window mechanics and core's
`harness.pin` resolves what each window is pinned to. This is the console onto it, in
the sense the word carries for a hosted service: the surface an operator drives it from.
"""

__version__ = "0.1.1"
