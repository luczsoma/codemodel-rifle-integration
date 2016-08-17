# Codemodel Rifle integration
**With this script, incremental analysis with Codemodel Rifle can be integrated into a Git-based CI-workflow.**

## Basic usage
Code (`--help` output) is worth a thousand words:

```
usage: codemodel_rifle_import_and_test.py [-h] [-i IGNOREFILE]
                                          [-b BABELCONFIGFILE] [-t N] [-v]
                                          [-d] [-f]
                                          GITREPOSITORYPATH RIFLEROOTPATH

Get the modified files since the last commit, and send them to the Codemodel
Rifle server for analysis.

positional arguments:
  GITREPOSITORYPATH     The Git repository of the project. Either relative or
                        absolute path.
  RIFLEROOTPATH         The root path of the Codemodel Rifle application, e.g.
                        http://127.0.0.1:8080/codemodel

optional arguments:
  -h, --help            show this help message and exit
  -i IGNOREFILE, --ignorefile IGNOREFILE
                        Files that are ignored during the import and analysis
                        should be listed in a separate file in separate lines.
                        This argument defaults to "codemodel_rifle_ignore".
                        Ignorefile should contain full relative paths to the
                        git repository. For example: app/lib/asmcrypto.js
                        instead of asmcrypto.js and app/lib/ instead of lib/.
                        Directories should have a trailing slash.
  -b BABELCONFIGFILE, --babel-config-file BABELCONFIGFILE
                        Babel CLI configuration file. Instead of .babelrc, you
                        can provide additional Babel configuration values via
                        the here specified file. This file must contain
                        exactly one valid Babel CLI config flag per line. For
                        more information, check Babel CLI configuration
                        options. This option defaults to
                        "codemodel_rifle_babel".
  -t N, --max-upload-trials N
                        In case of an unsuccessful file upload to the
                        Codemodel Rifle server due to network error, the
                        maximum number of retrials. Defaults to 10.
  -v, --verbose         Turn on extra information logging, such as answers
                        from servers, etc.
  -d, --debug           Turn on debug information logging, such as diffed and
                        transpiled files.
  -f, --reimport-full-branch
                        Do not search for previously imported commits of
                        branch (revision), upload the whole branch/revision to
                        Codemodel Rifle instead. Previously imported data for
                        the branch will be deleted from Codemodel Rifle.
```

## What does it do?
* We go to the specified git root path,
* fetch the HEAD commit's long hash
* fetch the current revision (branch name, or if detached, the HEAD commit's long hash),
* fetch the last uploaded commit for the previously specified revision,
* import files incrementally (based on git diff) or fully
	* if there is a previously uploaded commit on Codemodel Rifle on the current branch, only the differences will be uploaded to the Codemodel Rifle server (Added, Deleted and Modified files),
	* if there is no previously uploaded commit on Codemodel Rifle on the current branch (or if explicitly stated with the -f flag), the whole repository gets uploaded.

## Codemodel Rifle server
Codemodel Rifle server is an experimental Java-based web server with a basic REST API for parsing and analysing complex JavaScript repositories based on a complex Abstract Syntax Graph *[ASG]* (adjoint Abstract Syntax Trees *[AST]*) and a Control-Flow Graph *[CFG]* created upon the ASG. The documentation of Codemodel Rifle is available of Dániel Stein @ [Tresorit](https://www.tresorit.com), Hungary.

Behind the server, there is a [Shift](http://shift-ast.org) JavaScript parser and a [Neo4j graph database](https://neo4j.com). Because of the parser's limited capabilities, we need some minimal transpiling of the JavaScript files before sending them to the Codemodel Rifle server. After parsing, the ASTs of the individual files gets imported into a Neo4j graph database in graph form. After various transformation procedures, the continously maintained, for-branch-discrete graphs (ASG and CFG for each branch) can be queried.

The transpilation process happens with [babel](https://babeljs.io). Example configuration can be found in the **codemodel-rifle-babel** file.

## To do
* As currently Codemodel Rifle does not analyse or return anything, this script is only for importing purposes. In the future, the returned analysis values has to be printed, which has to be implemented in the script.
* Codemodel Rifle server can handle various Cypher queries. We need the possibility of any external query input, in order to specify additional custom analysis and transformation queries.