#!/usr/bin/env python

# Incrementally analyse JavaScript project files with the Codemodel Rifle server.
# Soma Lucz | Tresorit | 2016


import argparse
import subprocess
import os
import tempfile
import datetime
import shutil
import sys
import json
import errno
import atexit


class Logger(object):
    """Basic logger class

    Every output of the script has to be through a Logger instance's print_log() method."""

    def __init__(self, verbose, debug):
        self.verbose = verbose
        self.debug = debug

    @staticmethod
    def print_log(what):
        print('CODEMODEL RIFLE: {0}'.format(what))

    def print_verbose(self, what):
        if self.verbose or self.debug:
            self.print_log('VERBOSE: {0}'.format(what))

    def print_debug(self, what):
        if self.debug:
            self.print_log('DEBUG: {0}'.format(what))


class GitInteractor(object):
    """Custom GitInteractor for querying git

    GitPython was NOT suitable for the task as specific flags could not be overwritten.
    """

    def __init__(self, repo_path):
        self.project_git_repository_path = repo_path

    @staticmethod
    def git_query_all_files():
        """Query all *.js files in working directory

        The files are processed into a list. All elements of the list are indicated as an added file in a git diff.
        (This is needed for further processing of the list.)
        """

        pipe = subprocess.PIPE

        git_command = ['git', 'ls-files', '*.js']
        git_query = subprocess.Popen(git_command, stdout=pipe, stderr=pipe)
        stdout, stderr = git_query.communicate()

        if git_query.poll() != 0:
            raise RuntimeError(
                'Error: git ls-files did not return with 0. (Stdout: {0}) (Stderr: {1})'.format(stdout, stderr))

        query_answer = stdout

        # Answer is coming as a string, but we need a list
        files_list = query_answer.split('\n')
        # The list can contain empty elements
        files_list = filter(lambda onefile: len(onefile) > 0, files_list)
        # For further processing, this list must be a git diff list, and all the listed files are newly added files
        for i in range(len(files_list)):
            files_list[i] = ['A', files_list[i]]

        return files_list

    def git_query_diff(self, since):
        """Query diff since the spceified commit in working directory

        Diff is filtered to *.js, and only Added, Deleted or Modified files. Renames are shown as Delete-Add pairs.
        The files are processed into a list.
        """
        if (since is None) or (since == ''):
            return self.git_query_files()

        pipe = subprocess.PIPE

        # We only filter for Added, Deleted and Modified
        git_command = ['git', 'diff', '--name-status', '--diff-algorithm=minimal', '--no-renames', '--diff-filter=ADM',
                       since, 'HEAD', '*.js']
        git_query = subprocess.Popen(git_command, stdout=pipe, stderr=pipe)
        stdout, stderr = git_query.communicate()

        if git_query.poll() != 0:
            raise RuntimeError(
                'Error: git diff did not return with 0. (Stdout: {0}) (Stderr: {1})'.format(stdout, stderr))

        query_answer = stdout

        # Answer is coming as a string, but we need a list
        files_list = query_answer.split('\n')
        # The list can contain empty elements
        files_list = filter(lambda onefile: len(onefile) > 0, files_list)
        # The diff mode and the filename are separated with a \t (tab) character
        files_list = [onefile.split('\t') for onefile in files_list]

        return files_list

    @staticmethod
    def git_query_head():
        """Query the long hash of the commit of HEAD in working directory"""
        pipe = subprocess.PIPE

        git_command = ['git', 'rev-parse', 'HEAD']
        git_query = subprocess.Popen(git_command, stdout=pipe, stderr=pipe)
        stdout, stderr = git_query.communicate()

        if git_query.poll() != 0:
            raise RuntimeError(
                'Error: git rev-parse did not return with 0. (Stdout: {0}) (Stderr: {1})'.format(stdout, stderr))

        head = stdout.rstrip('\n')

        return head

    def git_query_current_revision(self):
        """Query the name of the current branch or revision in working directory

        If we are currently detached, return the commit hash as revision instead of the branch name.
        """
        pipe = subprocess.PIPE

        git_query = subprocess.Popen(['git', 'symbolic-ref', '--short', 'HEAD'], stdout=pipe, stderr=pipe)
        stdout, stderr = git_query.communicate()

        return_code = git_query.poll()

        if return_code != 0:
            # If another error (possibly detached HEAD), then return the HEAD commit name
            if return_code == 128:
                return self.git_query_head()

            raise RuntimeError(
                'Error: git symbolic-ref did not return with 0. (Stdout: {0}) (Stderr: {1})'.format(stdout, stderr))

        current_revision = stdout.rstrip('\n')

        return current_revision


