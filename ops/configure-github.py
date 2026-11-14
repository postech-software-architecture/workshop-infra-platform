"""Generate and publish Academy configuration without printing secret values."""
import argparse
import json
import os
from pathlib import Path
import re
import secrets
import subprocess
import sys

ORG = 'postech-software-architecture'
PLATFORM = 'workshop-infra-platform'
AWS_REPOS = ('workshop-infra-kubernetes', 'workshop-infra-database', PLATFORM,
             'workshop-auth-serverless', 'workshop-os-service',
             'workshop-billing-service', 'workshop-execution-service')
SHARED = {name: AWS_REPOS for name in
          ('AWS_ACCESS_KEY_ID', 'AWS_SECRET_ACCESS_KEY', 'AWS_SESSION_TOKEN')}
SHARED['NEW_RELIC_LICENSE_KEY'] = ('workshop-infra-kubernetes', PLATFORM, 'workshop-auth-serverless')
GENERATED = ('OS_DB_PASSWORD', 'BILLING_DB_PASSWORD', 'JWT_SECRET',
             'AUTH_SERVICE_TOKEN', 'OS_SERVICE_TOKEN', 'BILLING_SERVICE_TOKEN',
             'EXECUTION_SERVICE_TOKEN', 'OS_RABBIT_PASSWORD',
             'BILLING_RABBIT_PASSWORD', 'EXECUTION_RABBIT_PASSWORD',
             'RABBIT_ADMIN_PASSWORD', 'MONGO_ROOT_PASSWORD', 'MONGO_PASSWORD')
VARIABLES = ('AWS_REGION', 'EKS_CLUSTER_NAME', 'RDS_HOST', 'STORAGE_CLASS')
EXTERNAL = ('RDS_ADMIN_USER', 'RDS_ADMIN_PASSWORD')
OPTIONAL = ('MP_ACCESS_TOKEN', 'MP_SELLER_ID', 'MP_APPLICATION_ID', 'MP_POS_ID',
            'MP_WEBHOOK_SECRET', 'MAIL_HOST', 'MAIL_PORT', 'MAIL_USERNAME',
            'MAIL_PASSWORD', 'MAIL_FROM')
KNOWN = set(GENERATED + VARIABLES + EXTERNAL + OPTIONAL) | set(SHARED)


def placeholder(value):
    return value.strip().upper().startswith(('CHANGE_ME', 'CHANGEME', 'REPLACE_', '<'))


def read_env(path):
    values = {}
    for number, line in enumerate(path.read_text(encoding='utf-8-sig').splitlines(), 1):
        if not line.strip() or line.lstrip().startswith('#'):
            continue
        name, separator, value = line.partition('=')
        if not separator or not re.fullmatch('[A-Z][A-Z0-9_]*', name):
            raise ValueError(f'Invalid configuration at line {number}; use NAME=value.')
        if name in values:
            raise ValueError(f'Duplicate configuration name: {name}')
        # Literal format: no shell evaluation, interpolation or quote removal.
        values[name] = value
    return values


def private_path(path):
    if path.is_symlink() or path.suffix != '.env':
        raise ValueError('Use a private .env file, never a symlink or .env.example.')
    root = Path(__file__).resolve().parents[1]
    if path.resolve().is_relative_to(root):
        result = subprocess.run(['git', 'check-ignore', '--no-index', '-q', str(path.resolve())],
                                cwd=root, capture_output=True)
        if result.returncode != 0:
            raise ValueError('The configuration file must be excluded by .gitignore.')


def initialize(path, rds_host='', import_path=None):
    private_path(path)
    values = read_env(path) if path.exists() else {}
    if import_path:
        for name, value in read_env(import_path).items():
            if name in KNOWN and value and not placeholder(value) and not values.get(name):
                values[name] = value
    defaults = {'AWS_REGION': 'us-east-1', 'EKS_CLUSTER_NAME': 'workshop-eks',
                'STORAGE_CLASS': 'soat-ebs-gp3', 'RDS_ADMIN_USER': 'workshop',
                'RDS_HOST': rds_host}
    for name, value in defaults.items():
        if not values.get(name):
            values[name] = value
    for name in GENERATED:
        if not values.get(name):
            values[name] = secrets.token_hex(24)
    for name in (*SHARED, *EXTERNAL, *OPTIONAL):
        values.setdefault(name, '')
    path.parent.mkdir(parents=True, exist_ok=True)
    # Atomic replacement preserves the old file on write failure. Windows inherits
    # directory ACLs; POSIX creates both the temporary and final file as mode 0600.
    temporary = path.with_name(path.name + '.tmp-' + secrets.token_hex(6))
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(descriptor, 'w', encoding='utf-8', newline='\n') as handle:
            handle.write('# PRIVATE. Literal NAME=value; no quotes. Never commit.\n')
            handle.write(''.join(name + '=' + values[name] + '\n' for name in sorted(values)))
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)
    print('Private configuration prepared; existing values preserved; no upload.')


