"""Shared, deterministic word banks for benchmark data builders.

Everything here is pytest-free and importable from plain scripts. A single SEED
keeps every builder reproducible so benchmark inputs never drift between runs.
"""

from __future__ import annotations

SEED = 42

# Author.field must be one of the transmuter/schema Literal values.
FIELDS = [
    "Astrophysics",
    "Robotics",
    "Cybernetics",
    "Xenobiology",
    "Quantum Physics",
    "Science Fiction",
]

AUTHOR_NAMES = [
    "Isaac Asimov",
    "Arthur C. Clarke",
    "Ursula K. Le Guin",
    "Robert A. Heinlein",
    "Frank Herbert",
    "William Gibson",
    "Octavia E. Butler",
    "Ray Bradbury",
    "Larry Niven",
    "Neal Stephenson",
    "Philip K. Dick",
    "Cixin Liu",
]

COUNTRIES = ["USA", "UK", "Germany", "France", "Japan", "Canada"]

BOOK_ADJECTIVES = [
    "Galactic",
    "Neon",
    "Stellar",
    "Interstellar",
    "Synthetic",
    "Cybernetic",
]

BOOK_NOUNS = ["Odyssey", "Chronicles", "Protocol", "Singularity", "Nexus", "Expedition"]

CATEGORY_NAMES = [
    "Hard SF",
    "Space Opera",
    "Cyberpunk",
    "Dystopia",
    "First Contact",
    "Time Travel",
    "Post-Apocalyptic",
    "Military SF",
    "Biopunk",
    "Climate Fiction",
]

PUBLISHER_KINDS = ["House", "Press", "Books"]

TAG_WORDS = [
    "python",
    "rust",
    "go",
    "javascript",
    "typescript",
    "react",
    "vue",
    "svelte",
    "fastapi",
    "django",
    "flask",
    "sqlalchemy",
    "pydantic",
    "docker",
    "kubernetes",
    "aws",
    "gcp",
    "azure",
    "linux",
    "devops",
]

BLOG_AUTHOR_NAMES = [
    "Alice",
    "Bob",
    "Charlie",
    "Diana",
    "Eve",
    "Frank",
    "Grace",
    "Hank",
    "Ivy",
    "Jack",
]

BLOG_ADJECTIVES = ["Ultimate", "Practical", "Modern", "Advanced", "Essential", "Deep"]
BLOG_NOUNS = ["Guide", "Tutorial", "Handbook", "Overview", "Introduction", "Patterns"]

WAREHOUSE_GROUP_NAMES = ["tools", "parts", "supplies", "machines"]
GENERATED_FILE_ROLES = ["draft", "final", "appendix"]