class BabelInteractor:
    def __init__(self, babel_transpilation_temp_folder_path, reimport_full_branch, logger, ignores, config):
        self.babel_transpilation_temp_folder_path = babel_transpilation_temp_folder_path
        self.reimport_full_branch = reimport_full_branch
        self.logger = logger
        self.ignores = ignores
        self.config = config

    def transpile_directory(self):
        """Transpile a whole directory with Babel to the temporary transpilation directory

        Babel config is specified via the external babel-config file.
        """

        if self.logger.debug:
            pipe = subprocess.PIPE
            stdout = pipe
            stderr = pipe
        else:
            devnull = open(os.devnull, 'w')
            stdout = devnull
            stderr = subprocess.STDOUT

        outdirectory = self.babel_transpilation_temp_folder_path

        babel_command = ['babel', os.getcwd(), '--out-dir', outdirectory]
        # at directory transpile, files are directly ignored by babel
        babel_command.extend(['--ignore', ','.join(self.ignores)])

        # External configuration options for babel from codemodel_rifle_babel file
        babel_command.extend(self.config)

        babel = subprocess.Popen(babel_command, stdout=stdout, stderr=stderr)

        stdout, stderr = babel.communicate()

        return outdirectory

    def transpile_file(self, infile):
        """Transpile one file with Babel to the temporary transpilation directory

        Babel config is specified via tha external babel-config file.
        Return the transpiled file's path.
        """
        outfile = os.path.join(self.babel_transpilation_temp_folder_path, infile)
        # The direct parent directory of the file, we need to create that if does not exist with all its parents
        outfile_folder = '/'.join(outfile.split('/')[:-1])
        Miscellanious.ensure_dir(outfile_folder)

        if self.logger.debug:
            pipe = subprocess.PIPE
            stdout = pipe
            stderr = pipe
        else:
            devnull = open(os.devnull, 'w')
            stdout = devnull
            stderr = subprocess.STDOUT

        babel_command = ['babel', infile, '--out-file', outfile]

        # External configuration options for babel from codemodel_rifle_babel file
        babel_command.extend(self.config)

        babel = subprocess.Popen(babel_command, stdout=stdout, stderr=stderr)

        stdout, stderr = babel.communicate()

        return outfile

    def transpile(self, files_with_diff_mode_list):
        """Transpilation process

        The method decides if we need a full transpile or only incremental.

        Incremental:
        The method gets a filelist with the git diff mode prepended to the files in the list. Based on the diff modes,
        transpiles the files which need to be transpiled to the temporary transpilation directory.

        Full:
        Transpiles every file in the working directory to the temporary babel transpilation directory, except ignored
        files from codemodel_rifle_ignore.
        """

        if self.reimport_full_branch:
            try:
                self.transpile_directory()
            except Exception as e:
                e.message = 'Babel directory transpile failed. If debug (-d) set, you can see the filename as well.'
                raise e
            else:
                for i in range(len(files_with_diff_mode_list)):
                    filename = files_with_diff_mode_list[i][1]
                    # We need to know the transpiled files' full path
                    newfilename = os.path.join(self.babel_transpilation_temp_folder_path, filename)
                    # So we append it as a third element of each file "tuple"
                    files_with_diff_mode_list[i].append(newfilename)

        else:
            for i in range(len(files_with_diff_mode_list)):
                diff_mode = files_with_diff_mode_list[i][0]
                filename = files_with_diff_mode_list[i][1]

                try:
                    # Only Added and Modified files need transpilation
                    if diff_mode == 'A' or diff_mode == 'M':
                        if self.logger.debug:
                            self.logger.print_debug('Transpiling {0}...'.format(filename))

                        # We need to know the transpiled files' full path
                        newfilename = self.transpile_file(filename)
                        # So we append it as a third element of each file "tuple"
                        files_with_diff_mode_list[i].append(newfilename)
                except Exception as e:
                    e.message = filename
                    raise e


