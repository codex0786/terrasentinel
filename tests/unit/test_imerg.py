import numpy as np

from terrasentinel.ingestion.imerg import constraint, window

INDIA = {"west": 68, "south": 6, "east": 98, "north": 38}


def test_window_matches_project_grid():
    x0, x1, y0, y1 = window(INDIA)
    # IMERG cell centres: lon = -179.95 + 0.1 i, lat = -89.95 + 0.1 j
    assert np.isclose(-179.95 + 0.1 * x0, 68.05) and np.isclose(-179.95 + 0.1 * x1, 97.95)
    assert np.isclose(-89.95 + 0.1 * y0, 6.05) and np.isclose(-89.95 + 0.1 * y1, 37.95)
    assert (x1 - x0 + 1, y1 - y0 + 1) == (300, 320)


def test_constraint_requests_only_needed_variables():
    ce = constraint(INDIA)
    assert ce.startswith("/precipitation[0][2480:2779][960:1279];/precipitation_cnt")
    assert "randomError" not in ce
