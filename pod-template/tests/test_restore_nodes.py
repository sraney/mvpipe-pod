"""Check persistent-node state without network or package changes."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

SOURCE = Path(__file__).resolve().parents[1] / 'scripts/restore_nodes.py'
SPEC = importlib.util.spec_from_file_location('restore_nodes', SOURCE)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class PersistentNodeTest(unittest.TestCase):
    def test_cached_code_disabled_state_and_dependency_recheck(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            workspace, package = root / 'workspace', root / 'package'
            (package / 'node-profiles').mkdir(parents=True)
            manifest = {'nodes': [{'name': 'example-node', 'url': 'https://github.com/example/example-node',
                                   'commit': 'a' * 40, 'enabled': True}]}
            (package / 'node-profiles/test.json').write_text(json.dumps(manifest))
            for name in ['requirements.lock', 'optional-requirements.lock', 'extra_model_paths.yaml']:
                (package / name).write_text('')
            cached = workspace / 'custom_nodes/example-node'
            cached.mkdir(parents=True)
            (cached / 'preserve.txt').write_text('user code')
            with patch.dict(MODULE.os.environ, {'COMFYUI_CONTROL_ROOT': str(root / 'state')}), \
                    patch.object(MODULE, 'run', return_value='example==1'), \
                    patch.object(MODULE.subprocess, 'run') as install:
                MODULE.restore(workspace, package, 'test')
                active = workspace / 'comfyui-config/active-nodes/test/example-node'
                self.assertEqual(active.resolve(), cached)
                self.assertEqual(install.call_count, 1)
                MODULE.restore(workspace, package, 'test')
                self.assertEqual(install.call_count, 1, 'Unchanged environment was reinstalled')
                with patch.object(MODULE, 'run', return_value='example==2'):
                    MODULE.restore(workspace, package, 'test')
                self.assertEqual(install.call_count, 2, 'Changed environment was not rechecked')
                active.rename(active.with_name(active.name + '.disabled'))
                MODULE.restore(workspace, package, 'test')
                self.assertFalse(active.exists(), 'Disabled node was re-enabled')
                self.assertEqual((cached / 'preserve.txt').read_text(), 'user code')
                self.assertEqual(json.loads((workspace / 'comfyui-config/profiles/test.json').read_text()), manifest)


if __name__ == '__main__':
    unittest.main()