class CodemodelRifleInteractor:
    def __init__(self, root_path, maxupload, logger):
        self.codemodel_rifle_root_path = root_path
        self.max_upload_trials = maxupload
        self.logger = logger

    def codemodel_rifle_get_last_commit_for_revision(self, revision):
        """Queries the last stored commit for the specified revision from Codemodel Rifle

        The answer from Codemodel Rifle arrives in JSON format, containing the last commit ID
        for the specified revision/branch.
        """
        path = self.codemodel_rifle_root_path + '/lastcommit?branchid=' + revision

        pipe = subprocess.PIPE

        curl_command = ['curl', '-X', 'GET', path]
        curl = subprocess.Popen(curl_command, stdout=pipe, stderr=pipe)
        stdout, stderr = curl.communicate()

        if curl.poll() != 0:
            raise RuntimeError(
                'Could not get last commit for revision "{0}" from Codemodel Rifle. '.format(revision) +
                'Curl did not return with 0. (Curl stdout: {0}) (Curl stderr: {1})'.format(stdout, stderr))

        # The answer arrives in JSON
        json_object = json.loads(stdout)
        # The JSON can be empty
        if 'commitHash' in json_object:
            lastcommit = json_object['commitHash']
            return lastcommit

        return None

    def handle_file(self, filename, diff_mode, transpiled_filename, current_revision, head):
        """Sends the specified file to Codemodel Rifle for processing

        Reads the contents of the file, and sends the file to Codemodel Rifle based on the file's diff mode.
        If there is a server error (e.g. Codemodel Rifle was not able to parse the file), a RuntimeError is raised.
        If there is a network error (e.g. could not send the file to the server), an IOError is raised.
        """
        codemodel_rifle_handle_data_path = '/handle?path={0}&branchid={1}&commithash={2}'.format(filename,
                                                                                                 current_revision,
                                                                                                 head)
        path = self.codemodel_rifle_root_path + codemodel_rifle_handle_data_path

        # if the file was deleted, it was not transpiled a all, so we can not open, nor read it
        if diff_mode != 'D':
            with open(transpiled_filename, 'r') as f:
                contents = f.read()

        pipe = subprocess.PIPE

        # Do-while loop in Python
        i = 0
        while True:
            if diff_mode == 'A':
                curl_command = ['curl', '-X', 'POST', '--data-binary', contents, path]
            elif diff_mode == 'M':
                curl_command = ['curl', '-X', 'PUT', '--data-binary', contents, path]
            else:
                # diff mode can only be Deleted here
                curl_command = ['curl', '-X', 'DELETE', path]

            # we need only the HTTP response code, so we tell curl about it
            curl_command.extend(['-s', '-o', os.path.devnull, '-w', '%{http_code}'])

            curl = subprocess.Popen(curl_command, stdout=pipe, stderr=pipe)

            stdout, stderr = curl.communicate()

            # stdout contains nothing else than HTTP response code
            # but we check it to make sure
            try:
                http_response_code = int(stdout)
            except ValueError:
                http_response_code = ''

            if curl.poll() == 0 and http_response_code != 500:
                return True

            if http_response_code == 500:
                raise RuntimeError(filename)

            if i >= self.max_upload_trials:
                raise IOError(filename)

            i += 1

    def handle(self, files_with_diff_mode_list, current_revision, head):
        """Sends each file from the specified list to Codemodel Rifle for processing."""
        for elem in files_with_diff_mode_list:
            diff_mode = elem[0]
            filename = elem[1]
            if len(elem) >= 3:
                transpiled_filename = elem[2]
            else:
                transpiled_filename = elem[1]

            if self.logger.debug:
                self.logger.print_debug('Sending {0} to Codemodel Rifle...'.format(filename))

            self.handle_file(filename, diff_mode, transpiled_filename, current_revision, head)


