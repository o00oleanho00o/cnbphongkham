"""Composition root: builds the real objects of every package and connects them (package G).

Only ``pema.bootstrap`` and ``pema.workers.main`` import this package; it may import everything (the
import-linter contracts do not list it as a source). No business rule lives here.
"""
