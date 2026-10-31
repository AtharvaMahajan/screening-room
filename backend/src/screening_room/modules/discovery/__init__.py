"""Discovery: recommendations (ADR-0010, recommendation-engine.md).

engine/ is the pure core (no database, clock or randomness). retrieval.py reads
its inputs, service.py runs it and logs the results, router.py is the API.
"""