class Miscellanious:
    def __init__(self):
        pass

    @staticmethod
    def ensure_dir(dirname):
        """Replacement for the 'exists_ok' parameter of the makedirs() function in Python 3

        Recursive directory creation function.
        If the directory exists, we do not throw error but continue the creation.
        """
        try:
            os.makedirs(dirname)
        except OSError as e:
            if e.errno != errno.EEXIST:
                raise


class Application:
    def __init__(self, reimport_full_branch, ignorefile, babelconfigfile):
        self.reimport_full_branch = reimport_full_branch
        self.ignorefile = ignorefile
        self.babelconfigfile = babelconfigfile
        self.ignores = []
        self.babelconfig = []

    def read_ignore(self):
        """Reads and parses the provided ignorefile.

        Returns with True if the ignorefile is present and successfully parsed, False if no ignorefile present.
        """
        if os.path.exists(self.ignorefile):
            with open(self.ignorefile, 'r') as f:
                ignores = f.read()
            ignores = ignores.split('\n')
            ignores = filter(lambda ignore: len(ignore) > 0, ignores)

            self.ignores = ignores
            return True

        return False

    def ignored(self, filename):
        """Filter for filtering the files not needed for the analysis (files which are ignored)"""
        for ignore_rule in self.ignores:
            if ignore_rule in filename:
                return True

        return False

    def read_babelconfig(self):
        """Reads and parses the provided babel-config-file. (codemodel-rifle-babel by default)

        Returns with True if the config file is present and successfully parsed, False if no config file present.
        """
        if os.path.exists(self.babelconfigfile):
            with open(self.babelconfigfile, 'r') as f:
                babelconfig = f.read()
            babelconfig = babelconfig.split('\n')
            babelconfig = filter(lambda config: len(config) > 0, babelconfig)

            self.babelconfig = babelconfig
            return True

        return False

    @staticmethod
    def clean_directory(directory):
        # Checks if exists and is a directory
        if os.path.isdir(directory):
            shutil.rmtree(directory)


