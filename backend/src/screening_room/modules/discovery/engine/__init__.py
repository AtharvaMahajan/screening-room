"""The pure recommendation core: profile -> eligibility -> scoring -> ranking -> explanation.

Nothing here touches the database, reads the clock or uses randomness
(recommendation-engine.md §11); a test enforces it. pipeline.recommend() is
the entry point.
"""
