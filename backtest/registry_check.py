import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
os.chdir(PROJECT_ROOT)

from kuegi_bot.bots.strategies.strategy_one import StrategyOne
from kuegi_bot.bots.strategies.strategy_one_entry_modules import EntryModule


class DummyModule(EntryModule):
    name = "dummy"

    def run(self, ctx):
        return None


class DummyAfterModule(EntryModule):
    name = "dummy_after"

    def run(self, ctx):
        return None


class ReplacementModule(EntryModule):
    name = "replacement_10"

    def run(self, ctx):
        return None


def main():
    s = StrategyOne()
    initial = s.listEntryModules()
    assert initial[0] == "entry_1"
    assert initial[1] == "entry_10"
    assert initial[-1] == "entry_22"

    s.withEntryModule(DummyModule(), before="entry_5")
    names = s.listEntryModules()
    assert "dummy" in names
    assert names[names.index("dummy") + 1] == "entry_5"

    s.withEntryModule(DummyAfterModule(), after="entry_5")
    names = s.listEntryModules()
    assert names[names.index("entry_5") + 1] == "dummy_after"

    s.withEntryModule(ReplacementModule(), replace="entry_10")
    names = s.listEntryModules()
    assert "entry_10" not in names
    assert names[1] == "replacement_10"

    s.withoutEntryModule("dummy")
    names = s.listEntryModules()
    assert "dummy" not in names

    s.clearEntryModules()
    assert s.listEntryModules() == []

    print("entry_module_registry_checks: OK")


if __name__ == "__main__":
    main()
