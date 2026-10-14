"""The package's shape: every stage imports, the command line names every stage, the contract names every file."""

import importlib
import pathlib
import subprocess
import sys

import code_model_reliability as cmr
from code_model_reliability import cli

ROOT = pathlib.Path(__file__).resolve().parents[1]


def test_every_stage_imports():
    for stage in cmr.STAGES:
        module = importlib.import_module(f"code_model_reliability.{stage}")
        assert module.__doc__ and module.__doc__.strip(), stage


def test_cli_lists_every_stage():
    out = subprocess.run([sys.executable, "-m", "code_model_reliability.cli", "--help"], capture_output=True, text=True, check=True)
    for name in cli.COMMANDS:
        assert name in out.stdout, name


def test_cli_without_a_command_prints_help():
    assert cli.main([]) == 2


def test_contract_names_every_stage():
    text = (ROOT / "docs" / "data-contract.md").read_text(encoding="utf-8")
    for stage in cmr.STAGES:
        assert f"## {stage}" in text, stage
