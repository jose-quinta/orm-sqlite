import sys
from pathlib import Path

project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

import unittest

if __name__ == "__main__":
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()

    suite.addTests(loader.loadTestsFromName("src.tests.test_fields"))
    suite.addTests(loader.loadTestsFromName("src.tests.test_connection"))
    suite.addTests(loader.loadTestsFromName("src.tests.test_orm"))
    suite.addTests(loader.loadTestsFromName("src.tests.test_decorators"))
    suite.addTests(loader.loadTestsFromName("src.tests.test_orm_advanced"))
    suite.addTests(loader.loadTestsFromName("src.tests.test_orm_relations"))
    suite.addTests(loader.loadTestsFromName("src.tests.test_query_builder"))
    suite.addTests(loader.loadTestsFromName("src.tests.test_query_q"))
    suite.addTests(loader.loadTestsFromName("src.tests.test_lazy_loading"))
    suite.addTests(loader.loadTestsFromName("src.tests.test_constraints"))
    suite.addTests(loader.loadTestsFromName("src.tests.test_migrations"))

    runner = unittest.TextTestRunner(verbosity=2)
    runner.run(suite)
