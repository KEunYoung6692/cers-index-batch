from __future__ import annotations

import csv
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


REPO_ROOT = Path(__file__).resolve().parents[1]


class ParserSmokeTests(unittest.TestCase):
    def run_parser(
        self,
        *,
        name: str,
        parser_relpath: str,
        args: list[str],
        required_columns: list[str],
    ) -> None:
        parser_path = REPO_ROOT / parser_relpath
        self.assertTrue(parser_path.exists(), f"missing parser file: {parser_path}")

        with tempfile.TemporaryDirectory(prefix=f"{name}_smoke_") as tmp_dir:
            output_file = Path(tmp_dir) / "out.csv"
            cmd = [sys.executable, str(parser_path), *args, "--output-file", str(output_file)]
            result = subprocess.run(
                cmd,
                cwd=REPO_ROOT,
                text=True,
                capture_output=True,
                check=False,
            )

            self.assertEqual(
                result.returncode,
                0,
                msg=f"{name} failed\ncmd: {' '.join(cmd)}\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}",
            )
            self.assertTrue(
                output_file.exists(),
                msg=f"{name} did not create output file\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}",
            )

            with output_file.open("r", encoding="utf-8-sig", newline="") as fp:
                header = next(csv.reader(fp), [])
            self.assertGreater(len(header), 0, f"{name} output is missing header")
            for column in required_columns:
                self.assertIn(column, header, f"{name} missing column: {column}")

    def test_parsers_with_sample_inputs(self) -> None:
        krx_samples = sorted((REPO_ROOT / "src/sources/krx-esg/output_example").glob("*.pdf"))
        self.assertTrue(krx_samples, "no krx-esg sample PDF found")

        cases = [
            {
                "name": "gir-kor",
                "parser": "src/sources/gir-kor/parser.py",
                "args": ["--input-file", "src/sources/gir-kor/output-example/table_2024.csv"],
                "required": ["source_name", "company_name", "metric_key", "value"],
            },
            {
                "name": "nzdpu-data-explorer",
                "parser": "src/sources/nzdpu-data-explorer/parser.py",
                "args": ["--input-file", "src/sources/nzdpu-data-explorer/output_example/table_scope1.csv"],
                "required": ["source_name", "company_name", "metric_key", "value"],
            },
            {
                "name": "nzdpu-company",
                "parser": "src/sources/nzdpu-company/parser.py",
                "args": ["--input-file", "src/sources/nzdpu-company/output_example/nzdpu_companies_japan.csv"],
                "required": ["source_name", "company_name", "record_type", "value"],
            },
            {
                "name": "jpx-esgdata",
                "parser": "src/sources/jpx-esgdata/parser.py",
                "args": [
                    "--pdf-path",
                    "src/sources/jpx-esgdata/output_example/2025-12-23_285A0_2025-Sustainability-KIOXIA-JP.pdf",
                    "--max-pages",
                    "5",
                ],
                "required": ["source_name", "pdf_path", "record_type", "raw_text"],
            },
            {
                "name": "krx-esg",
                "parser": "src/sources/krx-esg/parser.py",
                "args": ["--pdf-path", str(krx_samples[0]), "--max-pages", "5"],
                "required": ["source_name", "pdf_path", "record_type", "raw_text"],
            },
        ]

        for case in cases:
            with self.subTest(parser=case["name"]):
                self.run_parser(
                    name=case["name"],
                    parser_relpath=case["parser"],
                    args=case["args"],
                    required_columns=case["required"],
                )

    def test_krx_fallback_without_input_args(self) -> None:
        self.run_parser(
            name="krx-esg-fallback",
            parser_relpath="src/sources/krx-esg/parser.py",
            args=["--max-pages", "1"],
            required_columns=["source_name", "pdf_path", "record_type"],
        )


if __name__ == "__main__":
    unittest.main()

