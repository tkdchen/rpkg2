import unittest
import warnings

import mock

from pyrpkg.utils import cached_property, warn_deprecated, log_result


class CachedPropertyTestCase(unittest.TestCase):
    def test_computed_only_once(self):
        class Foo(object):
            @cached_property
            def foo(self):
                runs.append("run once")
                return 42

        runs = []

        f = Foo()
        self.assertEqual(len(runs), 0)
        self.assertEqual(f.foo, 42)
        self.assertEqual(len(runs), 1)
        self.assertEqual(f.foo, 42)
        self.assertEqual(len(runs), 1)

    def test_not_shared_between_properties(self):
        class Foo(object):
            @cached_property
            def foo(self):
                foo_runs.append("run once")
                return 42

            @cached_property
            def bar(self):
                bar_runs.append("run once")
                return 43

        foo_runs = []
        bar_runs = []

        f = Foo()
        self.assertEqual(len(foo_runs), 0)
        self.assertEqual(f.foo, 42)
        self.assertEqual(len(foo_runs), 1)
        self.assertEqual(f.foo, 42)
        self.assertEqual(len(foo_runs), 1)

        self.assertEqual(len(bar_runs), 0)
        self.assertEqual(f.bar, 43)
        self.assertEqual(len(bar_runs), 1)
        self.assertEqual(f.bar, 43)
        self.assertEqual(len(bar_runs), 1)

    def test_not_shared_between_instances(self):
        class Foo(object):
            @cached_property
            def foo(self):
                foo_runs.append("run once")
                return 42

        class Bar(object):
            @cached_property
            def foo(self):
                bar_runs.append("run once")
                return 43

        foo_runs = []
        bar_runs = []

        f = Foo()
        self.assertEqual(len(foo_runs), 0)
        self.assertEqual(f.foo, 42)
        self.assertEqual(len(foo_runs), 1)
        self.assertEqual(f.foo, 42)
        self.assertEqual(len(foo_runs), 1)

        b = Bar()
        self.assertEqual(len(bar_runs), 0)
        self.assertEqual(b.foo, 43)
        self.assertEqual(len(bar_runs), 1)
        self.assertEqual(b.foo, 43)
        self.assertEqual(len(bar_runs), 1)

    def test_not_shared_when_inheriting(self):
        class Foo(object):
            @cached_property
            def foo(self):
                foo_runs.append("run once")
                return 42

        class Bar(Foo):
            @cached_property
            def foo(self):
                bar_runs.append("run once")
                return 43

        foo_runs = []
        bar_runs = []

        b = Bar()
        self.assertEqual(len(bar_runs), 0)
        self.assertEqual(b.foo, 43)
        self.assertEqual(len(bar_runs), 1)
        self.assertEqual(b.foo, 43)
        self.assertEqual(len(bar_runs), 1)

        f = Foo()
        self.assertEqual(len(foo_runs), 0)
        self.assertEqual(f.foo, 42)
        self.assertEqual(len(foo_runs), 1)
        self.assertEqual(f.foo, 42)
        self.assertEqual(len(foo_runs), 1)

        bar_runs = []
        b = Bar()
        self.assertEqual(len(bar_runs), 0)
        self.assertEqual(b.foo, 43)
        self.assertEqual(len(bar_runs), 1)
        self.assertEqual(b.foo, 43)
        self.assertEqual(len(bar_runs), 1)


class DeprecationUtilsTestCase(unittest.TestCase):
    def setUp(self):
        warnings.simplefilter('always', DeprecationWarning)

    @mock.patch('sys.stderr')
    def test_warn_deprecated(self, mock_stderr):
        class Foo(object):
            def old_method(self):
                warn_deprecated(self.__class__.__name__, 'old_method',
                                'new_method')
                return self.new_method()

            def new_method(self):
                return "Yay!"

        def mock_write(msg):
            written_lines.append(msg)

        written_lines = []
        mock_stderr.write.side_effect = mock_write

        foo = Foo()
        self.assertEqual(foo.old_method(), foo.new_method())
        self.assertEqual(len(written_lines), 1)
        self.assertTrue('DeprecationWarning' in written_lines[0])
        self.assertTrue('Foo.old_method' in written_lines[0])
        self.assertTrue('Foo.new_method' in written_lines[0])


class LogResultTestCase(unittest.TestCase):
    def setUp(self):
        self.logs = []

        def info(msg):
            self.logs.append(msg)

        self.log_func = info

    def test_dict_result(self):
        obj = {'spam': 'maps'}
        expected = [
            'spam:',
            '  maps',
        ]
        log_result(self.log_func, obj)
        self.assertEqual(self.logs, expected)

    def test_list_result(self):
        obj = ['eggs', 'bacon', 'hash']
        expected = [
            'eggs',
            'bacon',
            'hash',
        ]
        log_result(self.log_func, obj)
        self.assertEqual(self.logs, expected)

    def test_str_result(self):
        obj = 'spam'
        expected = [
            'spam',
        ]
        log_result(self.log_func, obj)
        self.assertEqual(self.logs, expected)

    def test_complex_result(self):
        obj = {'breakfast': ['eggs', 'bacon', {'spam': 'maps'}]}
        expected = [
            'breakfast:',
            '  eggs',
            '  bacon',
            '  spam:',
            '    maps',
        ]
        log_result(self.log_func, obj)
        self.assertEqual(self.logs, expected)
