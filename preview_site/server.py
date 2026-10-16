"""Windows-friendly local preview; never opens a real POS file."""
import argparse
from wsgiref.simple_server import make_server
from preview_site.wsgi import application

def main():
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument('--port', type=int, default=8766)
    args = cli.parse_args()
    if not 1 <= args.port <= 65535:
        cli.error('Invalid port')
    with make_server('127.0.0.1', args.port, application) as server:
        print(f'Synthetic preview: http://127.0.0.1:{args.port}/', flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass

if __name__ == '__main__':
    main()