def gh(args, value=None):
    # Secrets go only through stdin, never argv, shell commands or logs. Suppress
    # subprocess output even on failure: CLI debug output may contain request data.
    env = dict(os.environ)
    for name in ('GH_DEBUG', 'DEBUG'):
        env.pop(name, None)
    env['GH_PROMPT_DISABLED'] = '1'
    env['GH_HOST'] = 'github.com'
    try:
        result = subprocess.run(['gh', *args], input=value, text=True,
                                encoding='utf-8', capture_output=True, env=env,
                                timeout=120)
    except (OSError, subprocess.TimeoutExpired):
        raise RuntimeError('GitHub CLI unavailable or timed out; no values printed.') from None
    if result.returncode:
        raise RuntimeError('GitHub CLI failed. Check login, permissions and selected repositories; '
                           'CLI output suppressed to protect credentials.')
    return result.stdout


def names(kind, org=None, repo=None, environment=None):
    args = [kind, 'list', '--json', 'name']
    if org:
        args += ['--org', org]
    if repo:
        args += ['--repo', repo]
    if environment:
        args += ['--env', environment]
    return {entry['name'] for entry in json.loads(gh(args))}


def validate(values, required):
    missing = [name for name in required if not values.get(name)]
    if missing:
        raise ValueError('Fill these names in the private file: ' + ', '.join(missing))
    for name in required:
        value = values[name]
        if '\n' in value or '\r' in value or '\x00' in value:
            raise ValueError('Single-line values required: ' + name)
        if placeholder(value):
            raise ValueError('Replace the placeholder for: ' + name)


def sync(values, scope, org, environment, apply=False, allow_existing=False):
    if scope == 'shared':
        # AWS credentials are renewed together. New Relic can be managed manually
        # in the organization and omitted from this private local file.
        wanted = [name for name in SHARED if values.get(name)]
        aws_names = set(SHARED) - {'NEW_RELIC_LICENSE_KEY'}
        if aws_names.intersection(wanted) and not aws_names.issubset(wanted):
            raise ValueError('Update all three AWS session credentials together.')
        if not wanted:
            raise ValueError('Fill the shared credentials to publish, or manage them in the organization UI.')
        validate(values, wanted)
        for name in wanted:
            print('UPDATE organization secret ' + name + ': ' + ', '.join(SHARED[name]))
            if apply:
                gh(['secret', 'set', name, '--org', org, '--visibility', 'selected',
                    '--repos', ','.join(SHARED[name])], values[name])
    else:
        required = GENERATED + EXTERNAL + VARIABLES
        validate(values, required)
        if values['OS_DB_PASSWORD'] == values['BILLING_DB_PASSWORD']:
            raise ValueError('OS and Billing require distinct database passwords.')
        if len(values['AUTH_SERVICE_TOKEN']) < 32:
            raise ValueError('AUTH_SERVICE_TOKEN requires at least 32 characters.')
        if not re.fullmatch(r'[a-zA-Z0-9.-]+\.rds\.amazonaws\.com', values['RDS_HOST']):
            raise ValueError('RDS_HOST must be a bare RDS hostname.')
        if values['AWS_REGION'] != 'us-east-1':
            raise ValueError('This Academy infrastructure uses us-east-1.')
        repo = org + '/' + PLATFORM
        # Reading metadata is allowed in preview; it never retrieves secret values.
        existing = names('secret', repo=repo, environment=environment)
        desired = list(GENERATED + EXTERNAL) + [name for name in OPTIONAL if values.get(name)]
        validate(values, desired)
        # A remote value cannot be recovered or compared. Fail before any write if
        # an existing runtime credential might disagree with a newly generated file.
        collisions = sorted(existing.intersection(desired))
        if collisions and not allow_existing:
            raise ValueError('Existing platform secrets preserved; remote values cannot be compared. '
                             'Use the original private file and --update-existing only when it is '
                             'the source of truth. Names: ' + ', '.join(collisions))
        publish_platform(values, desired, repo, environment, apply)
    if not apply:
        print('Preview only. Add --apply to publish; no deploy or AWS mutation is performed.')


