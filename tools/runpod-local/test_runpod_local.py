import argparse
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import runpod_local as helper


class LifecycleTests(unittest.TestCase):
    def test_start_running_pod_does_not_resume_again(self):
        api = helper.RunPod(key='test-placeholder')
        api.status = Mock(return_value={'desiredStatus': 'RUNNING'})
        api.query = Mock()
        api.start('examplepod123')
        api.query.assert_not_called()

    def test_start_stopped_pod_resumes_only_that_pod(self):
        api = helper.RunPod(key='test-placeholder')
        api.status = Mock(return_value={'desiredStatus': 'EXITED'})
        api.query = Mock()
        api.start('examplepod123')
        query, variables = api.query.call_args.args
        self.assertIn('podResume', query)
        self.assertIn('gpuCount:1', query)
        self.assertEqual(variables, {'id': 'examplepod123'})
        self.assertEqual(api.query.call_count, 1)

    def test_terminated_pod_is_not_recreated(self):
        api = helper.RunPod(key='test-placeholder')
        api.status = Mock(return_value={'desiredStatus': 'TERMINATED'})
        api.query = Mock()
        with self.assertRaises(RuntimeError):
            api.start('examplepod123')
        api.query.assert_not_called()

    def test_discovers_public_ssh_port_instead_of_old_port(self):
        def port(public, number):
            return {'ip': '127.0.0.1', 'isIpPublic': public, 'privatePort': 22,
                    'publicPort': number, 'type': 'tcp'}
        pod = {'runtime': {'ports': [port(False, 11111), port(True, 22222)]}}
        self.assertEqual(helper.endpoint(pod), ('127.0.0.1', 22222))
        self.assertIsNone(helper.endpoint({'runtime': None}))

    def test_connect_never_starts_stopped_pod(self):
        with tempfile.TemporaryDirectory() as directory:
            args = argparse.Namespace(config=Path(directory) / 'absent.json',
                                      pod_id='examplepod123', action='connect')
            with patch.object(helper, 'RunPod') as constructor:
                api = constructor.return_value
                api.status.return_value = {'desiredStatus': 'EXITED'}
                with self.assertRaises(RuntimeError):
                    helper.execute(args)
                api.start.assert_not_called()


if __name__ == '__main__':
    unittest.main()
