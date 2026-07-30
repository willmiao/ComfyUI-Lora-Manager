import os
import logging
import toml
import zipfile
import shutil
import tempfile
import asyncio
from aiohttp import web, ClientError
from typing import Dict, List

from ..utils.settings_paths import ensure_settings_file
from ..services.downloader import get_downloader
from ..services.service_registry import ServiceRegistry

logger = logging.getLogger(__name__)

NETWORK_EXCEPTIONS = (ClientError, OSError, asyncio.TimeoutError)

# User-managed directories that live inside the plugin folder (portable
# mode) and must survive a Git-based update. ``git clean -fd`` would
# otherwise delete them because they are untracked and, in released tags,
# not listed in ``.gitignore``. ``-e`` excludes a path from cleaning
# regardless of whether it is ignored.
_PRESERVE_DIRS = ('settings.json', 'civitai', 'wildcards', 'backups', 'stats', 'logs', 'cache', 'model_cache')


def _clean_excludes() -> List[str]:
    """Build the ``-e`` arguments for ``git clean`` from :data:`_PRESERVE_DIRS`."""
    excludes: List[str] = []
    for name in _PRESERVE_DIRS:
        excludes.append('-e')
        excludes.append(name)
        # For directories, also exclude nested matches explicitly
        # (``-e dir`` alone matches the dir entry; ``-e dir/**`` guards
        # contents under all git versions as defense-in-depth).
        excludes.append('-e')
        excludes.append(f'{name}/**')
    return excludes


def _stage_preserved_items(plugin_root: str) -> tuple[str, list[str]]:
    """Move preserved user-data items to a temp directory outside *plugin_root*.

    This ensures that ``git reset --hard``, ``git clean -fd``, and ZIP-based
    replacement cannot touch these files even when ``-e`` exclusion patterns
    are mishandled (e.g. on Windows where forward-slash patterns may not
    match backslash-prefixed paths in some Git builds, or where file locks
    prevent deletion/recreation).

    Returns:
        ``(backup_root, staged_names)``: the temp directory path and the
        list of item names that were successfully moved.
    """
    backup_root = tempfile.mkdtemp(prefix='lora_manager_update_')
    staged: list[str] = []
    for name in _PRESERVE_DIRS:
        src = os.path.join(plugin_root, name)
        if not os.path.lexists(src):
            continue
        dst = os.path.join(backup_root, name)
        try:
            shutil.move(src, dst)
            staged.append(name)
            logger.debug("Staged '%s' for update safety", name)
        except OSError:
            # ``shutil.move`` may fail on Windows if a file handle inside
            # the directory is still open (e.g. a SQLite WAL file). Fall
            # back to copy-then-remove.
            logger.debug("Move failed for '%s', falling back to copy", name)
            try:
                if os.path.isdir(src) and not os.path.islink(src):
                    shutil.copytree(src, dst, symlinks=True)
                    shutil.rmtree(src, ignore_errors=True)
                else:
                    shutil.copy2(src, dst)
                    os.remove(src)
                staged.append(name)
                logger.info("Copied (then removed) '%s' for update safety", name)
            except Exception as exc:
                logger.warning(
                    "Could not stage '%s': %s (will rely on git -e / skip lists)", name, exc
                )
    return backup_root, staged


def _restore_preserved_items(plugin_root: str, backup_root: str, staged: list[str]) -> None:
    """Move staged items back from *backup_root* into *plugin_root*.

    Any leftover placeholder at the destination (created by git checkout or
    ZIP extraction) is removed before the move.
    """
    for name in staged:
        src = os.path.join(backup_root, name)
        dst = os.path.join(plugin_root, name)
        try:
            if os.path.lexists(dst):
                if os.path.isdir(dst) and not os.path.islink(dst):
                    shutil.rmtree(dst, ignore_errors=True)
                else:
                    os.remove(dst)
            shutil.move(src, dst)
            logger.debug("Restored '%s' after update", name)
        except OSError:
            logger.debug("Move failed restoring '%s', falling back to copy", name)
            try:
                if os.path.isdir(src) and not os.path.islink(src):
                    shutil.copytree(src, dst, symlinks=True, dirs_exist_ok=True)
                    shutil.rmtree(src, ignore_errors=True)
                else:
                    shutil.copy2(src, dst)
                    os.remove(src)
                logger.info("Copied '%s' back after update", name)
            except Exception as exc:
                logger.error("Failed to restore '%s': %s", name, exc)
    shutil.rmtree(backup_root, ignore_errors=True)



