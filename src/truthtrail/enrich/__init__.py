"""The enrich step (D-22) and the retention purge (D-16, D-18, OD-1).

``resolve`` and ``rollup`` are pure: they derive a cascade's structure (parent states, depth,
canonical order) and its counters from the set of stored rows, and import only the standard
library and ``truthtrail.core``. ``apply`` writes the result back one cascade per transaction,
``purge`` enforces the ratified retention windows as parameters, and ``__main__`` is the
``python -m truthtrail.enrich run|purge`` command line.
"""
