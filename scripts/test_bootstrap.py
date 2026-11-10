import json
import tempfile
import unittest
from pathlib import Path
from bootstrap_store import initialize
from worldwar.database import make_engine, migrate, sessions
from worldwar.service import create_draft


class BootstrapTests(unittest.TestCase):
    def test_interrupted_import_resumes_and_completed_store_is_left_alone(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);(root/'publication').mkdir()
            (root/'publication/official-results.json').write_text(json.dumps({'contests':[{'id':'fixture'}]}))
            engine=make_engine('sqlite:///'+str(root/'test.db'));migrate(engine)
            calls=[];fail=True
            def runner(*args):
                nonlocal fail
                calls.append(args[0])
                if args[0]=='migrate':
                    with sessions(engine).begin() as session:
                        create_draft(session,'sources',{'id':'fixture-source','title':'Synthetic bootstrap fixture',
                            'url':'https://example.org/fixture','publisher':'Fixture','source_type':'primary',
                            'rights':'Synthetic fixture'},'Bootstrap test')
                if args[0]=='import-official-results' and fail:
                    fail=False
                    raise RuntimeError('Simulated interruption after committed seed')
            with self.assertRaises(RuntimeError):initialize(engine,root,runner)
            initialize(engine,root,runner)
            self.assertEqual(calls.count('migrate'),1)
            self.assertEqual(calls.count('import-official-results'),2)
            self.assertEqual(calls[-1],'apply-publication-actions')
            before=list(calls);initialize(engine,root,runner)
            self.assertEqual(calls,before)
            engine.dispose()


if __name__=='__main__':unittest.main()
