import importlib.util
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location('foundation', Path(__file__).parents[1] / 'foundation.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class FoundationGuard(unittest.TestCase):
    def test_rejects_replacements_and_immutable_boundary_changes(self):
        for address, actions in [('module.iam.aws_iam_policy.github', ['delete', 'create']), ('aws_iam_policy.runtime_boundary', ['update'])]:
            with self.assertRaises(ValueError):
                module.check_changes({'resource_changes': [{'address': address, 'change': {'actions': actions}}]})

    def test_accepts_regular_ci_policy_update_and_unchanged_root_boundary(self):
        module.check_changes({'resource_changes': [
            {'address': 'module.iam.aws_iam_policy.github', 'change': {'actions': ['update']}},
            {'address': 'aws_iam_policy.runtime_boundary', 'change': {'actions': ['no-op']}}]})