def main():
    parser = argparse.ArgumentParser(
        description='Get the modified files since the last commit, ' +
                    'and send them to the Codemodel Rifle server for analysis.')

    # Positional arguments
    parser.add_argument('project_git_repository_path',
                        help='The Git repository of the project. Either relative or absolute path.',
                        metavar='GITREPOSITORYPATH')
    parser.add_argument('codemodel_rifle_root_path',
                        help='The root path of the Codemodel Rifle application, e.g. http://127.0.0.1:8080/codemodel',
                        metavar='RIFLEROOTPATH')

    # Optional arguments
    parser.add_argument('-i', '--ignorefile',
                        help='Files that are ignored during the import and analysis should be listed in a separate ' +
                             'file in separate lines. This argument defaults to "codemodel_rifle_ignore". ' +
                             'Ignorefile should contain full relative paths to the git repository. For example: ' +
                             'app/lib/asmcrypto.js instead of asmcrypto.js and app/lib/ instead of lib/. ' +
                             'Directories should have a trailing slash.',
                        metavar='IGNOREFILE', default='codemodel_rifle_ignore')
    parser.add_argument('-b', '--babel-config-file',
                        help='Babel CLI configuration file. Instead of .babelrc, you can provide additional Babel ' +
                             'configuration values via the here specified file. This file must contain exactly one ' +
                             'valid Babel CLI config flag per line. For more information, check Babel CLI ' +
                             'configuration options. This option defaults to "codemodel_rifle_babel".',
                        metavar='BABELCONFIGFILE', default='codemodel_rifle_babel')
    parser.add_argument('-t', '--max-upload-trials', type=int,
                        help='In case of an unsuccessful file upload to the Codemodel Rifle server due to network ' +
                             'error, the maximum number of retrials. Defaults to 10.',
                        metavar='N', default=10)
    parser.add_argument('-v', '--verbose', action='store_true',
                        help='Turn on extra information logging, such as answers from servers, etc.')
    parser.add_argument('-d', '--debug', action='store_true',
                        help='Turn on debug information logging, such as diffed and transpiled files.')
    parser.add_argument('-f', '--reimport-full-branch', action='store_true',
                        help='Do not search for previously imported commits of branch (revision), ' +
                             'upload the whole branch/revision to Codemodel Rifle instead. ' +
                             'Previously imported data for the branch will be deleted from Codemodel Rifle.')
    args = parser.parse_args()

    git = GitInteractor(args.project_git_repository_path)
    logger = Logger(args.verbose, args.debug)
    rifle = CodemodelRifleInteractor(args.codemodel_rifle_root_path.rstrip('/'), args.max_upload_trials, logger)
    application = Application(args.reimport_full_branch, args.ignorefile, args.babel_config_file)

    # Saving the current directory
    # Before exiting, we switch back here
    origin_directory = os.getcwd()
    atexit.register(os.chdir, origin_directory)

    logger.print_verbose('* Reading ignorefile...')

    try:
        ignore_present = application.read_ignore()
    except OSError as e:
        logger.print_log('ERROR during reading the ignorefile ({0}).'.format(application.ignorefile))
        logger.print_log(e.strerror)
        logger.print_log('Assuming the ignorefile is intentionally present ' +
                         'and therefore you need to ignore some files, aborting.')
        sys.exit(1)
    except Exception:
        logger.print_log('UNEXPECTED ERROR while reading ignorefile ({0}).'.format(application.ignorefile))
        logger.print_log('Assuming the ignorefile is intentionally present ' +
                         'and therefore you need to ignore some files, aborting.')
        sys.exit(1)
    else:
        if ignore_present:
            logger.print_verbose('Ignorefile present.')
            logger.print_debug('Ignorefile contents:')
            for item in application.ignores:
                logger.print_debug(item)
        else:
            logger.print_verbose('Ignorefile not present.')

    logger.print_verbose('* Ignorefile successfully read and parsed.')

    logger.print_verbose('* Reading babelconfigfile...')

    try:
        babelconfigfile_present = application.read_babelconfig()
    except OSError as e:
        logger.print_log('ERROR during reading the babel config file ({0}).'.format(application.babelconfigfile))
        logger.print_log(e.strerror)
        logger.print_log('Assuming the babelconfigfile is intentionally present ' +
                         'and therefore you need to configure babel, aborting.')
        sys.exit(1)
    except Exception:
        logger.print_log('UNEXPECTED ERROR while reading babelconfigfile ({0}).'.format(application.babelconfigfile))
        logger.print_log('Assuming the babelconfigfile is intentionally present ' +
                         'and therefore you need to configure babel, aborting.')
        sys.exit(1)
    else:
        if babelconfigfile_present:
            logger.print_verbose('Babelconfigfile present.')
            logger.print_debug('Babelconfigfile contents:')
            for item in application.babelconfig:
                logger.print_debug(item)
        else:
            logger.print_verbose('Babelconfigfile not present.')

    logger.print_verbose('* Babelconfigfile successfully read.')

    logger.print_verbose('* Switching to the specified git repository ({0})...'.format(git.project_git_repository_path))

    try:
        os.chdir(git.project_git_repository_path)
    except OSError as e:
        logger.print_log(
            'ERROR while switching to the git repository path ({0}).'.format(git.project_git_repository_path))
        logger.print_log(e.strerror)
        logger.print_log('Aborting.')
        sys.exit(1)
    except Exception:
        logger.print_log('UNEXPECTED ERROR while switching to the git repository path ({0}).'.format(
            git.project_git_repository_path))
        logger.print_log('Aborting.')
        sys.exit(1)
    else:
        logger.print_debug('Provided Git root directory: {0}'.format(git.project_git_repository_path))
        logger.print_debug('Current working directory: {0}'.format(os.getcwd()))

    logger.print_verbose(
        '* Successfully switched to the specified git repository ({0})'.format(git.project_git_repository_path))

    logger.print_verbose('* Fetching current revision from git...')

    try:
        git.current_revision = git.git_query_current_revision()
    except RuntimeError as e:
        logger.print_log('ERROR while querying current revision from git.')
        logger.print_log(e.message)
        logger.print_log('Aborting.')
        sys.exit(1)
    except Exception:
        logger.print_log('UNEXPECTED ERROR while querying current revision from git.')
        logger.print_log('Aborting.')
        sys.exit(1)
    else:
        logger.print_verbose('Current revision: "{0}"'.format(git.current_revision))

    logger.print_verbose('* Current revision successfully fetched from git.')

    logger.print_verbose('* Querying HEAD from git...')

    try:
        git.head = git.git_query_head()
    except RuntimeError as e:
        logger.print_log('ERROR while querying HEAD from git.')
        logger.print_log(e.message)
        logger.print_log('Aborting.')
        sys.exit(1)
    except Exception:
        logger.print_log('UNEXPECTED ERROR while querying HEAD from git.')
        logger.print_log('Aborting.')
        sys.exit(1)
    else:
        logger.print_verbose('HEAD is currently at: "{0}"'.format(git.head))

    logger.print_verbose('* HEAD successfully queried from git.')

    logger.print_verbose('* Testing Codemodel Rifle connection, querying last commit for revision...')

    try:
        rifle.last_uploaded_commit_on_revision = rifle.codemodel_rifle_get_last_commit_for_revision(
            git.current_revision)
    except RuntimeError as e:
        logger.print_log('ERROR during testing Codemodel Rifle connection, ' +
                         'could not fetch last commit for revision "{0}".'.format(git.current_revision))
        logger.print_log(e.message)
        logger.print_log('Aborting.')
        sys.exit(1)
    except Exception:
        logger.print_log('UNEXPECTED ERROR while testing Codemodel Rifle connection.')
        logger.print_log('Aborting.')
        sys.exit(1)
    else:
        logger.print_verbose(
            'Last commit for revision "{0}" on Codemodel Rifle: {1}'.format(git.current_revision,
                                                                            rifle.last_uploaded_commit_on_revision))

    logger.print_verbose('* Last commit for revision successfully acquired from Codemodel Rifle.')

    full_import = (rifle.last_uploaded_commit_on_revision is None) or application.reimport_full_branch

    if full_import:
        logger.print_verbose(
            '* Importing full repository to Codemodel Rifle (--reimport-full-branch or no uploaded commit ' +
            'for revision on Codemodel Rifle)...')
    else:
        logger.print_verbose('* Incrementally import repository...')

    # If not explicitly requested with --reimport-full-branch (-f), we do nothing if the HEAD has already been imported
    if not full_import and git.head == rifle.last_uploaded_commit_on_revision:
        logger.print_log('The current commit has already been imported to Codemodel Rifle.')
        logger.print_log('Exiting.')
        sys.exit(0)

    logger.print_verbose('** Fetching files for Codemodel Rifle import...')

    try:
        if full_import:
            files_list = git.git_query_all_files()
        else:
            files_list = git.git_query_diff(rifle.last_uploaded_commit_on_revision)
    except RuntimeError as e:
        logger.print_log('ERROR during getting the filelist from Git.')
        logger.print_log(e.message)
        logger.print_log('Aborting.')
        sys.exit(1)
    except Exception:
        logger.print_log('UNEXPECTED ERROR while getting the filelist from Git.')
        logger.print_log('Aborting.')
        sys.exit(1)
    else:
        logger.print_verbose('Successfully acquired fileslist from git.')
        logger.print_debug('THE FULL GIT FILELIST:')
        for item in files_list:
            # Printing diff mode and filename
            logger.print_debug('{0} -> {1}'.format(item[0], item[1]))

    logger.print_verbose('** Files successfully fetched for Codemodel Rifle import.')

    logger.print_verbose('** Filtering out ignored files...')

    # Filtering out ignored files
    files_list = filter(lambda onefile: not application.ignored(onefile[1]), files_list)

    logger.print_verbose('** Successfully filtered out ignored files.')

    logger.print_verbose('** Creating temporary transpilation directory for Babel.')

    try:
        directory_suffix = datetime.datetime.now().strftime('_%Y-%m-%d_%H%M%S')
        directory_prefix = 'codemodel_rifle_temp_'
        babel_transpilation_temp_folder = tempfile.mkdtemp(directory_suffix, directory_prefix)
    except OSError as e:
        logger.print_log('ERROR during creating temporary folder for Babel transpilation.')
        logger.print_log(e.strerror)
        logger.print_log('Aborting.')
        sys.exit(1)
    except Exception:
        logger.print_log('UNEXPECTED ERROR while creating temporary folder for Babel transpilation.')
        logger.print_log('Aborting.')
        sys.exit(1)
    else:
        # Registering temp directory cleanup function
        atexit.register(Application.clean_directory, babel_transpilation_temp_folder)
        logger.print_verbose(
            'Babel temporary transpilation directory path: {0}'.format(babel_transpilation_temp_folder))

    logger.print_verbose('** Successfully created temporary transpilation directory for Babel.')

    babel = BabelInteractor(babel_transpilation_temp_folder, application.reimport_full_branch, logger,
                            application.ignores, application.babelconfig)

    logger.print_verbose('** Transpiling files with Babel...')

    try:
        babel.transpile(files_list)
    except OSError as e:
        logger.print_log('ERROR while transpiling with Babel.')
        logger.print_log('Filename or error message: {0}'.format(e.message))
        logger.print_log(
            'It is possibly an error regarding creating child directories in the file\'s path within ' +
            'the temporary transpilation folder ({0}).'.format(babel.babel_transpilation_temp_folder_path))
        logger.print_log('Aborting.')
        sys.exit(1)
    except Exception as e:
        logger.print_log('UNEXPECTED ERROR while transpiling files.')
        logger.print_log(e.message)
        logger.print_log('Aborting.')
        sys.exit(1)

    logger.print_verbose('** Successfully transpiled all files with Babel.')

    logger.print_verbose('** Sending transpiled files to Codemodel Rifle...')

    try:
        rifle.handle(files_list, git.current_revision, git.head)
    except RuntimeError as e:
        filename = e.message
        logger.print_log('ERROR thrown by Codemodel Rifle while uploading file "{0}". '.format(filename) +
                         'The file is possibly uploaded but potentially could not be parsed by Codemodel Rifle.')
        logger.print_log('Continuing with other files.')
    except IOError as e:
        filename = e.message
        logger.print_log('ERROR while uploading file "{0}" '.format(filename) +
                         'Upload failed for more than {0} times. '.format(rifle.max_upload_trials) +
                         'Override this by specifying the --max-upload-trials flag.')
        logger.print_log('At the next import, you are suggested to run a full import to the branch ' +
                         '(with the -f or --reimport-full-branch flag).')
        logger.print_log('Aborting.')
        sys.exit(1)
    except Exception:
        logger.print_log('UNEXPECTED ERROR while uploading files to Codemodel Rifle.')
        logger.print_log('Aborting.')
        sys.exit(1)

    logger.print_verbose('** Successfully sent all files to Codemodel Rifle.')

    logger.print_verbose('* Successfully finished Codemodel Rifle import.')


if __name__ == '__main__':
    main()
