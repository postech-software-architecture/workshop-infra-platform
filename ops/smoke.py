"""Read-only smoke check for an already deployed gateway. Does not deploy or change business data."""
import argparse
import json
import urllib.request
import urllib.error


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base-url', required=True)
    args = parser.parse_args()
    results = []
    for path, allowed in [('/version', [200]), ('/api/v1/ordens-servico', [401]),
                          ('/api/v1/orcamentos/11111111-1111-4111-8111-111111111111', [401]),
                          ('/api/v1/trabalhos/11111111-1111-4111-8111-111111111111', [401]),
                          ('/internal/v1/identidade/introspectar', [404])]:
        try:
            with urllib.request.urlopen(args.base_url.rstrip('/') + path, timeout=5) as response:
                status = response.status
        except urllib.error.HTTPError as error:
            status = error.code
        if status not in allowed:
            raise RuntimeError(f'{path}: expected {allowed}, received {status}')
        results.append({'path': path, 'status': status})
    print(json.dumps({'passed': True, 'checks': results}, indent=2))


if __name__ == '__main__':
    main()
