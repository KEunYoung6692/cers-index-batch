from __future__ import annotations

import unittest

import pandas as pd

from src.transforms.source_inventory import (
    CANONICAL_COLUMNS,
    SOURCE_INVENTORY,
    available_sources,
    to_common_schema,
)


class SourceInventoryTests(unittest.TestCase):
    def test_every_source_projects_to_canonical_columns(self) -> None:
        for source_name in available_sources():
            with self.subTest(source=source_name):
                inventory = SOURCE_INVENTORY[source_name]
                sample = {column: None for column in inventory.output_columns}
                sample["source_name"] = source_name
                df = pd.DataFrame([sample])

                projected = to_common_schema(df, source_name)
                self.assertEqual(list(projected.columns), CANONICAL_COLUMNS)
                self.assertEqual(len(projected), 1)

    def test_unknown_source_raises(self) -> None:
        with self.assertRaises(KeyError):
            to_common_schema(pd.DataFrame([{"source_name": "x"}]), "unknown-source")


if __name__ == "__main__":
    unittest.main()