class UpdateRoutes:
    """Routes for handling plugin update checks"""
    
    @staticmethod
    def setup_routes(app):
        """Register update check routes"""
        app.router.add_get('/api/lm/check-updates', UpdateRoutes.check_updates)
        app.router.add_get('/api/lm/version-info', UpdateRoutes.get_version_info)
        app.router.add_post('/api/lm/perform-update', UpdateRoutes.perform_update)
        app.router.add_post('/api/lm/switch-channel', UpdateRoutes.switch_channel)
    
    @staticmethod
    async def check_updates(request):
        """
        Check for plugin updates by comparing local version with GitHub
        Returns update status and version information
        """
        try:
            nightly = request.query.get('nightly', 'false').lower() == 'true'
            
            # Read local version from pyproject.toml
            local_version = UpdateRoutes._get_local_version()
            
            # Get git info (commit hash, branch)
            git_info = UpdateRoutes._get_git_info()

            # Fetch remote version from GitHub
            if nightly:
                local_hash = git_info.get('short_hash', '')
                nightly_version, releases_result = await asyncio.gather(
                    UpdateRoutes._get_nightly_version(local_hash),
                    UpdateRoutes._get_remote_version()
                )
                remote_version, _, behind_by, commit_date = nightly_version
                _, changelog, releases = releases_result
            else:
                remote_version, changelog, releases = await UpdateRoutes._get_remote_version()
                behind_by = 0
                commit_date = ''
            
            # Compare versions
            if nightly:
                # For nightly, compare commit hashes
                update_available = UpdateRoutes._compare_nightly_versions(git_info, remote_version)
            else:
                # For stable, compare semantic versions
                update_available = UpdateRoutes._compare_versions(
                    local_version.replace('v', ''), 
                    remote_version.replace('v', '')
                )
            
            current_dir = os.path.dirname(os.path.abspath(__file__))
            plugin_root = os.path.dirname(os.path.dirname(current_dir))
            has_git = os.path.exists(os.path.join(plugin_root, '.git'))

            response_data = {
                'success': True,
                'current_version': local_version,
                'latest_version': remote_version,
                'update_available': update_available,
                'changelog': changelog,
                'git_info': git_info,
                'nightly': nightly,
                'has_git': has_git,
                'releases': releases,
                'behind_by': behind_by,
                'commit_date': commit_date
            }
            
            return web.json_response(response_data)
            
        except NETWORK_EXCEPTIONS as e:
            logger.warning("Network unavailable during update check: %s", e)
            return web.json_response({
                'success': False,
                'error': 'Network unavailable for update check'
            })
        except Exception as e:
            logger.error(f"Failed to check for updates: {e}", exc_info=True)
            return web.json_response({
                'success': False,
                'error': str(e)
            })
        
    @staticmethod
    async def get_version_info(request):
        """
        Returns the current version in the format 'version-short_hash'
        """
        try:
            # Read local version from pyproject.toml
            local_version = UpdateRoutes._get_local_version().replace('v', '')
            
            # Get git info (commit hash, branch)
            git_info = UpdateRoutes._get_git_info()
            short_hash = git_info['short_hash']
            
            # Format: version-short_hash
            version_string = f"{local_version}-{short_hash}"
            
            current_dir = os.path.dirname(os.path.abspath(__file__))
            plugin_root = os.path.dirname(os.path.dirname(current_dir))
            has_git = os.path.exists(os.path.join(plugin_root, '.git'))

            return web.json_response({
                'success': True,
                'version': version_string,
                'has_git': has_git
            })
            
        except Exception as e:
            logger.error(f"Failed to get version info: {e}", exc_info=True)
            return web.json_response({
                'success': False,
                'error': str(e)
            })
    
    @staticmethod
    async def perform_update(request):
        """
        Perform Git-based update to latest release tag or main branch.
        If .git is missing, fallback to ZIP download.
        """
        try:
            body = await request.json() if request.has_body else {}
            nightly = body.get('nightly', False)

            current_dir = os.path.dirname(os.path.abspath(__file__))
            plugin_root = os.path.dirname(os.path.dirname(current_dir))

            settings_path = ensure_settings_file(logger)
            settings_backup = None
            if os.path.exists(settings_path):
                with open(settings_path, 'r', encoding='utf-8') as f:
                    settings_backup = f.read()
                logger.debug("Backed up settings.json (%d bytes)", len(settings_backup))

            staged_backup_dir, staged_items = _stage_preserved_items(plugin_root)
            try:
                git_folder = os.path.join(plugin_root, '.git')
                if os.path.exists(git_folder):
                    success, new_version = await UpdateRoutes._perform_git_update(plugin_root, nightly)
                else:
                    success, new_version = await UpdateRoutes._download_and_replace_zip(plugin_root)
            finally:
                _restore_preserved_items(plugin_root, staged_backup_dir, staged_items)

            if settings_backup and success:
                with open(settings_path, 'w', encoding='utf-8') as f:
                    f.write(settings_backup)
                logger.debug("Restored settings.json content (%d bytes)", len(settings_backup))

            if success:
                return web.json_response({
                    'success': True,
                    'message': f'Successfully updated to {new_version}',
                    'new_version': new_version
                })
            else:
                return web.json_response({
                    'success': False,
                    'error': 'Failed to complete update'
                })

        except Exception as e:
            logger.error(f"Failed to perform update: {e}", exc_info=True)
            return web.json_response({
                'success': False,
                'error': str(e)
            })

    @staticmethod
    async def switch_channel(request):
        """
        Switch between release and nightly update channels.

        ZIP/CNR install → Nightly: git init + checkout main (one-way upgrade)
        Git install → Release:   git checkout latest tag (.git preserved)
        ZIP/CNR install → Release: ZIP download (no .git, stays in ZIP mode)
        Git install → Nightly:   git checkout main + pull
        """
        try:
            body = await request.json() if request.has_body else {}
            channel = body.get('channel', '')

            if channel not in ('release', 'nightly'):
                return web.json_response({
                    'success': False,
                    'error': f'Invalid channel: {channel}. Must be "release" or "nightly".'
                })

            current_dir = os.path.dirname(os.path.abspath(__file__))
            plugin_root = os.path.dirname(os.path.dirname(current_dir))

            settings_path = ensure_settings_file(logger)
            settings_backup = None
            if os.path.exists(settings_path):
                with open(settings_path, 'r', encoding='utf-8') as f:
                    settings_backup = f.read()
                logger.debug("Backed up settings.json before channel switch (%d bytes)", len(settings_backup))

            staged_backup_dir, staged_items = _stage_preserved_items(plugin_root)
            try:
                git_folder = os.path.join(plugin_root, '.git')

                if channel == 'nightly':
                    git_backup = None
                    if os.path.exists(git_folder):
                        git_backup = UpdateRoutes._backup_git(git_folder, 'nightly')

                    success = False
                    new_version = ''
                    try:
                        if os.path.exists(git_folder):
                            success, new_version = await UpdateRoutes._perform_git_update(
                                plugin_root, nightly=True
                            )
                        else:
                            success, new_version = UpdateRoutes._init_git_repo(plugin_root)
                    finally:
                        UpdateRoutes._restore_git(git_backup, git_folder, success, 'nightly')
                else:
                    success = False
                    new_version = ''
                    if os.path.exists(git_folder):
                        success, new_version = await UpdateRoutes._perform_git_update(
                            plugin_root, nightly=False
                        )
                    else:
                        tracking_file = os.path.join(plugin_root, '.tracking')
                        if os.path.exists(tracking_file):
                            os.remove(tracking_file)
                        success, new_version = await UpdateRoutes._download_and_replace_zip(plugin_root)
            finally:
                _restore_preserved_items(plugin_root, staged_backup_dir, staged_items)

            if settings_backup and success:
                with open(settings_path, 'w', encoding='utf-8') as f:
                    f.write(settings_backup)
                logger.debug("Restored settings.json content after channel switch (%d bytes)", len(settings_backup))

            if success:
                return web.json_response({
                    'success': True,
                    'channel': channel,
                    'new_version': new_version,
                    'message': f'Switched to {channel} channel'
                })
            else:
                return web.json_response({
                    'success': False,
                    'error': f'Failed to switch to {channel} channel'
                })

        except Exception as e:
            logger.error("Failed to switch channel: %s", e, exc_info=True)
            return web.json_response({
                'success': False,
                'error': str(e)
            })

    @staticmethod
    def _init_git_repo(plugin_root: str) -> tuple[bool, str]:
        """
        Initialize a Git repository in a ZIP-installed plugin folder.
        Clones the remote history and checks out main branch.
        """
        try:
            import git
        except ImportError:
            logger.error(
                "GitPython is not available: cannot initialize git repo. "
                "Install git or set $GIT_PYTHON_GIT_EXECUTABLE to the git binary path."
            )
            return False, ""

        clean_excludes = _clean_excludes()

        try:
            repo = git.Repo.init(plugin_root)
            origin = repo.create_remote(
                'origin',
                'https://github.com/willmiao/ComfyUI-Lora-Manager.git'
            )
            origin.fetch()

            repo.create_head('main', origin.refs.main)
            repo.git.checkout('main', '--force')
            repo.git.reset('--hard')
            repo.git.clean('-fd', *clean_excludes)

            tracking_file = os.path.join(plugin_root, '.tracking')
            if os.path.exists(tracking_file):
                os.remove(tracking_file)
                logger.info("Removed .tracking file (now in git mode)")

            new_version = f"main-{repo.head.commit.hexsha[:7]}"
            logger.info("Initialized git repo on main branch: %s", new_version)
            return True, new_version

        except Exception as e:
            logger.error("Failed to initialize git repo: %s", e, exc_info=True)
            return False, ""

    @staticmethod
    def _backup_git(git_folder, label):
        try:
            backup_dir = tempfile.mkdtemp()
            backup = os.path.join(backup_dir, '.git')
            shutil.copytree(git_folder, backup)
            logger.info("Backed up .git before switching to %s", label)
            return backup
        except Exception as e:
            logger.error("Failed to backup .git before %s switch: %s", label, e)
            return None

    @staticmethod
    def _restore_git(git_backup, git_folder, success, label):
        if git_backup and not success:
            try:
                if os.path.exists(git_folder):
                    shutil.rmtree(git_folder)
                shutil.copytree(git_backup, git_folder)
                logger.info("Restored .git after failed %s switch", label)
            except Exception as e:
                logger.error("Failed to restore .git after %s switch: %s", label, e)
        if git_backup:
            shutil.rmtree(os.path.dirname(git_backup), ignore_errors=True)

    @staticmethod
    async def _download_and_replace_zip(plugin_root: str) -> tuple[bool, str]:
        """
        Download latest release ZIP from GitHub and replace plugin files.
        Skips settings.json and civitai folder. Writes extracted file list to .tracking.
        """
        repo_owner = "willmiao"
        repo_name = "ComfyUI-Lora-Manager"
        github_api = f"https://api.github.com/repos/{repo_owner}/{repo_name}/releases/latest"

        try:
            downloader = await get_downloader()
            
            # Get release info
            success, data = await downloader.make_request(
                'GET',
                github_api,
                use_auth=False
            )
            if not success:
                logger.error(f"Failed to fetch release info: {data}")
                return False, ""
            
            zip_url = data.get("zipball_url")
            version = data.get("tag_name", "unknown")

            # Download ZIP to temporary file
            with tempfile.NamedTemporaryFile(delete=False, suffix=".zip") as tmp_zip:
                tmp_zip_path = tmp_zip.name
            
            success, result = await downloader.download_file(
                url=zip_url,
                save_path=tmp_zip_path,
                use_auth=False,
                allow_resume=False
            )
            
            if not success:
                logger.error(f"Failed to download ZIP: {result}")
                return False, ""

            zip_path = tmp_zip_path

            # Close the downloaded-versions SQLite connection before cleaning,
            # so that shutil.rmtree() does not fail on Windows (the process
            # cannot delete a file with an outstanding open handle).
            try:
                history_svc = ServiceRegistry._services.get("downloaded_version_history_service")
                if history_svc is not None:
                    history_svc.close()
                    logger.info("Closed downloaded-version history database connection")
            except Exception:
                logger.debug("Could not close downloaded-version history database", exc_info=True)

            UpdateRoutes._clean_plugin_folder(plugin_root, skip_files=list(_PRESERVE_DIRS))

            # Extract ZIP to temp dir
            with tempfile.TemporaryDirectory() as tmp_dir:
                    with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                        zip_ref.extractall(tmp_dir)
                    # Find extracted folder (GitHub ZIP contains a root folder)
                    extracted_root = next(os.scandir(tmp_dir)).path

                    # Copy files, skipping user data that should be preserved
                    skip_items = set(_PRESERVE_DIRS)
                    for item in os.listdir(extracted_root):
                        if item in skip_items:
                            continue
                        src = os.path.join(extracted_root, item)
                        dst = os.path.join(plugin_root, item)
                        if os.path.isdir(src):
                            if os.path.exists(dst):
                                shutil.rmtree(dst)
                            shutil.copytree(src, dst, ignore=shutil.ignore_patterns(*skip_items))
                        else:
                            shutil.copy2(src, dst)

                    # Write .tracking file: list all files under extracted_root, relative to extracted_root
                    # for ComfyUI Manager to work properly
                    tracking_info_file = os.path.join(plugin_root, '.tracking')
                    tracking_files = []
                    skip_tracked = set(_PRESERVE_DIRS) - {'settings.json'}
                    for root, dirs, files in os.walk(extracted_root):
                        # Skip user data directories and their contents
                        rel_root = os.path.relpath(root, extracted_root)
                        top_dir = rel_root.split(os.sep)[0] if rel_root != '.' else ''
                        if top_dir in skip_tracked:
                            continue
                        for file in files:
                            rel_path = os.path.relpath(os.path.join(root, file), extracted_root)
                            # Skip settings.json and any file under user data dirs
                            if rel_path == 'settings.json' or rel_path.split(os.sep)[0] in skip_tracked:
                                continue
                            tracking_files.append(rel_path.replace("\\", "/"))
                    with open(tracking_info_file, "w", encoding='utf-8') as file:
                        file.write('\n'.join(tracking_files))

            os.remove(zip_path)
            logger.info(f"Updated plugin via ZIP to {version}")
            return True, version

        except Exception as e:
            logger.error(f"ZIP update failed: {e}", exc_info=True)
            return False, ""

    @staticmethod
    def _clean_plugin_folder(plugin_root, skip_files=None):
        skip_files = skip_files or []
        for item in os.listdir(plugin_root):
            if item in skip_files:
                continue
            path = os.path.join(plugin_root, item)
            if os.path.isdir(path):
                shutil.rmtree(path)
            else:
                os.remove(path)
    
    @staticmethod
    async def _get_nightly_version(local_hash: str = "") -> tuple[str, List[str], int, str]:
        repo_owner = "willmiao"
        repo_name = "ComfyUI-Lora-Manager"

        github_url = f"https://api.github.com/repos/{repo_owner}/{repo_name}/commits/main"

        try:
            downloader = await get_downloader()
            success, data = await downloader.make_request(
                'GET', github_url,
                custom_headers={'Accept': 'application/vnd.github+json'}
            )

            if not success:
                logger.warning("Failed to fetch GitHub commit: %s", data)
                return "main", [], 0, ""

            commit_sha = data.get('sha', '')[:7]
            commit_message = data.get('commit', {}).get('message', '')
            commit_date = data.get('commit', {}).get('committer', {}).get('date', '')[:10]

            version = f"main-{commit_sha}"
            changelog = [commit_message] if commit_message else []

            behind_by = 0
            if local_hash and local_hash not in ('unknown', 'stable'):
                compare_url = (
                    f"https://api.github.com/repos/{repo_owner}/{repo_name}"
                    f"/compare/{local_hash}...main"
                )
                c_ok, c_data = await downloader.make_request(
                    'GET', compare_url,
                    custom_headers={'Accept': 'application/vnd.github+json'}
                )
                if c_ok:
                    if c_data.get('status') in ('ahead', 'diverged'):
                        behind_by = c_data.get('ahead_by', 0)
                    else:
                        behind_by = c_data.get('behind_by', 0)

            return version, changelog, behind_by, commit_date

        except NETWORK_EXCEPTIONS as e:
            logger.warning("Unable to reach GitHub for nightly version: %s", e)
            return "main", [], 0, ""
        except Exception as e:
            logger.error("Error fetching nightly version: %s", e, exc_info=True)
            return "main", [], 0, ""
    
    @staticmethod
    def _compare_nightly_versions(local_git_info: Dict[str, str], remote_version: str) -> bool:
        """
        Compare local commit hash with remote main branch
        """
        try:
            local_hash = local_git_info.get('short_hash', 'unknown')
            if local_hash == 'unknown':
                return True  # Assume update available if we can't get local hash
            
            # Extract remote hash from version string (format: "main-{hash}")
            if '-' in remote_version:
                remote_hash = remote_version.split('-')[-1]
                return local_hash != remote_hash
            
            return True  # Default to update available
            
        except Exception as e:
            logger.error(f"Error comparing nightly versions: {e}")
            return False
    
    @staticmethod
    async def _perform_git_update(plugin_root: str, nightly: bool = False) -> tuple[bool, str]:
        """
        Perform Git-based update using GitPython
        
        Args:
            plugin_root: Path to the plugin root directory
            nightly: Whether to update to main branch or latest release
            
        Returns:
            tuple: (success, new_version)
        """
        try:
            import git
        except ImportError:
            logger.error(
                "GitPython is not available: the git executable was not found in PATH. "
                "Install git or set $GIT_PYTHON_GIT_EXECUTABLE to the git binary path."
            )
            return False, ""

        clean_excludes = _clean_excludes()

        try:
            # Open the Git repository
            repo = git.Repo(plugin_root)
            
            # Fetch latest changes
            origin = repo.remotes.origin
            origin.fetch()
            
            if nightly:
                # Reset to discard any local changes
                repo.git.reset('--hard')
                # Clean untracked files, but preserve user-managed directories
                # (wildcards, backups, stats, civitai, caches, settings.json).
                repo.git.clean('-fd', *clean_excludes)
                
                # Switch to main branch and pull latest
                main_branch = 'main'
                if main_branch not in [branch.name for branch in repo.branches]:
                    # Create local main branch if it doesn't exist
                    repo.create_head(main_branch, origin.refs.main)
                
                repo.heads[main_branch].checkout()
                origin.pull(main_branch)
                
                # Get new commit hash
                new_version = f"main-{repo.head.commit.hexsha[:7]}"
                
            else:
                # Reset to discard any local changes
                repo.git.reset('--hard')
                # Clean untracked files, but preserve user-managed directories
                # (wildcards, backups, stats, civitai, caches, settings.json).
                repo.git.clean('-fd', *clean_excludes)
                
                # Get latest release tag
                tags = sorted(repo.tags, key=lambda t: t.commit.committed_datetime, reverse=True)
                if not tags:
                    logger.error("No tags found in repository")
                    return False, ""
                
                latest_tag = tags[0]
                
                # Checkout to latest tag
                repo.git.checkout(latest_tag.name)
                
                new_version = latest_tag.name
            
            logger.info(f"Successfully updated to {new_version}")
            return True, new_version
            
        except git.exc.GitError as e:
            logger.error(f"Git error during update: {e}")
            return False, ""
        except Exception as e:
            logger.error(f"Error during Git update: {e}")
            return False, ""
    
    @staticmethod
    def _get_local_version() -> str:
        """Get local plugin version from pyproject.toml"""
        try:
            # Find the plugin's pyproject.toml file
            current_dir = os.path.dirname(os.path.abspath(__file__))
            plugin_root = os.path.dirname(os.path.dirname(current_dir))
            pyproject_path = os.path.join(plugin_root, 'pyproject.toml')
            
            # Read and parse the toml file
            if os.path.exists(pyproject_path):
                with open(pyproject_path, 'r', encoding='utf-8') as f:
                    project_data = toml.load(f)
                    version = project_data.get('project', {}).get('version', '0.0.0')
                    return f"v{version}"
            else:
                logger.warning(f"pyproject.toml not found at {pyproject_path}")
                return "v0.0.0"
        
        except Exception as e:
            logger.error(f"Failed to get local version: {e}", exc_info=True)
            return "v0.0.0"
    
    @staticmethod
    def _get_git_info() -> Dict[str, str]:
        """Get Git repository information"""
        current_dir = os.path.dirname(os.path.abspath(__file__))
        plugin_root = os.path.dirname(os.path.dirname(current_dir))

        git_info = {
            'commit_hash': 'unknown',
            'short_hash': 'stable',
            'branch': 'unknown',
            'commit_date': 'unknown'
        }

        try:
            # Check if we're in a git repository
            if not os.path.exists(os.path.join(plugin_root, '.git')):
                return git_info

            import git
            repo = git.Repo(plugin_root)
            commit = repo.head.commit
            git_info['commit_hash'] = commit.hexsha
            git_info['short_hash'] = commit.hexsha[:7]
            git_info['branch'] = repo.active_branch.name if not repo.head.is_detached else 'detached'
            git_info['commit_date'] = commit.committed_datetime.strftime('%Y-%m-%d')
        except Exception as e:
            logger.warning(f"Error getting git info: {e}")

        return git_info
    
    @staticmethod
    async def _get_remote_version() -> tuple[str, List[str], List[Dict]]:
        """
        Fetch remote version from GitHub
        Returns:
            tuple: (version string, changelog list, releases list)
        """
        repo_owner = "willmiao"
        repo_name = "ComfyUI-Lora-Manager"
        
        # Use GitHub API to fetch the last 5 releases
        github_url = f"https://api.github.com/repos/{repo_owner}/{repo_name}/releases?per_page=5"
        
        try:
            downloader = await get_downloader()
            success, data = await downloader.make_request('GET', github_url, custom_headers={'Accept': 'application/vnd.github+json'})
            
            if not success:
                logger.warning(f"Failed to fetch GitHub releases: {data}")
                return "v0.0.0", [], []
            
            # Parse releases
            releases = []
            for i, release in enumerate(data):
                version = release.get('tag_name', '')
                if not version.startswith('v'):
                    version = f"v{version}"
                
                # Extract changelog from release notes
                body = release.get('body', '')
                changelog = UpdateRoutes._parse_changelog(body)
                
                releases.append({
                    'version': version,
                    'changelog': changelog,
                    'published_at': release.get('published_at', ''),
                    'is_latest': i == 0
                })
            
            # Get latest version and its changelog
            if releases:
                latest_version = releases[0]['version']
                latest_changelog = releases[0]['changelog']
                return latest_version, latest_changelog, releases
            
            return "v0.0.0", [], []
        
        except NETWORK_EXCEPTIONS as e:
            logger.warning("Unable to reach GitHub for release info: %s", e)
            return "v0.0.0", [], []
        except Exception as e:
            logger.error(f"Error fetching remote version: {e}", exc_info=True)
            return "v0.0.0", [], []
    
    @staticmethod
    def _parse_changelog(release_notes: str) -> List[str]:
        """
        Parse GitHub release notes to extract changelog items
        
        Args:
            release_notes: GitHub release notes markdown text
            
        Returns:
            List of changelog items
        """
        changelog = []
        
        # Simple parsing - extract bullet points
        lines = release_notes.split('\n')
        for line in lines:
            line = line.strip()
            # Look for bullet points or numbered items
            if line.startswith('- ') or line.startswith('* '):
                item = line[2:].strip()
                if item:
                    changelog.append(item)
            # Match numbered items like "1. Item"
            elif len(line) > 2 and line[0].isdigit() and line[1:].startswith('. '):
                item = line[line.index('. ')+2:].strip()
                if item:
                    changelog.append(item)
        
        # If we couldn't parse specific items, use the whole text (limited)
        if not changelog and release_notes:
            # Limit to first 500 chars and add ellipsis
            summary = release_notes.strip()[:500]
            if len(release_notes) > 500:
                summary += "..."
            changelog.append(summary)
            
        return changelog
    
    @staticmethod
    def _compare_versions(version1: str, version2: str) -> bool:
        """
        Compare two semantic version strings
        Returns True if version2 is newer than version1
        Ignores any suffixes after '-' (e.g., -bugfix, -alpha)
        """
        try:
            # Clean version strings - remove any suffix after '-'
            v1_clean = version1.split('-')[0]
            v2_clean = version2.split('-')[0]
            
            # Split versions into components
            v1_parts = [int(x) for x in v1_clean.split('.')]
            v2_parts = [int(x) for x in v2_clean.split('.')]
            
            # Ensure both have 3 components (major.minor.patch)
            while len(v1_parts) < 3:
                v1_parts.append(0)
            while len(v2_parts) < 3:
                v2_parts.append(0)
            
            # Compare version components
            for i in range(3):
                if v2_parts[i] > v1_parts[i]:
                    return True
                elif v2_parts[i] < v1_parts[i]:
                    return False
            
            # Versions are equal
            return False
        except Exception as e:
            logger.error(f"Error comparing versions: {e}", exc_info=True)
            return False
