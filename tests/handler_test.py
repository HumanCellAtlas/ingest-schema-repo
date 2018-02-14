from unittest import TestCase
import git
from unittest.mock import patch
import handler

class HandlerTest(TestCase):
    
    def test_handle(self):
        with patch('git.Repo.clone_from') as mock_clone, \
            patch('handler.clear_local_path') as mock_clear_local_path:
            # when
            repo_url = 'http://sample.com/git-repo'
            local_path = '/path/to/repo'
            handler.clone_repo(repo_url, local_path)
            
            # then
            mock_clear_local_path.assert_called_once_with(local_path)
            mock_clone.assert_called_once_with(repo_url, local_path)
            
    def test_handle_not_found(self):
        with patch('git.Repo.clone_from') as mock_clone, \
            patch('handler.clear_local_path'), \
            patch('handler.notify_of_error') as mock_notify:
            # given:
            error = git.GitCommandError('clone', 'not found')
            mock_clone.side_effect = error
                
            # when:
            handler.clone_repo('http://sample.org/git-repo', '/path/to/repo')
            
            # then:
            mock_notify.assert_called_once_with(error)
            