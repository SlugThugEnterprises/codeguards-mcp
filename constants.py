"""Shared constants for guard thresholds — single source of truth."""
# File length
MAX_PROD_LINES = 200
MAX_TEST_LINES = 500
MAX_FN_LINES = 50
MAX_FN_LINES_PYTHON = 50

# Structure
MAX_DOMAINS = 3
MAX_DEPS = 10
MIN_STRUCTURAL_SCORE = 70

# Complexity
MAX_NEST_DEPTH = 4
MAX_PARAMS = 5

# God file
MAX_PUBLIC_ITEMS = 15
MAX_IMPORTS = 20

# Tests
MIN_TEST_RATIO = 0.3

# Duplication
N_GRAM_SIZE = 5
MIN_REPEATS = 2
MIN_LINE_LEN = 10
MIN_COMMENTED_LINES = 5
