"""Synthetic regression cases for the repository documentation gate."""
import unittest

from check_docs import check_documents


def fixture():
    return {
        'package.json': '{"version":"0.2.0"}',
        'LocalFolderBridge/bridge/__init__.py': '__version__ = "1.1.1"',
        'README.md': '版本：0.2.0',
        'CHANGELOG.md': '## 0.2.0 — test',
        'PROJECT.md': '| 当前版本 | 1.1.1 | 0.2.0 |',
        'LocalFolderBridge/README.md': '# Local Folder Bridge 1.1.1',
        'LocalFolderBridge/CHANGELOG.md': '## 1.1.1 — test',
        'LocalFolderBridge/docs/操作手册.md': '**Local Folder Bridge 1.1.1｜test**',
    }


class DocumentationChecks(unittest.TestCase):
    def check(self, text, extra=()):
        files = fixture()
        files['docs/guide.md'] = text
        return check_documents(files, set(files) | set(extra))

    def test_consistent_documents_pass(self):
        files = fixture()
        self.assertEqual(check_documents(files, set(files)), [])

    def test_relative_links_references_and_images(self):
        errors = self.check('[text](../README.md)\n![image](img.png)\n[ref][a]\n\n[a]: ../PROJECT.md', ['docs/img.png'])
        self.assertEqual(errors, [])

    def test_missing_reference_target_fails(self):
        self.assertTrue(self.check('[ref][a]\n\n[a]: missing.md'))

    def test_untracked_link_target_fails(self):
        self.assertTrue(self.check('[private](private.md)'))

    def test_untracked_document_cannot_validate_an_unpublished_target(self):
        files = fixture()
        files['README.md'] += '\n[private](private.md)'
        files['private.md'] = 'not in Git'
        self.assertTrue(check_documents(files, set(fixture())))

    def test_encoded_chinese_paths_and_query_fragments(self):
        self.assertEqual(self.check('[manual](../LocalFolderBridge/docs/%E6%93%8D%E4%BD%9C%E6%89%8B%E5%86%8C.md?raw=1#part)'), [])

    def test_parent_escape_fails(self):
        self.assertTrue(self.check('[outside](../../private.md)'))

    def test_external_urls_and_examples_do_not_require_local_files(self):
        self.assertEqual(self.check('[site](https://example.invalid/doc)\n[mail](mailto:test@example.invalid)\n[part](#part)\n\n```md\n[example](missing.md)\n```\n\n`[example](missing.md)`'), [])

    def test_main_branch_links_to_this_repository_are_checked(self):
        prefix = 'https://github.com/MarkTian-Long/local-folder-bridge/blob/main/'
        self.assertEqual(self.check('[ok](' + prefix + 'README.md)'), [])
        self.assertTrue(self.check('[bad](' + prefix + 'missing.md)'))

    def test_node_version_drift_fails(self):
        files = fixture()
        files['package.json'] = '{"version":"0.3.0"}'
        self.assertTrue(check_documents(files, set(files)))

    def test_python_version_drift_fails(self):
        files = fixture()
        files['LocalFolderBridge/bridge/__init__.py'] = '__version__ = "1.2.0"'
        self.assertTrue(check_documents(files, set(files)))

    def test_version_in_old_prose_cannot_mask_stale_current_label(self):
        files = fixture()
        files['README.md'] = '版本：0.1.0\nPrevious release 0.2.0'
        self.assertTrue(check_documents(files, set(files)))


if __name__ == '__main__':
    unittest.main()