def publish_platform(values, desired, repo, environment, apply):
    for kind, wanted in [('variable', VARIABLES), ('secret', desired)]:
        for name in wanted:
            print('SET ' + repo + '/' + environment + ' ' + kind + ' ' + name)
            if apply:
                gh([kind, 'set', name, '--repo', repo, '--env', environment], values[name])


def org_access(org, name, expected):
    data = json.loads(gh(['api', f'orgs/{org}/actions/secrets/{name}']))
    if data.get('visibility') != 'selected':
        raise ValueError('Restrict organization secret to selected repositories: ' + name)
    pages = json.loads(gh(['api', '--paginate', '--slurp',
                          f'orgs/{org}/actions/secrets/{name}/repositories?per_page=100']))
    repositories = {repo['name']: repo for page in pages for repo in page['repositories']}
    if not set(expected).issubset(repositories):
        raise ValueError('Organization secret lacks required repository access: ' + name)
    # Private repositories require a paid organization plan; fail closed instead
    # of deleting their fallback. Public repos are the current supported migration.
    if any(repositories[repo].get('private', True) for repo in expected):
        raise ValueError('Private repository detected; confirm plan support before migrating: ' + name)


def migrate(org, environment, apply=False):
    # Complete all organization and local metadata checks before deleting anything.
    operations = []
    cached = {}
    for name, repos in SHARED.items():
        org_access(org, name, repos)
        for short in repos:
            repo = org + '/' + short
            for level in (None, environment):
                key = (repo, level)
                if key not in cached:
                    cached[key] = names('secret', repo=repo, environment=level)
                if name in cached[key]:
                    operations.append((name, repo, level))
    for name, repo, level in operations:
        print('REMOVE shadow ' + repo + '/' + (level or 'repository') + ': ' + name)
        if apply:
            args = ['secret', 'delete', name, '--repo', repo]
            if level:
                args += ['--env', level]
            gh(args)
    print('Shared-secret migration complete.' if apply else 'Preview only; add --apply after verifying central values.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--org', default=ORG)
    parser.add_argument('--environment', default='prod')
    commands = parser.add_subparsers(dest='command', required=True)
    init = commands.add_parser('init', help='Generate missing values in an ignored private file.')
    init.add_argument('--file', type=Path, default=Path('private/github.env'))
    init.add_argument('--rds-host', default='')
    init.add_argument('--import-env', type=Path)
    upload = commands.add_parser('sync', help='Preview or publish configuration through gh.')
    upload.add_argument('--file', type=Path, default=Path('private/github.env'))
    upload.add_argument('--scope', choices=('shared', 'platform'), required=True)
    upload.add_argument('--apply', action='store_true')
    upload.add_argument('--update-existing', action='store_true',
                        help='Confirm this private file is the original source, not newly generated credentials.')
    migration = commands.add_parser('migrate-shared', help='Verify grants and remove only shared-secret shadows.')
    migration.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    if not re.fullmatch('[A-Za-z0-9-]+', args.org) or args.environment != 'prod':
        raise ValueError('Use a valid organization name and the prod environment.')
    if args.command == 'init':
        initialize(args.file, args.rds_host, args.import_env)
    elif args.command == 'migrate-shared':
        migrate(args.org, args.environment, args.apply)
    else:
        private_path(args.file)
        values = read_env(args.file)
        sync(values, args.scope, args.org, args.environment, args.apply,
             allow_existing=args.update_existing)


if __name__ == '__main__':
    try:
        main()
    except (ValueError, RuntimeError, OSError, json.JSONDecodeError) as error:
        # File/parser and CLI errors above contain names only, never raw values.
        print(str(error), file=sys.stderr)
        sys.exit(1)
